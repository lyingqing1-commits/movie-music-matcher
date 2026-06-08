"""
剪映草稿生成模块 - 生成剪映可打开的草稿文件
==============================================
使用 pyJianYingDraft 库生成剪映草稿 JSON。
兼容策略：
  1. 使用 pyJianYingDraft 生成标准草稿（推荐）
  2. 如果库不可用，回退到手动 JSON 生成
  3. 草稿直接写入剪映草稿目录（如果存在）
"""
import os
import shutil
import uuid
import config

# ---- pyJianYingDraft 导入 ----
try:
    import pyJianYingDraft as jyd
    from pyJianYingDraft.time_util import Timerange
    HAS_JYD = True
except ImportError:
    HAS_JYD = False
    print("⚠️ pyJianYingDraft 未安装。将使用手动 JSON 模式（兼容性受限）。")

US = 1_000_000  # 1 秒 = 1,000,000 微秒


def _compute_beat_segments(
    video_duration_s: float,
    audio_duration_s: float,
    bpm: float = 120,
    beats_per_cut: int = 2,
) -> list[dict]:
    """
    根据音乐 BPM 计算视频切分方案。
    每 N 拍切一刀，生成片段列表。

    参数：
        video_duration_s: 视频时长（秒）
        audio_duration_s: 音频时长（秒）
        bpm: 音乐 BPM
        beats_per_cut: 每几拍切一刀（默认 2 拍）

    返回：
        [{source_start, source_duration, target_start}, ...]
    """
    if bpm <= 0:
        bpm = 120

    beat_duration = 60.0 / bpm
    cut_interval = beat_duration * beats_per_cut

    total_needed = audio_duration_s

    segments = []
    target_pos = 0.0
    source_pos = 0.0
    safe_limit = int(total_needed / max(cut_interval, 0.1)) + 10

    for _ in range(safe_limit):
        if target_pos >= total_needed:
            break

        take = min(cut_interval, total_needed - target_pos)

        # 视频读到头了 → 循环回开头
        if source_pos + take > video_duration_s:
            leftover = video_duration_s - source_pos
            if leftover > 0.3:
                segments.append({
                    "source_start": source_pos,
                    "source_duration": leftover,
                })
                target_pos += leftover
                take -= leftover
            source_pos = 0.0

        if take > 0.01:
            if take > video_duration_s:
                take = video_duration_s
            segments.append({
                "source_start": source_pos,
                "source_duration": take,
            })
            source_pos += take
            target_pos += take
            if source_pos >= video_duration_s:
                source_pos = 0.0
        else:
            target_pos += cut_interval

    # 在每段之间加微小间隙（0.02 秒），产生剪切感
    gap = 0.02
    offset = 0.0
    for seg in segments:
        seg["target_start"] = offset
        offset += seg["source_duration"] + gap

    print(f"   Beat sync: {len(segments)} segments, ~{cut_interval:.1f}s each (BPM={bpm}, {beats_per_cut} beats/cut)")
    return segments


# ============================================
# 主入口
# ============================================

def create_draft(
    video_path: str,
    audio_path: str,
    video_info: dict,
    match_result: dict,
    task_id: str,
) -> dict:
    """创建剪映草稿

    优先使用 pyJianYingDraft（产生标准格式），
    不可用时回退到手动 JSON。
    """
    if HAS_JYD:
        try:
            return _create_draft_with_jyd(
                video_path, audio_path, video_info, match_result, task_id
            )
        except Exception as e:
            print(f"[WARN] pyJianYingDraft 失败 ({e})，回退到手动 JSON 模式")
            return _create_draft_manual(
                video_path, audio_path, video_info, match_result, task_id
            )
    else:
        return _create_draft_manual(
            video_path, audio_path, video_info, match_result, task_id
        )


# ============================================
# 方案 A：pyJianYingDraft（推荐）
# ============================================

