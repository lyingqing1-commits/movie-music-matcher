"""
项目简报模块 — 创建、验证和管理项目简报
=========================================
定义剪辑项目的创作目标：主题、目标时长、平台、画幅、语言、剪辑偏好。
输出符合 DaVinci-AutoEdit-Agent 风格的 project-brief.json。

参照：DaVinci-AutoEdit-Agent examples/project-brief.example.json
"""
import json
import os
from datetime import datetime, timezone

import config
from modules.workspace_manager import generate_project_slug, create_run_folder, save_artifact

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
    language = form_data.get("language", "zh-CN")
    editing_mode = form_data.get("editing_mode", "video_first")
    editing_preferences = (form_data.get("editing_preferences", "") or "").strip()
    narration_enabled = form_data.get("narration_enabled", False)
    if isinstance(narration_enabled, str):
        narration_enabled = narration_enabled.lower() in ("true", "1", "yes", "on")
    custom_export_path = (form_data.get("custom_export_path", "") or "").strip() or None

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
            "profile": "custom" if editing_preferences else "default",
            "notes": editing_preferences or "使用内置最佳实践",
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
        "preferences": brief.get("editing_preferences", {}).get("notes", ""),
        "narration_enabled": brief.get("narration", {}).get("enabled", False),
        "created_at": brief.get("created_at", ""),
    }
