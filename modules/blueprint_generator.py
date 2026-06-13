"""
剪辑蓝图生成器 — 生成精确的逐镜头剪辑蓝图
==========================================
包装现有的智能编辑模块（scene_detector + segment_scorer + smart_editor），
将输出格式化为符合 DaVinci-AutoEdit-Agent blueprint-schema 的 edit-blueprint.json。

复用：
- scene_detector.detect_scenes() — FFmpeg 场景检测
- segment_scorer.score_segments() — AI 片段评分
- smart_editor.assemble_smart_draft() — 智能匹配算法
- music_structure_analyzer.analyze_music_structure() — 音乐结构分析
- music_matcher.analyze_audio() — 音频特征分析
"""
import json
import os
from datetime import datetime, timezone

from modules.workspace_manager import save_artifact


def generate_blueprint(
    video_path: str,
    audio_path: str,
    video_info: dict,
    material_review: dict,
    project_brief: dict,
    run_path: str,
    task_id: str = None,
    editing_mode: str = None,
    music_structure: dict = None,
    audio_features: dict = None,
) -> dict:
    """
    生成完整的剪辑蓝图。

    参数：
        video_path: 视频文件路径
        audio_path: 音频文件路径（最佳匹配）
        video_info: 视频元数据
        material_review: 素材审查结果
        project_brief: 项目简报
        run_path: 运行目录路径
        task_id: 任务 ID（用于帧提取）
        editing_mode: 剪辑模式
        music_structure: 预计算的音乐结构（可选）
        audio_features: 预计算的音频特征（可选）

    返回：
        edit-blueprint 字典，符合 blueprint-schema
    """
    editing_mode = editing_mode or project_brief.get("editing_mode", "video_first")

    # ---- Step 1: 场景检测 ----
    print("   [Blueprint] 检测场景...")
    scenes = []
    try:
        from modules.scene_detector import detect_scenes
        video_dur = video_info.get("duration", 60)
        scenes = detect_scenes(video_path, video_duration=video_dur)
        print(f"   [Blueprint] 检测到 {len(scenes)} 个场景")
    except Exception as e:
        print(f"   [WARN] 场景检测失败: {e}")
        # 回退到固定分段
        dur = video_info.get("duration", 60)
        seg_len = 5.0
        scenes = [
            {"start_time": i * seg_len, "end_time": min((i + 1) * seg_len, dur), "duration": min(seg_len, dur - i * seg_len)}
            for i in range(max(1, int(dur / seg_len)))
        ]

    # ---- Step 2: AI 片段评分 ----
    print("   [Blueprint] 评分片段...")
    scored_segments = []
    try:
        from modules.segment_scorer import score_segments
        movie_identity = material_review.get("identified_movie")
        scored_segments = score_segments(
            video_path, scenes, movie_identity,
            task_id or "blueprint", editing_mode,
        )
        print(f"   [Blueprint] 评分了 {len(scored_segments)} 个片段")
    except Exception as e:
        print(f"   [WARN] 片段评分失败: {e}")
        # 回退：使用场景数据 + 默认分数
        import random
        for i, sc in enumerate(scenes):
            scored_segments.append({
                "start_time": sc["start_time"],
                "end_time": sc["end_time"],
                "duration": sc["duration"],
                "highlight_score": random.randint(40, 80),
                "emotional_tone": "action" if random.random() > 0.5 else "emotional",
                "suggested_use": "chorus",
                "visual_quality": "medium",
                "description": f"场景 {i + 1}",
            })

    # ---- Step 3: 音频和音乐结构 ----
    best_audio_features = audio_features or {}
    best_music_structure = music_structure

    if not best_audio_features and audio_path and os.path.exists(audio_path):
        try:
            from modules.music_matcher import analyze_audio
            best_audio_features = analyze_audio(audio_path)
        except Exception as e:
            print(f"   [WARN] 音频分析失败: {e}")

    if not best_music_structure and audio_path and os.path.exists(audio_path):
        try:
            from modules.music_structure_analyzer import analyze_music_structure
            style = material_review.get("style_analysis", {})
            best_music_structure = analyze_music_structure(
                audio_path, best_audio_features, style,
            )
        except Exception as e:
            print(f"   [WARN] 音乐结构分析失败: {e}")

    # ---- Step 4: 智能匹配 ----
    print("   [Blueprint] 智能匹配...")
    smart_segments = []
    try:
        from modules.smart_editor import assemble_smart_draft

        if best_music_structure:
            structure = best_music_structure
        else:
            # 回退音乐结构
            bpm = best_audio_features.get("tempo_bpm", 120)
            dur = best_audio_features.get("duration_seconds", video_info.get("duration", 60))
            structure = _fallback_music_structure(dur, bpm)

        smart_segments = assemble_smart_draft(
            scored_segments=scored_segments,
            music_structure=structure,
            video_info=video_info,
            editing_mode=editing_mode,
        )
        print(f"   [Blueprint] 生成了 {len(smart_segments)} 个放置计划")
    except Exception as e:
        print(f"   [WARN] 智能匹配失败: {e}")
        # 最终回退：直接使用评分片段
        target = 0.0
        for seg in scored_segments[:20]:
            smart_segments.append({
                "source_start": seg.get("start_time", 0),
                "source_duration": seg.get("duration", 2),
                "target_start": target,
                "match_rationale": "回退模式：按顺序排列",
                "segment_score": seg.get("highlight_score", 50),
                "emotional_tone": seg.get("emotional_tone", "neutral"),
            })
            target += seg.get("duration", 2)

    # ---- Step 5: 构建蓝图 ----
    blueprint = _build_blueprint_document(
        smart_segments=smart_segments,
        video_path=video_path,
        audio_path=audio_path,
        video_info=video_info,
        audio_features=best_audio_features,
        music_structure=best_music_structure,
        material_review=material_review,
        project_brief=project_brief,
        editing_mode=editing_mode,
    )

    # 持久化
    if run_path:
        save_artifact(run_path, "edit-blueprint", blueprint)

    return blueprint


