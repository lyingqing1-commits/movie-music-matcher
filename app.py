"""
Movie Music Matcher - 主应用入口
=================================
电影素材自动匹配音乐 + 剪映草稿生成

用法：
    python app.py
    然后在浏览器打开 http://localhost:5000
"""
import os
import sys
import uuid
import re
import json
import threading
import time
import urllib.request
import urllib.error
import urllib.parse
import tempfile
import mimetypes

# Force UTF-8 encoding for stdout/stderr on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from flask import (
    Flask, render_template, request, jsonify,
    send_from_directory,
)


# ============================================
# 轻量 Markdown → HTML 转换
# ============================================

def _md_to_html(md_text: str) -> str:
    """将 Markdown 文本转换为 HTML（支持标题、列表、粗体、代码、表格）"""
    lines = md_text.split("\n")
    html = []
    in_list = None  # "ul" or "ol"

    def close_list():
        nonlocal in_list
        if in_list:
            html.append(f"</{in_list}>")
            in_list = None

    def _inline(text: str) -> str:
        """处理行内样式：粗体、代码、链接"""
        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
        text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)",
                      r'<a href="\2" target="_blank">\1</a>', text)
        return text

    for line in lines:
        stripped = line.strip()

        # 空行 → 关闭列表
        if not stripped:
            close_list()
            continue

        # 标题
        if stripped.startswith("### "):
            close_list()
            html.append(f"<h3>{_inline(stripped[4:])}</h3>")
            continue
        if stripped.startswith("## "):
            close_list()
            html.append(f"<h2>{_inline(stripped[3:])}</h2>")
            continue
        if stripped.startswith("# "):
            close_list()
            html.append(f"<h1>{_inline(stripped[2:])}</h1>")
            continue

        # 无序列表
        if re.match(r"^[-*]\s+", stripped):
            if in_list != "ul":
                close_list()
                html.append("<ul>")
                in_list = "ul"
            content = re.sub(r"^[-*]\s+", "", stripped)
            html.append(f"<li>{_inline(content)}</li>")
            continue

        # 有序列表
        if re.match(r"^\d+\.\s+", stripped):
            if in_list != "ol":
                close_list()
                html.append("<ol>")
                in_list = "ol"
            content = re.sub(r"^\d+\.\s+", "", stripped)
            html.append(f"<li>{_inline(content)}</li>")
            continue

        # 分隔线
        if stripped in ("---", "***", "___"):
            close_list()
            html.append("<hr>")
            continue

        # 表格
        if stripped.startswith("|") and stripped.endswith("|"):
            close_list()
            cells = [c.strip() for c in stripped.split("|")[1:-1]]
            if all(re.match(r"^[-:]+$", c) for c in cells):
                continue  # 跳过分隔行
            html.append("<table><tr>")
            for c in cells:
                html.append(f"<td>{_inline(c)}</td>")
            html.append("</tr></table>")
            continue

        # 普通段落
        close_list()
        html.append(f"<p>{_inline(stripped)}</p>")

    close_list()
    return "\n".join(html)
import config
from modules.frame_extractor import extract_frames, sample_frames
from modules.style_analyzer import analyze_style
from modules.music_matcher import analyze_audio as audio_analyze
from modules.music_matcher import match_music_to_style
from modules.draft_generator import create_draft
from modules.ai_music_generator import generate_music_options
from modules.updater import (
    detect_editor_info,
    get_compatibility_info,
    check_for_updates,
    perform_update,
    get_update_status,
)
from modules.movie_identifier import identify_movie
from modules.scene_detector import detect_scenes
from modules.segment_scorer import score_segments
from modules.music_structure_analyzer import analyze_music_structure
from modules.smart_editor import assemble_smart_draft

# v3.0 新增模块
from modules.workspace_manager import (
    create_run_folder, save_artifact, load_artifact, generate_project_slug, run_exists
)
from modules.project_brief import create_brief, validate_brief, load_brief, brief_to_display
from modules.media_scanner import scan_media, build_scan_preview
from modules.material_review import review_material, taxonomy_to_display
from modules.story_developer import develop_story, story_to_display
from modules.blueprint_generator import generate_blueprint, blueprint_to_display
from modules.blueprint_validator import validate_blueprint as validate_bp, suggest_fixes
from modules.delivery_auditor import audit_delivery, generate_pickup_report, pickup_to_display

app = Flask(__name__)
# Flask MAX_CONTENT_LENGTH: 使用视频大小的上限（2GB）
# Flask 默认不支持 >2GB 的单文件，如需更大文件请用分块上传
app.config["MAX_CONTENT_LENGTH"] = max(
    config.MAX_VIDEO_SIZE_MB, config.MAX_AUDIO_SIZE_MB
) * 1024 * 1024  # Flask 用字节

# 确保必要的文件夹存在
for folder in [config.UPLOAD_FOLDER, config.FRAME_FOLDER, config.OUTPUT_FOLDER,
                 getattr(config, "WORKSPACE_DIR", os.path.join(config.BASE_DIR, "workspace"))]:
    os.makedirs(folder, exist_ok=True)

# 任务状态存储（简单内存字典，生产环境应使用数据库）
tasks = {}


def allowed_file(filename: str, allowed_extensions: set) -> bool:
    """检查文件扩展名是否允许"""
    ext = os.path.splitext(filename)[1].lower()
    return ext in allowed_extensions


