"""
故事/旁白开发模块 — 基于真实素材证据的叙事结构开发
==================================================
取 material-review.json 和 project-brief.json 作为输入，
使用 AI 文本调用开发叙事结构、情绪弧线和场景节拍。
不凭空编造镜头 — 所有建议都基于实际素材。

参照：DaVinci-AutoEdit-Agent skills/viral-video-writer
"""
import json
import os
from datetime import datetime, timezone

from modules.workspace_manager import save_artifact


def develop_story(material_review: dict, project_brief: dict, run_path: str = None) -> dict:
    """
    基于素材审查结果开发叙事结构。

    参数：
        material_review: material-review.json 的内容
        project_brief: project-brief.json 的内容
        run_path: 运行目录路径

    返回：
        story-script 字典：
        {
            schema_version, developed_at,
            core_idea: str,
            story_structures: [{name, description, emotional_curve}],
            selected_structure: str,
            scene_beats: [{beat_name, start_pct, emotion, description}],
            titles: [{title, hook}],
            narration_policy: str,
            notes: str,
        }
    """
    # 提取关键信息
    taxonomy = material_review.get("taxonomy", {})
    style = material_review.get("style_analysis", {})
    movie = material_review.get("identified_movie", {})
    knowledge = movie.get("ai_knowledge", {}) if movie.get("identified") else {}

    genre = style.get("genre", "")
    mood = style.get("mood", "")
    themes = style.get("themes", [])
    emotional_arc = taxonomy.get("emotion", {}).get("emotional_arc", "")
    plot = knowledge.get("plot_summary", "")
    action_intensity = taxonomy.get("action", {}).get("action_intensity", "medium")

    topic = project_brief.get("topic", "")
    target_duration = project_brief.get("target_duration_seconds", 120)
    narration_enabled = project_brief.get("narration", {}).get("enabled", False)

    # ---- 尝试 AI 叙事开发 ----
    ai_story = None
    try:
        ai_story = _ai_story_development(
            material_review, project_brief,
        )
    except Exception as e:
        print(f"   [WARN] AI 故事开发失败，使用模板方案: {e}")

    if ai_story:
        story = ai_story
    else:
        story = _template_story(
            genre=genre, mood=mood, themes=themes,
            emotional_arc=emotional_arc, plot=plot,
            action_intensity=action_intensity,
            target_duration=target_duration,
        )

    # 构建故事脚本
    script = {
        "schema_version": "1.0.0",
        "developed_at": datetime.now(timezone.utc).isoformat(),
        "core_idea": story.get("core_idea", topic),
        "story_structures": story.get("story_structures", []),
        "selected_structure": story.get("selected_structure", "five-act"),
        "emotional_curve": story.get("emotional_curve", emotional_arc),
        "scene_beats": story.get("scene_beats", []),
        "titles": story.get("titles", _generate_titles(topic, genre, mood)),
        "narration_policy": "off" if not narration_enabled else "on",
        "notes": story.get("notes", ""),
    }

    if run_path:
        save_artifact(run_path, "story-script", script)

    return script


def _ai_story_development(material_review: dict, project_brief: dict) -> dict:
    """
    使用 AI 文本调用开发叙事结构。
    向 AI 发送素材审查的分类结果，要求基于证据生成故事方向。
    """
    try:
        import config
        from modules.style_analyzer import _get_client, _get_response_text

        client = _get_client()

        taxonomy = material_review.get("taxonomy", {})
        style = material_review.get("style_analysis", {})
        movie = material_review.get("identified_movie", {})
        topic = project_brief.get("topic", "")
        target_duration = project_brief.get("target_duration_seconds", 120)

        movie_context = ""
        if movie.get("identified"):
            knowledge = movie.get("ai_knowledge", {})
            movie_context = f"""
电影识别信息：
- 名称：{movie.get('movie_name', '')} ({movie.get('year', '')})
- 情节：{knowledge.get('plot_summary', '')}
- 名场面：{json.dumps(knowledge.get('key_scenes', []), ensure_ascii=False)}
- 情绪弧线：{knowledge.get('emotional_arc', '')}
"""

        prompt = f"""你是一位专业的视频剪辑故事编辑。请基于以下素材证据开发叙事结构。

## 项目目标
- 主题：{topic}
- 目标时长：{target_duration} 秒

{movie_context}

## 素材审查证据
- 类型：{style.get('genre', '未知')}
- 情绪：{style.get('mood', '未知')}
- 主题：{json.dumps(style.get('themes', []), ensure_ascii=False)}
- 动作强度：{taxonomy.get('action', {}).get('action_intensity', 'medium')}
- 情绪范围：{json.dumps(taxonomy.get('emotion', {}).get('emotional_range', []), ensure_ascii=False)}
- 场景设定：{json.dumps(taxonomy.get('scene', {}), ensure_ascii=False)}

请输出 JSON 格式：
{{
    "core_idea": "一个核心创意（一句话）",
    "story_structures": [
        {{"name": "方案名", "description": "叙事结构描述", "emotional_curve": "情绪曲线"}}
    ],
    "selected_structure": "推荐方案名",
    "emotional_curve": "详细情绪曲线描述",
    "scene_beats": [
        {{"beat_name": "节拍名", "start_pct": 0.0, "emotion": "情绪", "description": "基于证据的描述"}}
    ],
    "notes": "额外注释"
}}

重要规则：
1. 不要凭空编造不存在的镜头
2. 基于提供的素材证据
3. scene_beats 的 start_pct 从 0.0 到 1.0，覆盖完整时长
4. 使用中文输出"""

        response = client.messages.create(
            model=config.AI_MODEL,
            max_tokens=2000,
            system="你是一位专业的视频剪辑叙事设计师。只基于提供的素材证据进行创作。",
            messages=[{"role": "user", "content": prompt}],
        )

        text = _get_response_text(response)
        return _parse_json_response(text)

    except Exception as e:
        print(f"   AI 故事开发调用失败: {e}")
        return None


