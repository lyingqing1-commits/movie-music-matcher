"""
项目简报模块 — 创建、验证和管理项目简报
=========================================
定义剪辑项目的创作目标：主题、目标时长、平台、画幅、语言、剪辑偏好。
输出符合 DaVinci-AutoEdit-Agent 风格的 project-brief.json。

v2: 支持结构化偏好选项（节奏/转场/情绪/调色/旁白/音乐融合）
v3: AI 自动解释偏好关键词，生成偏好摘要和故事脚本指导
"""
import json
import os
from datetime import datetime, timezone

import config
from modules.workspace_manager import generate_project_slug, create_run_folder, save_artifact

# ---- 偏好关键词 → 人类可读描述映射 ----

PREFERENCE_DESCRIPTIONS = {
    # Pacing
    "fast": "快节奏剪辑，频繁切换，高能量感",
    "moderate": "中等节奏，自然流畅的叙事推进",
    "slow": "慢节奏，电影感长镜头，留白呼吸",
    "dynamic": "变化节奏，快慢结合，营造张力起伏",

    # Transitions
    "hard_cut": "硬切为主，干净利落的镜头转换",
    "crossfade": "叠化过渡，柔和的时间/空间转换",
    "jcut": "J-cut/L-cut，声音先行或延后以增强连贯性",
    "match_cut": "匹配剪辑，用视觉/动作相似性连接镜头",
    "speed_ramp": "变速效果，用速度变化强调关键动作",

    # Mood
    "energetic": "活力明快，积极向上的情绪基调",
    "emotional": "感性煽情，触动心弦的情感表达",
    "dark": "暗黑情绪化，深沉压抑的氛围营造",
    "tense": "紧张悬疑，扣人心弦的压迫感",
    "inspirational": "励志振奋，鼓舞人心的积极力量",
    "calm": "平静沉思，安宁内省的静谧感",

    # Color Grade
    "warm": "暖色调/金色，温暖怀旧的视觉质感",
    "cool": "冷色调/蓝色，冷静克制的视觉风格",
    "high_contrast": "高对比度，强烈的明暗反差",
    "soft": "柔和/粉彩，轻盈梦幻的视觉感",
    "desaturated": "去饱和/低调，朴素真实的质感",
    "vibrant": "鲜艳/饱和，色彩丰富的视觉冲击",

    # Narration
    "none": "无旁白，纯视觉叙事",
    "documentary": "专业纪录片风格旁白，客观权威",
    "casual": "随意Vlog风格，亲切自然的第一人称",
    "poetic": "诗意文学风格，抒情写意的语言",

    # Music Integration
    "music_forward": "音乐主导，视频服务于音乐节奏",
    "balanced": "均衡融合，音乐与画面相辅相成",
    "dialogue_first": "对话/音效优先，音乐作为背景烘托",
}

# 偏好分组的中文标签
PREFERENCE_GROUP_LABELS = {
    "pacing": "节奏",
    "transition": "转场",
    "mood": "情绪",
    "color_grade": "调色",
    "narration_style": "旁白",
    "music_integration": "音乐融合",
}

# 支持的平台和画幅
SUPPORTED_PLATFORMS = {
    "jianying": "剪映专业版",
    "capcut": "CapCut",
    "resolve": "DaVinci Resolve",
    "universal": "通用（仅蓝图）",
}

SUPPORTED_ASPECT_RATIOS = {
    "16:9": "横屏 16:9（标准）",
    "9:16": "竖屏 9:16（短视频）",
    "1:1": "方形 1:1",
    "4:3": "经典 4:3",
    "original": "保持原始比例",
}

DURATION_PRESETS = {
    "short": 30,       # 短视频
    "medium": 120,     # 中视频
    "long": 480,       # 长片
    "feature": 1800,   # 长片+
}


