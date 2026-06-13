"""
音乐结构分析模块 — 识别歌曲的段落结构
=====================================
结合 librosa 的音频信号处理和 AI 的音乐知识，
识别 intro/verse/chorus/bridge/drop/buildup/outro 等段落。

超越单纯的 BPM 检测，理解音乐的完整叙事结构。
"""
import json
import os
import numpy as np
from anthropic import Anthropic
import config


def _safe_float(value) -> float:
    if isinstance(value, np.ndarray):
        if value.ndim == 0:
            return value.item()
        elif value.ndim == 1 and value.shape[0] == 1:
            return value[0].item()
        raise ValueError(f"Cannot convert array of shape {value.shape} to float")
    return float(value)


def _get_client() -> Anthropic:
    kwargs = {"api_key": config.ANTHROPIC_API_KEY}
    if config.ANTHROPIC_BASE_URL:
        kwargs["base_url"] = config.ANTHROPIC_BASE_URL
    return Anthropic(**kwargs)


def _get_response_text(response) -> str:
    for block in response.content:
        if getattr(block, "type", None) == "text":
            return getattr(block, "text", "") or ""
    return str(response.content[0]) if response.content else ""


# 尝试导入 librosa
try:
    import librosa
    HAS_LIBROSA = True
except ImportError:
    HAS_LIBROSA = False
    print("⚠️ librosa 未安装，音乐结构分析将使用 AI 纯文本模式")


# ---- librosa 分析 ----

def _extract_energy_curve(y, sr, hop_length: int = 512) -> list[dict]:
    """
    提取 RMS 能量曲线（下采样到合理点数）。
    返回每点的相对时间和归一化能量值。
    """
    rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
    rms_max = np.max(rms)
    if rms_max > 0:
        rms = rms / rms_max

    times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop_length)

    # 下采样到 ~100 个数据点
    target_points = 100
    if len(times) > target_points:
        step = len(times) / target_points
        indices = [int(i * step) for i in range(target_points)]
        times = times[indices]
        rms = rms[indices]

    return [
        {"time": round(_safe_float(t), 1), "energy": round(_safe_float(e), 3)}
        for t, e in zip(times, rms)
    ]


def _extract_onset_times(y, sr) -> list[float]:
    """提取音符起始点时间"""
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    onset_frames = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr)
    onset_times = librosa.frames_to_time(onset_frames, sr=sr)
    return [round(_safe_float(t), 1) for t in onset_times]


def _extract_spectral_contrast_curve(y, sr, hop_length: int = 512) -> list[dict]:
    """提取频谱对比度曲线（区分 harmonic/percussive）"""
    contrast = librosa.feature.spectral_contrast(y=y, sr=sr, hop_length=hop_length)
    mean_contrast = np.mean(contrast, axis=0)

    times = librosa.frames_to_time(np.arange(len(mean_contrast)), sr=sr, hop_length=hop_length)

    # 下采样到 ~50 点
    target_points = 50
    if len(times) > target_points:
        step = len(times) / target_points
        indices = [int(i * step) for i in range(target_points)]
        times = times[indices]
        mean_contrast = mean_contrast[indices]

    return [
        {"time": round(_safe_float(t), 1), "contrast": round(_safe_float(c), 3)}
        for t, c in zip(times, mean_contrast)
    ]


# ---- 系统提示词 ----