def _create_draft_with_jyd(
    video_path: str,
    audio_path: str,
    video_info: dict,
    match_result: dict,
    task_id: str,
) -> dict:
    """使用 pyJianYingDraft 生成标准剪映草稿"""
    print("Using pyJianYingDraft to generate standard draft...")

    # ---- 视频元数据 ----
    width = video_info.get("width", 1920)
    height = video_info.get("height", 1080)
    fps = round(video_info.get("fps", 30))
    if fps <= 0:
        fps = 30

    video_duration_s = video_info.get("duration", 30)
    audio_duration_s = match_result.get("duration_seconds", 30)
    bpm = match_result.get("tempo_bpm", 120)
    if bpm <= 0:
        bpm = 120

    # ---- 草稿名称 ----
    draft_name = f"MovieMatch_{task_id[:8]}"

    # ---- 确定草稿写入位置 ----
    # 优先写入剪映草稿目录（如果存在），同时也在 output 保留副本
    capcut_draft_path = None
    output_draft_path = None

    # 写入 output 目录（始终保留副本）
    output_dir = os.path.join(config.OUTPUT_FOLDER, task_id)
    os.makedirs(output_dir, exist_ok=True)

    # 创建临时 DraftFolder 指向 output 目录来生成草稿
    df_output = jyd.DraftFolder(output_dir)

    try:
        script = df_output.create_draft(
            draft_name, width, height, fps,
            maintrack_adsorb=True, allow_replace=True,
        )
    except Exception as e:
        raise RuntimeError(f"创建草稿失败: {e}")

    output_draft_path = os.path.join(output_dir, draft_name)

    # ---- 添加素材和轨道 ----
    # 视频
    video_mat = jyd.VideoMaterial(video_path)
    script.add_material(video_mat)
    script.add_track(jyd.TrackType.video)

    # 音频
    audio_mat = jyd.AudioMaterial(audio_path)
    script.add_material(audio_mat)
    script.add_track(jyd.TrackType.audio)

    # ---- 按 BPM 节拍切分视频片段 ----
    beat_segments = _compute_beat_segments(
        video_duration_s=video_duration_s,
        audio_duration_s=audio_duration_s,
        bpm=bpm,
        beats_per_cut=2,
    )

    for seg in beat_segments:
        target_start_us = int(seg["target_start"] * US)
        seg_duration_us = int(seg["source_duration"] * US)
        source_start_us = int(seg["source_start"] * US)

        target_tr = Timerange(target_start_us, seg_duration_us)
        source_tr = Timerange(source_start_us, seg_duration_us)

        video_seg = jyd.VideoSegment(
            video_mat, target_tr,
            source_timerange=source_tr,
            volume=1.0,
        )
        script.add_segment(video_seg)

    # ---- 添加音频片段 ----
    audio_seg = jyd.AudioSegment(
        audio_mat,
        Timerange(0, int(audio_duration_s * US)),
        volume=1.0,
    )
    script.add_segment(audio_seg)

    # ---- 保存草稿 ----
    script.save()
    print(f"Draft saved (JYD): {output_draft_path}")

    # ---- 尝试复制到剪映目录 ----
    capcut_draft_dir = config.CAPCUT_DRAFT_DIR
    if os.path.exists(os.path.dirname(capcut_draft_dir)):
        try:
            # 直接在剪映目录中重建草稿
            df_capcut = jyd.DraftFolder(capcut_draft_dir)
            script2 = df_capcut.create_draft(
                draft_name, width, height, fps,
                maintrack_adsorb=True, allow_replace=True,
            )

            # 复用素材对象
            script2.add_material(video_mat)
            script2.add_material(audio_mat)
            script2.add_track(jyd.TrackType.video)
            script2.add_track(jyd.TrackType.audio)

            for seg in beat_segments:
                target_tr = Timerange(
                    int(seg["target_start"] * US),
                    int(seg["source_duration"] * US),
                )
                source_tr = Timerange(
                    int(seg["source_start"] * US),
                    int(seg["source_duration"] * US),
                )
                video_seg = jyd.VideoSegment(video_mat, target_tr, source_timerange=source_tr)
                script2.add_segment(video_seg)

            script2.add_segment(jyd.AudioSegment(
                audio_mat,
                Timerange(0, int(audio_duration_s * US)),
            ))
            script2.save()

            capcut_draft_path = os.path.join(capcut_draft_dir, draft_name)
            print(f"Draft copied to CapCut/JianYing: {capcut_draft_path}")
        except Exception as e:
            print(f"Copy to CapCut dir failed: {e}")
            capcut_draft_path = None

    return {
        "draft_folder": output_draft_path,
        "capcut_draft_path": capcut_draft_path,
        "draft_name": draft_name,
        "editing_hint": (
            "视频已按音乐节拍自动切分为多段。"
            "若草稿已复制到剪映目录，请重启剪映后查看「我的草稿」。"
        ),
    }


