"""
智能剪辑引擎 — "拼水果盘"而非"切蛋糕"
======================================
这是整个应用最核心的模块。实现了两种剪辑策略：

1. **视频优先 (video_first)**：
   - 按 highlight_score 降序排列所有视频片段
   - 将最高分片段分配到音乐最重要的段落（drop > chorus > bridge > verse > intro）
   - 确保视频的"爽点""爆点"出现在音乐最激昂的时刻

2. **音乐优先 (music_first)**：
   - 按 emotional_tone 将视频片段分组
   - 为每个音乐段落匹配情感基调最合适的视频片段
   - 视频剪辑服务于音乐结构，营造 MV 感

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
        [{source_start, source_duration, target_start}, ...]
        格式与 _compute_beat_segments() 完全兼容
    """
    if not scored_segments or not music_structure:
        return []

    music_sections = music_structure.get("structure", [])
    if not music_sections:
        return []

    video_duration = video_info.get("duration", 60)
    music_duration = music_structure.get("duration", 60)

    print(f"\n🎬 智能剪辑引擎启动 (模式: {editing_mode})")
    print(f"   视频片段: {len(scored_segments)} 个, 音乐段落: {len(music_sections)} 个")
    print(f"   视频时长: {video_duration:.1f}s, 音乐时长: {music_duration:.1f}s")

    if editing_mode == "music_first":
        placements = _assemble_music_first(scored_segments, music_sections, video_duration, music_duration)
    else:
        placements = _assemble_video_first(scored_segments, music_sections, video_duration, music_duration)

    # 后处理：确保 target_start 连续且覆盖完整音乐时长
    placements = _post_process_placements(placements, music_duration)

    print(f"   ✅ 生成 {len(placements)} 个放置计划")
    sample_placements = placements[:5]
    for p in sample_placements:
        print(f"      视频 {p['source_start']:.1f}s→{p['source_start']+p['source_duration']:.1f}s "
              f"→ 时间轴 {p['target_start']:.1f}s "
              f"[{p.get('match_rationale', '')}]")

    return placements


# ============================================
# 视频优先模式
# ============================================

# 音乐段落在视频优先模式下的重要性权重
SECTION_IMPORTANCE = {
    "drop": 10,
    "final_chorus": 9,
    "climax": 9,
    "chorus": 8,
    "buildup": 6,
    "bridge": 5,
    "pre_chorus": 5,
    "verse": 3,
    "breakdown": 3,
    "interlude": 2,
    "intro": 2,
    "outro": 1,
}


def _assemble_video_first(
    segments: list[dict],
    music_sections: list[dict],
    video_duration: float,
    music_duration: float,
) -> list[dict]:
    """
    视频优先算法：
    1. 按 highlight_score 排序所有片段
    2. 音乐段落按重要性排序
    3. 贪心匹配：最高分片段 → 最重要段落
    4. 素材用尽时循环最佳片段
    """
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
        remaining = section_dur

        # 为该段落分配片段
        clips_for_section = []

        while remaining > 0.3 and ranked_idx < len(ranked):
            seg = ranked[ranked_idx]
            # 找到该片段在原始列表中的索引
            seg_idx = segments.index(seg)

            available = seg["duration"] - used_from_segment.get(seg_idx, 0)
            if available < 0.3:
                ranked_idx += 1
                continue

            take = min(available, remaining)

            clips_for_section.append({
                "source_start": seg["start_time"] + used_from_segment.get(seg_idx, 0),
                "source_duration": round(take, 2),
                "segment_score": seg.get("highlight_score", 50),
                "emotional_tone": seg.get("emotional_tone", ""),
                "segment_idx": seg_idx,
            })

            used_from_segment[seg_idx] = used_from_segment.get(seg_idx, 0) + take
            remaining -= take

            if used_from_segment[seg_idx] >= seg["duration"] - 0.1:
                ranked_idx += 1

        # 如果该段落未填满，循环使用最高分片段
        loop_count = 0
        while remaining > 0.3 and loop_count < 100:
            loop_count += 1
            best_seg = ranked[0]  # 最高分片段
            seg_idx = segments.index(best_seg)

            # 找到新的未使用区间（循环回开头）
            source_start = best_seg["start_time"]
            take = min(best_seg["duration"], remaining)

            clips_for_section.append({
                "source_start": source_start,
                "source_duration": round(take, 2),
                "segment_score": best_seg.get("highlight_score", 50),
                "emotional_tone": best_seg.get("emotional_tone", ""),
                "segment_idx": seg_idx,
                "is_loop": True,
            })

            remaining -= take

        # 将片段放置在时间轴上
        current_target = section_start
        for clip in clips_for_section:
            placements.append({
                "source_start": clip["source_start"],
                "source_duration": clip["source_duration"],
                "target_start": round(current_target, 2),
                "match_rationale": (
                    f"排名 #{ranked.index(segments[clip['segment_idx']])+1} "
                    f"高光片段({clip['segment_score']}分) → {section_name}"
                    + (" [循环]" if clip.get("is_loop") else "")
                ),
            })
            current_target += clip["source_duration"] + 0.02  # 0.02s 间隙

    return placements


# ============================================
# 音乐优先模式
# ============================================