SYSTEM_PROMPT_STRUCTURE = """你是一位专业音乐制作人/DJ。你需要根据音频分析数据识别歌曲的结构段落。

典型的歌曲结构包括：
- **intro**: 开场，通常能量较低，乐器逐渐加入
- **verse**: 主歌，能量中等，叙事性
- **pre_chorus**: 前副歌，能量开始攀升
- **chorus**: 副歌，能量高峰，重复性，最"洗脑"的部分
- **drop**: EDM/电子音乐中的"爆发点"，能量急剧上升后释放
- **bridge**: 桥段/间奏，能量变化，提供对比
- **buildup**: 渐进式能量攀升
- **breakdown**: 能量骤降，简约编排
- **outro**: 尾声，能量逐渐消退
- **interlude**: 插曲，过渡性段落

我提供的数据包括：
1. 能量曲线（时间 → 归一化能量值 0-1）
2. 音符起始点时间列表（onset times）
3. 频谱对比度曲线（harmonic/percussive 成分的变化）
4. 音频基础特征（BPM、时长、调性等）

请识别歌曲的完整结构，以 JSON 格式返回：
{
  "sections": [
    {
      "section": "intro",
      "start_time": 0.0,
      "end_time": 16.2,
      "energy_level": 0.3,
      "character": "环境音铺垫，打击乐逐渐进入"
    },
    ...
  ],
  "key_moments": [
    {"time": 48.5, "label": "第一段副歌开始", "energy": 0.85},
    {"time": 80.0, "label": "Drop / 情绪最高点", "energy": 1.0}
  ],
  "overall_structure": "intro → verse → chorus → verse → chorus → bridge → final_chorus → outro",
  "genre_hint": "Electronic / Pop"
}

规则：
- sections 必须覆盖整首歌（从 0 到总时长）
- section 之间紧密相连，无空隙
- energy_level 是 0-1 的相对值
- key_moments 标注最重要的 2-5 个转折点
- 如果某类段落不确定，标注为 "unknown"
"""


def analyze_music_structure(
    audio_path: str,
    audio_features: dict,
    style_analysis: dict = None,
) -> dict:
    """
    分析音乐结构，返回段落划分和关键时刻。

    参数：
        audio_path: 音频文件路径
        audio_features: 来自 music_matcher.analyze_audio() 的基础特征
        style_analysis: 电影风格分析（可选，用于上下文提示）

    返回：
        {
            "duration": float,
            "bpm": float,
            "structure": [
                {section, start_time, end_time, duration, energy_level, character},
                ...
            ],
            "key_moments": [{time, label, energy}, ...],
            "overall_structure": str,
            "analysis_mode": "ai" | "librosa_only"
        }
    """
    duration = audio_features.get("duration_seconds", 60)
    bpm = audio_features.get("tempo_bpm", 120)
    if bpm <= 0:
        bpm = 120

    # ---- 使用 librosa 提取信号特征 ----
    librosa_data = None
    if HAS_LIBROSA:
        try:
            print(f"   📊 librosa 提取音乐结构特征...")
            y, sr = librosa.load(audio_path, sr=22050, duration=min(duration, 180))

            librosa_data = {
                "energy_curve": _extract_energy_curve(y, sr),
                "onset_times": _extract_onset_times(y, sr),
                "contrast_curve": _extract_spectral_contrast_curve(y, sr),
            }
            print(f"      能量曲线: {len(librosa_data['energy_curve'])} 点, "
                  f"起始点: {len(librosa_data['onset_times'])} 个")
        except Exception as e:
            print(f"   ⚠️ librosa 分析失败: {e}")

    # ---- 尝试 AI 结构识别 ----
    if config.ANTHROPIC_API_KEY:
        try:
            return _ai_structure_analysis(
                duration, bpm, audio_features, librosa_data, style_analysis
            )
        except Exception as e:
            print(f"   ⚠️ AI 结构分析失败: {e}，回退到信号分析")

    # ---- 回退：纯信号分析 ----
    return _signal_only_structure(duration, bpm, librosa_data)


