"""
交付审计 + 补拍建议模块
=======================
构建完成后，审计实际生成的时间线。
对比：脚本/蓝图 vs. 实际成片 → 生成补拍报告。

参照：DaVinci-AutoEdit-Agent 的 audit delivery + pickup-shot report 阶段
"""
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from modules.workspace_manager import save_artifact


def audit_delivery(
    blueprint: dict,
    draft_info: dict,
    material_review: dict,
    story_script: dict = None,
    run_path: str = None,
) -> dict:
    """
    审计已生成的草稿，与蓝图和脚本对比。

    参数：
        blueprint: edit-blueprint.json
        draft_info: create_draft() 返回的 draft_info
        material_review: material-review.json
        story_script: story-script.json（可选）
        run_path: 运行目录路径

    返回：
        audit-report 字典
    """
    clips = blueprint.get("clips", [])
    t_summary = blueprint.get("timeline_summary", {})
    video_info = blueprint.get("video_source", {})
    audio_info = blueprint.get("audio_source", {})

    issues = []
    stats = {}

    # ---- 检查 1: 草稿是否成功生成 ----
    draft_folder = draft_info.get("draft_folder", "")
    draft_exists = os.path.isdir(draft_folder) if draft_folder else False

    if not draft_exists:
        issues.append({
            "level": "error",
            "category": "build",
            "message": f"草稿目录不存在: {draft_folder}",
        })

    # ---- 检查 2: 覆盖率计算 ----
    if clips:
        total_timeline = t_summary.get("total_duration", 0)
        total_source_used = sum(
            c.get("source_out_seconds", 0) - c.get("source_in_seconds", 0)
            for c in clips
        )
        video_duration = video_info.get("duration", 1)

        stats["timeline_coverage"] = round(total_timeline / max(
            blueprint.get("project", {}).get("target_duration_seconds", total_timeline), 1
        ), 2)

        stats["source_utilization"] = round(total_source_used / max(video_duration, 1), 2)

        if stats["source_utilization"] < 0.3:
            issues.append({
                "level": "warning",
                "category": "coverage",
                "message": f"源素材利用率低 ({stats['source_utilization']*100:.0f}%)，可能有较多未使用的好素材",
            })

    # ---- 检查 3: 情绪分布 ----
    emotional_tones = t_summary.get("emotional_tones", {})
    if emotional_tones:
        stats["emotional_distribution"] = emotional_tones
        dominating = max(emotional_tones, key=emotional_tones.get)
        dominating_pct = emotional_tones[dominating] / max(len(clips), 1)
        if dominating_pct > 0.7:
            issues.append({
                "level": "warning",
                "category": "diversity",
                "message": f"情绪分布过于集中 ({dominating}: {dominating_pct*100:.0f}%)，建议增加情绪多样性",
            })

    # ---- 检查 4: 高光分数分布 ----
    if clips:
        scores = [c.get("highlight_score", 0) for c in clips]
        stats["avg_highlight_score"] = round(sum(scores) / len(scores), 1)
        stats["min_highlight_score"] = min(scores)
        stats["max_highlight_score"] = max(scores)

        low_score_clips = [c for c in clips if c.get("highlight_score", 0) < 40]
        if len(low_score_clips) > len(clips) * 0.3:
            issues.append({
                "level": "warning",
                "category": "quality",
                "message": f"{len(low_score_clips)} 个片段评分较低 (<40)，可能影响成片质量",
            })

    # ---- 检查 5: 音乐同步 ----
    if not audio_info.get("path"):
        issues.append({
            "level": "info",
            "category": "audio",
            "message": "无音频源，纯视觉剪辑",
        })

    # ---- 检查 6: 草稿文件完整性 ----
    if draft_exists:
        draft_dir = Path(draft_folder)
        json_files = list(draft_dir.glob("*.json"))
        stats["draft_files_found"] = len(json_files)
        stats["draft_file_names"] = [f.name for f in json_files]

        # 检查关键文件
        required = ["draft_content.json", "draft_meta_info.json"]
        for req in required:
            if not (draft_dir / req).exists():
                issues.append({
                    "level": "error",
                    "category": "build",
                    "message": f"缺少关键草稿文件: {req}",
                })

    # ---- 检查 7: 剪映目录同步 ----
    capcut_path = draft_info.get("capcut_draft_path")
    if capcut_path:
        if os.path.exists(capcut_path):
            stats["capcut_sync"] = "success"
        else:
            stats["capcut_sync"] = "failed"
            issues.append({
                "level": "warning",
                "category": "export",
                "message": "草稿未成功同步到剪映目录",
            })
    else:
        stats["capcut_sync"] = "skipped"

    # ---- 检查 8: 帧级间隙/重叠检测 + 邻近重复源检测 ----
    project_fps = blueprint.get("project", {}).get("fps", 30)
    sorted_by_timeline = sorted(
        [c for c in clips if "timeline_in_seconds" in c and "timeline_out_seconds" in c],
        key=lambda c: c["timeline_in_seconds"],
    ) if clips else []
    if clips and project_fps > 0:
        frame_dur = 1.0 / project_fps
        gap_count = 0
        overlap_count = 0
        for i in range(len(sorted_by_timeline) - 1):
            curr_end = sorted_by_timeline[i]["timeline_out_seconds"]
            next_start = sorted_by_timeline[i + 1]["timeline_in_seconds"]
            delta = next_start - curr_end
            if delta > frame_dur + 0.001:
                gap_count += 1
            elif delta < -frame_dur - 0.001:
                overlap_count += 1
        stats["frame_gaps"] = gap_count
        stats["frame_overlaps"] = overlap_count
        if gap_count > 0:
            issues.append({
                "level": "warning",
                "category": "timeline",
                "message": f"发现 {gap_count} 处帧级间隙（>{project_fps}fps 帧率下 1 帧）",
            })
        if overlap_count > 0:
            issues.append({
                "level": "warning",
                "category": "timeline",
                "message": f"发现 {overlap_count} 处帧级重叠",
            })

    # ---- 检查 9: 邻近段落边界的重复源检测 ----
    if sorted_by_timeline and len(sorted_by_timeline) >= 2:
        adjacent_repeats = 0
        for i in range(len(sorted_by_timeline) - 1):
            curr = sorted_by_timeline[i]
            next_c = sorted_by_timeline[i + 1]
            if (curr.get("source_path") == next_c.get("source_path") and
                abs(curr.get("source_out_seconds", 0) - next_c.get("source_in_seconds", 0)) < 0.05):
                adjacent_repeats += 1
        stats["adjacent_source_repeats"] = adjacent_repeats
        if adjacent_repeats > 0:
            issues.append({
                "level": "warning",
                "category": "editing",
                "message": f"发现 {adjacent_repeats} 处相邻重复源 — 检查是否是'伪切'",
            })

    # 构建审计报告
    report = {
        "schema_version": "1.0.0",
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "project_slug": blueprint.get("project_slug", ""),
        "issues": issues,
        "stats": stats,
        "error_count": sum(1 for i in issues if i["level"] == "error"),
        "warning_count": sum(1 for i in issues if i["level"] == "warning"),
        "passed": sum(1 for i in issues if i["level"] == "error") == 0,
        "summary": _generate_audit_summary(issues, stats),
    }

    if run_path:
        save_artifact(run_path, "audit-report", report)

    return report