def process_task(task_id: str, video_path: str, audio_paths: list[str]):
    """
    后台处理任务：完整的分析 + 匹配 + 智能剪辑 + 生成流程

    v2.0 新增智能编辑管线：
    1. 电影识别（一致性锚定）
    2. 增强风格分析（带入电影知识）
    3. 音乐结构分析（段落识别）
    4. 场景检测 + 片段评分
    5. 智能匹配引擎
    6. 生成草稿
    """
    editing_mode = tasks[task_id].get("editing_mode", config.DEFAULT_EDITING_MODE)
    smart_enabled = getattr(config, "SMART_EDITING_ENABLED", True)

    try:
        # ---- 步骤 1：提取视频帧 ----
        tasks[task_id]["status"] = "extracting"
        tasks[task_id]["progress"] = 5
        tasks[task_id]["message"] = "正在提取视频帧..."

        frame_files, video_info = extract_frames(video_path, task_id)
        tasks[task_id]["video_info"] = video_info
        tasks[task_id]["frame_count"] = len(frame_files)
        tasks[task_id]["progress"] = 15
        sampled = sample_frames(frame_files)

        # ---- 步骤 2a：电影识别（新功能，提升一致性） ----
        movie_identity = None
        if smart_enabled:
            try:
                tasks[task_id]["status"] = "identifying_movie"
                tasks[task_id]["message"] = "🔍 AI 正在识别电影内容..."
                tasks[task_id]["progress"] = 18

                movie_identity = identify_movie(sampled)
                tasks[task_id]["movie_identity"] = movie_identity
            except Exception as e:
                print(f"[WARN] 电影识别失败（不影响后续流程）: {e}")
                movie_identity = None

        # ---- 步骤 2b：AI 分析电影风格（增强：结合电影知识） ----
        tasks[task_id]["status"] = "analyzing_style"
        tasks[task_id]["message"] = "AI 正在分析电影画面风格..."
        tasks[task_id]["progress"] = 22

        style_result = analyze_style(sampled, movie_identity)
        tasks[task_id]["style_analysis"] = style_result
        tasks[task_id]["progress"] = 35

        # ---- 步骤 3：分析所有音乐 ----
        tasks[task_id]["status"] = "analyzing_audio"
        tasks[task_id]["message"] = "正在分析音乐特征..."

        audio_features_list = []
        for i, audio_path in enumerate(audio_paths):
            feat = audio_analyze(audio_path)
            audio_features_list.append(feat)
            tasks[task_id]["progress"] = 35 + int(10 * (i + 1) / len(audio_paths))

        tasks[task_id]["audio_features"] = audio_features_list
        tasks[task_id]["progress"] = 45

        # ---- 步骤 3b：音乐结构分析（新功能） ----
        music_structure = None
        best_audio_path = audio_paths[0] if audio_paths else ""
        best_audio_features = audio_features_list[0] if audio_features_list else {}

        if smart_enabled and best_audio_path:
            try:
                tasks[task_id]["status"] = "analyzing_music_structure"
                tasks[task_id]["message"] = "🎵 AI 正在分析音乐结构..."
                tasks[task_id]["progress"] = 48

                music_structure = analyze_music_structure(
                    best_audio_path,
                    best_audio_features,
                    style_result,
                )
                tasks[task_id]["music_structure"] = music_structure
            except Exception as e:
                print(f"[WARN] 音乐结构分析失败（不影响后续流程）: {e}")
                music_structure = None

        # ---- 步骤 4：AI 匹配音乐与电影风格 ----
        tasks[task_id]["status"] = "matching"
        tasks[task_id]["message"] = "AI 正在匹配音乐与电影风格..."
        tasks[task_id]["progress"] = 55

        match_results = match_music_to_style(style_result, audio_features_list)
        tasks[task_id]["match_results"] = match_results
        tasks[task_id]["progress"] = 65

        # ---- 步骤 5：智能编辑管线（新功能） ----
        smart_segments = None
        if smart_enabled and match_results:
            best_match = match_results[0]
            try:
                # 5a: 场景检测
                tasks[task_id]["status"] = "detecting_scenes"
                tasks[task_id]["message"] = "🎬 正在检测视频场景..."
                tasks[task_id]["progress"] = 68

                video_dur = video_info.get("duration", 60)
                scenes = detect_scenes(video_path, video_duration=video_dur)
                tasks[task_id]["scene_count"] = len(scenes)

                # 5b: AI 片段评分
                tasks[task_id]["status"] = "scoring_segments"
                tasks[task_id]["message"] = f"🤖 AI 正在评估 {len(scenes)} 个片段的高光度..."
                tasks[task_id]["progress"] = 72

                scored = score_segments(
                    video_path, scenes, movie_identity, task_id, editing_mode
                )
                tasks[task_id]["scored_segments"] = scored

                # 5c: 智能匹配
                tasks[task_id]["status"] = "smart_matching"
                mode_label = "视频优先" if editing_mode == "video_first" else "音乐优先"
                tasks[task_id]["message"] = f"✂️ 智能匹配中（{mode_label}模式）..."
                tasks[task_id]["progress"] = 78

                smart_segments = assemble_smart_draft(
                    scored_segments=scored,
                    music_structure=music_structure or _fallback_structure(
                        best_match.get("duration_seconds", 60),
                        best_match.get("tempo_bpm", 120),
                    ),
                    video_info=video_info,
                    editing_mode=editing_mode,
                )
                tasks[task_id]["smart_segments_info"] = {
                    "mode": editing_mode,
                    "segment_count": len(smart_segments),
                    "scene_count": len(scenes),
                }

                tasks[task_id]["progress"] = 85

            except Exception as e:
                print(f"[WARN] 智能编辑失败，回退到节拍等分模式: {e}")
                smart_segments = None

        # ---- 步骤 6：生成剪映草稿 ----
        tasks[task_id]["status"] = "generating"
        tasks[task_id]["message"] = "正在生成剪映草稿..."
        tasks[task_id]["progress"] = 90

        if match_results:
            best_match = match_results[0]
            custom_output = tasks[task_id].get("custom_export_path")
            draft_info = create_draft(
                video_path=video_path,
                audio_path=best_match["file_path"],
                video_info=video_info,
                match_result=best_match,
                task_id=task_id,
                smart_segments=smart_segments,
                editing_mode=editing_mode if smart_segments else None,
                custom_output_dir=custom_output,
            )
            tasks[task_id]["draft_info"] = draft_info

        tasks[task_id]["status"] = "completed"
        tasks[task_id]["progress"] = 100
        tasks[task_id]["message"] = "✅ 处理完成！请在剪映中打开草稿查看。"

    except Exception as e:
        tasks[task_id]["status"] = "error"
        tasks[task_id]["message"] = f"❌ 处理出错: {str(e)}"
        import traceback
        tasks[task_id]["error_detail"] = traceback.format_exc()
        print(f"[ERROR] Task {task_id} failed:\n{tasks[task_id]['error_detail']}")


def _fallback_structure(duration: float, bpm: float) -> dict:
    """在音乐结构分析失败时构建最小结构"""
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


def process_task_video_only(task_id: str, video_path: str):
    """
    Phase 1：仅处理视频（抽帧 + 电影识别 + 分析风格），不处理音频
    完成后等待用户选择音乐来源
    """
    try:
        # ---- 步骤 1：提取视频帧 ----
        tasks[task_id]["status"] = "extracting"
        tasks[task_id]["progress"] = 15
        tasks[task_id]["message"] = "正在提取视频帧..."

        frame_files, video_info = extract_frames(video_path, task_id)
        tasks[task_id]["video_info"] = video_info
        tasks[task_id]["frame_count"] = len(frame_files)
        tasks[task_id]["progress"] = 30
        sampled = sample_frames(frame_files)

        # ---- 步骤 2a：电影识别（新） ----
        movie_identity = None
        if getattr(config, "SMART_EDITING_ENABLED", True):
            try:
                tasks[task_id]["message"] = "🔍 AI 正在识别电影内容..."
                movie_identity = identify_movie(sampled)
                tasks[task_id]["movie_identity"] = movie_identity
            except Exception as e:
                print(f"[WARN] 电影识别失败: {e}")

        # ---- 步骤 2b：AI 分析电影风格 ----
        tasks[task_id]["status"] = "analyzing_style"
        tasks[task_id]["message"] = "AI 正在分析电影画面风格..."
        tasks[task_id]["progress"] = 40

        style_result = analyze_style(sampled, movie_identity)
        tasks[task_id]["style_analysis"] = style_result
        tasks[task_id]["progress"] = 100

        # 风格分析完成，等待用户选择音乐来源
        tasks[task_id]["status"] = "style_ready"
        tasks[task_id]["message"] = "✅ 电影风格分析完成！请选择音乐来源。"

    except Exception as e:
        tasks[task_id]["status"] = "error"
        tasks[task_id]["message"] = f"❌ 处理出错: {str(e)}"
        import traceback
        tasks[task_id]["error_detail"] = traceback.format_exc()
        print(f"[ERROR] Task {task_id} failed:\n{tasks[task_id]['error_detail']}")


def process_task_with_ai_track(task_id: str, video_path: str, ai_track: dict):
    """
    Phase 3：用户选择了 AI 生成的音轨后，分析音频 + 匹配 + 智能剪辑 + 生成草稿
    """
    try:
        audio_path = ai_track.get("path")
        if not audio_path or not os.path.exists(audio_path):
            raise ValueError(f"AI 音轨文件不存在: {audio_path}")

        video_info = tasks[task_id].get("video_info", {})
        style_result = tasks[task_id].get("style_analysis", {})
        movie_identity = tasks[task_id].get("movie_identity")
        editing_mode = tasks[task_id].get("editing_mode", config.DEFAULT_EDITING_MODE)
        smart_enabled = getattr(config, "SMART_EDITING_ENABLED", True)

        # ---- 步骤 1：分析 AI 生成的音频 ----
        tasks[task_id]["status"] = "analyzing_audio"
        tasks[task_id]["message"] = "正在分析 AI 生成的音乐..."
        tasks[task_id]["progress"] = 50

        audio_feat = audio_analyze(audio_path)
        audio_feat["file_path"] = audio_path
        audio_feat["label"] = ai_track.get("label", "AI 生成音乐")
        audio_features_list = [audio_feat]
        tasks[task_id]["audio_features"] = audio_features_list

        # ---- 步骤 1b：音乐结构分析 ----
        music_structure = None
        if smart_enabled:
            try:
                tasks[task_id]["message"] = "🎵 AI 正在分析音乐结构..."
                tasks[task_id]["progress"] = 55
                music_structure = analyze_music_structure(
                    audio_path, audio_feat, style_result
                )
                tasks[task_id]["music_structure"] = music_structure
            except Exception as e:
                print(f"[WARN] 音乐结构分析失败: {e}")

        # ---- 步骤 2：AI 匹配 ----
        tasks[task_id]["status"] = "matching"
        tasks[task_id]["message"] = "AI 正在匹配音乐与电影风格..."
        tasks[task_id]["progress"] = 65

        match_results = match_music_to_style(style_result, audio_features_list)
        tasks[task_id]["match_results"] = match_results
        tasks[task_id]["progress"] = 75

        # ---- 步骤 3：智能编辑管线 ----
        smart_segments = None
        if smart_enabled and match_results:
            try:
                tasks[task_id]["status"] = "detecting_scenes"
                tasks[task_id]["message"] = "🎬 正在检测视频场景..."
                tasks[task_id]["progress"] = 78

                video_dur = video_info.get("duration", 60)
                scenes = detect_scenes(video_path, video_duration=video_dur)
                tasks[task_id]["scene_count"] = len(scenes)

                tasks[task_id]["status"] = "scoring_segments"
                tasks[task_id]["message"] = f"🤖 AI 正在评估 {len(scenes)} 个片段..."
                tasks[task_id]["progress"] = 82

                scored = score_segments(
                    video_path, scenes, movie_identity, task_id, editing_mode
                )

                tasks[task_id]["status"] = "smart_matching"
                tasks[task_id]["message"] = f"✂️ 智能匹配中（{editing_mode}模式）..."
                tasks[task_id]["progress"] = 88

                smart_segments = assemble_smart_draft(
                    scored_segments=scored,
                    music_structure=music_structure or _fallback_structure(
                        audio_feat.get("duration_seconds", 60),
                        audio_feat.get("tempo_bpm", 120),
                    ),
                    video_info=video_info,
                    editing_mode=editing_mode,
                )
                tasks[task_id]["smart_segments_info"] = {
                    "mode": editing_mode,
                    "segment_count": len(smart_segments),
                    "scene_count": len(scenes),
                }
            except Exception as e:
                print(f"[WARN] 智能编辑失败，回退: {e}")

        # ---- 步骤 4：生成剪映草稿 ----
        tasks[task_id]["status"] = "generating"
        tasks[task_id]["message"] = "正在生成剪映草稿..."
        tasks[task_id]["progress"] = 92

        if match_results:
            best_match = match_results[0]
            custom_output = tasks[task_id].get("custom_export_path")
            draft_info = create_draft(
                video_path=video_path,
                audio_path=audio_path,
                video_info=video_info,
                match_result=best_match,
                task_id=task_id,
                smart_segments=smart_segments,
                editing_mode=editing_mode if smart_segments else None,
                custom_output_dir=custom_output,
            )
            tasks[task_id]["draft_info"] = draft_info

        tasks[task_id]["status"] = "completed"
        tasks[task_id]["progress"] = 100
        tasks[task_id]["message"] = "✅ 处理完成！请在剪映中打开草稿查看。"

    except Exception as e:
        tasks[task_id]["status"] = "error"
        tasks[task_id]["message"] = f"❌ 处理出错: {str(e)}"
        import traceback
        tasks[task_id]["error_detail"] = traceback.format_exc()
        print(f"[ERROR] Task {task_id} failed:\n{tasks[task_id]['error_detail']}")


