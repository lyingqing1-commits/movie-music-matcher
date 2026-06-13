"""
电影风格分析模块 - 使用 AI API 分析电影画面
============================================
支持 Vision API（图片分析）和文本回退模式（帧颜色/亮度数值分析）
"""
import base64
import json
import mimetypes
from anthropic import Anthropic
from PIL import Image
import numpy as np
import config


def _safe_float(value) -> float:
    """安全地将 numpy 值转换为 Python float"""
    if isinstance(value, np.ndarray):
        if value.ndim == 0:
            return value.item()
        elif value.ndim == 1 and value.shape[0] == 1:
            return value[0].item()
        else:
            raise ValueError(f"Cannot convert array of shape {value.shape} to float")
    return float(value)


def _safe_int(value) -> int:
    """安全地将 numpy 值转换为 Python int"""
    if isinstance(value, np.ndarray):
        if value.ndim == 0:
            return value.item()
        elif value.ndim == 1 and value.shape[0] == 1:
            return value[0].item()
        else:
            raise ValueError(f"Cannot convert array of shape {value.shape} to int")
    return int(value)


def _get_client() -> Anthropic:
    """创建 AI 客户端（支持自定义 base_url）"""
    kwargs = {"api_key": config.ANTHROPIC_API_KEY}
    if config.ANTHROPIC_BASE_URL:
        kwargs["base_url"] = config.ANTHROPIC_BASE_URL
    return Anthropic(**kwargs)


def _get_response_text(response) -> str:
    """从 API 响应中提取文本（跳过 ThinkingBlock 思考链）"""
    for block in response.content:
        if getattr(block, "type", None) == "text":
            return getattr(block, "text", "") or ""
    return str(response.content[0]) if response.content else ""


def _encode_image(image_path: str) -> dict:
    """将图片编码为 base64，用于 Vision API 调用"""
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


def _extract_frame_metadata(frame_paths: list[str]) -> list[dict]:
    """
    提取帧的数值特征（颜色、亮度、运动感等）
    作为 Vision API 不可用时的回退方案
    """
    metadata_list = []

    prev_hist = None
    for i, path in enumerate(frame_paths):
        img = Image.open(path).convert("RGB")
        arr = np.array(img, dtype=np.float32)

        # 平均亮度
        brightness = _safe_float(np.mean(arr) / 255.0)

        # RGB 各通道均值
        r_mean = _safe_float(np.mean(arr[:, :, 0]))
        g_mean = _safe_float(np.mean(arr[:, :, 1]))
        b_mean = _safe_float(np.mean(arr[:, :, 2]))

        # 判断色调（暖/冷）
        warmth_ratio = (r_mean + 1) / (b_mean + 1)

        # 饱和度（简化估计）
        gray_arr = np.mean(arr, axis=2)
        saturation = _safe_float(np.mean(np.std(arr, axis=2)))

        # 对比度
        contrast = _safe_float(np.std(gray_arr))

        # 帧间差异（运动感）
        hist, _ = np.histogram(gray_arr, bins=32, range=(0, 255))
        hist = hist.astype(np.float32)
        hist = hist / (np.sum(hist) + 1e-10)
        motion = 0.0
        if prev_hist is not None:
            diff = np.sum(np.abs(hist - prev_hist))
            motion = _safe_float(diff)
        prev_hist = hist

        metadata_list.append({
            "frame_index": i,
            "brightness": round(brightness, 3),
            "warmth_ratio": round(warmth_ratio, 3),
            "saturation": round(saturation, 3),
            "contrast": round(contrast, 1),
            "motion_vs_prev": round(motion, 3),
            "r_avg": round(r_mean, 1),
            "g_avg": round(g_mean, 1),
            "b_avg": round(b_mean, 1),
        })

    # 聚合统计
    brightnesses = [m["brightness"] for m in metadata_list]
    motions = [m["motion_vs_prev"] for m in metadata_list if m["motion_vs_prev"] > 0]

    summary = {
        "frame_count": len(metadata_list),
        "avg_brightness": round(_safe_float(np.mean(brightnesses)), 3),
        "brightness_variance": round(_safe_float(np.var(brightnesses)), 4),
        "avg_warmth": round(_safe_float(np.mean([m["warmth_ratio"] for m in metadata_list])), 3),
        "avg_saturation": round(_safe_float(np.mean([m["saturation"] for m in metadata_list])), 3),
        "avg_contrast": round(_safe_float(np.mean([m["contrast"] for m in metadata_list])), 1),
        "avg_motion": round(_safe_float(np.mean(motions)) if motions else 0, 3),
    }

    return metadata_list, summary


# ---- 提示词 ----

