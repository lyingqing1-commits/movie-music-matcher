"""
片段评分模块 — AI 对每个视频片段进行"高光度"评估
=================================================
为每个通过场景检测切分的视频片段提取代表帧，
使用 AI 批量评分：highlight_score, emotional_tone, suggested_use。

结合电影身份信息可以显著提升评分准确性。
"""
import base64
import json
import mimetypes
import os
import subprocess
import sys
from anthropic import Anthropic
import config


def _get_client() -> Anthropic:
    kwargs = {"api_key": config.ANTHROPIC_API_KEY}
    if config.ANTHROPIC_BASE_URL:
        kwargs["base_url"] = config.ANTHROPIC_BASE_URL
    return Anthropic(**kwargs)


def _encode_image(image_path: str) -> dict:
    with open(image_path, "rb") as f:
        image_data = f.read()
    base64_data = base64.b64encode(image_data).decode("utf-8")
    mime_type, _ = mimetypes.guess_type(image_path)
    if not mime_type:
        mime_type = "image/jpeg"
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": mime_type,
            "data": base64_data,
        },
    }


def _get_response_text(response) -> str:
    for block in response.content:
        if getattr(block, "type", None) == "text":
            return getattr(block, "text", "") or ""
    return str(response.content[0]) if response.content else ""


# ---- 片段帧提取 ----

def _extract_segment_frame(
    video_path: str,
    start_time: float,
    task_dir: str,
    segment_index: int,
) -> str:
    """
    从视频片段中点提取一帧画面。

    优先提取中点帧；如果片段时长 > 5 秒，也尝试提取"最具动态"的帧。
    """
    # 使用 frame_extractor 中的 FFmpeg 查找逻辑
    from modules.frame_extractor import _find_ffmpeg, _get_ffmpeg

    ffmpeg = _get_ffmpeg()

    # 取片段中点
    mid_time = start_time + 0.5  # 优先取片段开始后 0.5 秒（避开转场黑帧）
    frame_path = os.path.join(task_dir, f"seg_{segment_index:03d}.jpg")

    cmd = [
        ffmpeg,
        "-ss", str(mid_time),
        "-i", video_path,
        "-vframes", "1",
        "-q:v", "2",
        "-y",
        frame_path,
    ]

    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    subprocess.run(cmd, capture_output=True, timeout=30, creationflags=creationflags)

    if os.path.isfile(frame_path) and os.path.getsize(frame_path) > 100:
        return frame_path

    # 回退：尝试在片段 1/3 处提取
    alt_time = start_time + 0.2
    cmd[2] = str(alt_time)
    subprocess.run(cmd, capture_output=True, timeout=30, creationflags=creationflags)

    if os.path.isfile(frame_path) and os.path.getsize(frame_path) > 100:
        return frame_path

    return ""  # 提取失败


# ---- 系统提示词 ----

SYSTEM_PROMPT_SEGMENT_SCORER = """你是一位资深视频剪辑师，擅长为影视混剪/高光集锦挑选最佳片段。

我会给你一组视频片段的代表帧画面，请对每个片段进行评分和分类。

评分维度：
1. **highlight_score (0-100)**：这个片段作为高光时刻的价值
   - 90-100: 极致画面/情绪爆点/名场面——必须入选
   - 75-89: 精彩动作/强烈情绪/视觉效果突出
   - 60-74: 叙事推进/不错的画面
   - 40-59: 普通过渡画面
   - 0-39: 静态/空镜/无关画面

2. **emotional_tone**：片段的情感基调（选择一个最准确的）
   - "action": 动作/打斗/追逐/爆炸
   - "emotional": 感动/煽情/人物特写
   - "tension": 紧张/悬疑/惊悚
   - "calm": 平静/对话/日常
   - "triumph": 胜利/燃/热血
   - "mystery": 神秘/未知/探索
   - "melancholy": 忧伤/怀旧/沉重
   - "establishing": 定场/风景/环境
   - "dialogue": 对话/互动
   - "climax": 高潮/关键时刻

3. **suggested_use**：这个片段最适合放在音乐结构的哪个位置
   - "drop": 适合放在音乐的 Drop/高潮段
   - "chorus": 适合放在副歌段
   - "verse": 适合放在主歌段
   - "intro": 适合作为开场
   - "bridge": 适合放在间奏/过渡段
   - "outro": 适合作为结尾

4. **visual_quality**：画面质量评价
   - "high": 构图精良/画面清晰/视觉冲击力强
   - "medium": 合格的画面
   - "low": 模糊/过暗/过曝

{familiarity_context}

请为每个片段返回评分，以 JSON 数组格式返回。每个元素对应一个片段：
[
  {
    "segment_index": 0,
    "highlight_score": 85,
    "emotional_tone": "action",
    "suggested_use": "drop",
    "description": "快速追逐场景，暖色调，大量运动模糊",
    "visual_quality": "high"
  },
  ...
]

严格按照片段顺序返回，不要跳过任何片段。只返回 JSON 数组。"""


