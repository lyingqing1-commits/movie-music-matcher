"""
智能剪辑引擎 — "拼水果盘"而非"切蛋糕"
======================================
这是整个应用最核心的模块。实现了两种剪辑策略：

1. **视频优先 (video_first)**：
   - 按 highlight_score 降序排列所有视频片段
   - 将最高分片段分配到音乐最重要的段落（drop > chorus > bridge > verse > intro）
   - 确保视频的"爽点""爆点"出现在音乐最激昂的时刻
   - 适合：动作混剪、高光合集、预告片

2. **音乐优先 (music_first)**：
   - 按 emotional_tone 将视频片段分组
   - 为每个音乐段落匹配情感基调最合适的视频片段
   - 视频剪辑服务于音乐结构，营造 MV 感
   - 适合：MV、情感短片、叙事性剪辑

输出格式与 _compute_beat_segments() 完全兼容，
可直接作为 create_draft() 的 smart_segments 参数。
"""
import random
from typing import Optional


def assemble_smart_draft(
    scored_segments: list[dict],
    music_structure: dict,
    video_info: dict,
    editing_mode: str = "video_first",
) -> list[dict]:
    """
    智能匹配：将视频片段分配到音乐段落中的最佳位置。

    参数：
        scored_segments: 经 segment_scorer 评分后的视频片段
            [{start_time, end_time, duration, highlight_score,
              emotional_tone, suggested_use, visual_quality, description}, ...]
        music_structure: 经 music_structure_analyzer 分析的音乐结构
            {duration, bpm, structure: [{section, start_time, end_time,
              duration, energy_level, character}], key_moments, ...}
        video_info: 视频元数据 {duration, width, height, fps}
        editing_mode: "video_first" | "music_first"

    返回：
        [{source_start, source_duration, target_start, music_section,
          match_rationale, segment_score, emotional_tone}, ...]
        格式与 _compute_beat_segments() 完全兼容
    """
    if not scored_segments or not music_structure:
        return []

    music_sections = music_structure.get("structure", [])
    if not music_sections:
        return []

    video_duration = video_info.get("duration", 60)
    music_duration = music_structure.get("duration", 60)

    mode_label = "Video First" if editing_mode == "video_first" else "Music First"
    print(f"\n[SmartEditor] Mode: {mode_label}")
    print(f"   Video clips: {len(scored_segments)}, Music sections: {len(music_sections)}")
    print(f"   Video dur: {video_duration:.1f}s, Music dur: {music_duration:.1f}s")

    if editing_mode == "music_first":
        placements = _assemble_music_first(scored_segments, music_sections, video_duration, music_duration)
    else:
        placements = _assemble_video_first(scored_segments, music_sections, video_duration, music_duration)

    # 后处理：确保 target_start 连续且覆盖完整音乐时长，添加转场间隙
    placements = _post_process_placements(placements, music_duration)

    # 统计摘要
    sections_used = set(p.get("music_section", "") for p in placements)
    avg_score = sum(p.get("segment_score", 0) for p in placements) / max(len(placements), 1)
    print(f"   Generated {len(placements)} placements (covers {len(sections_used)} music sections, avg highlight {avg_score:.0f})")
    for p in placements[:5]:
        print(f"      src {p['source_start']:.1f}s->{p['source_start']+p['source_duration']:.1f}s "
              f"-> t={p['target_start']:.1f}s [{p.get('music_section', '?')}] "
              f"[{p.get('match_rationale', '')}]")

    return placements


# ============================================
# 视频优先模式
# ============================================

# 音乐段落在视频优先模式下的重要性权重
# 高权重段落会优先获得高光片段
SECTION_IMPORTANCE = {
    "drop": 10,
    "final_chorus": 9,
    "climax": 9,
    "chorus": 8,
    "buildup": 7,
    "pre_chorus": 6,
    "bridge": 5,
    "verse": 4,
    "breakdown": 3,
    "interlude": 2,
    "intro": 2,
    "outro": 1,
}

# 视频片段 suggested_use → 音乐段落的最佳映射（用于 tie-breaking）
USE_TO_SECTION = {
    "drop":    ["drop", "climax", "final_chorus", "chorus"],
    "chorus":  ["chorus", "final_chorus", "climax", "drop"],
    "bridge":  ["bridge", "breakdown", "interlude", "pre_chorus"],
    "intro":   ["intro", "buildup", "pre_chorus"],
    "outro":   ["outro", "breakdown", "bridge"],
    "verse":   ["verse", "bridge", "pre_chorus"],
}