# Vision 模式的系统提示词（有图片输入）
SYSTEM_PROMPT_VISION = """你是一位资深电影评论家和音乐总监。你需要分析电影画面的视觉风格，并推荐匹配的音乐风格。

请仔细观察这些从电影中提取的帧画面，从以下维度进行专业分析：

1. **电影类型 (genre)**：动作、文艺、悬疑、科幻、爱情、纪录片、恐怖、喜剧等
2. **情绪氛围 (mood)**：紧张、温馨、悲伤、热血、平静、神秘、欢乐、忧郁等
3. **色调风格 (color_palette)**：暖色调、冷色调、高饱和度、低饱和度、复古色调等
4. **画面节奏感 (pacing)**：快速剪辑感、中等节奏、缓慢沉稳
5. **主题内涵 (themes)**：提炼 2-4 个核心主题词
6. **视觉风格 (visual_style)**：手持镜头、稳定构图、大量特写、广角远景等

然后，基于以上分析，推荐最适合这段电影画面的音乐风格：
7. **推荐音乐**：genre, tempo_bpm, instruments, mood_match, lyrics_theme

请以严格的 JSON 格式返回，不要包含其他文字："""

# 元数据模式的系统提示词（纯文本，分析数值特征）
SYSTEM_PROMPT_METADATA = """你是一位资深电影评论家和音乐总监。你需要根据电影画面的数值特征分析其视觉风格。

以下是每帧画面的数值特征说明：
- brightness: 亮度 (0-1, 越高越亮)
- warmth_ratio: 暖色调比例 (R/B, >1偏暖, <1偏冷)
- saturation: 饱和度 (色彩丰富程度)
- contrast: 对比度 (明暗差异)
- motion_vs_prev: 帧间运动量 (越大画面变化越剧烈)

请根据这些数值推断：
1. **电影类型 (genre)**：动作、文艺、悬疑、科幻、爱情等
2. **情绪氛围 (mood)**：紧张、温馨、悲伤、热血、平静等
3. **色调风格 (color_palette)**：暖色调、冷色调、高饱和、低饱和等
4. **画面节奏感 (pacing)**：快速、中等、缓慢
5. **主题内涵 (themes)**：2-4 个核心主题词
6. **视觉风格 (visual_style)**：推测拍摄风格

然后推荐匹配的音乐风格。
请以严格的 JSON 格式返回，不要包含其他文字。"""


def _build_movie_context(movie_identity: dict) -> str:
    """
    根据电影识别结果构建系统提示词的电影背景部分。
    当 movie_identity 可用时，AI 会基于电影知识产生一致性分析。
    """
    if not movie_identity or not movie_identity.get("identified"):
        return ""

    mk = movie_identity.get("ai_knowledge", {})
    if not mk:
        return ""

    context = f"""

【电影背景知识 — 请充分利用以下知识进行风格分析】
这部电影是《{movie_identity['movie_name']}》（{movie_identity.get('year', '')}）。

情节概要：{mk.get('plot_summary', '')}

核心主题：{', '.join(mk.get('themes', []))}

著名场景：
"""
    for scene in mk.get("key_scenes", []):
        context += f"  · {scene.get('description', '')}（{scene.get('position', '')}，{scene.get('tone', '')}）\n"

    context += f"""
情感弧线：{mk.get('emotional_arc', '')}

视觉特征：{mk.get('visual_signature', '')}

请结合你对这部电影的深入了解，对画面进行一致性分析。
你的分析应该以电影知识为主要依据，画面特征为辅助验证。"""

    return context


