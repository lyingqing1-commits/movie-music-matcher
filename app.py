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
import json
import threading
import time

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

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = max(
    config.MAX_VIDEO_SIZE_MB, config.MAX_AUDIO_SIZE_MB
) * 1024 * 1024  # Flask 用字节

# 确保必要的文件夹存在
for folder in [config.UPLOAD_FOLDER, config.FRAME_FOLDER, config.OUTPUT_FOLDER]:
    os.makedirs(folder, exist_ok=True)

# 任务状态存储（简单内存字典，生产环境应使用数据库）
tasks = {}


def allowed_file(filename: str, allowed_extensions: set) -> bool:
    """检查文件扩展名是否允许"""
    ext = os.path.splitext(filename)[1].lower()
    return ext in allowed_extensions


def process_task(task_id: str, video_path: str, audio_paths: list[str]):
    """
    后台处理任务：完整的分析 + 匹配 + 生成流程
    """
    try:
        # ---- 步骤 1：提取视频帧 ----
        tasks[task_id]["status"] = "extracting"
        tasks[task_id]["progress"] = 10
        tasks[task_id]["message"] = "正在提取视频帧..."

        frame_files, video_info = extract_frames(video_path, task_id)
        tasks[task_id]["video_info"] = video_info
        tasks[task_id]["frame_count"] = len(frame_files)
        tasks[task_id]["progress"] = 25

        # ---- 步骤 2：AI 分析电影风格 ----
        tasks[task_id]["status"] = "analyzing_style"
        tasks[task_id]["message"] = "AI 正在分析电影画面风格..."

        sampled = sample_frames(frame_files)
        style_result = analyze_style(sampled)
        tasks[task_id]["style_analysis"] = style_result
        tasks[task_id]["progress"] = 50

        # ---- 步骤 3：分析所有音乐 ----
        tasks[task_id]["status"] = "analyzing_audio"
        tasks[task_id]["message"] = "正在分析音乐特征..."

        audio_features_list = []
        for i, audio_path in enumerate(audio_paths):
            feat = audio_analyze(audio_path)
            audio_features_list.append(feat)
            tasks[task_id]["progress"] = 50 + int(15 * (i + 1) / len(audio_paths))

        tasks[task_id]["audio_features"] = audio_features_list

        # ---- 步骤 4：AI 匹配音乐与电影风格 ----
        tasks[task_id]["status"] = "matching"
        tasks[task_id]["message"] = "AI 正在匹配音乐与电影风格..."
        tasks[task_id]["progress"] = 70

        match_results = match_music_to_style(style_result, audio_features_list)
        tasks[task_id]["match_results"] = match_results
        tasks[task_id]["progress"] = 85

        # ---- 步骤 5：生成剪映草稿 ----
        tasks[task_id]["status"] = "generating"
        tasks[task_id]["message"] = "正在生成剪映草稿..."

        if match_results:
            best_match = match_results[0]
            draft_info = create_draft(
                video_path=video_path,
                audio_path=best_match["file_path"],
                video_info=video_info,
                match_result=best_match,
                task_id=task_id,
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


def process_task_video_only(task_id: str, video_path: str):
    """
    Phase 1：仅处理视频（抽帧 + 分析风格），不处理音频
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
        tasks[task_id]["progress"] = 40

        # ---- 步骤 2：AI 分析电影风格 ----
        tasks[task_id]["status"] = "analyzing_style"
        tasks[task_id]["message"] = "AI 正在分析电影画面风格..."

        sampled = sample_frames(frame_files)
        style_result = analyze_style(sampled)
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
    Phase 3：用户选择了 AI 生成的音轨后，分析音频 + 匹配 + 生成草稿
    """
    try:
        audio_path = ai_track.get("path")
        if not audio_path or not os.path.exists(audio_path):
            raise ValueError(f"AI 音轨文件不存在: {audio_path}")

        video_info = tasks[task_id].get("video_info", {})
        style_result = tasks[task_id].get("style_analysis", {})

        # ---- 步骤 1：分析 AI 生成的音频 ----
        tasks[task_id]["status"] = "analyzing_audio"
        tasks[task_id]["message"] = "正在分析 AI 生成的音乐..."
        tasks[task_id]["progress"] = 55

        audio_feat = audio_analyze(audio_path)
        audio_feat["file_path"] = audio_path
        audio_feat["label"] = ai_track.get("label", "AI 生成音乐")
        audio_features_list = [audio_feat]
        tasks[task_id]["audio_features"] = audio_features_list

        # ---- 步骤 2：AI 匹配 ----
        tasks[task_id]["status"] = "matching"
        tasks[task_id]["message"] = "AI 正在匹配音乐与电影风格..."
        tasks[task_id]["progress"] = 75

        match_results = match_music_to_style(style_result, audio_features_list)
        tasks[task_id]["match_results"] = match_results
        tasks[task_id]["progress"] = 90

        # ---- 步骤 3：生成剪映草稿 ----
        tasks[task_id]["status"] = "generating"
        tasks[task_id]["message"] = "正在生成剪映草稿..."

        if match_results:
            best_match = match_results[0]
            draft_info = create_draft(
                video_path=video_path,
                audio_path=audio_path,
                video_info=video_info,
                match_result=best_match,
                task_id=task_id,
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
    if "video" not in request.files:
        return jsonify({"error": "请上传电影素材（视频文件）"}), 400

    video_file = request.files["video"]
    if video_file.filename == "":
        return jsonify({"error": "请选择视频文件"}), 400

    if not allowed_file(video_file.filename, config.ALLOWED_VIDEO_EXTENSIONS):
        return jsonify({
            "error": f"不支持的视频格式。支持: {', '.join(config.ALLOWED_VIDEO_EXTENSIONS)}"
        }), 400

    # 创建任务目录
    task_dir = os.path.join(config.UPLOAD_FOLDER, task_id)
    os.makedirs(task_dir, exist_ok=True)

    # 保存视频
    video_filename = video_file.filename
    video_path = os.path.join(task_dir, video_filename)
    video_file.save(video_path)

    # ---- AI 模式：只上传视频，稍后 AI 生成音乐 ----
    if mode == "ai":
        tasks[task_id] = {
            "id": task_id,
            "mode": "ai",
            "status": "uploaded",
            "progress": 0,
            "message": "视频已上传，正在分析影片风格...",
            "video_path": video_path,
            "video_filename": video_filename,
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


@app.route("/health")
def health():
    """健康检查"""
    return jsonify({
        "status": "ok",
        "ffmpeg_ready": True,  # 假设已安装
        "api_configured": bool(config.ANTHROPIC_API_KEY and config.ANTHROPIC_API_KEY.strip()),
    })


# ============================================
# 启动
# ============================================

if __name__ == "__main__":
    print("=" * 60)
    print("🎬 Movie Music Matcher - 电影音乐智能匹配")
    print("=" * 60)
    print(f"📂 上传目录: {config.UPLOAD_FOLDER}")
    print(f"🖼️  帧缓存目录: {config.FRAME_FOLDER}")
    print(f"📤 输出目录: {config.OUTPUT_FOLDER}")
    print(f"✂️  剪映草稿目录: {config.CAPCUT_DRAFT_DIR}")
    print(f"🤖 AI 模型: {config.AI_MODEL}")
    print(f"🔑 API Key 已配置: {config.ANTHROPIC_API_KEY not in ('your-api-key-here', '')}")
    print("-" * 60)
    print("🌐 在浏览器打开: http://localhost:5000")
    print("=" * 60)

    app.run(host="127.0.0.1", port=5000, debug=True)