def create_brief(form_data: dict) -> dict:
    """
    从用户表单数据创建并验证项目简报。

    参数：
        form_data: {
            topic: str,                    # 项目主题/标题
            target_duration: int,          # 目标时长（秒），15-3600
            platform: str,                 # jianying | capcut | resolve | universal
            aspect_ratio: str,             # 16:9 | 9:16 | 1:1 | 4:3 | original
            language: str,                 # zh-CN | en | ja | ...
            editing_mode: str,             # video_first | music_first
            editing_preferences: str,      # 用户剪辑偏好自由文本
            narration_enabled: bool,       # 是否需要旁白/TTS
            custom_export_path: str,       # 自定义导出路径（可选）
        }

    返回：
        完整验证后的 project_brief 字典
    """
    # 基础字段
    topic = (form_data.get("topic", "") or "").strip()
    if not topic:
        raise ValueError("项目主题不能为空")

    target_duration = _parse_duration(form_data.get("target_duration", 120))
    platform = form_data.get("platform", config.DEFAULT_PLATFORM if hasattr(config, "DEFAULT_PLATFORM") else "jianying")
    aspect_ratio = form_data.get("aspect_ratio", "16:9")
    # 语言固定为中文，旁白默认关闭（已从面移除）
    language = "zh-CN"
    editing_mode = form_data.get("editing_mode", "video_first")
    editing_preferences = (form_data.get("editing_preferences", "") or "").strip()
    narration_enabled = False
    custom_export_path = (form_data.get("custom_export_path", "") or "").strip() or None

    # ---- 解析结构化偏好 ----
    structured_prefs = {}
    prefs_summary_lines = []
    prefs_raw_text = ""

    if editing_preferences:
        try:
            # 尝试解析 JSON 格式的结构化偏好
            structured_prefs = json.loads(editing_preferences)
            if isinstance(structured_prefs, dict):
                for group, values in structured_prefs.items():
                    if isinstance(values, list) and values:
                        group_label = PREFERENCE_GROUP_LABELS.get(group, group)
                        descriptions = []
                        for v in values:
                            desc = PREFERENCE_DESCRIPTIONS.get(v, v)
                            descriptions.append(desc)
                        prefs_summary_lines.append(f"【{group_label}】{'; '.join(descriptions)}")
                        prefs_raw_text += f"{group_label}: {', '.join(values)}\n"
        except (json.JSONDecodeError, TypeError):
            # 不是 JSON → 自由文本
            prefs_raw_text = editing_preferences
            if editing_preferences:
                prefs_summary_lines.append(editing_preferences)

    preferences_summary = "\n".join(prefs_summary_lines) if prefs_summary_lines else ""
    if not prefs_raw_text:
        prefs_raw_text = preferences_summary or "使用内置最佳实践"

    # 生成 AI 偏好解释（如果有 API key）
    ai_prefs_interpretation = ""
    if structured_prefs and config.ANTHROPIC_API_KEY:
        try:
            ai_prefs_interpretation = _interpret_preferences_with_ai(
                topic, structured_prefs, editing_mode, target_duration, language
            )
        except Exception as e:
            print(f"   [WARN] AI 偏好解释失败: {e}")

    # 生成 slug
    project_slug = generate_project_slug(topic)

    # 构建简报
    brief = {
        "schema_version": "1.0.0",
        "project_name": topic,
        "project_slug": project_slug,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "media_paths": [],  # 在上传时填充
        "topic": topic,
        "platform": platform,
        "target_duration_seconds": target_duration,
        "aspect_ratio": aspect_ratio,
        "language": language,
        "editing_mode": editing_mode,
        "editing_preferences": {
            "profile": "custom" if (structured_prefs or editing_preferences) else "default",
            "notes": prefs_raw_text,
            "summary": preferences_summary,
            "structured": structured_prefs,
            "ai_interpretation": ai_prefs_interpretation,
            "editing_mode": editing_mode,
        },
        "narration": {
            "enabled": narration_enabled,
        },
        "output": {
            "custom_export_path": custom_export_path,
        },
        "status": "created",
    }

    # 验证
    errors = validate_brief(brief)
    if errors:
        raise ValueError("简报验证失败:\n" + "\n".join(f"  - {e}" for e in errors))

    # 创建运行目录并保存
    run_path = create_run_folder(project_slug)
    brief["run_path"] = run_path
    save_artifact(run_path, "project-brief", brief)

    return brief


def validate_brief(brief: dict) -> list[str]:
    """
    验证简报字段的合法性。

    返回：
        错误字符串列表；空列表表示验证通过
    """
    errors = []

    # 必填字段
    if not brief.get("topic"):
        errors.append("项目主题 (topic) 不能为空")

    # 时长
    duration = brief.get("target_duration_seconds", 0)
    if not isinstance(duration, (int, float)) or duration < 5 or duration > 7200:
        errors.append(f"目标时长 {duration}s 无效（范围：5-7200 秒）")

    # 平台
    platform = brief.get("platform", "")
    if platform not in SUPPORTED_PLATFORMS:
        errors.append(f"不支持的平台: {platform}（支持: {', '.join(SUPPORTED_PLATFORMS.keys())}）")

    # 画幅
    ratio = brief.get("aspect_ratio", "")
    if ratio not in SUPPORTED_ASPECT_RATIOS:
        errors.append(f"不支持的画幅比: {ratio}（支持: {', '.join(SUPPORTED_ASPECT_RATIOS.keys())}）")

    # 剪辑模式
    mode = brief.get("editing_mode", "")
    if mode not in ("video_first", "music_first"):
        errors.append(f"不支持的剪辑模式: {mode}（支持: video_first, music_first）")

    return errors