# ============================================
# 方案 B：手动 JSON（备用）
# ============================================

def _create_draft_manual(
    video_path: str,
    audio_path: str,
    video_info: dict,
    match_result: dict,
    task_id: str,
) -> dict:
    """
    手动创建剪映草稿（备用方案，不依赖 pyJianYingDraft）
    生成最小化的 draft_content.json 和 draft_meta_info.json
    """
    print("Using manual draft mode (pyJianYingDraft unavailable)...")

    output_dir = os.path.join(config.OUTPUT_FOLDER, task_id)
    draft_name = f"MovieMatch_{task_id[:8]}"
    draft_dir = os.path.join(output_dir, draft_name)
    os.makedirs(draft_dir, exist_ok=True)

    # 生成 UUID
    video_material_id = str(uuid.uuid4()).replace("-", "")[:32]
    audio_material_id = str(uuid.uuid4()).replace("-", "")[:32]
    draft_id = str(uuid.uuid4()).upper()

    video_duration_sec = video_info.get("duration", 30)
    audio_duration_sec = match_result.get("duration_seconds", 30)
    audio_duration_us = int(audio_duration_sec * US)

    # 视频尺寸
    width = video_info.get("width", 1920)
    height = video_info.get("height", 1080)
    fps = round(video_info.get("fps", 30))
    if fps <= 0:
        fps = 30

    # 节拍同步切分
    bpm = match_result.get("tempo_bpm", 120)
    if bpm <= 0:
        bpm = 120
    beat_segments = _compute_beat_segments(
        video_duration_s=video_duration_sec,
        audio_duration_s=audio_duration_sec,
        bpm=bpm,
        beats_per_cut=2,
    )

    # ---- draft_meta_info.json ----
    # 使用与真实剪映草稿一致的文件名 draft_meta_info.json（不是 draft_info.json）
    import time as time_mod
    now_us = int(time_mod.time() * 1_000_000)

    draft_meta_info = {
        "draft_id": draft_id,
        "draft_name": draft_name,
        "draft_fold_path": draft_dir.replace("\\", "/"),
        "draft_root_path": config.OUTPUT_FOLDER.replace("\\", "/"),
        "draft_cover": "draft_cover.jpg",
        "draft_is_invisible": False,
        "draft_is_ai_shorts": False,
        "draft_is_ai_translate": False,
        "draft_is_article_video_draft": False,
        "draft_cloud_last_action_download": False,
        "draft_new_version": "",
        "draft_type": "",
        "draft_timeline_materials_size_": 0,
        "tm_draft_create": now_us,
        "tm_draft_modified": now_us,
        "tm_draft_removed": 0,
        "tm_duration": audio_duration_us,
    }

    # ---- draft_content.json ----
    # 构建 segments
    video_segments_json = []
    for seg in beat_segments:
        seg_start_us = int(seg["source_start"] * US)
        seg_duration_us = int(seg["source_duration"] * US)
        target_start_us = int(seg["target_start"] * US)
        seg_id = str(uuid.uuid4()).upper()

        video_segments_json.append({
            "id": seg_id,
            "material_id": video_material_id,
            "target_timerange": {
                "start": target_start_us,
                "duration": seg_duration_us,
            },
            "source_timerange": {
                "start": seg_start_us,
                "duration": seg_duration_us,
            },
            "speed": 1.0,
            "volume": 1.0,
            "visible": True,
            "clip": {
                "alpha": 1.0,
                "flip": {"horizontal": False, "vertical": False},
                "rotation": 0.0,
                "scale": {"x": 1.0, "y": 1.0},
                "transform": {"x": 0.0, "y": 0.0},
            },
            "hdr_settings": {"intensity": 1.0, "mode": 1, "nits": 1000},
            "common_keyframes": [],
            "extra_material_refs": [],
            "keyframe_refs": [],
            "render_index": 0,
            "track_render_index": 0,
            "is_loop": False,
            "reverse": False,
            "last_nonzero_volume": 1.0,
            "enable_adjust": True,
            "enable_color_curves": True,
            "enable_color_wheels": True,
            "enable_lut": True,
            "enable_hsl": False,
            "enable_adjust_mask": False,
            "enable_color_correct_adjust": False,
            "enable_color_match_adjust": False,
            "enable_smart_color_adjust": False,
            "enable_video_mask": True,
            "template_scene": "default",
            "uniform_scale": {"on": True, "value": 1.0},
            "responsive_layout": {
                "enable": False,
                "horizontal_pos_layout": 0,
                "size_layout": 0,
                "target_follow": "",
                "vertical_pos_layout": 0,
            },
            "state": 0,
            "caption_info": None,
            "cartoon": False,
            "group_id": "",
            "intensifies_audio": False,
            "is_placeholder": False,
            "is_tone_modify": False,
            "raw_segment_id": "",
            "template_id": "",
            "track_attribute": 0,
            "desc": "",
            "lyric_keyframes": None,
        })

    # 视频素材
    video_material_json = {
        "aigc_history_id": "",
        "aigc_item_id": "",
        "aigc_type": "none",
        "audio_fade": None,
        "cartoon_path": "",
        "category_id": "",
        "category_name": "local",
        "check_flag": 62978047,
        "crop": {
            "lower_left_x": 0.0, "lower_left_y": 1.0,
            "lower_right_x": 1.0, "lower_right_y": 1.0,
            "upper_left_x": 0.0, "upper_left_y": 0.0,
            "upper_right_x": 1.0, "upper_right_y": 0.0,
        },
        "crop_ratio": "free",
        "crop_scale": 1.0,
        "duration": int(video_duration_sec * US),
        "extra_type_option": 0,
        "formula_id": "",
        "freeze": None,
        "has_audio": True,
        "has_sound_separated": False,
        "height": height,
        "id": video_material_id,
        "intensifies_audio_path": "",
        "intensifies_path": "",
        "is_ai_generate_content": False,
        "is_copyright": False,
        "is_text_edit_overdub": False,
        "is_unified_beauty_mode": False,
        "local_id": "",
        "local_material_from": "",
        "local_material_id": "",
        "material_id": "",
        "material_name": os.path.basename(video_path),
        "material_url": "",
        "matting": {
            "custom_matting_id": "", "expansion": 0, "feather": 0, "flag": 0,
            "has_use_quick_brush": False, "has_use_quick_eraser": False,
            "interactiveTime": [], "path": "", "reverse": False, "strokes": [],
        },
        "media_path": "",
        "multi_camera_info": None,
        "object_locked": None,
        "origin_material_id": "",
        "path": video_path.replace("\\", "/"),
        "picture_from": "none",
        "picture_set_category_id": "",
        "picture_set_category_name": "",
        "request_id": "",
        "reverse_intensifies_path": "",
        "reverse_path": "",
        "smart_match_info": None,
        "smart_motion": None,
        "source": 0,
        "source_platform": 0,
        "stable": {
            "matrix_path": "",
            "stable_level": 0,
            "time_range": {"duration": 0, "start": 0},
        },
        "team_id": "",
        "type": "video",
        "video_algorithm": {
            "ai_background_configs": [], "aigc_generate": None,
            "algorithms": [], "complement_frame_config": None,
            "deflicker": None, "gameplay_configs": [],
            "motion_blur_config": None, "mouth_shape_driver": None,
            "noise_reduction": None, "path": "",
            "quality_enhance": None, "smart_complement_frame": None,
            "super_resolution": None, "time_range": None,
        },
        "width": width,
    }

    # 音频素材
    audio_material_json = {
        "aigc_history_id": "",
        "aigc_item_id": "",
        "aigc_type": "none",
        "audio_fade": None,
        "category_id": "",
        "category_name": "local",
        "check_flag": 62978047,
        "duration": audio_duration_us,
        "extra_type_option": 0,
        "formula_id": "",
        "id": audio_material_id,
        "intensifies_audio_path": "",
        "intensifies_path": "",
        "is_ai_generate_content": False,
        "is_copyright": False,
        "is_text_edit_overdub": False,
        "is_unified_beauty_mode": False,
        "local_id": "",
        "local_material_from": "",
        "local_material_id": "",
        "material_id": "",
        "material_name": os.path.basename(audio_path),
        "material_url": "",
        "multi_camera_info": None,
        "name": os.path.basename(audio_path),
        "object_locked": None,
        "origin_material_id": "",
        "path": audio_path.replace("\\", "/"),
        "picture_from": "none",
        "picture_set_category_id": "",
        "picture_set_category_name": "",
        "request_id": "",
        "reverse_intensifies_path": "",
        "reverse_path": "",
        "source": 0,
        "source_platform": 0,
        "team_id": "",
        "type": "audio",
        "video_algorithm": None,
    }

    audio_segment_json = {
        "id": str(uuid.uuid4()).upper(),
        "material_id": audio_material_id,
        "target_timerange": {
            "start": 0,
            "duration": audio_duration_us,
        },
        "source_timerange": {
            "start": 0,
            "duration": audio_duration_us,
        },
        "speed": 1.0,
        "volume": 1.0,
        "visible": True,
        "common_keyframes": [],
        "extra_material_refs": [],
        "keyframe_refs": [],
        "render_index": 0,
        "track_render_index": 0,
        "is_loop": False,
        "reverse": False,
        "last_nonzero_volume": 1.0,
        "enable_adjust": False,
        "enable_color_curves": True,
        "enable_color_wheels": True,
        "enable_lut": False,
        "enable_hsl": False,
        "enable_adjust_mask": False,
        "enable_color_correct_adjust": False,
        "enable_color_match_adjust": False,
        "enable_smart_color_adjust": False,
        "enable_video_mask": True,
        "template_scene": "default",
        "responsive_layout": {
            "enable": False, "horizontal_pos_layout": 0,
            "size_layout": 0, "target_follow": "",
            "vertical_pos_layout": 0,
        },
        "state": 0,
        "caption_info": None,
        "cartoon": False,
        "group_id": "",
        "intensifies_audio": False,
        "is_placeholder": False,
        "is_tone_modify": False,
        "raw_segment_id": "",
        "template_id": "",
        "track_attribute": 0,
        "desc": "",
        "lyric_keyframes": None,
        "hdr_settings": None,
        "uniform_scale": None,
        "clip": None,
    }

    draft_content = {
        "canvas_config": {
            "background": None,
            "height": height,
            "ratio": "original",
            "width": width,
        },
        "color_space": 0,
        "config": {
            "adjust_max_index": 1,
            "attachment_info": [],
            "combination_max_index": 1,
            "export_range": None,
            "extract_audio_last_index": 1,
            "lyrics_recognition_id": "",
            "lyrics_sync": True,
            "lyrics_taskinfo": [],
            "maintrack_adsorb": True,
            "material_save_mode": 0,
            "multi_language_current": "none",
            "multi_language_list": [],
            "multi_language_main": "none",
            "multi_language_mode": "none",
            "original_sound_last_index": 1,
            "record_audio_last_index": 1,
            "sticker_max_index": 1,
            "subtitle_keywords_config": None,
            "subtitle_recognition_id": "",
            "subtitle_sync": True,
            "subtitle_taskinfo": [],
            "system_font_list": [],
            "video_mute": False,
            "zoom_info_params": None,
        },
        "cover": None,
        "create_time": 0,
        "duration": audio_duration_us,
        "extra_info": None,
        "fps": float(fps),
        "free_render_index_mode_on": False,
        "group_container": None,
        "id": draft_id,
        "is_drop_frame_timecode": False,
        "keyframe_graph_list": [],
        "keyframes": {
            "adjusts": [], "audios": [], "effects": [],
            "filters": [], "handwrites": [], "stickers": [],
            "texts": [], "videos": [],
        },
        "last_modified_platform": {
            "app_id": 359289,
            "app_source": "cc",
            "app_version": "5.2.0",
            "device_id": "",
            "hard_disk_id": "",
            "mac_address": "",
            "os": "windows",
            "os_version": "10.0.22631",
        },
        "lyrics_effects": [],
        "materials": {
            "ai_translates": [],
            "audio_balances": [],
            "audio_effects": [],
            "audio_fades": [],
            "audio_track_indexes": [],
            "audios": [audio_material_json],
            "beats": [],
            "canvases": [],
            "chromas": [],
            "color_curves": [],
            "common_mask": [],
            "digital_humans": [],
            "drafts": [],
            "effects": [],
            "flowers": [],
            "green_screens": [],
            "handwrites": [],
            "hsl": [],
            "images": [],
            "log_color_wheels": [],
            "loudnesses": [],
            "manual_deformations": [],
            "material_animations": [],
            "material_colors": [],
            "multi_language_refs": [],
            "placeholder_infos": [],
            "placeholders": [],
            "plugin_effects": [],
            "primary_color_wheels": [],
            "realtime_denoises": [],
            "shapes": [],
            "smart_crops": [],
            "smart_relights": [],
            "sound_channel_mappings": [],
            "speeds": [],
            "stickers": [],
            "tail_leaders": [],
            "text_templates": [],
            "texts": [],
            "time_marks": [],
            "transitions": [],
            "video_effects": [],
            "video_trackings": [],
            "videos": [video_material_json],
            "vocal_beautifys": [],
            "vocal_separations": [],
        },
        "mutable_config": None,
        "name": "",
        "new_version": "125.0.0",
        "path": "",
        "platform": {
            "app_id": 359289,
            "app_source": "cc",
            "app_version": "5.2.0",
            "device_id": "",
            "hard_disk_id": "",
            "mac_address": "",
            "os": "windows",
            "os_version": "10.0.22631",
        },
        "relationships": [],
        "render_index_track_mode_on": True,
        "retouch_cover": None,
        "source": "default",
        "static_cover_image_path": "",
        "time_marks": None,
        "tracks": [
            {
                "attribute": 0,
                "flag": 0,
                "id": str(uuid.uuid4()).upper(),
                "is_default_name": True,
                "name": "",
                "segments": video_segments_json,
                "type": "video",
            },
            {
                "attribute": 0,
                "flag": 0,
                "id": str(uuid.uuid4()).upper(),
                "is_default_name": True,
                "name": "",
                "segments": [audio_segment_json],
                "type": "audio",
            },
        ],
        "update_time": 0,
        "version": 360000,
    }

    # 写入文件
    import json as json_mod

    with open(os.path.join(draft_dir, "draft_meta_info.json"), "w", encoding="utf-8") as f:
        json_mod.dump(draft_meta_info, f, ensure_ascii=False, indent=2)

    with open(os.path.join(draft_dir, "draft_content.json"), "w", encoding="utf-8") as f:
        json_mod.dump(draft_content, f, ensure_ascii=False, indent=2)

    # 尝试复制到剪映目录
    capcut_draft_path = None
    capcut_draft_dir = config.CAPCUT_DRAFT_DIR
    if os.path.exists(os.path.dirname(capcut_draft_dir)):
        capcut_draft_path = os.path.join(capcut_draft_dir, draft_name)
        try:
            if os.path.exists(capcut_draft_path):
                shutil.rmtree(capcut_draft_path)
            shutil.copytree(draft_dir, capcut_draft_path)
            print(f"Draft copied to CapCut/JianYing: {capcut_draft_path}")
        except Exception as e:
            print(f"Copy to CapCut dir failed: {e}")
            capcut_draft_path = None

    print(f"Draft saved (manual): {draft_dir}")

    return {
        "draft_folder": draft_dir,
        "capcut_draft_path": capcut_draft_path,
        "draft_name": draft_name,
        "editing_hint": (
            "视频已按音乐节拍自动切分为多段。"
            "若草稿已复制到剪映目录，请重启剪映后查看「我的草稿」。"
        ),
    }
