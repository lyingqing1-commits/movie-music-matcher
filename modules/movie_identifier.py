"""
电影识别模块 — 利用 AI 训练知识锚定分析结果
=============================================
发送视频帧给 DeepSeek Vision API，识别电影名称并提取背景知识。
已知电影 → 返回 plot_summary, themes, key_scenes 等作为分析锚点
未知素材 → 返回 identified=False，不影响后续流程

这一步骤解决了"同一电影多次上传分析结果不一致"的问题：
一旦 AI 识别出电影，后续风格分析会基于电影的背景知识，
而非仅依赖随机采样的帧画面。
"""
import base64
import json
import mimetypes
import hashlib
import os
from anthropic import Anthropic
import config


def _get_client() -> Anthropic:
    """创建 AI 客户端（支持自定义 base_url）"""
    kwargs = {"api_key": config.ANTHROPIC_API_KEY}
    if config.ANTHROPIC_BASE_URL:
        kwargs["base_url"] = config.ANTHROPIC_BASE_URL
    return Anthropic(**kwargs)


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


def _get_response_text(response) -> str:
    """从 API 响应中提取文本（跳过 ThinkingBlock 思考链）"""
    for block in response.content:
        if getattr(block, "type", None) == "text":
            return getattr(block, "text", "") or ""
    return str(response.content[0]) if response.content else ""


# ---- 提示词 ----

SYSTEM_PROMPT_MOVIE_ID = """你是一位资深电影数据库专家和影评人。请仔细观察这些从视频中提取的帧画面。

你的任务：

1. **识别判断**：判断这是否是一部已知的电影/电视剧/纪录片
   - 如果认识：给出准确的名称（中文名 + 英文名/原片名）、上映年份
   - 如果不认识：如实说明，并描述画面内容

2. **背景知识**（仅当你认识这部电影时）：
   - 情节概要：1-2 句话概括
   - 核心主题：3-5 个关键词（如：复仇、救赎、家庭、战争、自由…）
   - 关键场景：3-5 个著名场景（描述 + 大致位置「开场/中段/高潮/结尾」+ 场景情绪）
   - 情感走向：电影整体的情感弧线（如：轻松幽默→渐入紧张→悲壮高潮→温情结局）
   - 视觉特征：画面风格（如：冷色调科幻、暖色调怀旧、手持纪实感、宽幅史诗感…）

3. **如果完全不认识**：
   - 设置 identified=false
   - 描述画面中看到的内容（场景类型、人物、色调、时代感）

请以严格的 JSON 格式返回，不要包含其他文字：
{
  "identified": true/false,
  "movie_name": "电影名 / null",
  "year": 2020 / null,
  "confidence": "high" / "medium" / "low",
  "ai_knowledge": {
    "plot_summary": "...",
    "themes": ["主题1", "主题2", ...],
    "key_scenes": [
      {"description": "...", "position": "开场/中段/高潮/结尾", "tone": "情绪"}
    ],
    "emotional_arc": "...",
    "visual_signature": "..."
  }
}"""


def identify_movie(frame_paths: list[str]) -> dict:
    """
    识别电影/视频内容并提取背景知识。

    参数：
        frame_paths: 帧图片路径列表（通常 10 张采样帧）

    返回：
        {
            "identified": bool,
            "movie_name": str | None,
            "year": int | None,
            "confidence": "high" | "medium" | "low",
            "ai_knowledge": {
                "plot_summary": str,
                "themes": [str, ...],
                "key_scenes": [{description, position, tone}, ...],
                "emotional_arc": str,
                "visual_signature": str,
            } | None,
        }

    如果 API 调用失败或模型不支持 Vision，返回 identified=False
    """
    if not config.ANTHROPIC_API_KEY:
        return _unidentified("API Key 未配置")

    # 如果当前模型/API 不支持 Vision，直接跳过（避免浪费 API 调用）
    if not getattr(config, "VISION_SUPPORTED", True):
        print("   [INFO] API 不支持图片识别（VISION_SUPPORTED=False），跳过电影识别步骤")
        return _unidentified("API 不支持 Vision")

    client = _get_client()

    try:
        print(f"🔍 AI 正在识别电影内容（{len(frame_paths)} 帧）...")

        # 构建 Vision API 请求
        content = [
            {"type": "text", "text": "请识别以下电影帧画面属于哪部电影，以 JSON 格式返回。"}
        ]
        for frame_path in frame_paths:
            content.append(_encode_image(frame_path))

        response = client.messages.create(
            model=config.AI_MODEL,
            max_tokens=2048,
            system=SYSTEM_PROMPT_MOVIE_ID,
            messages=[{"role": "user", "content": content}],
        )

        response_text = _get_response_text(response)
        result = _parse_identification(response_text)

        if result.get("identified") and result.get("movie_name"):
            print(f"   ✅ 识别结果: {result['movie_name']} ({result.get('year', '?')}) [置信度: {result.get('confidence', '?')}]")
        else:
            print("   ℹ️ 未识别为已知电影，将使用纯视觉分析模式")

        return result

    except Exception as e:
        error_msg = str(e)
        print(f"   ⚠️ 电影识别 API 调用失败: {error_msg[:200]}")

        # 检查是否是模型不支持 Vision 的错误
        if any(kw in error_msg.lower() for kw in ("image", "vision", "multipart")):
            print("   当前模型不支持图片识别，跳过电影识别步骤")
        else:
            print("   将使用纯视觉分析模式继续")

        return _unidentified(f"API 错误: {error_msg[:100]}")