def _assemble_video_first(
    segments: list[dict],
    music_sections: list[dict],
    video_duration: float,
    music_duration: float,
) -> list[dict]:
    """
    视频优先算法 (v2.1)：
    1. 按 highlight_score 排序所有片段
    2. 音乐段落按重要性排序
    3. 贪心匹配：最高分片段 → 最重要段落
    4. 同时考虑片段的 suggested_use 与音乐段落的匹配度，打破同分平局
    5. 素材用尽时循环最佳片段
    """
    if not segments:
        return []

    # 构建 seg_id → index 的快速查找表，避免 O(n²) 的 segments.index()
    seg_id_to_idx = {id(seg): i for i, seg in enumerate(segments)}

    # 排序：highlight_score 降序
    ranked = sorted(segments, key=lambda s: s.get("highlight_score", 0), reverse=True)
    if not ranked:
        return []

    # 音乐段落按重要性排序的索引
    section_order = sorted(
        range(len(music_sections)),
        key=lambda i: SECTION_IMPORTANCE.get(
            music_sections[i].get("section", ""), 2
        ),
        reverse=True,
    )

    # 跟踪每个片段的已使用时长（秒）
    used_from_segment = {i: 0.0 for i in range(len(segments))}

    placements = []
    ranked_idx = 0  # 当前使用的排名位置

    for section_idx in section_order:
        music_sec = music_sections[section_idx]
        section_start = music_sec["start_time"]
        section_end = music_sec["end_time"]
        section_dur = section_end - section_start
        section_name = music_sec.get("section", "unknown")
        section_energy = music_sec.get("energy_level", 0.5)
        remaining = section_dur

        # 候选片段：在当前未用完的排名片段中，优先匹配 suggested_use
        candidates = []
        for ri in range(ranked_idx, len(ranked)):
            seg = ranked[ri]
            seg_idx = seg_id_to_idx[id(seg)]
            available = seg["duration"] - used_from_segment.get(seg_idx, 0)
            if available < 0.3:
                continue

            # 计算匹配加分：suggested_use 匹配该音乐段落类型
            suggested = seg.get("suggested_use", "verse")
            preferred_sections = USE_TO_SECTION.get(suggested, ["verse"])
            match_bonus = 15 if section_name in preferred_sections else 0

            candidates.append({
                "ri": ri,
                "seg": seg,
                "seg_idx": seg_idx,
                "available": available,
                "score": seg.get("highlight_score", 50) + match_bonus,
                "match_bonus": match_bonus,
            })

        # 按综合分数排序
        candidates.sort(key=lambda c: c["score"], reverse=True)

        clips_for_section = []
        for cand in candidates:
            if remaining <= 0.3:
                break

            seg_idx = cand["seg_idx"]
            seg = cand["seg"]
            take = min(cand["available"], remaining)

            # 从已使用偏移量开始取
            offset = used_from_segment.get(seg_idx, 0)
            clips_for_section.append({
                "source_start": seg["start_time"] + offset,
                "source_duration": round(take, 2),
                "segment_score": seg.get("highlight_score", 50),
                "emotional_tone": seg.get("emotional_tone", ""),
                "suggested_use": seg.get("suggested_use", ""),
                "segment_idx": seg_idx,
                "visual_quality": seg.get("visual_quality", "medium"),
            })

            used_from_segment[seg_idx] = offset + take
            remaining -= take

            # 如果该片段已用完，将 ranked_idx 向前推进
            if used_from_segment[seg_idx] >= seg["duration"] - 0.1:
                if ranked_idx <= cand["ri"]:
                    ranked_idx = cand["ri"] + 1

        # 如果该段落未填满，循环使用最高分片段
        loop_count = 0
        while remaining > 0.3 and loop_count < 100:
            loop_count += 1
            best_seg = ranked[0]  # 最高分片段
            seg_idx = seg_id_to_idx[id(best_seg)]

            source_start = best_seg["start_time"]
            take = min(best_seg["duration"], remaining)

            clips_for_section.append({
                "source_start": source_start,
                "source_duration": round(take, 2),
                "segment_score": best_seg.get("highlight_score", 50),
                "emotional_tone": best_seg.get("emotional_tone", ""),
                "suggested_use": best_seg.get("suggested_use", ""),
                "segment_idx": seg_idx,
                "is_loop": True,
            })

            remaining -= take

        # 将片段放置在时间轴上
        current_target = section_start
        for clip in clips_for_section:
            placement = {
                "source_start": clip["source_start"],
                "source_duration": clip["source_duration"],
                "target_start": round(current_target, 2),
                "music_section": section_name,
                "section_energy": round(section_energy, 2),
                "segment_score": clip.get("segment_score", 50),
                "emotional_tone": clip.get("emotional_tone", ""),
                "match_rationale": (
                    f"[VF] Score#{clip.get('segment_score', 0)} -> {section_name}"
                    + (f" (suggested_use匹配)" if clip.get("match_bonus") else "")
                    + (" [循环]" if clip.get("is_loop") else "")
                ),
            }
            placements.append(placement)
            current_target += clip["source_duration"] + 0.02

    return placements