def _generate_audit_summary(issues: list, stats: dict) -> str:
    """生成审计摘要文本"""
    errors = [i for i in issues if i["level"] == "error"]
    warnings = [i for i in issues if i["level"] == "warning"]
    infos = [i for i in issues if i["level"] == "info"]

    parts = []
    if errors:
        parts.append(f"{len(errors)} 个错误")
    if warnings:
        parts.append(f"{len(warnings)} 个警告")
    if infos:
        parts.append(f"{len(infos)} 个提示")

    if not parts:
        return "✅ 审计通过，无问题"

    return "⚠️ " + "，".join(parts)


def generate_pickup_report(
    blueprint: dict,
    material_review: dict,
    story_script: dict = None,
    run_path: str = None,
) -> dict:
    """
    生成补拍建议报告。
    对比脚本/蓝图需求 vs 素材库实际内容，识别缺失素材。

    参照：DaVinci-AutoEdit-Agent 的 pickup-shot report 阶段

    返回：
        {
            p0_required: [{script_ref, timeline_timecode, missing_info, shot_spec, ...}],
            p1_recommended: [...],
            p2_optional: [...],
        }
    """
    clips = blueprint.get("clips", [])
    taxonomy = material_review.get("taxonomy", {})
    style = material_review.get("style_analysis", {})
    video_duration = material_review.get("video_info", {}).get("duration", 0)

    p0_required = []
    p1_recommended = []
    p2_optional = []

    # ---- P0 检查: 基本必需素材 ----

    # 情绪覆盖检查
    emotional_range = taxonomy.get("emotion", {}).get("emotional_range", [])
    used_tones = set(c.get("emotional_tone", "") for c in clips)

    for emotion in emotional_range:
        if emotion not in used_tones:
            p0_required.append({
                "priority": "P0",
                "related_script": f"需要{emotion}情绪的画面",
                "timeline_timecode": "全片",
                "missing_info": f"缺少{emotion}情绪的镜头",
                "shot_spec": {
                    "subject": f"能够表达{emotion}情绪的镜头",
                    "action": f"{emotion}情绪场景",
                    "framing": "中景/近景",
                    "duration_seconds": 5,
                    "location": "视素材而定",
                },
                "evidence_no_existing": f"素材中未找到{emotion}情绪标签的片段",
                "reshooting_needed": True,
                "alternative": "使用现有素材通过调色/变速/裁剪模拟该情绪",
            })

    # 动作覆盖检查
    action_intensity = taxonomy.get("action", {}).get("action_intensity", "")
    has_high_action = any(c.get("highlight_score", 0) > 80 for c in clips)
    if action_intensity == "high" and not has_high_action:
        p1_recommended.append({
            "priority": "P1",
            "related_script": "高潮段落需要高能动作素材",
            "timeline_timecode": "中后段",
            "missing_info": "缺少高光动作镜头（评分 >80）",
            "shot_spec": {
                "subject": "高能动作场景",
                "action": "激烈动作/对战/追逐",
                "framing": "广角/特写交替",
                "duration_seconds": 15,
            },
            "evidence_no_existing": "片段的最高分" + str(max((c.get("highlight_score", 0) for c in clips), default=0)),
            "reshooting_needed": False,
            "alternative": "使用现有中高分片段通过加速/特效增强动作感",
        })

    # 开场/收尾检查
    first_clip = clips[0] if clips else {}
    last_clip = clips[-1] if clips else {}

    if not first_clip.get("emotional_tone") in ("establishing", "calm", "mystery", "atmosphere"):
        p2_optional.append({
            "priority": "P2",
            "related_script": "开场段落",
            "timeline_timecode": "00:00",
            "missing_info": "开场片段的情绪建立感较弱",
            "shot_spec": {
                "subject": "建立氛围的开场镜头",
                "action": "环境/场景建立",
                "framing": "广角/全景",
                "duration_seconds": 10,
            },
            "evidence_no_existing": f"开场使用{first_clip.get('emotional_tone', 'unknown')}情绪",
            "reshooting_needed": False,
            "alternative": "在现有素材中寻找或使用定场镜头",
        })

    if not last_clip.get("emotional_tone") in ("resolution", "reflection", "calm", "melancholy"):
        p2_optional.append({
            "priority": "P2",
            "related_script": "结尾段落",
            "timeline_timecode": "片尾",
            "missing_info": "结尾缺少余韵感",
            "shot_spec": {
                "subject": "提供余韵的结束镜头",
                "action": "淡出/收束",
                "framing": "远景/长镜头",
                "duration_seconds": 8,
            },
            "evidence_no_existing": f"结尾使用{last_clip.get('emotional_tone', 'unknown')}情绪",
            "reshooting_needed": False,
            "alternative": "使用黑场/淡出转场或文字标题收尾",
        })

    # 如有故事脚本，对比节拍覆盖
    if story_script:
        beats = story_script.get("scene_beats", [])
        for beat in beats:
            beat_name = beat.get("beat_name", "")
            beat_emotion = beat.get("emotion", "")
            beat_pct = beat.get("start_pct", 0)

            # 检查该节拍是否有对应的片段素材
            covered = any(
                c.get("emotional_tone", "") == beat_emotion
                for c in clips
            )
            if not covered and beat_emotion not in ("establishing", "neutral"):
                p0_required.append({
                    "priority": "P0",
                    "related_script": f"节拍: {beat_name} ({beat_emotion})",
                    "timeline_timecode": f"{beat_pct * video_duration:.0f}s",
                    "missing_info": f"缺少{beat_emotion}情绪的画面来覆盖 '{beat_name}' 节拍",
                    "shot_spec": {
                        "subject": beat.get("description", beat_name),
                        "action": beat_emotion,
                        "framing": "中景",
                        "duration_seconds": 5,
                    },
                    "evidence_no_existing": f"素材库中无{beat_emotion}标签片段",
                    "reshooting_needed": True,
                    "alternative": f"脚本删除此节拍或使用{beat.get('description', '其他素材')}替代",
                })

    # 如果没有必要补拍，明确说明
    if not p0_required:
        p0_required = [{
            "priority": "P0",
            "related_script": "N/A",
            "timeline_timecode": "N/A",
            "missing_info": "无需必要补拍素材",
            "shot_spec": {},
            "evidence_no_existing": "当前素材库已覆盖所有叙事需求",
            "reshooting_needed": False,
            "alternative": "",
        }]

    report = {
        "schema_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_slug": blueprint.get("project_slug", ""),
        "p0_required": p0_required,
        "p1_recommended": p1_recommended,
        "p2_optional": p2_optional,
        "total_recommendations": {
            "p0": len(p0_required),
            "p1": len(p1_recommended),
            "p2": len(p2_optional),
        },
    }

    if run_path:
        save_artifact(run_path, "pickup-report", report)

    return report


def pickup_to_display(report: dict) -> dict:
    """将补拍报告转换为前端友好格式"""
    return {
        "p0_count": report.get("total_recommendations", {}).get("p0", 0),
        "p1_count": report.get("total_recommendations", {}).get("p1", 0),
        "p2_count": report.get("total_recommendations", {}).get("p2", 0),
        "p0_items": report.get("p0_required", [])[:5],
        "p1_items": report.get("p1_recommended", [])[:5],
        "p2_items": report.get("p2_optional", [])[:5],
    }