# ============================================
# 路由
# ============================================

@app.route("/")
def index():
    """主页"""
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    """上传电影素材（+ 可选音乐文件）"""
    task_id = str(uuid.uuid4())[:12]
    mode = request.form.get("mode", "manual")  # "manual" | "ai"

    # 检查视频文件
    video_server_path = request.form.get("video_server_path", "").strip()
    video_filename_override = request.form.get("video_filename", "").strip()

    # 创建任务目录
    task_dir = os.path.join(config.UPLOAD_FOLDER, task_id)
    os.makedirs(task_dir, exist_ok=True)

    # 视频来源：优先使用服务器上已有的路径（URL下载），否则保存上传文件
    if video_server_path and os.path.isfile(video_server_path):
        video_filename = video_filename_override or os.path.basename(video_server_path)
        video_path = video_server_path  # 直接使用已有文件
        print(f"[Upload] 使用已下载视频: {video_path}")
    else:
        if "video" not in request.files:
            return jsonify({"error": "请上传电影素材（视频文件）"}), 400
        video_file = request.files["video"]
        if video_file.filename == "":
            return jsonify({"error": "请选择视频文件"}), 400
        if not allowed_file(video_file.filename, config.ALLOWED_VIDEO_EXTENSIONS):
            return jsonify({
                "error": f"不支持的视频格式。支持: {', '.join(config.ALLOWED_VIDEO_EXTENSIONS)}"
            }), 400
        video_filename = video_file.filename
        video_path = os.path.join(task_dir, video_filename)
        video_file.save(video_path)

    # ---- AI 模式：只上传视频，稍后 AI 生成音乐 ----
    if mode == "ai":
        editing_mode = request.form.get("editing_mode", config.DEFAULT_EDITING_MODE)
        custom_export_path = request.form.get("custom_export_path", "").strip()
        tasks[task_id] = {
            "id": task_id,
            "mode": "ai",
            "status": "uploaded",
            "progress": 0,
            "message": "视频已上传，正在分析影片风格...",
            "video_path": video_path,
            "video_filename": video_filename,
            "editing_mode": editing_mode,
            "custom_export_path": custom_export_path if custom_export_path else None,
        }

        thread = threading.Thread(
            target=process_task_video_only,
            args=(task_id, video_path),
            daemon=True,
        )
        thread.start()

        return jsonify({
            "task_id": task_id,
            "mode": "ai",
            "message": "上传成功，正在分析影片风格...",
        })

    # ---- 手动模式：需要音频文件 ----
    audio_files = request.files.getlist("audio")
    if not audio_files or audio_files[0].filename == "":
        return jsonify({"error": "请至少上传一首音乐文件，或切换到 AI 生成模式"}), 400

    # 保存所有音频
    audio_paths = []
    audio_server_paths = request.form.get("audio_server_paths", "").strip()
    audio_filenames_list = request.form.get("audio_filenames_list", "").strip()

    # 优先使用服务器已有的音频路径
    if audio_server_paths:
        for p in audio_server_paths.split(","):
            p = p.strip()
            if p and os.path.isfile(p):
                audio_paths.append(p)
                print(f"[Upload] 使用已下载音频: {p}")

    # 也处理直接上传的音频文件
    for audio_file in audio_files:
        if audio_file.filename == "":
            continue
        if not allowed_file(audio_file.filename, config.ALLOWED_AUDIO_EXTENSIONS):
            continue
        audio_path = os.path.join(task_dir, audio_file.filename)
        audio_file.save(audio_path)
        audio_paths.append(audio_path)

    if not audio_paths:
        return jsonify({"error": "没有有效的音乐文件"}), 400

    # 获取剪辑模式和自定义导出路径
    editing_mode = request.form.get("editing_mode", config.DEFAULT_EDITING_MODE)
    custom_export_path = request.form.get("custom_export_path", "").strip()

    # 初始化任务
    tasks[task_id] = {
        "id": task_id,
        "mode": "manual",
        "status": "uploaded",
        "progress": 0,
        "message": "文件已上传，等待处理...",
        "video_path": video_path,
        "audio_paths": audio_paths,
        "video_filename": video_filename,
        "audio_filenames": [os.path.basename(p) for p in audio_paths],
        "editing_mode": editing_mode,
        "custom_export_path": custom_export_path if custom_export_path else None,
    }

    # 启动后台处理
    thread = threading.Thread(
        target=process_task,
        args=(task_id, video_path, audio_paths),
        daemon=True,
    )
    thread.start()

    return jsonify({
        "task_id": task_id,
        "mode": "manual",
        "message": "上传成功，正在后台处理...",
    })


@app.route("/status/<task_id>")
def task_status(task_id: str):
    """查询任务状态"""
    if task_id not in tasks:
        return jsonify({"error": "任务不存在"}), 404

    task = tasks[task_id]
    status = task.get("status", "")

    # 在 style_ready / ai_music_ready / completed 状态时返回风格分析
    include_style = status in ("style_ready", "ai_music_ready", "completed")
    include_match = status == "completed"

    return jsonify({
        "task_id": task_id,
        "mode": task.get("mode", "manual"),
        "status": status,
        "progress": task["progress"],
        "message": task.get("message", ""),
        "style_analysis": task.get("style_analysis") if include_style else None,
        "match_results": task.get("match_results") if include_match else None,
        "draft_info": task.get("draft_info") if include_match else None,
        "video_info": task.get("video_info") if include_match else None,
        "ai_tracks": task.get("ai_tracks") if status == "ai_music_ready" else None,
        "editing_mode": task.get("editing_mode", ""),
        "movie_identity": task.get("movie_identity") if include_style else None,
        "music_structure": task.get("music_structure") if include_match else None,
        "smart_segments_info": task.get("smart_segments_info") if include_match else None,
        "scene_count": task.get("scene_count", 0) if include_match else 0,
        "export_path": task.get("custom_export_path") or config.OUTPUT_FOLDER,
    })