# ============================================
# 音乐优先模式
# ============================================

# 音乐段落到所需情绪的映射（按优先级排序）
SECTION_TONE_MAP = {
    "intro":        ["establishing", "calm", "mystery", "ambient", "dialogue"],
    "verse":        ["dialogue", "narrative", "calm", "emotional", "building"],
    "pre_chorus":   ["building", "tension", "anticipation", "emotional"],
    "chorus":       ["action", "emotional", "triumph", "climax", "high_energy"],
    "final_chorus": ["climax", "triumph", "action", "emotional", "high_energy"],
    "drop":         ["climax", "action", "triumph", "high_energy", "tension"],
    "bridge":       ["emotional", "reflective", "melancholy", "calm", "dialogue"],
    "breakdown":    ["calm", "minimal", "melancholy", "reflective"],
    "buildup":      ["building", "tension", "anticipation", "action"],
    "outro":        ["melancholy", "calm", "establishing", "resolution", "reflective"],
    "interlude":    ["mystery", "calm", "ambient", "establishing"],
    "climax":       ["climax", "triumph", "action", "emotional", "high_energy"],
}

# 情绪兼容映射：当某个 tone 池为空时，可从兼容 tone 借用
TONE_COMPATIBILITY = {
    "climax":       ["action", "triumph", "emotional", "tension"],
    "action":       ["climax", "triumph", "tension", "high_energy"],
    "triumph":      ["climax", "action", "emotional"],
    "emotional":    ["melancholy", "triumph", "reflective", "climax"],
    "tension":      ["action", "building", "anticipation"],
    "building":     ["tension", "anticipation", "action"],
    "anticipation": ["building", "tension", "mystery"],
    "calm":         ["dialogue", "establishing", "ambient", "reflective"],
    "dialogue":     ["calm", "narrative", "establishing"],
    "narrative":    ["dialogue", "calm", "emotional"],
    "melancholy":   ["emotional", "reflective", "calm", "resolution"],
    "reflective":   ["melancholy", "emotional", "calm"],
    "mystery":      ["tension", "anticipation", "ambient"],
    "ambient":      ["calm", "mystery", "establishing"],
    "establishing": ["calm", "ambient", "dialogue"],
    "high_energy":  ["action", "climax", "triumph", "tension"],
    "resolution":   ["melancholy", "calm", "reflective"],
    "minimal":      ["calm", "ambient"],
}


