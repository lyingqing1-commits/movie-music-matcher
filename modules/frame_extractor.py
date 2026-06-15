"""
视频帧提取模块 - 使用 FFmpeg 从视频中提取关键帧
================================================
跨平台自动检测系统中的 FFmpeg 安装位置（无需手动配置 PATH）。
支持 Windows / Linux / macOS。
"""
import os
import subprocess
import json
import sys as _sys
import config


# ---- FFmpeg 跨平台自动检测 ----

def _find_ffmpeg(tool: str = "ffmpeg") -> str:
    """
    自动查找 ffmpeg/ffprobe 的可执行文件路径（Windows / Linux / macOS）。
    搜索顺序：环境变量覆盖 → PATH → 常见安装位置。

    可通过环境变量手动指定路径：
      FFMPEG_PATH  — ffmpeg 可执行文件路径
      FFPROBE_PATH — ffprobe 可执行文件路径
    """
    is_win = _sys.platform == "win32"
    tool_exe = f"{tool}.exe" if is_win else tool  # Linux/macOS 不需要 .exe

    # 0. 检查环境变量覆盖
    env_key = f"{tool.upper()}_PATH"
    env_path = os.environ.get(env_key, "")
    if env_path and os.path.isfile(env_path):
        return env_path

    # 1. 先在 PATH 中查找
    if is_win:
        result = subprocess.run(
            ["where", tool_exe], capture_output=True, text=True, shell=True,
            encoding="utf-8", errors="replace"
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().split("\n")[0].strip()
    else:
        # Linux/macOS: use 'which' or 'command -v'
        result = subprocess.run(
            ["which", tool_exe], capture_output=True, text=True,
            encoding="utf-8", errors="replace"
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().split("\n")[0].strip()
        # Fallback: try 'command -v'
        result2 = subprocess.run(
            ["sh", "-c", f"command -v {tool_exe}"], capture_output=True, text=True,
            encoding="utf-8", errors="replace"
        )
        if result2.returncode == 0 and result2.stdout.strip():
            return result2.stdout.strip().split("\n")[0].strip()

    # 2. 常见安装位置（按平台）
    if is_win:
        common_paths = [
            os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"),
            r"C:\ffmpeg\bin",
            r"C:\Program Files\FFmpeg\bin",
            r"C:\Program Files (x86)\FFmpeg\bin",
            os.path.expandvars(r"%USERPROFILE%\ffmpeg\bin"),
        ]

        # Winget 安装的路径可能是版本号命名的子目录
        winget_base = os.path.expandvars(
            r"%LOCALAPPDATA%\Microsoft\WinGet\Packages"
        )
        if os.path.isdir(winget_base):
            for d in os.listdir(winget_base):
                if d.startswith("Gyan.FFmpeg"):
                    common_paths.insert(0, os.path.join(winget_base, d))

        # CapCut / 剪映 自带的 FFmpeg
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
    else:
        # Linux/macOS 常见路径
        common_paths = [
            "/usr/bin",
            "/usr/local/bin",
            "/opt/ffmpeg/bin",
            os.path.expanduser("~/bin"),
        ]

    for base in common_paths:
        if os.path.isdir(base):
            # 检查直接路径
            exe_path = os.path.join(base, tool_exe)
            if os.path.isfile(exe_path):
                return exe_path
            # 子目录搜索（但不要太深）
            try:
                for root, dirs, files in os.walk(base):
                    if tool_exe in files:
                        return os.path.join(root, tool_exe)
                    if len(root.split(os.sep)) - len(base.split(os.sep)) > 3:
                        dirs.clear()  # 不深入太深
            except PermissionError:
                pass

    # 如果都找不到，返回工具名（让系统报错，但错误信息更清晰）
    return tool_exe


# 模块加载时确定 FFmpeg 路径
_FFMPEG_PATH = None
_FFPROBE_PATH = None


def _get_ffmpeg():
    global _FFMPEG_PATH
    if _FFMPEG_PATH is None:
        _FFMPEG_PATH = _find_ffmpeg("ffmpeg")
        print(f"[FFmpeg] Found: {_FFMPEG_PATH} (platform: {_sys.platform})")
    return _FFMPEG_PATH


def _get_ffprobe():
    global _FFPROBE_PATH
    if _FFPROBE_PATH is None:
        _FFPROBE_PATH = _find_ffmpeg("ffprobe")
        print(f"[FFprobe] Found: {_FFPROBE_PATH} (platform: {_sys.platform})")
    return _FFPROBE_PATH


def is_ffmpeg_available() -> bool:
    """检查 FFmpeg 和 FFprobe 是否都可用"""
    try:
        ffprobe = _get_ffprobe()
        result = subprocess.run(
            [ffprobe, "-version"], capture_output=True, text=True,
            timeout=10, encoding="utf-8", errors="replace"
        )
        return result.returncode == 0
    except Exception:
        return False


# ---- 视频处理功能 ----

def get_video_info(video_path: str) -> dict:
    """
    获取视频元数据：时长、分辨率、FPS
    """
    cmd = [
        _get_ffprobe(),
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        video_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")

    if result.returncode != 0:
        raise RuntimeError(f"ffprobe 读取视频信息失败:\n{result.stderr}")

    data = json.loads(result.stdout)

    # 找到视频流
    video_stream = None
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            video_stream = stream
            break

    if not video_stream:
        raise RuntimeError("未在文件中找到视频流")

    duration = float(data["format"].get("duration", 0))
    width = video_stream.get("width", 0)
    height = video_stream.get("height", 0)

    # FPS：可能是分数形式如 "24/1" 或 "24000/1001"
    fps_str = video_stream.get("r_frame_rate", "0/1")
    num, den = fps_str.split("/")
    fps = float(num) / float(den) if float(den) != 0 else 0

    return {
        "duration": duration,
        "width": width,
        "height": height,
        "fps": round(fps, 2),
        "file_path": video_path,
    }


def extract_frames(video_path: str, task_id: str) -> tuple[list[str], dict]:
    """
    从视频中提取帧
    返回：(帧文件路径列表, 视频信息字典)
    """
    info = get_video_info(video_path)
    duration = info["duration"]

    # 创建该任务的帧目录
    frame_dir = os.path.join(config.FRAME_FOLDER, task_id)
    os.makedirs(frame_dir, exist_ok=True)

    # 计算提取间隔
    interval = config.FRAME_EXTRACT_INTERVAL
    total_possible_frames = int(duration / interval)
    if total_possible_frames > config.MAX_FRAMES:
        interval = duration / config.MAX_FRAMES

    # 计算缩放参数
    max_width = config.FRAME_MAX_WIDTH
    scale_filter = f"scale={max_width}:-1"

    # FFmpeg 命令
    output_pattern = os.path.join(frame_dir, "frame_%04d.jpg")
    cmd = [
        _get_ffmpeg(),
        "-i", video_path,
        "-vf", f"fps=1/{interval},{scale_filter}",
        "-q:v", str(config.FRAME_QUALITY),
        "-y",
        output_pattern,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")

    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg 提取帧失败:\n{result.stderr}")

    # 收集生成的帧文件
    frame_files = sorted(
        [os.path.join(frame_dir, f) for f in os.listdir(frame_dir) if f.endswith(".jpg")]
    )

    print(f"从视频中提取了 {len(frame_files)} 帧 (时长: {duration:.1f}s, 间隔: {interval:.1f}s)")

    return frame_files, info


def sample_frames(frame_files: list[str], count: int = None) -> list[str]:
    """
    从帧列表中均匀采样指定数量的帧
    """
    if count is None:
        count = config.SAMPLE_FRAMES

    if len(frame_files) <= count:
        return frame_files

    step = len(frame_files) / count
    sampled = [frame_files[int(i * step)] for i in range(count)]
    return sampled