def load_brief(project_slug: str) -> dict:
    """加载已保存的项目简报"""
    from modules.workspace_manager import load_artifact, get_run_path
    run_path = get_run_path(project_slug)
    return load_artifact(run_path, "project-brief")


def _parse_duration(value) -> int:
    """解析时长输入：支持整数（秒）、字符串（如 '2m'、'120'）"""
    if isinstance(value, (int, float)):
        return max(5, min(7200, int(value)))

    if isinstance(value, str):
        value = value.strip().lower()
        if value.endswith("m"):
            try:
                return max(5, min(7200, int(float(value[:-1]) * 60)))
            except ValueError:
                pass
        if value.endswith("s"):
            try:
                return max(5, min(7200, int(float(value[:-1]))))
            except ValueError:
                pass
        try:
            return max(5, min(7200, int(float(value))))
        except ValueError:
            pass

    return 120  # 默认 2 分钟


def brief_to_display(brief: dict) -> dict:
    """
    将简报数据转换为前端友好的显示格式。

    返回：
        {topic, duration_display, platform_display, aspect_ratio, mode_display, ...}
    """
    duration = brief.get("target_duration_seconds", 0)
    if duration >= 60:
        duration_display = f"{duration // 60}分{duration % 60}秒" if duration % 60 else f"{duration // 60}分钟"
    else:
        duration_display = f"{duration}秒"

    platform = brief.get("platform", "jianying")
    platform_display = SUPPORTED_PLATFORMS.get(platform, platform)

    mode = brief.get("editing_mode", "video_first")
    mode_display = "视频优先" if mode == "video_first" else "音乐优先"

    prefs = brief.get("editing_preferences", {})
    preferences_summary = prefs.get("summary", "") or prefs.get("notes", "")
    ai_interpretation = prefs.get("ai_interpretation", "")

    return {
        "topic": brief.get("topic", ""),
        "slug": brief.get("project_slug", ""),
        "duration_seconds": duration,
        "duration_display": duration_display,
        "platform": platform,
        "platform_display": platform_display,
        "aspect_ratio": brief.get("aspect_ratio", "16:9"),
        "language": brief.get("language", "zh-CN"),
        "mode": mode,
        "mode_display": mode_display,
        "preferences": preferences_summary,
        "preferences_summary": preferences_summary,
        "ai_interpretation": ai_interpretation,
        "narration_enabled": brief.get("narration", {}).get("enabled", False),
        "created_at": brief.get("created_at", ""),
    }


def _interpret_preferences_with_ai(
    topic: str,
    structured_prefs: dict,
    editing_mode: str,
    target_duration: int,
    language: str,
) -> str:
    """
    使用 AI 解释用户的偏好选择，生成：
    1. 偏好关键词的含义解释
    2. 针对该主题的具体剪辑建议
    3. 故事脚本的创作方向
    """
    from anthropic import Anthropic

    kwargs = {"api_key": config.ANTHROPIC_API_KEY}
    if config.ANTHROPIC_BASE_URL:
        kwargs["base_url"] = config.ANTHROPIC_BASE_URL
    client = Anthropic(**kwargs)

    # 构建偏好描述
    pref_lines = []
    for group, values in structured_prefs.items():
        if isinstance(values, list) and values:
            group_label = PREFERENCE_GROUP_LABELS.get(group, group)
            descriptions = [PREFERENCE_DESCRIPTIONS.get(v, v) for v in values]
            pref_lines.append(f"- {group_label}: {', '.join(descriptions)}")

    prefs_text = "\n".join(pref_lines) if pref_lines else "无特殊偏好"

    mode_label = "视频优先（突出高光片段）" if editing_mode == "video_first" else "音乐优先（情感匹配音乐结构）"

    prompt = f"""你是一位资深影视剪辑顾问。用户正在使用AI自动剪辑工具制作视频。

【项目主题】
{topic}

【目标时长】
{target_duration} 秒

【剪辑模式】
{mode_label}

【用户选择的风格偏好】
{prefs_text}

请根据以上偏好，生成一段简洁的剪辑指导说明（中文，200字以内），包含：
1. 这些偏好的组合意味着什么风格定位
2. 针对该主题的具体剪辑建议
3. 建议的故事脚本方向或情绪弧线

直接返回指导文本，不要使用markdown标题。"""

    try:
        response = client.messages.create(
            model=config.AI_MODEL,
            max_tokens=600,
            system="你是一位资深影视剪辑顾问，擅长将抽象的剪辑偏好转化为具体的创作指导。回答简洁有力，直接给出可执行的建议。",
            messages=[{"role": "user", "content": prompt}],
        )
        text = ""
        for block in response.content:
            if getattr(block, "type", None) == "text":
                text += getattr(block, "text", "") or ""
        return text.strip()
    except Exception as e:
        print(f"   [WARN] AI 偏好解释请求失败: {e}")
        return ""