def _assemble_music_first(
    segments: list[dict],
    music_sections: list[dict],
    video_duration: float,
    music_duration: float,
) -> list[dict]:
    """
    音乐优先算法 (v2.1)：
    1. 按 emotional_tone 将视频片段分组
    2. 每个音乐段落从匹配的情绪池中选取最佳片段
    3. 优先保证情绪匹配，其次考虑 highlight_score
    4. 空池回退：从兼容情绪池借用
    5. 保持片段在时间轴上的连续性
    """
    seg_id_to_idx = {id(seg): i for i, seg in enumerate(segments)}

    # 按 emotional_tone 分组
    tone_pools: dict[str, list] = {}
    for i, seg in enumerate(segments):
        tone = seg.get("emotional_tone", "calm")
        if tone not in tone_pools:
            tone_pools[tone] = []
        tone_pools[tone].append({
            "index": i,
            "segment": seg,
            "used_offset": 0.0,  # 已使用的起始偏移
        })

    # 每个池按 highlight_score 降序排列
    for tone in tone_pools:
        tone_pools[tone].sort(
            key=lambda x: x["segment"].get("highlight_score", 0),
            reverse=True,
        )

    placements = []

    for music_sec in music_sections:
        section_name = music_sec.get("section", "verse")
        section_start = music_sec["start_time"]
        section_end = music_sec["end_time"]
        section_dur = section_end - section_start
        energy = music_sec.get("energy_level", 0.5)

        # 该段落需要的情绪类型（按优先级）
        target_tones = SECTION_TONE_MAP.get(section_name, ["action", "emotional", "calm"])

        remaining = section_dur
        current_target = section_start

        # 从匹配的情绪池中收集可用片段
        candidates = []
        for tone_priority, tone in enumerate(target_tones):
            pool = tone_pools.get(tone, [])
            # 如果主池为空，尝试从兼容池借用
            if not pool:
                compat_tones = TONE_COMPATIBILITY.get(tone, [])
                borrowed_from = None
                for ct in compat_tones:
                    if ct in tone_pools and tone_pools[ct]:
                        pool = tone_pools[ct]
                        borrowed_from = ct
                        break

            for entry in pool:
                seg = entry["segment"]
                available = seg["duration"] - entry["used_offset"]
                if available >= 0.3:
                    # 综合评分：情绪匹配度（高位优先）+ 高光度 + 能量匹配
                    tone_score = (len(target_tones) - tone_priority) * 20  # 0-180
                    energy_match = 1.0 - abs(seg.get("energy_level", 0.5) - energy)
                    energy_bonus = int(energy_match * 15)  # 0-15
                    highlight = seg.get("highlight_score", 50)

                    combined_score = tone_score + highlight + energy_bonus

                    candidates.append({
                        "entry": entry,
                        "tone": tone,
                        "combined_score": combined_score,
                        "available": available,
                    })

        # 按综合评分排序
        candidates.sort(key=lambda c: c["combined_score"], reverse=True)

        for cand in candidates:
            if remaining <= 0.3:
                break

            entry = cand["entry"]
            seg = entry["segment"]
            take = min(cand["available"], remaining)

            placement = {
                "source_start": seg["start_time"] + entry["used_offset"],
                "source_duration": round(take, 2),
                "target_start": round(current_target, 2),
                "music_section": section_name,
                "section_energy": round(energy, 2),
                "segment_score": seg.get("highlight_score", 50),
                "emotional_tone": seg.get("emotional_tone", ""),
                "match_rationale": (
                    f"[MF] '{seg.get('emotional_tone', '?')}'->{section_name} "
                    f"(高光{seg.get('highlight_score', 0)}分, 能量匹配{energy:.1f})"
                ),
            }
            placements.append(placement)

            entry["used_offset"] += take
            remaining -= take
            current_target += take + 0.02

        # 如果该段落未填满，用最高分片段补齐（跨池借用）
        if remaining > 0.3:
            all_entries = []
            for tone, pool in tone_pools.items():
                for entry in pool:
                    seg = entry["segment"]
                    available = seg["duration"] - entry["used_offset"]
                    if available >= 0.3:
                        all_entries.append((entry, available, tone))

            all_entries.sort(
                key=lambda x: x[0]["segment"].get("highlight_score", 0),
                reverse=True,
            )

            for entry, available, tone in all_entries:
                if remaining <= 0.3:
                    break
                seg = entry["segment"]
                take = min(available, remaining)

                placement = {
                    "source_start": seg["start_time"] + entry["used_offset"],
                    "source_duration": round(take, 2),
                    "target_start": round(current_target, 2),
                    "music_section": section_name,
                    "section_energy": round(energy, 2),
                    "segment_score": seg.get("highlight_score", 50),
                    "emotional_tone": seg.get("emotional_tone", ""),
                    "match_rationale": (
                        f"[MF-fill] '{seg.get('emotional_tone', '?')}'->{section_name} "
                        f"(高光{seg.get('highlight_score', 0)}分)"
                    ),
                }
                placements.append(placement)

                entry["used_offset"] += take
                remaining -= take
                current_target += take + 0.02

        # 仍然未填满：循环使用最佳匹配
        if remaining > 0.3:
            _fill_with_loops(placements, segments, remaining, current_target,
                           section_name, energy, seg_id_to_idx)

    return placements