def _parse_identification(text: str) -> dict:
    """从 AI 响应中解析电影识别结果"""
    if not text or not isinstance(text, str):
        return _unidentified("空响应")

    # 尝试提取 JSON
    if "```json" in text:
        json_start = text.find("```json") + 7
        json_end = text.find("```", json_start)
        text = text[json_start:json_end].strip()
    elif "```" in text:
        json_start = text.find("```") + 3
        json_end = text.find("```", json_start)
        text = text[json_start:json_end].strip()

    try:
        result = json.loads(text)
        # 标准化字段
        if not isinstance(result.get("identified"), bool):
            result["identified"] = bool(result.get("movie_name"))
        if result.get("identified") and not result.get("ai_knowledge"):
            result["ai_knowledge"] = _default_knowledge(result.get("movie_name", ""))
        return result
    except (json.JSONDecodeError, TypeError):
        # 如果 JSON 解析失败，检查是否提到了电影名
        # 保守处理：返回未识别
        print(f"   电影识别 JSON 解析失败，原始响应:\n{text[:300]}")
        return _unidentified("JSON 解析失败")


def _unidentified(reason: str = "") -> dict:
    """构建"未识别"响应"""
    return {
        "identified": False,
        "movie_name": None,
        "year": None,
        "confidence": None,
        "ai_knowledge": None,
        "reason": reason,
    }


def _default_knowledge(movie_name: str) -> dict:
    """为已识别但缺少详细知识的电影提供最小结构"""
    return {
        "plot_summary": f"这是一部名为《{movie_name}》的电影。",
        "themes": [],
        "key_scenes": [],
        "emotional_arc": "",
        "visual_signature": "",
    }


# ============================================
# 视频指纹缓存（可选：避免重复调用）
# ============================================

def _compute_video_fingerprint(video_path: str) -> str:
    """
    计算视频指纹用于缓存。
    读取文件头尾 + 元数据，生成哈希。
    """
    try:
        file_size = os.path.getsize(video_path)
        hasher = hashlib.sha256()

        # 读取前 10MB
        with open(video_path, "rb") as f:
            hasher.update(f.read(min(10_000_000, file_size)))

        # 读取后 10MB（如果文件足够大）
        if file_size > 20_000_000:
            with open(video_path, "rb") as f:
                f.seek(max(0, file_size - 10_000_000))
                hasher.update(f.read(10_000_000))

        # 加入文件大小
        hasher.update(str(file_size).encode())

        return hasher.hexdigest()[:32]
    except Exception:
        return ""  # 指纹计算失败，不使用缓存


def identify_movie_cached(
    video_path: str,
    frame_paths: list[str],
    cache_dir: str = None,
) -> dict:
    """
    带缓存支持的电影识别（可选使用）。

    与 identify_movie 功能相同，但会：
    1. 计算视频文件指纹
    2. 检查缓存 → 命中则跳过 API 调用
    3. 未命中 → 调用 API → 写入缓存

    缓存文件: {cache_dir}/movie_id_cache.json
    """
    if cache_dir is None:
        cache_dir = config.OUTPUT_FOLDER
    os.makedirs(cache_dir, exist_ok=True)

    cache_path = os.path.join(cache_dir, "movie_id_cache.json")

    fingerprint = _compute_video_fingerprint(video_path)
    if not fingerprint:
        # 无法计算指纹，直接调用 API
        print("   无法计算视频指纹，跳过缓存")
        return identify_movie(frame_paths)

    # 读取缓存
    cache = {}
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            cache = {}

    # 检查命中
    if fingerprint in cache:
        cached_result = cache[fingerprint]
        print(f"   📦 缓存命中！电影: {cached_result.get('movie_name', '未知')}")
        return cached_result

    # 调用 API
    result = identify_movie(frame_paths)

    # 写入缓存
    cache[fingerprint] = result
    try:
        # 限制缓存大小（最多保留 50 条）
        if len(cache) > 50:
            oldest_keys = list(cache.keys())[:10]
            for k in oldest_keys:
                if k != fingerprint:
                    del cache[k]
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass  # 缓存写入失败不影响主流程

    return result