def score_segments(
    video_path: str,
    segments: list[dict],
    movie_identity: dict = None,
    task_id: str = "",
    editing_mode: str = "video_first",
) -> list[dict]:
    """
    对每个视频片段进行 AI 高光度评分。

    参数：
        video_path: 视频文件路径
        segments: 场景检测结果 [{start_time, end_time, duration}, ...]
        movie_identity: 电影识别结果（可选，用于提升评分准确性）
        task_id: 任务 ID（用于帧存储目录）
        editing_mode: 剪辑模式 ("video_first" | "music_first")

    返回：
        segments 列表，每个元素附加了评分字段：
        highlight_score, emotional_tone, suggested_use, visual_quality, description
    """
    if not config.ANTHROPIC_API_KEY:
        print("   ⚠️ 未配置 API Key，使用默认评分")
        return _default_scores(segments)

    # 如果当前 API 不支持 Vision，直接使用默认评分
    if not getattr(config, "VISION_SUPPORTED", True):
        print("   [INFO] API 不支持图片评分（VISION_SUPPORTED=False），使用默认评分")
        return _default_scores(segments)

    if not segments:
        return []

    # 限制评分数量以控制 API 成本
    max_to_score = getattr(config, "MAX_SEGMENTS_TO_SCORE", 30)
    if len(segments) > max_to_score:
        print(f"   ⚠️ 片段过多 ({len(segments)} > {max_to_score})，采样评分")
        # 均匀采样
        step = len(segments) / max_to_score
        sampled = [segments[int(i * step)] for i in range(max_to_score)]
        # 标记原始索引
        for i, seg in enumerate(sampled):
            seg["_orig_idx"] = int(i * step)
    else:
        sampled = list(segments)
        for i, seg in enumerate(sampled):
            seg["_orig_idx"] = i

    # 提取每个片段的中帧
    task_dir = os.path.join(config.FRAME_FOLDER, task_id) if task_id else config.FRAME_FOLDER
    os.makedirs(task_dir, exist_ok=True)

    print(f"   📸 提取 {len(sampled)} 个片段代表帧...")
    frame_paths = []
    valid_indices = []
    for i, seg in enumerate(sampled):
        fp = _extract_segment_frame(
            video_path, seg["start_time"], task_dir, seg["_orig_idx"]
        )
        if fp:
            frame_paths.append(fp)
            valid_indices.append(i)
        else:
            # 帧提取失败，用默认评分
            sampled[i]["highlight_score"] = 50
            sampled[i]["emotional_tone"] = "calm"
            sampled[i]["suggested_use"] = "verse"
            sampled[i]["visual_quality"] = "medium"
            sampled[i]["description"] = "（帧提取失败）"

    if not frame_paths:
        print("   ⚠️ 所有帧提取失败，使用默认评分")
        return _default_scores(segments)

    # 批量 AI 评分（每批最多 8 帧，避免单次请求过大）
    BATCH_SIZE = 8
    client = _get_client()

    for batch_start in range(0, len(frame_paths), BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, len(frame_paths))
        batch_frames = frame_paths[batch_start:batch_end]
        batch_indices = valid_indices[batch_start:batch_end]

        print(f"   🤖 AI 评分: 片段 {batch_start+1}-{batch_end}/{len(frame_paths)}")

        # 构建电影上下文
        familiarity_context = ""
        if movie_identity and movie_identity.get("identified"):
            mk = movie_identity.get("ai_knowledge", {})
            familiarity_context = f"""
【电影背景知识】
这部电影是《{movie_identity['movie_name']}》（{movie_identity.get('year', '')}）。
情节：{mk.get('plot_summary', '')}
主题：{', '.join(mk.get('themes', []))}
情感弧线：{mk.get('emotional_arc', '')}
视觉特征：{mk.get('visual_signature', '')}

请结合你对这部电影的了解来评估每个片段的重要性和情感基调。"""

        system_prompt = SYSTEM_PROMPT_SEGMENT_SCORER.format(
            familiarity_context=familiarity_context
        )

        # 构建请求
        content = [
            {"type": "text", "text": f"请评估以下 {len(batch_frames)} 个视频片段的高光度。为每个片段返回评分 JSON。片段索引从 {batch_start} 到 {batch_end-1}。"}
        ]
        for fp in batch_frames:
            content.append(_encode_image(fp))

        try:
            response = client.messages.create(
                model=config.AI_MODEL,
                max_tokens=2048,
                system=system_prompt,
                messages=[{"role": "user", "content": content}],
            )

            response_text = _get_response_text(response)
            scores = _parse_scores(response_text, len(batch_indices))

            # 将评分映射回 sampled 列表
            for j, score_obj in enumerate(scores):
                if j < len(batch_indices):
                    idx = batch_indices[j]
                    sampled[idx]["highlight_score"] = score_obj.get("highlight_score", 50)
                    sampled[idx]["emotional_tone"] = score_obj.get("emotional_tone", "calm")
                    sampled[idx]["suggested_use"] = score_obj.get("suggested_use", "verse")
                    sampled[idx]["visual_quality"] = score_obj.get("visual_quality", "medium")
                    sampled[idx]["description"] = score_obj.get("description", "")

        except Exception as e:
            print(f"   ⚠️ AI 评分批次失败: {e}")
            # 该批次使用默认评分
            for j, idx in enumerate(batch_indices):
                if "highlight_score" not in sampled[idx]:
                    sampled[idx]["highlight_score"] = 50
                    sampled[idx]["emotional_tone"] = "calm"
                    sampled[idx]["suggested_use"] = "verse"
                    sampled[idx]["visual_quality"] = "medium"
                    sampled[idx]["description"] = f"（评分失败: {str(e)[:50]}）"

    # 为未评分的补充默认值
    for seg in sampled:
        if "highlight_score" not in seg:
            seg["highlight_score"] = 50
            seg["emotional_tone"] = "calm"
            seg["suggested_use"] = "verse"
            seg["visual_quality"] = "medium"
            seg["description"] = ""

    # 移除临时字段
    for seg in sampled:
        seg.pop("_orig_idx", None)

    # 合并回原始 segments（如果采样过）
    if len(sampled) < len(segments):
        # 为未采样的片段估算评分（取相邻已评分片段的平均值）
        for i, seg in enumerate(segments):
            if "highlight_score" not in seg:
                seg["highlight_score"] = 50
                seg["emotional_tone"] = "calm"
                seg["suggested_use"] = "verse"
                seg["visual_quality"] = "medium"
                seg["description"] = "（未采样评分）"

    # 输出评分摘要
    scores = [s["highlight_score"] for s in segments if "highlight_score" in s]
    if scores:
        print(f"   ✅ 片段评分完成: 平均 {sum(scores)/len(scores):.0f} 分, "
              f"最高 {max(scores)} 分, 最低 {min(scores)} 分")

    return segments