# 音乐段落到所需情绪的映射
SECTION_TONE_MAP = {
    "intro":        ["establishing", "calm", "mystery", "ambient"],
    "verse":        ["dialogue", "narrative", "calm", "building"],
    "pre_chorus":   ["building", "tension", "anticipation"],
    "chorus":       ["action", "emotional", "triumph", "climax"],
    "final_chorus": ["climax", "triumph", "action", "emotional"],
    "drop":         ["climax", "action", "triumph", "high_energy"],
    "bridge":       ["emotional", "reflective", "melancholy", "calm"],
    "breakdown":    ["calm", "minimal", "melancholy"],
    "buildup":      ["building", "tension", "anticipation"],
    "outro":        ["melancholy", "calm", "establishing", "resolution"],
    "interlude":    ["mystery", "calm", "ambient", "establishing"],
    "climax":       ["climax", "triumph", "action", "emotional"],
}


def _assemble_music_first(
    segments: list[dict],
    music_sections: list[dict],
    video_duration: float,
    music_duration: float,
) -> list[dict]:
    """
    音乐优先算法：
    1. 按 emotional_tone 将视频片段分组
    2. 每个音乐段落从匹配的情绪池中选取最佳片段
    3. 优先保证情绪匹配，其次考虑 highlight_score
    """
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

        # 该段落需要的情绪类型
        target_tones = SECTION_TONE_MAP.get(section_name, ["action", "emotional", "calm"])

        remaining = section_dur
        current_target = section_start

        # 从匹配的情绪池中收集可用片段
        candidates = []
        for tone in target_tones:
            if tone in tone_pools:
                for entry in tone_pools[tone]:
                    seg = entry["segment"]
                    available = seg["duration"] - entry["used_offset"]
                    if available >= 0.3:
                        # 综合评分：情绪匹配度 + 高光度
                        tone_rank = len(target_tones) - target_tones.index(tone)
                        combined_score = tone_rank * 15 + seg.get("highlight_score", 50)
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

            placements.append({
                "source_start": seg["start_time"] + entry["used_offset"],
                "source_duration": round(take, 2),
                "target_start": round(current_target, 2),
                "match_rationale": (
                    f"'{seg.get('emotional_tone', '')}'→{section_name} "
                    f"(高光{seg.get('highlight_score', 0)}分, 能量{energy:.1f})"
                ),
            })

            entry["used_offset"] += take
            remaining -= take
            current_target += take + 0.02

        # 如果该段落未填满，用最高分片段补齐
        if remaining > 0.3:
            all_entries = []
            for tone, pool in tone_pools.items():
                for entry in pool:
                    seg = entry["segment"]
                    available = seg["duration"] - entry["used_offset"]
                    if available >= 0.3:
                        all_entries.append((entry, available))

            all_entries.sort(
                key=lambda x: x[0]["segment"].get("highlight_score", 0),
                reverse=True,
            )

            for entry, available in all_entries:
                if remaining <= 0.3:
                    break
                seg = entry["segment"]
                take = min(available, remaining)

                placements.append({
                    "source_start": seg["start_time"] + entry["used_offset"],
                    "source_duration": round(take, 2),
                    "target_start": round(current_target, 2),
                    "match_rationale": (
                        f"补齐: '{seg.get('emotional_tone', '')}'→{section_name} "
                        f"({seg.get('highlight_score', 0)}分)"
                    ),
                })

                entry["used_offset"] += take
                remaining -= take
                current_target += take + 0.02

        # 仍然未填满：循环使用最佳匹配
        if remaining > 0.3:
            _fill_with_loops(placements, segments, remaining, current_target, section_name)

    return placements


def _fill_with_loops(
    placements: list[dict],
    segments: list[dict],
    remaining: float,
    current_target: float,
    section_name: str,
):
    """用循环视频片段填充未覆盖的音乐时长"""
    if not segments:
        return

    best = max(segments, key=lambda s: s.get("highlight_score", 0))

    while remaining > 0.3:
        take = min(best["duration"], remaining)
        placements.append({
            "source_start": best["start_time"],
            "source_duration": round(take, 2),
            "target_start": round(current_target, 2),
            "match_rationale": f"循环填充→{section_name} (高光{best.get('highlight_score', 0)}分)",
        })
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
    2. 确保连续无空隙
    3. 微调最后一段以精确匹配音乐时长
    4. 移除过短的碎片
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

    # 如果超出音乐时长，裁剪最后一段
    last_target_end = filtered[-1]["target_start"] + filtered[-1]["source_duration"]
    if last_target_end > music_duration + 0.5:
        excess = last_target_end - music_duration
        if filtered[-1]["source_duration"] > excess + 0.3:
            filtered[-1]["source_duration"] = round(filtered[-1]["source_duration"] - excess, 2)

    # 如果未覆盖完整音乐时长，循环填充
    final_end = filtered[-1]["target_start"] + filtered[-1]["source_duration"]
    if final_end < music_duration - 0.5:
        best_clip = max(filtered, key=lambda p: p.get("segment_score", 0) if "segment_score" in p else 0)
        if not best_clip:
            best_clip = filtered[0]

        remaining = music_duration - final_end
        current_target = final_end + 0.02

        while remaining > 0.5:
            take = min(best_clip["source_duration"], remaining)
            filtered.append({
                "source_start": best_clip["source_start"],
                "source_duration": round(take, 2),
                "target_start": round(current_target, 2),
                "match_rationale": "尾部补齐（循环）",
            })
            remaining -= take
            current_target += take + 0.02

    return filtered