def _ai_structure_analysis(
    duration: float,
    bpm: float,
    audio_features: dict,
    librosa_data: dict,
    style_analysis: dict = None,
) -> dict:
    """使用 AI 分析音乐结构"""
    print("   🤖 AI 正在分析音乐结构...")

    client = _get_client()

    # 构建数据摘要
    data_lines = [
        f"歌曲时长: {duration:.1f} 秒",
        f"BPM: {bpm}",
        f"调性: {audio_features.get('estimated_key', '?')}",
        f"能量: {audio_features.get('energy', '?')}",
        f"音色亮度: {audio_features.get('brightness', '?')}",
    ]

    if librosa_data:
        # 能量曲线摘要
        energy_curve = librosa_data["energy_curve"]
        if energy_curve:
            # 下采样到 ~30 个关键点
            step = max(1, len(energy_curve) // 30)
            key_energies = energy_curve[::step]
            data_lines.append(f"\n能量曲线（{len(key_energies)} 个采样点）:")
            data_lines.append(
                ", ".join(f"t{e['time']:.0f}:{e['energy']:.2f}" for e in key_energies)
            )

        # Onset 密度
        onsets = librosa_data["onset_times"]
        if onsets:
            # 每 10 秒的 onset 数量
            onset_density = []
            for window_start in range(0, int(duration), 10):
                count = sum(1 for t in onsets if window_start <= t < window_start + 10)
                onset_density.append(f"{window_start}s-{window_start+10}s: {count}个")
            data_lines.append(f"\n音符密度（每10秒）: {'; '.join(onset_density[:15])}")

        # 对比度摘要
        contrast_curve = librosa_data.get("contrast_curve", [])
        if contrast_curve:
            peak_times = [
                f"t{c['time']:.0f}" for c in contrast_curve
                if c["contrast"] > 0.7
            ]
            if peak_times:
                data_lines.append(f"\n高对比度时刻: {', '.join(peak_times[:10])}")

    user_message = "\n".join(data_lines)
    user_message += "\n\n请识别这首歌曲的结构段落（intro/verse/chorus/drop/bridge/outro 等），返回 JSON。"

    response = client.messages.create(
        model=config.AI_MODEL,
        max_tokens=2048,
        system=SYSTEM_PROMPT_STRUCTURE,
        messages=[{"role": "user", "content": user_message}],
    )

    response_text = _get_response_text(response)
    result = _parse_structure(response_text, duration, bpm)

    if result and result.get("structure"):
        print(f"   ✅ AI 识别到 {len(result['structure'])} 个音乐段落")
        for s in result["structure"][:5]:
            print(f"      {s['section']}: {s['start_time']:.0f}s - {s['end_time']:.0f}s "
                  f"(能量: {s.get('energy_level', '?')})")
        result["analysis_mode"] = "ai"
        return result

    # 解析失败
    print("   ⚠️ AI 结构解析失败，回退到信号分析")
    return _signal_only_structure(duration, bpm, librosa_data)


def _parse_structure(text: str, duration: float, bpm: float) -> dict:
    """从 AI 响应中解析音乐结构"""
    if not text:
        return {}

    if "```json" in text:
        start = text.find("```json") + 7
        end = text.find("```", start)
        text = text[start:end].strip()
    elif "```" in text:
        start = text.find("```") + 3
        end = text.find("```", start)
        text = text[start:end].strip()

    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        # 尝试提取 JSON 对象
        brace_start = text.find("{")
        brace_end = text.rfind("}") + 1
        if brace_start >= 0 and brace_end > brace_start:
            try:
                result = json.loads(text[brace_start:brace_end])
            except json.JSONDecodeError:
                return {}
        else:
            return {}

    # 标准化
    if "sections" in result and not result.get("structure"):
        result["structure"] = result["sections"]

    if result.get("structure"):
        for s in result["structure"]:
            s.setdefault("duration", round(s.get("end_time", 0) - s.get("start_time", 0), 1))
            s.setdefault("energy_level", 0.5)
            s.setdefault("character", "")
            s["start_time"] = round(s.get("start_time", 0), 1)
            s["end_time"] = round(s.get("end_time", 0), 1)
            s["duration"] = round(s.get("duration", s["end_time"] - s["start_time"]), 1)

    result.setdefault("duration", duration)
    result.setdefault("bpm", bpm)
    result.setdefault("key_moments", [])
    result.setdefault("overall_structure", "")

    return result


def _signal_only_structure(
    duration: float,
    bpm: float,
    librosa_data: dict,
) -> dict:
    """
    纯信号分析的音乐结构（AI 不可用时的回退）。

    基于能量曲线峰值/谷值做简单分段。
    """
    print("   📊 使用信号分析构建音乐结构...")

    if librosa_data and librosa_data.get("energy_curve"):
        energy_curve = librosa_data["energy_curve"]
        energies = [e["energy"] for e in energy_curve]
        times = [e["time"] for e in energy_curve]

        # 找到能量峰值和谷值
        mean_energy = np.mean(energies) if energies else 0.5

        # 简化分段：高中低三档
        sections = []
        current_section = None
        section_start = 0.0

        for i, (t, e) in enumerate(zip(times, energies)):
            if e > mean_energy * 1.3:
                label = "chorus"
                level = min(e * 1.2, 1.0)
            elif e > mean_energy * 0.7:
                label = "verse"
                level = e
            else:
                label = "intro" if t < duration * 0.15 else "bridge"
                level = e

            if current_section != label:
                if current_section is not None:
                    sections.append({
                        "section": current_section,
                        "start_time": round(section_start, 1),
                        "end_time": round(t, 1),
                        "duration": round(t - section_start, 1),
                        "energy_level": round(level, 2),
                        "character": f"信号检测: {current_section}",
                    })
                current_section = label
                section_start = t

        # 最后一段
        if current_section and section_start < duration:
            sections.append({
                "section": current_section,
                "start_time": round(section_start, 1),
                "end_time": round(duration, 1),
                "duration": round(duration - section_start, 1),
                "energy_level": round(energies[-1] if energies else 0.5, 2),
                "character": f"信号检测: {current_section}",
            })

        # 合并过短的段落（< 3 秒）
        merged = []
        for s in sections:
            if merged and s["duration"] < 3:
                merged[-1]["end_time"] = s["end_time"]
                merged[-1]["duration"] = round(merged[-1]["end_time"] - merged[-1]["start_time"], 1)
            else:
                merged.append(s)
        sections = merged

    else:
        # 无 librosa 数据时使用 BPM 估算段落
        beat_dur = 60.0 / max(bpm, 1)
        bar_dur = beat_dur * 4  # 以 4/4 拍为准
        section_beats = 32  # 每 32 拍一个段落

        sections = []
        pos = 0.0
        labels = ["intro", "verse", "chorus", "verse", "chorus", "bridge", "chorus", "outro"]
        idx = 0
        while pos < duration:
            end = min(pos + bar_dur * section_beats / 4, duration)
            sections.append({
                "section": labels[min(idx, len(labels) - 1)],
                "start_time": round(pos, 1),
                "end_time": round(end, 1),
                "duration": round(end - pos, 1),
                "energy_level": 0.5,
                "character": f"BPM 估算: {labels[min(idx, len(labels) - 1)]}",
            })
            pos = end
            idx += 1

    # 确保至少有一个段落
    if not sections:
        sections = [{
            "section": "verse",
            "start_time": 0.0,
            "end_time": round(duration, 1),
            "duration": round(duration, 1),
            "energy_level": 0.5,
            "character": "整曲（未能分段）",
        }]

    print(f"   ✅ 信号分析: {len(sections)} 个段落")

    return {
        "duration": duration,
        "bpm": bpm,
        "structure": sections,
        "key_moments": _detect_key_moments(sections, duration),
        "overall_structure": " → ".join(s["section"] for s in sections),
        "analysis_mode": "librosa_only",
    }


def _detect_key_moments(sections: list[dict], duration: float) -> list[dict]:
    """从段落中自动检测关键时刻"""
    moments = []
    for s in sections:
        if s["section"] in ("chorus", "drop", "final_chorus", "climax"):
            if s.get("energy_level", 0) >= 0.6:
                moments.append({
                    "time": s["start_time"],
                    "label": f"{s['section']} 开始",
                    "energy": s.get("energy_level", 0.5),
                })

    # 按时间排序
    moments.sort(key=lambda m: m["time"])

    # 取前 4 个
    if len(moments) > 4:
        moments = sorted(moments, key=lambda m: m["energy"], reverse=True)[:4]
        moments.sort(key=lambda m: m["time"])

    return moments
