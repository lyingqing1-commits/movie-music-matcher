"""
蓝图验证器 — 在构建前验证剪辑蓝图
===================================
纯逻辑验证，无 AI 调用。
检查：时间线空隙、片段重叠、源边界违规、相邻重复源、不可用素材引用。

参照：DaVinci-AutoEdit-Agent skills/davinci-autoedit-agent/scripts/validate_blueprint.py
"""
import json
import os
from pathlib import Path
from collections import Counter


def validate_blueprint(blueprint: dict) -> dict:
    """
    验证剪辑蓝图的完整性和正确性。

    参数：
        blueprint: edit-blueprint.json 字典或文件路径

    返回：
        {
            errors: [{level: "error"|"warning", clip_id, message}],
            warnings: [...],
            stats: {clip_count, gaps_count, overlaps_count, ...},
            passed: bool,
        }
    """
    if isinstance(blueprint, (str, Path)):
        bp_path = Path(blueprint)
        if bp_path.exists():
            with open(bp_path, "r", encoding="utf-8") as f:
                blueprint = json.load(f)

    clips = blueprint.get("clips", [])
    errors = []
    warnings = []

    # ---- 检查 1: 基本结构 ----
    if not clips:
        errors.append({
            "level": "error",
            "clip_id": "blueprint",
            "message": "蓝图中没有片段",
        })
        return _build_report(blueprint, errors, warnings)

    if "schema_version" not in blueprint:
        warnings.append({
            "level": "warning",
            "clip_id": "blueprint",
            "message": "缺少 schema_version",
        })

    # ---- 检查 2: 每个片段的字段完整性 ----
    for i, clip in enumerate(clips):
        cid = clip.get("id", f"clip-{i}")

        # 必填字段
        for field in ["source_path", "source_in_seconds", "source_out_seconds",
                       "timeline_in_seconds", "timeline_out_seconds"]:
            if field not in clip:
                errors.append({
                    "level": "error",
                    "clip_id": cid,
                    "message": f"缺少必填字段: {field}",
                })

        # 源文件存在性
        source_path = clip.get("source_path", "")
        if source_path and not os.path.exists(source_path):
            errors.append({
                "level": "error",
                "clip_id": cid,
                "message": f"源文件不存在: {source_path}",
            })

        # 源时长有效性（正值）
        source_in = clip.get("source_in_seconds", 0)
        source_out = clip.get("source_out_seconds", 0)
        if source_out <= source_in:
            errors.append({
                "level": "error",
                "clip_id": cid,
                "message": f"源时长无效: in={source_in}, out={source_out}",
            })

        # 时间线时长有效性
        tl_in = clip.get("timeline_in_seconds", 0)
        tl_out = clip.get("timeline_out_seconds", 0)
        if tl_out <= tl_in:
            errors.append({
                "level": "error",
                "clip_id": cid,
                "message": f"时间线时长无效: in={tl_in}, out={tl_out}",
            })

        # 源/时间线时长一致性（公差 0.05s，除非声明变速）
        src_dur = source_out - source_in
        tl_dur = tl_out - tl_in
        if abs(src_dur - tl_dur) > 0.05 and not clip.get("speed"):
            warnings.append({
                "level": "warning",
                "clip_id": cid,
                "message": f"源/时间线时长不匹配（差 {abs(src_dur - tl_dur):.3f}s）且未声明变速",
            })

    # ---- 检查 3: 时间线连续性（空隙和重叠） ----
    # 按 timeline_in 排序
    sorted_clips = sorted(
        [c for c in clips if "timeline_in_seconds" in c],
        key=lambda c: c["timeline_in_seconds"],
    )

    for i in range(len(sorted_clips) - 1):
        curr = sorted_clips[i]
        next_clip = sorted_clips[i + 1]
        curr_id = curr.get("id", f"clip-{i}")
        next_id = next_clip.get("id", f"clip-{i+1}")

        curr_end = curr.get("timeline_out_seconds", 0)
        next_start = next_clip.get("timeline_in_seconds", 0)

        delta = next_start - curr_end

        if delta > 0.01:
            # 空隙
            warnings.append({
                "level": "warning",
                "clip_id": f"{curr_id} → {next_id}",
                "message": f"时间线空隙: {delta:.3f}s",
            })
        elif delta < -0.01:
            # 重叠
            warnings.append({
                "level": "warning",
                "clip_id": f"{curr_id} → {next_id}",
                "message": f"时间线重叠: {-delta:.3f}s",
            })

    # ---- 检查 4: 相邻重复源 ----
    prev_source = ""
    for i, clip in enumerate(sorted_clips):
        source = str(clip.get("source_path", ""))
        src_in = clip.get("source_in_seconds", 0)
        src_out = clip.get("source_out_seconds", 0)
        cid = clip.get("id", f"clip-{i}")

        if source and src_in is not None and prev_source:
            # 检查是否与上一片段使用相同源的相邻范围
            prev_clip = sorted_clips[i - 1] if i > 0 else None
            if prev_clip and prev_clip.get("source_path") == source:
                prev_out = prev_clip.get("source_out_seconds", 0)
                curr_in = clip.get("source_in_seconds", 0)
                if abs(curr_in - prev_out) < 0.02:
                    warnings.append({
                        "level": "warning",
                        "clip_id": cid,
                        "message": f"相邻片段使用相同源的相同区域（疑似重复切分）",
                    })

        prev_source = source

    # ---- 检查 5: 源素材覆盖率统计 ----
    # 按源文件分组
    source_groups = Counter()
    for clip in sorted_clips:
        group = clip.get("source_group", "unclassified")
        tl_out = clip.get("timeline_out_seconds", 0)
        tl_in = clip.get("timeline_in_seconds", 0)
        source_groups[group] += tl_out - tl_in

    # ---- 检查 6: 目标时长匹配 ----
    project = blueprint.get("project", {})
    target_duration = project.get("target_duration_seconds", 0)
    fps = project.get("fps", 30)
    if target_duration > 0 and sorted_clips:
        actual_end = sorted_clips[-1].get("timeline_out_seconds", 0)
        diff_pct = abs(actual_end - target_duration) / target_duration
        if diff_pct > 0.15:
            warnings.append({
                "level": "warning",
                "clip_id": "timeline",
                "message": f"实际时长 ({actual_end:.1f}s) 与目标时长 ({target_duration}s) 偏差 {diff_pct*100:.0f}%",
            })

    # ---- 检查 7: 源素材覆盖率统计 ----
    # 按源文件/源分组统计，任一可用源使用率为 0% 需要警告
    source_usage = {}
    for clip in sorted_clips:
        src = clip.get("source_path", "")
        if src:
            source_usage[src] = source_usage.get(src, 0) + (
                clip.get("timeline_out_seconds", 0) - clip.get("timeline_in_seconds", 0)
            )
    # 从项目中获取已知素材列表
    known_sources = blueprint.get("known_sources", [])
    for src in known_sources:
        if src not in source_usage:
            warnings.append({
                "level": "warning",
                "clip_id": "coverage",
                "message": f"素材 '{os.path.basename(src)}' 使用了 0%，需明确排除理由",
            })

    # ---- 检查 8: 图片片段时长声明 ----
    for i, clip in enumerate(clips):
        if clip.get("media_type") == "image":
            src_in = clip.get("source_in_seconds", 0)
            src_out = clip.get("source_out_seconds", 0)
            dur = src_out - src_in
            if dur < 0.5:
                warnings.append({
                    "level": "warning",
                    "clip_id": clip.get("id", f"clip-{i}"),
                    "message": f"图片片段时长过短 ({dur:.1f}s)，推荐至少 3-5 秒",
                })
            if "still_duration_declared" not in clip and dur <= 0:
                errors.append({
                    "level": "error",
                    "clip_id": clip.get("id", f"clip-{i}"),
                    "message": "图片片段未声明有效时长（source_out <= source_in）",
                })

    # ---- 检查 9: 轨道范围 ----
    tracks = blueprint.get("tracks", {})
    max_video_tracks = len(tracks.get("video", ["V1"]))
    max_audio_tracks = len(tracks.get("audio", ["A1"]))
    for i, clip in enumerate(clips):
        cid = clip.get("id", f"clip-{i}")
        v_track = clip.get("video_track", 1)
        a_track = clip.get("audio_track", 1)
        if v_track > max_video_tracks:
            errors.append({
                "level": "error",
                "clip_id": cid,
                "message": f"视频轨道 {v_track} 超出声明范围 (最多 {max_video_tracks})",
            })
        if a_track > max_audio_tracks:
            errors.append({
                "level": "error",
                "clip_id": cid,
                "message": f"音频轨道 {a_track} 超出声明范围 (最多 {max_audio_tracks})",
            })

    # ---- 检查 10: 帧精确边界检查 ----
    if fps > 0 and sorted_clips:
        frame_duration = 1.0 / fps
        for i in range(len(sorted_clips) - 1):
            curr = sorted_clips[i]
            next_clip = sorted_clips[i + 1]
            curr_end = curr.get("timeline_out_seconds", 0)
            next_start = next_clip.get("timeline_in_seconds", 0)
            delta = next_start - curr_end
            # 间隙超过 1 帧
            if delta > frame_duration + 0.001:
                warnings.append({
                    "level": "warning",
                    "clip_id": f"{curr.get('id', '?')} → {next_clip.get('id', '?')}",
                    "message": f"帧级间隙: {delta:.4f}s ({delta*fps:.1f} 帧 @ {fps}fps)",
                })
            # 重叠超过 1 帧
            elif delta < -frame_duration - 0.001:
                warnings.append({
                    "level": "warning",
                    "clip_id": f"{curr.get('id', '?')} → {next_clip.get('id', '?')}",
                    "message": f"帧级重叠: {-delta:.4f}s ({-delta*fps:.1f} 帧 @ {fps}fps)",
                })

    return _build_report(blueprint, errors, warnings, dict(source_groups))