def _parse_json_response(text: str) -> dict:
    """从 AI 回复中提取 JSON"""
    import re

    # 尝试提取 ```json 块
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 尝试找到 { } 包围的 JSON
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return None  # 解析失败


def _template_story(genre: str, mood: str, themes: list, emotional_arc: str,
                    plot: str, action_intensity: str, target_duration: int) -> dict:
    """
    无 AI 时的模板化故事开发 — 基于证据生成叙事结构。
    """
    # 根据类型选择标准结构
    if action_intensity == "high":
        structures = [
            {
                "name": "动作高潮结构",
                "description": "开场动作 → 铺垫 → 高潮叠加 → 终极对决 → 余韵",
                "emotional_curve": "high → medium → building → peak → resolution",
            },
            {
                "name": "节奏交替结构",
                "description": "快慢交替，在激烈和舒缓之间切换",
                "emotional_curve": "action → calm → action → climax → calm",
            },
        ]
        selected = "动作高潮结构"
    else:
        structures = [
            {
                "name": "情绪递进结构",
                "description": "氛围铺垫 → 情绪递进 → 主题展开 → 情感高潮 → 回味",
                "emotional_curve": "ambient → building → developing → peak → reflection",
            },
            {
                "name": "对比结构",
                "description": "在不同情绪之间跳跃对比",
                "emotional_curve": "contrast → merge → conflict → resolution",
            },
        ]
        selected = "情绪递进结构"

    # 生成场景节拍（基于目标时长）
    beats_count = max(3, min(8, target_duration // 20))
    beat_duration_pct = 1.0 / beats_count

    emotions_sequence = ["establishing", "building", "tension", "action", "climax", "resolution", "reflection"]
    if beats_count <= len(emotions_sequence):
        emotions_sequence = emotions_sequence[:beats_count]

    beats = []
    for i in range(beats_count):
        emotion_idx = min(i, len(emotions_sequence) - 1)
        beats.append({
            "beat_name": f"节拍 {i + 1}",
            "start_pct": round(i * beat_duration_pct, 3),
            "emotion": emotions_sequence[emotion_idx],
            "description": _beat_description(i, beats_count, genre, mood),
        })

    core = f"以{genre}风格呈现{mood}情绪，{themes[0] if themes else '视觉叙事'}"

    return {
        "core_idea": core,
        "story_structures": structures,
        "selected_structure": selected,
        "emotional_curve": emotional_arc or f"从{mood}发展到高潮再到余韵",
        "scene_beats": beats,
        "notes": "基于素材证据自动生成（模板模式）",
    }


def _beat_description(index: int, total: int, genre: str, mood: str) -> str:
    """生成场景节拍描述"""
    if index == 0:
        return f"开场画面，建立{mood}氛围"
    elif index == total - 1:
        return "终场画面，回归平静"
    elif index == total // 2:
        return "中段高潮，情绪峰值"
    else:
        return f"发展段落，推进叙事"


def _generate_titles(topic: str, genre: str, mood: str) -> list[dict]:
    """生成标题和钩子选项"""
    titles = [
        {"title": topic, "hook": f"一段{genre}风格的{mood}之旅"},
    ]

    mood_map = {
        "epic": "史诗",
        "dark": "暗黑",
        "uplifting": "治愈",
        "tense": "紧张",
        "melancholic": "忧郁",
        "action": "燃",
        "romantic": "浪漫",
    }

    mood_cn = mood_map.get(mood.lower(), mood)

    titles.extend([
        {"title": f"{topic}｜{mood_cn}混剪", "hook": f"用{mood_cn}的方式打开{topic}"},
        {"title": f"【{genre}】{topic}", "hook": f"每一帧都是{genre}美学"},
    ])

    return titles[:5]


def story_to_display(script: dict) -> dict:
    """将故事脚本转换为前端友好的显示格式"""
    return {
        "core_idea": script.get("core_idea", ""),
        "story_structures": script.get("story_structures", []),
        "selected_structure": script.get("selected_structure", ""),
        "emotional_curve": script.get("emotional_curve", ""),
        "scene_beats": script.get("scene_beats", []),
        "titles": script.get("titles", []),
        "narration_policy": script.get("narration_policy", "off"),
        "notes": script.get("notes", ""),
    }
