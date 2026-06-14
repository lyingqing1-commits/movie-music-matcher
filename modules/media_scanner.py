"""
媒体扫描模块 — 生成详细的 media-manifest.json
============================================
对上传的视频、音频文件进行 FFprobe 深度扫描，生成完整清单。
复用 frame_extractor 模块的 FFmpeg/FFprobe 探测逻辑。

参照：DaVinci-AutoEdit-Agent skills/davinci-autoedit-agent/scripts/scan_media.py
"""
import json
import hashlib
import os
from pathlib import Path

from modules.frame_extractor import get_video_info, extract_frames, sample_frames
from modules.workspace_manager import save_artifact


# 支持的媒体格式
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".mts", ".m2ts", ".webm", ".mpg", ".mpeg", ".mxf"}
AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".aiff", ".wma"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp", ".heic"}


def quick_hash(file_path: str) -> str:
    """
    快速文件哈希（用于去重检测）。
    哈希文件头 64KB + 文件大小。
    优化：减小读取量以提升扫描速度。
    """
    path = Path(file_path)
    if not path.exists():
        return ""

    digest = hashlib.sha256()
    size = path.stat().st_size

    try:
        with path.open("rb") as handle:
            # 读头部 64KB（原 1MB 太慢，对大文件影响显著）
            digest.update(handle.read(64 * 1024))
            # 读尾部 64KB（如果文件足够大）
            if size > 128 * 1024:
                handle.seek(max(0, size - 64 * 1024))
                digest.update(handle.read(64 * 1024))
        digest.update(str(size).encode("ascii"))
        return digest.hexdigest()
    except Exception:
        return ""


def scan_media(video_path: str, audio_paths: list[str] = None, run_path: str = None) -> dict:
    """
    扫描所有输入媒体文件，生成完整的媒体清单。

    参数：
        video_path: 视频文件路径
        audio_paths: 音频文件路径列表（可选）
        run_path: 运行目录路径（用于保存产物）

    返回：
        media-manifest 字典：
        {
            schema_version, scanned_at,
            files: [{path, media_type, extension, size_bytes, quick_hash, probe: {...}}],
            summary: {total_files, video_count, audio_count, total_duration, ...}
        }
    """
    from datetime import datetime, timezone

    manifest = {
        "schema_version": "1.0.0",
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "inputs": [],
        "files": [],
        "summary": {},
    }

    files = []
    total_duration = 0.0
    video_count = 0
    audio_count = 0

    # 扫描视频
    if video_path and os.path.exists(video_path):
        vp = Path(video_path)
        suffix = vp.suffix.lower()
        media_type = "video" if suffix in VIDEO_EXTENSIONS else "audio" if suffix in AUDIO_EXTENSIONS else "image"

        print(f"   [SCAN] 正在探测视频: {vp.name} ({round(vp.stat().st_size/(1024*1024),1)}MB)...")
        video_meta = {}
        try:
            video_meta = get_video_info(video_path)
            print(f"   [SCAN] 视频时长: {video_meta.get('duration', '?')}s, "
                  f"分辨率: {video_meta.get('width','?')}x{video_meta.get('height','?')}")
        except Exception as e:
            video_meta = {"error": str(e)}
            print(f"   [WARN] 视频探测失败: {e}")

        file_entry = {
            "path": str(vp.resolve()),
            "filename": vp.name,
            "media_type": media_type,
            "extension": suffix,
            "size_bytes": vp.stat().st_size,
            "size_mb": round(vp.stat().st_size / (1024 * 1024), 2),
            "quick_hash": quick_hash(video_path),
            "probe": video_meta,
        }
        files.append(file_entry)
        manifest["inputs"].append(str(vp.resolve()))

        if media_type == "video":
            video_count += 1
            dur = video_meta.get("duration", 0)
            if isinstance(dur, (int, float)) and dur > 0:
                total_duration += dur

    # 扫描音频
    if audio_paths:
        for i, audio_path in enumerate(audio_paths):
            if not audio_path or not os.path.exists(audio_path):
                continue
            ap = Path(audio_path)
            suffix = ap.suffix.lower()

            print(f"   [SCAN] 正在探测音频 ({i+1}/{len(audio_paths)}): {ap.name} ({round(ap.stat().st_size/(1024*1024),1)}MB)...")
            audio_meta = {}
            try:
                audio_meta = get_video_info(audio_path)  # ffprobe 对音频也适用
            except Exception as e:
                audio_meta = {"error": str(e)}
                print(f"   [WARN] 音频探测失败: {e}")

            file_entry = {
                "path": str(ap.resolve()),
                "filename": ap.name,
                "media_type": "audio",
                "extension": suffix,
                "size_bytes": ap.stat().st_size,
                "size_mb": round(ap.stat().st_size / (1024 * 1024), 2),
                "quick_hash": quick_hash(audio_path),
                "probe": audio_meta,
            }
            files.append(file_entry)
            manifest["inputs"].append(str(ap.resolve()))
            audio_count += 1

            dur = audio_meta.get("duration", 0)
            if isinstance(dur, (int, float)) and dur > 0:
                total_duration += dur

    # 保存
    manifest["files"] = files
    manifest["summary"] = {
        "total_files": len(files),
        "video_count": video_count,
        "audio_count": audio_count,
        "total_duration_seconds": round(total_duration, 1),
    }

    if run_path:
        save_artifact(run_path, "media-manifest", manifest)

    return manifest


def build_scan_preview(manifest: dict) -> dict:
    """
    从原始 manifest 构建前端友好的预览数据。

    返回：
        {file_count, video_duration_display, audio_count, files_summary, ...}
    """
    summary = manifest.get("summary", {})
    files = manifest.get("files", [])

    video_files = [f for f in files if f.get("media_type") == "video"]
    audio_files = [f for f in files if f.get("media_type") == "audio"]

    total_dur = summary.get("total_duration_seconds", 0)
    if total_dur >= 60:
        dur_display = f"{int(total_dur // 60)}分{int(total_dur % 60)}秒"
    else:
        dur_display = f"{int(total_dur)}秒"

    files_summary = []
    for f in files:
        probe = f.get("probe", {})
        files_summary.append({
            "filename": f.get("filename", ""),
            "media_type": f.get("media_type", ""),
            "size_mb": f.get("size_mb", 0),
            "duration": probe.get("duration", 0),
            "resolution": f"{probe.get('width', '?')}x{probe.get('height', '?')}"
                         if probe.get("width") else "",
        })

    return {
        "total_files": summary.get("total_files", 0),
        "video_count": summary.get("video_count", 0),
        "audio_count": summary.get("audio_count", 0),
        "duration_display": dur_display,
        "total_duration": total_dur,
        "files": files_summary,
        "video_files": [f for f in files_summary if f["media_type"] == "video"],
        "audio_files": [f for f in files_summary if f["media_type"] == "audio"],
    }