@app.route("/generate-ai-music/<task_id>", methods=["POST"])
def generate_ai_music(task_id: str):
    """
    Phase 2：根据风格分析结果生成 AI 音乐
    调用 AI 音乐生成 API，生成 2-3 首备选曲目
    """
    if task_id not in tasks:
        return jsonify({"error": "任务不存在"}), 404

    task = tasks[task_id]
    if task.get("status") != "style_ready":
        return jsonify({"error": "风格分析尚未完成，请等待"}), 400

    style_analysis = task.get("style_analysis")
    if not style_analysis:
        return jsonify({"error": "风格分析结果不可用"}), 500

    # 更新状态为正在生成
    task["status"] = "generating_music"
    task["progress"] = 100
    task["message"] = "AI 正在生成匹配音乐..."

    # 在后台线程中生成音乐（避免阻塞请求）
    def _generate():
        try:
            ai_tracks = generate_music_options(
                style_analysis=style_analysis,
                task_id=task_id,
            )
            task["ai_tracks"] = ai_tracks

            # 过滤成功的曲目
            success_tracks = [t for t in ai_tracks if t.get("success")]
            if success_tracks:
                task["status"] = "ai_music_ready"
                task["message"] = f"✅ AI 已生成 {len(success_tracks)} 首备选音乐，请选择一首"
                task["progress"] = 100
            else:
                task["status"] = "style_ready"  # 回退
                task["message"] = "⚠️ AI 音乐生成失败，请手动上传音乐或重试"
                task["progress"] = 100

        except Exception as e:
            task["status"] = "style_ready"
            task["message"] = f"⚠️ AI 音乐生成出错: {str(e)[:100]}"
            import traceback
            print(f"❌ AI 音乐生成失败:\n{traceback.format_exc()}")

    thread = threading.Thread(target=_generate, daemon=True)
    thread.start()

    return jsonify({
        "task_id": task_id,
        "message": "AI 音乐生成已启动，请等待...",
    })


@app.route("/select-ai-track/<task_id>/<int:track_index>", methods=["POST"])
def select_ai_track(task_id: str, track_index: int):
    """
    Phase 3：用户选择了某首 AI 音乐，继续生成草稿
    """
    if task_id not in tasks:
        return jsonify({"error": "任务不存在"}), 404

    task = tasks[task_id]
    if task.get("status") != "ai_music_ready":
        return jsonify({"error": "AI 音乐尚未就绪，请等待生成完成"}), 400

    ai_tracks = task.get("ai_tracks", [])
    if track_index < 0 or track_index >= len(ai_tracks):
        return jsonify({"error": f"无效的曲目索引: {track_index}"}), 400

    selected_track = ai_tracks[track_index]
    if not selected_track.get("success"):
        return jsonify({"error": "该曲目生成失败，请选择其他曲目"}), 400

    video_path = task.get("video_path")
    if not video_path:
        return jsonify({"error": "视频文件路径丢失"}), 500

    # 更新状态
    task["status"] = "selected_track"
    task["selected_track"] = selected_track
    task["message"] = f"已选择: {selected_track.get('label', 'AI 音乐')}，正在分析..."
    task["progress"] = 50

    # 后台继续处理
    thread = threading.Thread(
        target=process_task_with_ai_track,
        args=(task_id, video_path, selected_track),
        daemon=True,
    )
    thread.start()

    return jsonify({
        "task_id": task_id,
        "message": "已选择 AI 音乐，正在生成草稿...",
    })


@app.route("/frames/<task_id>/<filename>")
def serve_frame(task_id: str, filename: str):
    """提供帧图片访问"""
    frame_dir = os.path.join(config.FRAME_FOLDER, task_id)
    return send_from_directory(frame_dir, filename)


@app.route("/ai-music/<task_id>/<filename>")
def serve_ai_music(task_id: str, filename: str):
    """提供 AI 生成的音乐文件访问（用于前端试听）"""
    music_dir = os.path.join(config.UPLOAD_FOLDER, task_id, "ai_music")
    return send_from_directory(music_dir, filename)


# ============================================
# 更新相关路由
# ============================================

@app.route("/api/version-info")
def api_version_info():
    """获取当前应用版本和编辑器兼容性信息"""
    editor = detect_editor_info()
    compat = get_compatibility_info(editor.get("editor_version"))
    return jsonify(compat)


@app.route("/api/check-update")
def api_check_update():
    """检查是否有可用更新"""
    result = check_for_updates()
    return jsonify(result)


@app.route("/api/start-update", methods=["POST"])
def api_start_update():
    """开始更新流程"""
    result = perform_update()
    return jsonify(result)


@app.route("/api/update-status")
def api_update_status():
    """查询更新进度"""
    return jsonify(get_update_status())


@app.route("/api/tutorial")
def api_tutorial():
    """
    返回使用教程的 HTML 内容。
    从桌面文件读取，管理员可直接编辑该文件。
    """
    tutorial_path = os.path.expanduser(r"~\Desktop\MovieMusicMatcher_教程.md")

    try:
        if not os.path.exists(tutorial_path):
            return jsonify({"html": "<p style='color:var(--text-secondary)'>教程文件不存在，请在桌面创建 MovieMusicMatcher_教程.md</p>"})

        with open(tutorial_path, "r", encoding="utf-8") as f:
            md_text = f.read()

        if not md_text.strip():
            return jsonify({"html": "<p style='color:var(--text-secondary)'>教程内容为空，请编辑桌面上的 MovieMusicMatcher_教程.md</p>"})

        html_content = _md_to_html(md_text)
        return jsonify({"html": html_content})

    except Exception as e:
        return jsonify({"html": f"<p style='color:var(--error)'>读取教程失败: {e}</p>"})


@app.route("/api/default-export-path")
def api_default_export_path():
    """返回默认导出路径和系统常用路径，供前端初始化"""
    import platform as _platform
    home = os.path.expanduser("~")
    system = _platform.system()

    # 根据操作系统构建常用路径
    common_paths = [config.OUTPUT_FOLDER]
    if system == "Windows":
        common_paths += [
            os.path.join(home, "Desktop"),
            os.path.join(home, "Documents"),
            os.path.join(home, "Downloads"),
            os.path.join(home, "Videos"),
            os.path.join(home, "Movies"),
        ]
    elif system == "Darwin":  # macOS
        common_paths += [
            os.path.join(home, "Desktop"),
            os.path.join(home, "Documents"),
            os.path.join(home, "Downloads"),
            os.path.join(home, "Movies"),
            os.path.join(home, "Music"),
        ]
    else:  # Linux
        common_paths += [
            os.path.join(home, "Desktop"),
            os.path.join(home, "Documents"),
            os.path.join(home, "Downloads"),
            os.path.join(home, "Videos"),
        ]

    # 去重且只保留存在的路径
    seen = set()
    available = []
    for p in common_paths:
        p = os.path.normpath(p)
        if p not in seen:
            seen.add(p)
            available.append({
                "path": p,
                "label": os.path.basename(p),
                "exists": os.path.isdir(p),
            })

    return jsonify({
        "default_path": config.OUTPUT_FOLDER,
        "capcut_draft_dir": config.CAPCUT_DRAFT_DIR,
        "system": system,
        "home": home,
        "common_paths": available,
    })


@app.route("/health")
def health():
    """健康检查 — 实际验证 FFmpeg 是否可用"""
    from modules.frame_extractor import is_ffmpeg_available
    return jsonify({
        "status": "ok",
        "platform": sys.platform,
        "ffmpeg_ready": is_ffmpeg_available(),
        "api_configured": bool(config.ANTHROPIC_API_KEY and config.ANTHROPIC_API_KEY.strip()),
    })


# ============================================
# URL 上传 — 从社交媒体 / 链接下载素材
# ============================================

# 常见社交媒体域名识别
SOCIAL_MEDIA_DOMAINS = {
    "weixin.qq.com": "微信",
    "wechat.com": "微信",
    "pan.baidu.com": "百度网盘",
    "bilibili.com": "B站",
    "b23.tv": "B站",
    "youtube.com": "YouTube",
    "youtu.be": "YouTube",
    "douyin.com": "抖音",
    "tiktok.com": "TikTok",
    "xiaohongshu.com": "小红书",
    "xhslink.com": "小红书",
    "kuaishou.com": "快手",
    "weibo.com": "微博",
    "qq.com": "QQ",
    "v.qq.com": "腾讯视频",
    "iqiyi.com": "爱奇艺",
    "youku.com": "优酷",
    "mg.tv": "芒果TV",
    "drive.google.com": "Google Drive",
    "dropbox.com": "Dropbox",
}

def _detect_platform(url: str) -> str:
    """识别 URL 来自哪个平台"""
    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        for domain, name in SOCIAL_MEDIA_DOMAINS.items():
            if domain in host:
                return name
    except Exception:
        pass
    return "URL"


def _is_media_url(url: str) -> bool:
    """检查 URL 是否直接指向媒体文件"""
    ext = os.path.splitext(urllib.parse.urlparse(url).path)[1].lower()
    return ext in config.ALLOWED_VIDEO_EXTENSIONS or ext in config.ALLOWED_AUDIO_EXTENSIONS