def _build_report(blueprint: dict, errors: list, warnings: list,
                  source_groups: dict = None) -> dict:
    """组装验证报告"""
    clips = blueprint.get("clips", [])
    all_issues = errors + warnings
    error_count = sum(1 for e in errors if e.get("level") == "error")
    warning_count = sum(1 for w in warnings if w.get("level") == "warning")

    return {
        "schema_version": "1.0.0",
        "project_slug": blueprint.get("project_slug", ""),
        "clip_count": len(clips),
        "error_count": error_count,
        "warning_count": warning_count,
        "passed": error_count == 0,
        "issues": all_issues,
        "errors": errors,
        "warnings": warnings,
        "duration_by_source_group_seconds": source_groups or {},
        "summary": f"{len(clips)} 片段, {error_count} 错误, {warning_count} 警告 — {'✓ 通过' if error_count == 0 else '✗ 需要修复'}",
    }


def suggest_fixes(validation_report: dict, blueprint: dict) -> dict:
    """
    基于验证报告尝试自动修复蓝图。

    当前支持的修复：
    - 填补时间线空隙：拉伸前一片段或插入新片段
    - 移除无效片段

    返回：修复后的 blueprint 副本
    """
    import copy
    fixed = copy.deepcopy(blueprint)
    clips = fixed.get("clips", [])

    if not clips:
        return fixed

    sorted_clips = sorted(clips, key=lambda c: c.get("timeline_in_seconds", 0))
    fixed_clips = [sorted_clips[0]]

    for i in range(1, len(sorted_clips)):
        prev = fixed_clips[-1]
        curr = sorted_clips[i]

        prev_end = prev.get("timeline_out_seconds", 0)
        curr_start = curr.get("timeline_in_seconds", 0)

        delta = curr_start - prev_end

        if delta > 0.01:
            # 空隙：拉伸前一片段
            prev["timeline_out_seconds"] = curr_start
            prev_dur = prev.get("timeline_out_seconds", 0) - prev.get("timeline_in_seconds", 0)
            prev["source_out_seconds"] = prev.get("source_in_seconds", 0) + prev_dur
        elif delta < -0.01:
            # 重叠：将当前片段后移
            curr["timeline_in_seconds"] = prev_end
            curr["timeline_out_seconds"] = prev_end + (
                curr.get("timeline_out_seconds", curr_start) - curr_start
            )

        fixed_clips.append(curr)

    fixed["clips"] = fixed_clips
    return fixed
