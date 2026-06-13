"""
场景检测模块 — 使用 FFmpeg 检测视频中的自然转场点
================================================
使用 FFmpeg 的 scene 滤镜检测画面突变（转场），
将视频分割为内容感知的自然片段，替代等时切分。

纯 FFmpeg 工具模块，不消耗 AI 调用。
"""
import os
import re
import subprocess
import sys
from typing import Optional
import config


def _find_ffmpeg() -> str:
    """查找 FFmpeg 可执行文件（复用 frame_extractor 的逻辑）"""
    tool_exe = "ffmpeg.exe"

    # 1. PATH 查找
    result = subprocess.run(
        ["where", tool_exe], capture_output=True, text=True, shell=True,
        encoding="utf-8", errors="replace"
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip().split("\n")[0].strip()

    # 2. 常见位置
    common_paths = [
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"),
        r"C:\ffmpeg\bin",
        r"C:\Program Files\FFmpeg\bin",
    ]
    winget_base = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages")
    if os.path.isdir(winget_base):
        for d in os.listdir(winget_base):
            if d.startswith("Gyan.FFmpeg"):
                common_paths.insert(0, os.path.join(winget_base, d))

    for base in common_paths:
        if os.path.isdir(base):
            exe_path = os.path.join(base, tool_exe)
            if os.path.isfile(exe_path):
                return exe_path
            for root, dirs, files in os.walk(base):
                if tool_exe in files:
                    return os.path.join(root, tool_exe)
                if len(root.split(os.sep)) - len(base.split(os.sep)) > 3:
                    break

    # 3. CapCut/剪映 自带
    capcut_bases = [
        os.path.expandvars(r"%LOCALAPPDATA%\JianyingPro\Apps"),
        os.path.expandvars(r"%LOCALAPPDATA%\CapCut\Apps"),
    ]
    for capcut_base in capcut_bases:
        if os.path.isdir(capcut_base):
            for version_dir in sorted(os.listdir(capcut_base), reverse=True):
                exe_path = os.path.join(capcut_base, version_dir, tool_exe)
                if os.path.isfile(exe_path):
                    return exe_path

    return "ffmpeg"


_FFMPEG: Optional[str] = None


def _get_ffmpeg() -> str:
    global _FFMPEG
    if _FFMPEG is None:
        _FFMPEG = _find_ffmpeg()
    return _FFMPEG


def detect_scenes(
    video_path: str,
    threshold: float = None,
    video_duration: float = None,
) -> list[dict]:
    """
    使用 FFmpeg 场景检测滤镜找到视频中的自然转场点。

    参数：
        video_path: 视频文件路径
        threshold: 场景变化敏感度 (0.0-1.0)，越低检测越敏感
                   默认使用 config.SCENE_DETECTION_THRESHOLD
        video_duration: 视频总时长（秒），如果已知可传入避免重复检测

    返回：
        [
            {"start_time": 0.0, "end_time": 5.2, "duration": 5.2},
            {"start_time": 5.2, "end_time": 12.8, "duration": 7.6},
            ...
        ]

    如果 FFmpeg 场景检测失败，回退到固定间隔分段模式。
    """
    if threshold is None:
        threshold = getattr(config, "SCENE_DETECTION_THRESHOLD", 0.3)
    min_dur = getattr(config, "MIN_SEGMENT_DURATION", 1.0)

    print(f"🎬 正在检测场景转场 (threshold={threshold})...")

    try:
        change_times = _run_scene_detection(video_path, threshold)

        if not change_times:
            print("   ℹ️ 未检测到明显转场，使用固定间隔分段")
            return _fallback_fixed_segments(video_path, video_duration)

        # 构建连续片段
        # change_times 包含视频结束时间作为最后一个标记
        total_dur = change_times[-1] if change_times else (video_duration or 60)

        segments = []
        prev_time = 0.0

        for t in change_times:
            dur = t - prev_time
            if dur >= min_dur:
                segments.append({
                    "start_time": round(prev_time, 2),
                    "end_time": round(t, 2),
                    "duration": round(dur, 2),
                })
            else:
                # 合并过短的片段到前一个
                if segments:
                    segments[-1]["end_time"] = round(t, 2)
                    segments[-1]["duration"] = round(t - segments[-1]["start_time"], 2)
            prev_time = t

        # 确保不超出视频边界
        if segments and segments[-1]["end_time"] > total_dur:
            segments[-1]["end_time"] = round(total_dur, 2)
            segments[-1]["duration"] = round(segments[-1]["end_time"] - segments[-1]["start_time"], 2)

        # 如果合并后只剩太少片段（< 3 个），回退到固定分段
        if len(segments) < 3:
            print(f"   ⚠️ 场景检测仅找到 {len(segments)} 个片段，使用固定间隔分段")
            return _fallback_fixed_segments(video_path, video_duration)

        print(f"   ✅ 检测到 {len(segments)} 个自然场景片段")
        for i, seg in enumerate(segments[:5]):
            print(f"      片段 {i+1}: {seg['start_time']:.1f}s - {seg['end_time']:.1f}s ({seg['duration']:.1f}s)")
        if len(segments) > 5:
            print(f"      ... 等共 {len(segments)} 个片段")

        return segments

    except Exception as e:
        print(f"   ⚠️ 场景检测异常: {e}，回退到固定间隔分段")
        return _fallback_fixed_segments(video_path, video_duration)


def _run_scene_detection(video_path: str, threshold: float) -> list[float]:
    """
    运行 FFmpeg 场景检测并解析时间戳。

    使用 filter:
      select='gt(scene,{threshold})' 选择场景变化大的帧
      showinfo 输出每帧的时间戳信息

    返回排序后的场景变化时间戳列表（包含视频总时长）。
    """
    ffmpeg = _get_ffmpeg()

    # 构建 filter：选择场景变化 > threshold 的帧，并用 showinfo 输出时间
    filter_str = f"select='gt(scene,{threshold})',showinfo"

    cmd = [
        ffmpeg,
        "-i", video_path,
        "-filter:v", filter_str,
        "-f", "null",
        "-",
    ]

    # Windows: 隐藏控制台窗口
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=300,  # 5 分钟超时（大文件需要更长时间）
        creationflags=creationflags,
    )

    # showinfo 输出在 stderr 中
    output = proc.stderr

    # 解析 pts_time 值
    # 格式: "pts_time:123.456"
    times = []
    for line in output.split("\n"):
        match = re.search(r"pts_time:([\d.]+)", line)
        if match:
            t = float(match.group(1))
            times.append(t)

    # 去重并排序
    times = sorted(set(round(t, 2) for t in times))

    # 过滤掉起始时间 (0.0) 和过近的时间 (< 0.5s 间隔)
    filtered = []
    for t in times:
        if t < 0.1:  # 跳过起始
            continue
        if filtered and t - filtered[-1] < 0.5:
            continue
        filtered.append(t)

    # 添加视频结束时间（需要从 duration 获取）
    # 从 stderr 中尝试解析 duration
    dur_match = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", output)
    if dur_match:
        h, m, s = int(dur_match.group(1)), int(dur_match.group(2)), float(dur_match.group(3))
        total_dur = h * 3600 + m * 60 + s
        filtered.append(round(total_dur, 2))

    if not filtered:
        return []

    return filtered


def _fallback_fixed_segments(
    video_path: str,
    video_duration: float = None,
    segment_duration: float = 5.0,
) -> list[dict]:
    """
    回退方案：按固定时长等分视频。
    当 FFmpeg 场景检测不可用或视频无明显转场时使用。

    仍然优于旧的节拍等分方式，因为这里按自然段落长度（5秒）
    而非音乐 BPM 切分。
    """
    if video_duration is None:
        # 尝试获取视频时长
        try:
            from modules.frame_extractor import get_video_info
            info = get_video_info(video_path)
            video_duration = info.get("duration", 60)
        except Exception:
            video_duration = 60

    segments = []
    pos = 0.0
    while pos < video_duration:
        end = min(pos + segment_duration, video_duration)
        dur = end - pos
        if dur >= 0.5:  # 最小 0.5 秒
            segments.append({
                "start_time": round(pos, 2),
                "end_time": round(end, 2),
                "duration": round(dur, 2),
            })
        pos = end

    print(f"   固定分段: {len(segments)} 个片段（{segment_duration}s/段）")
    return segments