@app.route("/api/upload/url", methods=["POST"])
def api_upload_url():
    """从 URL 下载视频/音频素材"""
    data = request.get_json() if request.is_json else {}
    url = (data.get("url") or "").strip()

    if not url:
        return jsonify({"error": "请提供媒体文件链接"}), 400

    # 验证 URL
    if not url.startswith(("http://", "https://")):
        return jsonify({"error": "仅支持 http/https 链接"}), 400

    media_type = data.get("type", "auto")  # "video" | "audio" | "auto"
    project_slug = data.get("project_slug", "").strip()

    platform = _detect_platform(url)
    print(f"[URL Upload] 检测到平台: {platform}, URL: {url[:80]}...")

    # 创建临时任务目录
    task_id = str(uuid.uuid4())[:12]
    task_dir = os.path.join(config.UPLOAD_FOLDER, task_id)
    os.makedirs(task_dir, exist_ok=True)

    try:
        # 设置 User-Agent 避免被拒绝
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Accept": "*/*",
        })

        print(f"[URL Upload] 开始下载: {url[:100]}...")
        with urllib.request.urlopen(req, timeout=60) as response:
            content_type = response.headers.get("Content-Type", "")
            content_disposition = response.headers.get("Content-Disposition", "")
            content_length = response.headers.get("Content-Length", "")

            # 确定文件名
            filename = None
            # 优先从 Content-Disposition 提取
            if "filename=" in content_disposition:
                import re as _re
                match = _re.search(r'filename[^;=\n]*=["\']?([^"\';\n]*)', content_disposition)
                if match:
                    filename = match.group(1).strip()

            if not filename:
                # 从 URL 路径提取
                parsed_path = urllib.parse.urlparse(url).path
                filename = os.path.basename(parsed_path)
                if not filename or "." not in filename:
                    # 根据 content-type 推断扩展名
                    ext = mimetypes.guess_extension(content_type.split(";")[0].strip())
                    if not ext:
                        ext = ".mp4" if media_type == "video" else ".mp3"
                    filename = f"download_{task_id}{ext}"

            # 安全检查：确保文件名安全
            filename = "".join(c for c in filename if c.isascii() and c not in r'<>:"/\|?*')
            if not filename:
                filename = f"download_{task_id}.mp4"

            # 检查文件大小
            size_mb = 0
            if content_length:
                size_mb = int(content_length) / (1024 * 1024)

            max_mb = config.MAX_VIDEO_SIZE_MB if media_type == "video" else config.MAX_AUDIO_SIZE_MB
            if size_mb > max_mb:
                return jsonify({
                    "error": f"文件过大 ({size_mb:.0f}MB)，上限 {max_mb}MB"
                }), 413

            # 下载文件
            file_path = os.path.join(task_dir, filename)
            downloaded = 0
            with open(file_path, "wb") as f:
                while True:
                    chunk = response.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    # 进度保护：超过上限则中止
                    if downloaded > max_mb * 1024 * 1024 + 10 * 1024 * 1024:
                        f.close()
                        os.unlink(file_path)
                        return jsonify({"error": f"文件实际大小超过上限 {max_mb}MB"}), 413

            actual_mb = downloaded / (1024 * 1024)
            print(f"[URL Upload] 下载完成: {filename} ({actual_mb:.1f}MB)")

            # 检测实际文件类型
            ext = os.path.splitext(filename)[1].lower()
            determined_type = media_type
            if determined_type == "auto":
                if ext in config.ALLOWED_VIDEO_EXTENSIONS:
                    determined_type = "video"
                elif ext in config.ALLOWED_AUDIO_EXTENSIONS:
                    determined_type = "audio"
                else:
                    # 尝试用 ffprobe 探测
                    try:
                        from modules.frame_extractor import get_video_info
                        probe = get_video_info(file_path)
                        determined_type = "video" if probe.get("width", 0) > 0 else "audio"
                    except Exception:
                        determined_type = "video" if ext in {".mp4", ".mov", ".avi", ".mkv"} else "audio"

            return jsonify({
                "task_id": task_id,
                "type": determined_type,
                "filename": filename,
                "file_path": file_path,
                "size_mb": round(actual_mb, 1),
                "platform": platform,
                "message": f"✅ 从{platform}下载完成: {filename} ({actual_mb:.1f}MB)",
            })

    except urllib.error.HTTPError as e:
        return jsonify({
            "error": f"下载失败 (HTTP {e.code}): 链接可能已过期或需要权限"
        }), 502
    except urllib.error.URLError as e:
        return jsonify({
            "error": f"无法连接到服务器: {str(e.reason)}"
        }), 502
    except Exception as e:
        print(f"[URL Upload] 错误: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"下载失败: {str(e)}"}), 500


# ============================================
# v3.0 管道阶段处理函数
# ============================================

def _get_task_safe(task_id: str) -> dict:
    """安全获取任务，不存在时返回 None"""
    return tasks.get(task_id)


def _abort_if_error(task_id: str) -> bool:
    """检查任务是否处于错误状态，是则返回 True"""
    task = _get_task_safe(task_id)
    if task and task.get("status") == "error":
        return True
    return False


def run_media_scan(task_id: str):
    """v3 阶段 2：媒体扫描 + 帧提取（为后续阶段准备帧数据）"""
    task = _get_task_safe(task_id)
    if not task:
        return

    try:
        video_path = task.get("video_path", "")
        audio_paths = task.get("audio_paths", [])
        run_path = task.get("run_path", "")

        # Step A: 扫描媒体文件
        task["status"] = "scanning"
        task["phase"] = "media_scan"
        task["progress"] = 2
        task["message"] = "正在扫描媒体文件..."

        manifest = scan_media(video_path, audio_paths, run_path)
        task["manifest"] = manifest
        task["scan_preview"] = build_scan_preview(manifest)
        task["progress"] = 8

        # Step B: 提取视频帧（为素材审查做准备）
        if video_path and os.path.exists(video_path):
            task["message"] = "正在提取视频帧..."
            task["progress"] = 10
            try:
                from modules.frame_extractor import extract_frames as _extract
                frame_files, video_info = _extract(video_path, task_id)
                task["frame_files"] = frame_files
                task["video_info"] = video_info
                task["progress"] = 15
            except Exception as e:
                print(f"   [WARN] 帧提取失败（不影响扫描完成）: {e}")
                task.setdefault("video_info", {})
                task.setdefault("frame_files", [])

        task["status"] = "scan_complete"
        task["progress"] = 15
        task["message"] = "媒体扫描完成（含帧提取），请确认素材审查"

    except Exception as e:
        task["status"] = "error"
        task["message"] = f"❌ 媒体扫描失败: {str(e)}"
        import traceback
        task["error_detail"] = traceback.format_exc()
        print(f"[ERROR] Media scan failed for {task_id}:\n{task['error_detail']}")


def run_material_review(task_id: str):
    """v3 阶段 3：素材审查（使用扫描阶段已提取的帧，无需重复提取）"""
    task = _get_task_safe(task_id)
    if not task:
        return

    try:
        task["status"] = "reviewing"
        task["phase"] = "material_review"
        task["progress"] = 18
        task["message"] = "AI 正在审查素材（风格分析+分类）..."

        video_path = task.get("video_path", "")
        run_path = task.get("run_path", "")
        frame_files = task.get("frame_files", [])
        video_info = task.get("video_info", {})
        editing_mode = task.get("editing_mode", "video_first")

        # 如果扫描阶段未提取帧（极少情况），在此补提
        if not frame_files and video_path:
            print("   [INFO] 扫描阶段未提取帧，在此补提...")
            try:
                from modules.frame_extractor import extract_frames as _extract
                frame_files, video_info = _extract(video_path, task_id)
                task["frame_files"] = frame_files
                task["video_info"] = video_info
            except Exception as e:
                print(f"   [WARN] 补提帧失败: {e}")

        # 执行素材审查（即使帧为空也能产生启发式结果）
        review = review_material(
            frame_files=frame_files or [],
            video_info=video_info or {},
            run_path=run_path,
            editing_mode=editing_mode,
        )
        task["review"] = review
        task["review_display"] = taxonomy_to_display(review)

        task["progress"] = 30
        task["status"] = "review_complete"
        task["message"] = "素材审查完成，请确认后继续"

    except Exception as e:
        task["status"] = "scan_complete"  # 回退到扫描完成状态，允许重试
        task["message"] = f"⚠️ 素材审查失败（可重试）: {str(e)[:100]}"
        print(f"[WARN] Material review failed for {task_id}: {e}")


def run_story(task_id: str):
    """v3 阶段 4：故事开发（允许空 review 数据，使用模板回退）"""
    task = _get_task_safe(task_id)
    if not task:
        return

    try:
        task["status"] = "developing_story"
        task["phase"] = "story"
        task["progress"] = 32
        task["message"] = "AI 正在开发叙事结构..."

        review = task.get("review", {})
        brief = task.get("brief", {})
        run_path = task.get("run_path", "")

        # 确保 review 有最小结构
        if not review:
            review = {
                "style_analysis": {"genre": "短片", "mood": "neutral", "themes": []},
                "taxonomy": {"emotion": {"emotional_arc": ""}, "action": {"action_intensity": "medium"}},
                "identified_movie": {"identified": False},
            }

        task["progress"] = 38
        script = develop_story(review, brief, run_path)
        task["story"] = script
        task["story_display"] = story_to_display(script)

        task["progress"] = 45
        task["status"] = "story_complete"
        task["message"] = "故事开发完成，请确认后继续（可跳过）"

    except Exception as e:
        task["status"] = "review_complete"  # 回退，允许跳过
        task["message"] = f"⚠️ 故事开发失败（可跳过）: {str(e)[:100]}"
        print(f"[WARN] Story development failed for {task_id}: {e}")


def run_blueprint(task_id: str):
    """v3 阶段 5：剪辑蓝图生成（允许部分数据缺失，产生可用蓝图）"""
    task = _get_task_safe(task_id)
    if not task:
        return

    try:
        task["status"] = "generating_blueprint"
        task["phase"] = "blueprint"
        task["progress"] = 47
        task["message"] = "正在生成剪辑蓝图..."

        video_path = task.get("video_path", "")
        audio_paths = task.get("audio_paths", [])
        audio_path = audio_paths[0] if audio_paths else ""
        run_path = task.get("run_path", "")
        review = task.get("review", {})
        brief = task.get("brief", {})
        video_info = task.get("video_info", {})
        editing_mode = task.get("editing_mode", "video_first")
        music_structure = task.get("music_structure")

        # 确保 review 有最小结构
        if not review:
            review = {
                "style_analysis": {"genre": "短片", "mood": "neutral", "themes": []},
                "taxonomy": {"emotion": {"emotional_arc": ""}, "action": {"action_intensity": "medium"}},
                "video_info": video_info or {"duration": 60, "fps": 30, "width": 1920, "height": 1080},
            }

        # 音频分析（如果没有预先分析）
        audio_features = None
        if audio_path and os.path.exists(audio_path):
            try:
                from modules.music_matcher import analyze_audio
                audio_features = analyze_audio(audio_path)
                task["audio_features"] = [audio_features]
            except Exception as e:
                print(f"   [WARN] 音频分析失败: {e}")

        blueprint = generate_blueprint(
            video_path=video_path,
            audio_path=audio_path,
            video_info=video_info,
            material_review=review,
            project_brief=brief,
            run_path=run_path,
            task_id=task_id,
            editing_mode=editing_mode,
            music_structure=music_structure,
            audio_features=audio_features,
        )
        task["blueprint"] = blueprint
        task["blueprint_display"] = blueprint_to_display(blueprint)

        task["progress"] = 70
        task["status"] = "blueprint_complete"
        task["message"] = "剪辑蓝图已生成，请审查后确认"

    except Exception as e:
        task["status"] = "error"
        task["message"] = f"❌ 蓝图生成失败: {str(e)}"
        import traceback
        task["error_detail"] = traceback.format_exc()
        print(f"[ERROR] Blueprint generation failed for {task_id}:\n{task['error_detail']}")


def run_validate(task_id: str):
    """v3 阶段 6：蓝图验证"""
    task = _get_task_safe(task_id)
    if not task:
        return

    try:
        task["status"] = "validating"
        task["phase"] = "validate"
        task["progress"] = 72
        task["message"] = "正在验证剪辑蓝图..."

        blueprint = task.get("blueprint", {})
        run_path = task.get("run_path", "")

        validation = validate_bp(blueprint)
        task["validation"] = validation

        if run_path:
            save_artifact(run_path, "blueprint-audit", validation)

        # 如果有错误，尝试自动修复
        if not validation.get("passed", False):
            try:
                fixed_bp = suggest_fixes(validation, blueprint)
                if fixed_bp:
                    task["blueprint"] = fixed_bp
                    task["blueprint_display"] = blueprint_to_display(fixed_bp)
                    # 重新验证
                    validation2 = validate_bp(fixed_bp)
                    task["validation"] = validation2
                    if run_path:
                        save_artifact(run_path, "blueprint-audit", validation2)
                    if validation2.get("passed", False):
                        task["message"] = "✅ 蓝图已自动修复并通过验证"
            except Exception as e:
                print(f"   [WARN] 自动修复失败: {e}")

        task["progress"] = 80
        task["status"] = "validation_complete"
        if not task.get("message"):
            task["message"] = "🔍 蓝图验证完成，请确认后开始构建"

    except Exception as e:
        task["status"] = "error"
        task["message"] = f"❌ 蓝图验证失败: {str(e)}"
        import traceback
        task["error_detail"] = traceback.format_exc()
        print(f"[ERROR] Blueprint validation failed for {task_id}:\n{task['error_detail']}")


def run_build(task_id: str):
    """v3 阶段 7：构建草稿 + 审计"""
    task = _get_task_safe(task_id)
    if not task:
        return

    try:
        task["status"] = "building"
        task["phase"] = "build"
        task["progress"] = 82
        task["message"] = "正在生成剪映草稿..."

        video_path = task.get("video_path", "")
        audio_paths = task.get("audio_paths", [])
        audio_path = audio_paths[0] if audio_paths else ""
        video_info = task.get("video_info", {})
        blueprint = task.get("blueprint", {})
        review = task.get("review", {})
        story = task.get("story", {})
        run_path = task.get("run_path", "")
        editing_mode = task.get("editing_mode", "video_first")
        custom_output = task.get("custom_export_path")

        # 从 blueprint 中提取 smart_segments（兼容 create_draft 接口）
        smart_segments = []
        for clip in blueprint.get("clips", []):
            if clip.get("media_type") == "video":
                smart_segments.append({
                    "source_start": clip.get("source_in_seconds", 0),
                    "source_duration": clip.get("source_out_seconds", 0) - clip.get("source_in_seconds", 0),
                    "target_start": clip.get("timeline_in_seconds", 0),
                    "match_rationale": clip.get("purpose", ""),
                    "segment_score": clip.get("highlight_score", 0),
                    "emotional_tone": clip.get("emotional_tone", ""),
                })

        # 构建匹配结果兼容格式
        audio_features = task.get("audio_features", [{}])
        match_result = audio_features[0] if audio_features else {}
        match_result["file_path"] = audio_path

        # 获取简报参数
        brief = task.get("brief", {})
        project_name = brief.get("topic", "") or brief.get("project_name", "")
        platform = brief.get("platform", "jianying")
        aspect_ratio = brief.get("aspect_ratio", "16:9")
        target_duration = brief.get("target_duration_seconds", 0)

        # 生成草稿
        from modules.draft_generator import create_draft as gen_draft
        draft_info = gen_draft(
            video_path=video_path,
            audio_path=audio_path,
            video_info=video_info,
            match_result=match_result,
            task_id=task_id,
            smart_segments=smart_segments if smart_segments else None,
            editing_mode=editing_mode if smart_segments else None,
            custom_output_dir=custom_output if custom_output else None,
            project_name=project_name,
            platform=platform,
            aspect_ratio=aspect_ratio,
            target_duration=target_duration,
        )
        task["draft_info"] = draft_info

        task["progress"] = 90
        task["message"] = "正在审计交付..."

        # 交付审计
        audit_report = audit_delivery(
            blueprint=blueprint,
            draft_info=draft_info,
            material_review=review,
            story_script=story,
            run_path=run_path,
        )
        task["audit"] = audit_report

        # 补拍报告
        pickup_report = generate_pickup_report(
            blueprint=blueprint,
            material_review=review,
            story_script=story,
            run_path=run_path,
        )
        task["pickup"] = pickup_report
        task["pickup_display"] = pickup_to_display(pickup_report)

        task["status"] = "completed"
        task["progress"] = 100
        task["message"] = "✅ 全部完成！草稿已生成，请在剪映中查看。"

    except Exception as e:
        task["status"] = "error"
        task["message"] = f"❌ 构建失败: {str(e)}"
        import traceback
        task["error_detail"] = traceback.format_exc()
        print(f"[ERROR] Build failed for {task_id}:\n{task['error_detail']}")


# v3 阶段分发器
PHASE_HANDLERS = {
    "media_scan": run_media_scan,
    "material_review": run_material_review,
    "story": run_story,
    "blueprint": run_blueprint,
    "validate": run_validate,
    "build": run_build,
}

PHASE_FLOW = [
    "media_scan",
    "material_review",
    "story",
    "blueprint",
    "validate",
    "build",
]


def _get_next_phase(current_phase: str) -> str | None:
    """获取下一阶段名称"""
    try:
        idx = PHASE_FLOW.index(current_phase)
        if idx + 1 < len(PHASE_FLOW):
            return PHASE_FLOW[idx + 1]
    except ValueError:
        pass
    return None


def _launch_phase(task_id: str, phase_name: str):
    """在后台线程中启动管道阶段"""
    handler = PHASE_HANDLERS.get(phase_name)
    if handler:
        thread = threading.Thread(target=handler, args=(task_id,), daemon=True)
        thread.start()
        return True
    return False


# ============================================
# v3.0 API 路由
# ============================================

@app.route("/api/brief/create", methods=["POST"])
def api_create_brief():
    """v3 Phase 1：创建项目简报"""
    try:
        form_data = request.get_json() if request.is_json else request.form.to_dict()
        brief = create_brief(form_data)

        # 创建任务 ID
        task_id = brief.get("project_slug", str(uuid.uuid4())[:12])

        tasks[task_id] = {
            "id": task_id,
            "mode": "v3",
            "phase": "brief",
            "status": "brief_created",
            "progress": 0,
            "message": "✅ 项目简报已创建，请上传视频和音乐",
            "brief": brief,
            "brief_display": brief_to_display(brief),
            "run_path": brief.get("run_path", ""),
            "project_slug": brief.get("project_slug", ""),
        }

        prefs = brief.get("editing_preferences", {})
        prefs_summary = prefs.get("summary", "")
        ai_interp = prefs.get("ai_interpretation", "")

        return jsonify({
            "task_id": task_id,
            "project_slug": brief.get("project_slug", ""),
            "brief": brief_to_display(brief),
            "message": "简报已创建，请上传素材",
            "preferences_summary": prefs_summary,
            "ai_interpretation": ai_interp,
        })

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"创建简报失败: {str(e)}"}), 500


@app.route("/api/upload/v3", methods=["POST"])
def api_upload_v3():
    """v3 Phase 2：上传视频和音乐，触发媒体扫描"""
    project_slug = request.form.get("project_slug", "").strip()

    if not project_slug:
        return jsonify({"error": "请先创建项目简报（project_slug 不能为空）"}), 400

    # 检查 video 文件
    video_server_path = request.form.get("video_server_path", "").strip()
    video_filename_override = request.form.get("video_filename", "").strip()

    # 创建任务目录
    task_dir = os.path.join(config.UPLOAD_FOLDER, project_slug)
    os.makedirs(task_dir, exist_ok=True)

    # 视频来源：优先使用服务器上已有的路径（URL下载），否则保存上传文件
    if video_server_path and os.path.isfile(video_server_path):
        video_filename = video_filename_override or os.path.basename(video_server_path)
        video_path = video_server_path  # 直接使用已有文件
        print(f"[V3 Upload] 使用已下载视频: {video_path}")
    else:
        if "video" not in request.files:
            return jsonify({"error": "请上传视频文件"}), 400
        video_file = request.files["video"]
        if video_file.filename == "":
            return jsonify({"error": "请选择视频文件"}), 400
        if not allowed_file(video_file.filename, config.ALLOWED_VIDEO_EXTENSIONS):
            return jsonify({
                "error": f"不支持的视频格式。支持: {', '.join(config.ALLOWED_VIDEO_EXTENSIONS)}"
            }), 400
        video_filename = video_file.filename
        video_path = os.path.join(task_dir, video_filename)
        video_file.save(video_path)

    # 保存音频
    audio_paths = []
    audio_server_paths = request.form.get("audio_server_paths", "").strip()

    # 优先使用服务器已有的音频路径
    if audio_server_paths:
        for p in audio_server_paths.split(","):
            p = p.strip()
            if p and os.path.isfile(p):
                audio_paths.append(p)
                print(f"[V3 Upload] 使用已下载音频: {p}")

    # 也处理直接上传的音频文件
    audio_files = request.files.getlist("audio")
    for audio_file in audio_files:
        if audio_file.filename == "":
            continue
        if not allowed_file(audio_file.filename, config.ALLOWED_AUDIO_EXTENSIONS):
            continue
        audio_path = os.path.join(task_dir, audio_file.filename)
        audio_file.save(audio_path)
        audio_paths.append(audio_path)

    # 获取配置
    editing_mode = request.form.get("editing_mode", "video_first")
    custom_export_path = request.form.get("custom_export_path", "").strip() or None

    # 尝试加载已有简报
    run_path = ""
    brief = {}
    try:
        if run_exists(project_slug):
            from modules.workspace_manager import get_run_path
            run_path = get_run_path(project_slug)
            brief = load_artifact(run_path, "project-brief")
    except Exception:
        pass

    # 创建/更新任务
    task_id = project_slug

    tasks[task_id] = {
        "id": task_id,
        "mode": "v3",
        "phase": "media_scan",
        "status": "uploaded",
        "progress": 5,
        "message": "文件已上传，开始媒体扫描...",
        "video_path": video_path,
        "audio_paths": audio_paths,
        "video_filename": video_filename,
        "audio_filenames": [os.path.basename(p) for p in audio_paths],
        "editing_mode": editing_mode,
        "custom_export_path": custom_export_path,
        "run_path": run_path,
        "project_slug": project_slug,
        "brief": brief,
        "brief_display": brief_to_display(brief) if brief else {},
    }

    # 后台启动媒体扫描
    thread = threading.Thread(target=run_media_scan, args=(task_id,), daemon=True)
    thread.start()

    return jsonify({
        "task_id": task_id,
        "phase": "media_scan",
        "message": "上传成功，正在后台扫描媒体...",
    })


@app.route("/api/pipeline/confirm/<task_id>", methods=["POST"])
def api_pipeline_confirm(task_id: str):
    """v3：确认当前阶段，进入下一阶段"""
    task = _get_task_safe(task_id)
    if not task:
        return jsonify({"error": "任务不存在"}), 404

    data = request.get_json() or {}
    current_phase = data.get("phase", task.get("phase", ""))

    next_phase = _get_next_phase(current_phase)
    if not next_phase:
        return jsonify({"error": f"当前阶段 '{current_phase}' 已是最后一个阶段"}), 400

    # 启动下一阶段
    if _launch_phase(task_id, next_phase):
        return jsonify({
            "task_id": task_id,
            "previous_phase": current_phase,
            "next_phase": next_phase,
            "message": f"已确认 {current_phase}，进入 {next_phase}",
        })
    else:
        return jsonify({"error": f"无法启动阶段: {next_phase}"}), 500


@app.route("/api/pipeline/skip/<task_id>", methods=["POST"])
def api_pipeline_skip(task_id: str):
    """v3：跳过当前阶段（仅可选阶段可跳过，如 story）"""
    task = _get_task_safe(task_id)
    if not task:
        return jsonify({"error": "任务不存在"}), 404

    data = request.get_json() or {}
    current_phase = data.get("phase", task.get("phase", ""))

    # 故事和素材审查阶段可以跳过
    if current_phase not in ("story", "material_review"):
        return jsonify({"error": f"阶段 '{current_phase}' 不可跳过"}), 400

    next_phase = _get_next_phase(current_phase)
    if not next_phase:
        return jsonify({"error": "无法确定下一阶段"}), 400

    # 跳过故事阶段
    task["story"] = {}
    task["story_display"] = {}

    if _launch_phase(task_id, next_phase):
        return jsonify({
            "task_id": task_id,
            "skipped_phase": current_phase,
            "next_phase": next_phase,
            "message": f"已跳过 {current_phase}，进入 {next_phase}",
        })
    else:
        return jsonify({"error": f"无法启动阶段: {next_phase}"}), 500


@app.route("/api/pipeline/retry/<task_id>", methods=["POST"])
def api_pipeline_retry(task_id: str):
    """v3：重试当前阶段（不覆盖已批准的产物）"""
    task = _get_task_safe(task_id)
    if not task:
        return jsonify({"error": "任务不存在"}), 404

    data = request.get_json() or {}
    phase_name = data.get("phase", task.get("phase", ""))

    if phase_name not in PHASE_HANDLERS:
        return jsonify({"error": f"未知阶段: {phase_name}"}), 400

    if _launch_phase(task_id, phase_name):
        return jsonify({
            "task_id": task_id,
            "phase": phase_name,
            "message": f"正在重试 {phase_name}...",
        })
    else:
        return jsonify({"error": f"无法重试阶段: {phase_name}"}), 500


@app.route("/api/pipeline/status/<task_id>")
def api_pipeline_status(task_id: str):
    """v3：查询完整的管道状态"""
    task = _get_task_safe(task_id)
    if not task:
        return jsonify({"error": "任务不存在"}), 404

    status = task.get("status", "")

    # 判断哪些阶段数据可用
    include_review = status in ("review_complete", "story_complete", "blueprint_complete",
                                 "validation_complete", "completed")
    include_story = status in ("story_complete", "blueprint_complete",
                                "validation_complete", "completed")
    include_blueprint = status in ("blueprint_complete", "validation_complete", "completed")
    include_validation = status in ("validation_complete", "completed")
    include_build = status == "completed"

    return jsonify({
        "task_id": task_id,
        "mode": task.get("mode", "v3"),
        "phase": task.get("phase", ""),
        "status": status,
        "progress": task.get("progress", 0),
        "message": task.get("message", ""),
        "brief": task.get("brief_display"),
        "scan_preview": task.get("scan_preview"),
        "review": task.get("review_display") if include_review else None,
        "story": task.get("story_display") if include_story else None,
        "blueprint": task.get("blueprint_display") if include_blueprint else None,
        "validation": task.get("validation") if include_validation else None,
        "draft_info": task.get("draft_info") if include_build else None,
        "audit": task.get("audit") if include_build else None,
        "pickup": task.get("pickup_display") if include_build else None,
        "editing_mode": task.get("editing_mode", ""),
        "export_path": task.get("custom_export_path") or config.OUTPUT_FOLDER,
    })


@app.route("/api/artifact/<project_slug>/<phase>")
def api_get_artifact(project_slug: str, phase: str):
    """v3：获取阶段产物 JSON"""
    from modules.workspace_manager import get_run_path, load_artifact as load_art

    valid_phases = ["project-brief", "media-manifest", "material-review",
                    "story-script", "edit-blueprint", "blueprint-audit",
                    "audit-report", "pickup-report"]

    if phase not in valid_phases:
        return jsonify({"error": f"未知阶段产物: {phase}（有效: {', '.join(valid_phases)}）"}), 400

    try:
        run_path = get_run_path(project_slug)
        artifact = load_art(run_path, phase)
        if not artifact:
            return jsonify({"error": f"产物不存在: {phase}"}), 404
        return jsonify(artifact)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================
# 启动
# ============================================

# ============================================
# 📬 意见箱 API
# ============================================
import threading
_suggestions_lock = threading.Lock()
SUGGESTIONS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "workspace", "suggestions.json")


def _load_suggestions() -> list[dict]:
    """加载所有意见"""
    if not os.path.exists(SUGGESTIONS_FILE):
        return []
    try:
        with open(SUGGESTIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _save_suggestions(suggestions: list[dict]):
    """保存所有意见"""
    os.makedirs(os.path.dirname(SUGGESTIONS_FILE), exist_ok=True)
    with open(SUGGESTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(suggestions, f, ensure_ascii=False, indent=2)


def _check_admin() -> bool:
    """验证管理员密钥"""
    if not config.ADMIN_KEY:  # 未配置密钥时禁用管理功能
        return False
    key = request.headers.get("X-Admin-Key", "") or request.args.get("admin_key", "")
    return bool(key) and key == config.ADMIN_KEY


@app.route("/api/suggestions", methods=["GET"])
def api_get_suggestions():
    """获取建议（管理员可查看全部含已隐藏+私密；普通用户仅看公开未隐藏）"""
    is_admin = _check_admin()
    show_all = is_admin and request.args.get("all") == "1"
    with _suggestions_lock:
        suggestions = _load_suggestions()
    if not show_all:
        suggestions = [
            s for s in suggestions
            if not s.get("hidden", False)  # 未隐藏
            and (s.get("visibility", "public") == "public" or is_admin)  # 公开 或 管理员可见私密
        ]
    return jsonify({"suggestions": suggestions, "total": len(suggestions)})


@app.route("/api/suggestions", methods=["POST"])
def api_post_suggestion():
    """提交新建议"""
    data = request.get_json() if request.is_json else {}
    nickname = (data.get("nickname", "") or "").strip()
    content = (data.get("content", "") or "").strip()
    visibility = (data.get("visibility", "") or "").strip()

    if visibility not in ("public", "private"):
        visibility = "public"

    if not nickname:
        return jsonify({"error": "请填写昵称"}), 400
    if not content:
        return jsonify({"error": "请填写意见内容"}), 400
    if len(content) > 2000:
        return jsonify({"error": "内容不能超过 2000 字"}), 400
    if len(nickname) > 50:
        return jsonify({"error": "昵称不能超过 50 字"}), 400

    import time as _time
    suggestion = {
        "id": str(uuid.uuid4())[:8],
        "nickname": nickname,
        "content": content,
        "visibility": visibility,  # public | private
        "status": "pending",
        "hidden": False,
        "created_at": _time.strftime("%Y-%m-%d %H:%M UTC", _time.gmtime()),
    }

    with _suggestions_lock:
        suggestions = _load_suggestions()
        suggestions.insert(0, suggestion)
        _save_suggestions(suggestions)

    return jsonify({"suggestion": suggestion, "total": len(suggestions)}), 201


@app.route("/api/suggestions/<sid>", methods=["DELETE"])
def api_delete_suggestion(sid: str):
    """删除/隐藏建议（仅管理员）"""
    if not _check_admin():
        return jsonify({"error": "需要管理员权限"}), 403

    with _suggestions_lock:
        suggestions = _load_suggestions()
        for s in suggestions:
            if s.get("id") == sid:
                s["hidden"] = True
                s["hidden_at"] = __import__("time").strftime("%Y-%m-%d %H:%M UTC", __import__("time").gmtime())
                _save_suggestions(suggestions)
                return jsonify({"success": True, "suggestion": s})
    return jsonify({"error": "建议不存在"}), 404


@app.route("/api/suggestions/<sid>/restore", methods=["POST"])
def api_restore_suggestion(sid: str):
    """保留/恢复建议（仅管理员）"""
    if not _check_admin():
        return jsonify({"error": "需要管理员权限"}), 403

    with _suggestions_lock:
        suggestions = _load_suggestions()
        for s in suggestions:
            if s.get("id") == sid:
                s["hidden"] = False
                s.pop("hidden_at", None)
                _save_suggestions(suggestions)
                return jsonify({"success": True, "suggestion": s})
    return jsonify({"error": "建议不存在"}), 404


@app.route("/api/suggestions/<sid>/status", methods=["PUT"])
def api_update_suggestion_status(sid: str):
    """更新建议状态（仅管理员）"""
    if not _check_admin():
        return jsonify({"error": "需要管理员权限"}), 403

    data = request.get_json() if request.is_json else {}
    new_status = (data.get("status", "") or "").strip()

    if new_status not in ("pending", "in_progress", "completed"):
        return jsonify({"error": "无效状态，可选: pending, in_progress, completed"}), 400

    with _suggestions_lock:
        suggestions = _load_suggestions()
        for s in suggestions:
            if s.get("id") == sid:
                s["status"] = new_status
                _save_suggestions(suggestions)
                return jsonify({"success": True, "suggestion": s})
    return jsonify({"error": "建议不存在"}), 404


if __name__ == "__main__":
    # Render.com 自动设置 $PORT，本地用 FLASK_PORT 或默认 5000
    host = os.environ.get("FLASK_HOST", "127.0.0.1")
    port = int(os.environ.get("PORT") or os.environ.get("FLASK_PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "true").lower() == "true"

    print("=" * 60)
    print("🎬 Movie Music Matcher v3.0 — 电影音乐智能匹配")
    print("=" * 60)
    print(f"📂 上传目录: {config.UPLOAD_FOLDER}")
    print(f"🖼️  帧缓存目录: {config.FRAME_FOLDER}")
    print(f"📤 输出目录: {config.OUTPUT_FOLDER}")
    workspace = getattr(config, "WORKSPACE_DIR", os.path.join(config.BASE_DIR, "workspace"))
    print(f"📁 工作空间: {workspace}")
    print(f"✂️  剪映草稿目录: {config.CAPCUT_DRAFT_DIR}")
    print(f"🤖 AI 模型: {config.AI_MODEL}")
    print(f"🔑 API Key 已配置: {config.ANTHROPIC_API_KEY not in ('your-api-key-here', '')}")
    print("-" * 60)
    print("🔄 v2.0 经典模式: /  (一键管线)")
    print("🆕 v3.0 管道模式: /?v=3 (分阶段确认)")
    print(f"🌐 在浏览器打开: http://{host}:{port}")
    print("=" * 60)

    app.run(host=host, port=port, debug=debug)