def _fill_with_loops(
    placements: list[dict],
    segments: list[dict],
    remaining: float,
    current_target: float,
    section_name: str,
    section_energy: float,
    seg_id_to_idx: dict,
):
    """用循环视频片段填充未覆盖的音乐时长"""
    if not segments:
        return

    best = max(segments, key=lambda s: s.get("highlight_score", 0))
    loop_count = 0

    while remaining > 0.3 and loop_count < 50:
        loop_count += 1
        take = min(best["duration"], remaining)
        placement = {
            "source_start": best["start_time"],
            "source_duration": round(take, 2),
            "target_start": round(current_target, 2),
            "music_section": section_name,
            "section_energy": round(section_energy, 2),
            "segment_score": best.get("highlight_score", 50),
            "emotional_tone": best.get("emotional_tone", ""),
            "match_rationale": f"[Loop] Fill->{section_name} (score {best.get('highlight_score', 0)})",
        }
        placements.append(placement)
        remaining -= take
        current_target += take + 0.02


# ============================================
# 后处理
# ============================================

def _post_process_placements(
    placements: list[dict],
    music_duration: float,
) -> list[dict]:
    """
    后处理放置计划：
    1. 按 target_start 排序
    2. 确保连续无空隙（间隙 ≤ 0.1s）
    3. 微调最后一段以精确匹配音乐时长
    4. 移除过短的碎片 (< 0.3s)
    5. 相邻同源片段合并
    """
    if not placements:
        return []

    # 排序
    placements.sort(key=lambda p: p["target_start"])

    # 过滤过短的片段
    filtered = [p for p in placements if p["source_duration"] >= 0.3]

    if not filtered:
        return placements

    # 修复 target_start 的连续性
    for i in range(1, len(filtered)):
        expected = filtered[i - 1]["target_start"] + filtered[i - 1]["source_duration"] + 0.02
        if abs(filtered[i]["target_start"] - expected) > 0.5:
            filtered[i]["target_start"] = round(expected, 2)

    # 合并相邻同源片段（同一 source_start 且相邻）
    merged = [filtered[0]]
    for i in range(1, len(filtered)):
        prev = merged[-1]
        curr = filtered[i]
        # 如果 source_start 相同且 emotional_tone 相同，合并
        if (abs(curr["source_start"] - prev["source_start"]) < 0.05 and
            curr.get("emotional_tone") == prev.get("emotional_tone") and
            abs(curr["target_start"] - (prev["target_start"] + prev["source_duration"])) < 0.1):
            # 合并：延长前一个的 source_duration
            prev["source_duration"] = round(prev["source_duration"] + curr["source_duration"], 2)
            prev["match_rationale"] += " +" + curr.get("match_rationale", "")
            continue
        merged.append(curr)
    filtered = merged

    # 如果超出音乐时长，裁剪最后一段
    last_target_end = filtered[-1]["target_start"] + filtered[-1]["source_duration"]
    if last_target_end > music_duration + 0.5:
        excess = last_target_end - music_duration
        if filtered[-1]["source_duration"] > excess + 0.3:
            filtered[-1]["source_duration"] = round(filtered[-1]["source_duration"] - excess, 2)

    # 如果未覆盖完整音乐时长，循环填充
    final_end = filtered[-1]["target_start"] + filtered[-1]["source_duration"]
    if final_end < music_duration - 0.5:
        best_clip = max(filtered, key=lambda p: p.get("segment_score", 0))
        if not best_clip:
            best_clip = filtered[0]

        remaining = music_duration - final_end
        current_target = final_end + 0.02

        loop_count = 0
        while remaining > 0.5 and loop_count < 50:
            loop_count += 1
            take = min(best_clip["source_duration"], remaining)
            filtered.append({
                "source_start": best_clip["source_start"],
                "source_duration": round(take, 2),
                "target_start": round(current_target, 2),
                "music_section": best_clip.get("music_section", "outro"),
                "section_energy": best_clip.get("section_energy", 0.2),
                "segment_score": best_clip.get("segment_score", 50),
                "emotional_tone": best_clip.get("emotional_tone", ""),
                "match_rationale": "[Loop] Tail fill (best clip)",
            })
            remaining -= take
            current_target += take + 0.02

    return filtered