def _parse_scores(text: str, expected_count: int) -> list[dict]:
    """从 AI 响应中解析评分数组"""
    if not text:
        return []

    # 提取 JSON 数组
    if "```json" in text:
        start = text.find("```json") + 7
        end = text.find("```", start)
        text = text[start:end].strip()
    elif "```" in text:
        start = text.find("```") + 3
        end = text.find("```", start)
        text = text[start:end].strip()

    # 尝试找到 JSON 数组
    bracket_start = text.find("[")
    bracket_end = text.rfind("]") + 1
    if bracket_start >= 0 and bracket_end > bracket_start:
        text = text[bracket_start:bracket_end]

    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return [result]
    except json.JSONDecodeError:
        print(f"   ⚠️ 评分 JSON 解析失败:\n{text[:300]}")

    return []


def _default_scores(segments: list[dict]) -> list[dict]:
    """默认评分（AI 不可用时的回退）"""
    import random
    random.seed(42)  # 固定种子以保证可复现

    tones = ["action", "emotional", "tension", "calm", "triumph", "mystery",
             "melancholy", "establishing", "dialogue", "climax"]
    uses = ["drop", "chorus", "verse", "intro", "bridge", "outro"]

    for seg in segments:
        seg["highlight_score"] = random.randint(40, 85)
        seg["emotional_tone"] = random.choice(tones)
        seg["suggested_use"] = random.choice(uses)
        seg["visual_quality"] = "medium"
        seg["description"] = "（默认评分）"
        seg["_default_scored"] = True

    print(f"   [WARN] 使用默认评分 ({len(segments)} 个片段)")
    return segments