def analyze_style(frame_paths: list[str], movie_identity: dict = None) -> dict:
    """
    分析电影画面风格
    先尝试 Vision API，失败则回退到元数据模式

    参数：
        frame_paths: 帧图片路径列表（已采样，10-20张）
        movie_identity: 电影识别结果（可选）。
                       有值时结合电影知识进行一致性分析。
    返回：
        风格分析结果字典
    """
    if not config.ANTHROPIC_API_KEY:
        raise ValueError("请先在 config.py 中设置 ANTHROPIC_API_KEY。")

    client = _get_client()

    # 构建电影上下文（如果有）
    movie_context = _build_movie_context(movie_identity)

    # 如果当前 API 不支持 Vision，直接走元数据模式
    if not getattr(config, "VISION_SUPPORTED", True):
        print(f"当前 API 不支持图片分析（VISION_SUPPORTED=False），直接使用元数据模式...")
        return _analyze_by_metadata(frame_paths, client, movie_identity)

    # ---- 方法 1：尝试 Vision API ----
    try:
        mode_str = "（Vision + 电影知识模式）" if movie_context else "（Vision 模式）"
        print(f"AI 正在分析 {len(frame_paths)} 帧画面{mode_str}...")

        content = [
            {"type": "text", "text": "请分析以下电影帧画面的风格，以 JSON 格式返回分析结果："}
        ]
        for frame_path in frame_paths:
            content.append(_encode_image(frame_path))

        system_prompt = SYSTEM_PROMPT_VISION + movie_context

        response = client.messages.create(
            model=config.AI_MODEL,
            max_tokens=2048,
            system=system_prompt,
            messages=[{"role": "user", "content": content}],
        )

        response_text = _get_response_text(response)
        result = _parse_json_response(response_text)

        # 检查 Vision 响应是否有效（排除"error"或全"unknown"的回退响应）
        if result and not result.get("parse_error"):
            if result.get("error") or (
                result.get("genre") == "unknown"
                and result.get("mood") == "unknown"
                and result.get("pacing") == "unknown"
            ):
                print("Vision API returned invalid result, falling back to metadata mode...")
                result = None  # 标记为无效，触发回退
            else:
                result["analysis_mode"] = "vision"
                print("Film style analysis complete (Vision)")
                return result

        if result:
            result["analysis_mode"] = "vision"
            if movie_identity and movie_identity.get("identified"):
                result["movie_identity"] = movie_identity
            return result

    except Exception as e:
        error_msg = str(e)
        print(f"Vision API 调用失败: {error_msg[:200]}")

        # 检查是否是模型不支持 vision 的错误
        if "image" in error_msg.lower() or "multipart" in error_msg.lower() or "vision" in error_msg.lower():
            print("当前模型不支持图片分析，切换到元数据模式...")
        else:
            print("尝试元数据模式...")

    # ---- 方法 2：回退到元数据模式 ----
    return _analyze_by_metadata(frame_paths, client, movie_identity)


def _analyze_by_metadata(frame_paths: list[str], client: Anthropic, movie_identity: dict = None) -> dict:
    """
    通过帧的数值特征来分析电影风格（纯文本模式，不需要 Vision）
    """
    print(f"正在通过数值特征分析 {len(frame_paths)} 帧...")

    metadata_list, summary = _extract_frame_metadata(frame_paths)

    # 构建纯文本的分析请求
    movie_context = _build_movie_context(movie_identity)
    context_prefix = ""
    if movie_context:
        context_prefix = f"""以下电影已识别，请结合背景知识进行分析：

{movie_context}

---

"""

    user_message = f"""{context_prefix}请根据以下电影帧画面的数值特征分析其风格：

【整体统计】
- 帧数: {summary['frame_count']}
- 平均亮度: {summary['avg_brightness']} (0=暗, 1=亮)
- 亮度变化: {summary['brightness_variance']} (越大说明明暗变化越剧烈)
- 暖色调指数: {summary['avg_warmth']} (>1偏暖, <1偏冷)
- 平均饱和度: {summary['avg_saturation']}
- 平均对比度: {summary['avg_contrast']}
- 平均运动量: {summary['avg_motion']} (越大画面变化越快)

【逐帧数据（部分）】
{json.dumps(metadata_list[:5], ensure_ascii=False, indent=2)}
{"..." if len(metadata_list) > 5 else ""}

请根据以上数值推断电影风格，返回 JSON 格式分析结果：
{{
  "genre": "电影类型",
  "mood": "情绪氛围",
  "color_palette": "色调风格",
  "pacing": "画面节奏",
  "themes": ["主题1", "主题2"],
  "visual_style": "视觉风格",
  "recommended_music": {{
    "genre": "推荐音乐流派",
    "tempo_bpm": 120,
    "instruments": ["乐器1"],
    "mood_match": "情绪匹配说明",
    "lyrics_theme": "歌词主题"
  }}
}}"""

    response = client.messages.create(
        model=config.AI_MODEL,
        max_tokens=2048,
        system=SYSTEM_PROMPT_METADATA,
        messages=[{"role": "user", "content": user_message}],
    )

    response_text = _get_response_text(response)
    result = _parse_json_response(response_text)
    if result:
        result["analysis_mode"] = "metadata"
        result["frame_stats"] = summary
        if movie_identity and movie_identity.get("identified"):
            result["movie_identity"] = movie_identity

    print("电影风格分析完成 (元数据模式)")
    return result


def _parse_json_response(text: str) -> dict:
    """从 AI 响应中解析 JSON"""
    if not text or not isinstance(text, str):
        print(f"Warning: empty or invalid response text: {type(text)}")
        return {"raw_analysis": str(text) if text else "", "parse_error": True}

    # 尝试提取 JSON
    if "```json" in text:
        json_start = text.find("```json") + 7
        json_end = text.find("```", json_start)
        text = text[json_start:json_end].strip()
    elif "```" in text:
        json_start = text.find("```") + 3
        json_end = text.find("```", json_start)
        text = text[json_start:json_end].strip()

    if not text:
        return {"raw_analysis": text, "parse_error": True}

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        print(f"JSON parse failed, raw:\n{text[:500]}")
        return {"raw_analysis": text, "parse_error": True}