def _build_blueprint_document(
    smart_segments: list,
    video_path: str,
    audio_path: str,
    video_info: dict,
    audio_features: dict,
    music_structure: dict,
    material_review: dict,
    project_brief: dict,
    editing_mode: str,
) -> dict:
    """按照 blueprint-schema 构建完整的蓝图文档"""

    width = video_info.get("width", 1920)
    height = video_info.get("height", 1080)
    fps = video_info.get("fps", 30) or 30
    video_duration = video_info.get("duration", 0)
    audio_duration = audio_features.get("duration_seconds", video_duration)
    bpm = audio_features.get("tempo_bpm", 120)

    # 构建片段列表
    segments = []
    for i, seg in enumerate(smart_segments):
        source_start = seg.get("source_start", 0)
        source_duration = seg.get("source_duration", 2)
        target_start = seg.get("target_start", 0)
        target_duration = source_duration  # 默认保持速度 1x

        # 确保在源素材范围内
        if video_duration > 0:
            source_start = min(source_start, video_duration - 0.1)
            source_duration = min(source_duration, video_duration - source_start)

        segment = {
            "id": f"seg-{i:04d}",
            "media_type": "video",
            "source_path": os.path.abspath(video_path).replace("\\", "/"),
            "source_in_seconds": round(source_start, 3),
            "source_out_seconds": round(source_start + source_duration, 3),
            "timeline_in_seconds": round(target_start, 3),
            "timeline_out_seconds": round(target_start + target_duration, 3),
            "video_track": 1,
            "audio_track": 1,
            "purpose": seg.get("match_rationale", f"片段 {i + 1}"),
            "source_group": "main",
            "confidence": 0.8,
            "emotional_tone": seg.get("emotional_tone", "neutral"),
            "highlight_score": seg.get("segment_score", 50),
            "music_section": seg.get("music_section", "verse"),
        }
        segments.append(segment)

    # 音频片段
    if audio_path and os.path.exists(audio_path):
        audio_segment = {
            "id": "audio-main",
            "media_type": "audio",
            "source_path": os.path.abspath(audio_path).replace("\\", "/"),
            "source_in_seconds": 0.0,
            "source_out_seconds": audio_duration,
            "timeline_in_seconds": 0.0,
            "timeline_out_seconds": audio_duration,
            "video_track": 0,
            "audio_track": 1,
            "purpose": "背景音乐",
            "source_group": "audio",
            "confidence": 1.0,
        }
    else:
        audio_segment = None

    # 计算时间线统计
    if segments:
        timeline_end = max(s.get("timeline_out_seconds", 0) for s in segments)
        timeline_start = 0.0
        used_duration = sum(s.get("source_out_seconds", 0) - s.get("source_in_seconds", 0)
                          for s in segments)
    else:
        timeline_end = 0
        timeline_start = 0
        used_duration = 0

    # 收集情绪音调及分值统计
    tones_used = {}
    for s in segments:
        t = s.get("emotional_tone", "neutral")
        tones_used[t] = tones_used.get(t, 0) + 1

    return {
        "schema_version": "1.0.0",
        "project_slug": project_brief.get("project_slug", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "editing_mode": editing_mode,
        "project": {
            "name": project_brief.get("project_name", ""),
            "fps": round(fps),
            "width": width,
            "height": height,
            "target_duration_seconds": project_brief.get("target_duration_seconds",
                                                         timeline_end),
        },
        "tracks": {
            "video": ["V1"],
            "audio": ["A1"],
        },
        "video_source": {
            "path": os.path.abspath(video_path).replace("\\", "/"),
            "duration": video_duration,
            "width": width,
            "height": height,
            "fps": fps,
        },
        "audio_source": {
            "path": os.path.abspath(audio_path).replace("\\", "/") if audio_path else "",
            "duration": audio_duration,
            "bpm": bpm,
        },
        "music_structure": music_structure,
        "clips": segments,
        "narration": [],
        "music": [audio_segment] if audio_segment else [],
        "captions": [],
        "notes": [],
        "timeline_summary": {
            "total_clips": len(segments),
            "total_duration": round(timeline_end - timeline_start, 1),
            "coverage_start": timeline_start,
            "coverage_end": round(timeline_end, 1),
            "source_utilization": round(used_duration / video_duration, 3) if video_duration > 0 else 0,
            "emotional_tones": tones_used,
            "avg_highlight_score": round(
                sum(s.get("highlight_score", 0) for s in segments) / len(segments), 1
            ) if segments else 0,
        },
    }


def _fallback_music_structure(duration: float, bpm: float) -> dict:
    """音乐结构回退（复刻 app.py 的 _fallback_structure）"""
    return {
        "duration": duration,
        "bpm": bpm,
        "structure": [
            {"section": "intro", "start_time": 0, "end_time": duration * 0.15, "energy_level": 0.3},
            {"section": "verse", "start_time": duration * 0.15, "end_time": duration * 0.4, "energy_level": 0.5},
            {"section": "chorus", "start_time": duration * 0.4, "end_time": duration * 0.65, "energy_level": 0.8},
            {"section": "bridge", "start_time": duration * 0.65, "end_time": duration * 0.8, "energy_level": 0.45},
            {"section": "outro", "start_time": duration * 0.8, "end_time": duration, "energy_level": 0.25},
        ],
        "key_moments": [{"time": duration * 0.4, "label": "副歌", "energy": 0.8}],
        "overall_structure": "intro → verse → chorus → bridge → outro",
    }


def blueprint_to_display(blueprint: dict) -> dict:
    """
    将蓝图转换为前端友好的显示格式。
    用于时间线可视化和片段表格。
    """
    t_summary = blueprint.get("timeline_summary", {})
    clips = blueprint.get("clips", [])

    return {
        "editing_mode": blueprint.get("editing_mode", ""),
        "total_clips": t_summary.get("total_clips", 0),
        "total_duration": t_summary.get("total_duration", 0),
        "source_utilization": t_summary.get("source_utilization", 0),
        "avg_highlight_score": t_summary.get("avg_highlight_score", 0),
        "emotional_tones": t_summary.get("emotional_tones", {}),
        "clips": [
            {
                "id": c.get("id", ""),
                "timeline_in": c.get("timeline_in_seconds", 0),
                "timeline_out": c.get("timeline_out_seconds", 0),
                "duration": c.get("timeline_out_seconds", 0) - c.get("timeline_in_seconds", 0),
                "source_in": c.get("source_in_seconds", 0),
                "source_out": c.get("source_out_seconds", 0),
                "emotional_tone": c.get("emotional_tone", ""),
                "highlight_score": c.get("highlight_score", 0),
                "music_section": c.get("music_section", ""),
                "purpose": c.get("purpose", ""),
            }
            for c in clips
        ],
    }
