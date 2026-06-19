"""
剪映草稿生成模块 - 生成剪映可打开的草稿文件
==============================================
使用 pyJianYingDraft 库生成标准多轨剪映草稿 JSON（推荐）。
兼容策略：
  1. pyJianYingDraft 生成标准加密草稿 → 剪映目录（推荐）
  2. 手动 JSON 生成 → output 目录（备用，pyJianYingDraft 不可用时）

输出结构（4 轨）：
  轨道 1 — 视频轨：用户上传并剪辑后的视频片段（静音）
  轨道 2 — 原声音轨：视频分离后的原声（与视频片段对齐）
  轨道 3 — BGM 音轨：用户上传并由应用剪辑后的音乐
  轨道 4 — （未来）转场/特效轨
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
    print("pyJianYingDraft 未安装。将使用手动 JSON 模式。")

US = 1_000_000  # 1 秒 = 1,000,000 微秒


def _aspect_ratio_to_resolution(aspect_ratio: str, video_info: dict) -> tuple:
    """将画幅比转换为 (width, height)，以 1080p 为基准"""
    vid_w = video_info.get("width", 1920)
    vid_h = video_info.get("height", 1080)

    ratio_map = {
        "16:9": (1920, 1080),
        "9:16": (1080, 1920),
        "1:1": (1080, 1080),
        "4:3": (1440, 1080),
        "original": (vid_w, vid_h),
    }
    return ratio_map.get(aspect_ratio, (1920, 1080))


def _compute_beat_segments(
    video_duration_s: float,
    audio_duration_s: float,
    bpm: float = 120,
    beats_per_cut: int = 2,
) -> list[dict]:
    """根据音乐 BPM 计算视频切分方案。"""
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
        if source_pos + take > video_duration_s:
            leftover = video_duration_s - source_pos
            if leftover > 0.3:
                segments.append({"source_start": source_pos, "source_duration": leftover})
                target_pos += leftover
                take -= leftover
            source_pos = 0.0
        if take > 0.01:
            if take > video_duration_s:
                take = video_duration_s
            segments.append({"source_start": source_pos, "source_duration": take})
            source_pos += take
            target_pos += take
            if source_pos >= video_duration_s:
                source_pos = 0.0
        else:
            target_pos += cut_interval

    # 片段间留微小间隙
    gap = 0.02
    offset = 0.0
    for seg in segments:
        seg["target_start"] = offset
        offset += seg["source_duration"] + gap

    print(f"   Beat sync: {len(segments)} segments, ~{cut_interval:.1f}s each (BPM={bpm})")
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
    smart_segments: list[dict] = None,
    editing_mode: str = None,
    custom_output_dir: str = None,
    project_name: str = "",
    platform: str = "jianying",
    aspect_ratio: str = "16:9",
    target_duration: int = 0,
) -> dict:
    """创建剪映草稿 — pyJianYingDraft 优先（支持加密 + 命名轨道），手动 JSON 备用

    Args:
        project_name: 项目主题，用作草稿文件名
        platform: 目标剪辑平台 (jianying/capcut/resolve/universal)
        aspect_ratio: 目标画幅比 (16:9/9:16/1:1/4:3/original)
        target_duration: 目标时长（秒），0 表示不限制
    """
    # 解析画幅比 → 宽高
    ar_width, ar_height = _aspect_ratio_to_resolution(aspect_ratio, video_info)

    if HAS_JYD:
        try:
            return _create_draft_jyd(
                video_path, audio_path, video_info, match_result, task_id,
                smart_segments, editing_mode, custom_output_dir,
                project_name, platform, ar_width, ar_height, target_duration,
            )
        except Exception as e:
            print(f"[WARN] pyJianYingDraft 生成失败 ({e})，回退手动 JSON")
    return _create_draft_manual(
        video_path, audio_path, video_info, match_result, task_id,
        smart_segments, editing_mode, custom_output_dir,
        project_name, platform, ar_width, ar_height, target_duration,
    )


# ============================================
# 方案 A：pyJianYingDraft（推荐 — 支持命名多轨 + 剪映加密）
# ============================================

def _get_platform_label(platform: str) -> str:
    """返回平台的显示名称"""
    labels = {
        "jianying": "JianYing Pro",
        "capcut": "CapCut",
        "resolve": "DaVinci Resolve",
        "universal": "Universal Blueprint",
    }
    return labels.get(platform, platform)


def _copy_draft_to_dir(src_base: str, draft_name: str, dest_dir: str):
    """将草稿从 output 目录复制到目标平台目录"""
    src = os.path.join(src_base, draft_name)
    if not os.path.isdir(src):
        return
    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dest_dir, item)
        if os.path.isfile(s):
            shutil.copy2(s, d)
        elif os.path.isdir(s):
            if not os.path.exists(d):
                shutil.copytree(s, d)


def _create_draft_jyd(
    video_path: str, audio_path: str, video_info: dict, match_result: dict,
    task_id: str, smart_segments: list[dict] = None, editing_mode: str = None,
    custom_output_dir: str = None,
    project_name: str = "", platform: str = "jianying",
    ar_width: int = 1920, ar_height: int = 1080, target_duration: int = 0,
) -> dict:
    """使用 pyJianYingDraft 生成多轨剪辑草稿，支持多平台输出"""

    width = ar_width or video_info.get("width", 1920)
    height = ar_height or video_info.get("height", 1080)
    fps = round(video_info.get("fps", 30)) or 30

    video_dur = video_info.get("duration", 30)
    audio_dur = float(match_result.get("duration_seconds", 30))
    bpm = match_result.get("tempo_bpm", 120) or 120

    # 主题作为文件名（清理非法字符）
    safe_name = project_name.strip() if project_name else f"MovieMatch_{task_id[:8]}"
    safe_name = "".join(c for c in safe_name if c not in r'<>:"/\|?*')
    safe_name = safe_name[:60] or f"MovieMatch_{task_id[:8]}"
    draft_name = f"{safe_name}_{task_id[:4]}"
    base_out = custom_output_dir or config.OUTPUT_FOLDER
    out_dir = os.path.join(base_out, task_id)
    os.makedirs(out_dir, exist_ok=True)

    # 分段
    if smart_segments:
        segments = smart_segments
        print(f"   [Segments] Smart: {len(segments)} clips")
    else:
        segments = _compute_beat_segments(video_dur, audio_dur, bpm)

    # ---- 按目标时长裁剪片段（必须在构建轨道之前执行） ----
    if target_duration > 0:
        trimmed = []
        for seg in segments:
            ts = seg.get("target_start", 0)
            dur = seg.get("source_duration", 0)
            if dur <= 0:
                continue
            seg_end = ts + dur
            if seg_end > target_duration:
                remaining = target_duration - ts
                if remaining > 0.3:
                    trimmed.append({**seg, "source_duration": remaining})
                break
            trimmed.append(seg)
        if trimmed:
            segments = trimmed
            audio_dur = min(audio_dur, target_duration)
            print(f"   [Duration] Trimmed to {target_duration}s, {len(segments)} clips, BGM capped at {audio_dur:.0f}s")
    else:
        # 确保 target_start 存在（智能分段可能已有，节拍分段可能无）
        ct = 0.0
        for seg in segments:
            if "target_start" not in seg:
                seg["target_start"] = ct
            ct = seg.get("target_start", ct) + seg.get("source_duration", 0)

    total = len(segments)

    # ---- output 目录草稿 ----
    df = jyd.DraftFolder(out_dir)
    script = df.create_draft(draft_name, width, height, fps,
                             maintrack_adsorb=True, allow_replace=True)

    vmat = jyd.VideoMaterial(video_path)
    vamat = jyd.AudioMaterial(video_path)  # 视频原声
    bmat = jyd.AudioMaterial(audio_path)    # BGM
    script.add_material(vmat)
    script.add_material(vamat)
    script.add_material(bmat)

    # Track 1: Video (muted)
    script.add_track(jyd.TrackType.video, track_name="Video Track")
    for seg in segments:
        sd = seg.get("source_duration", 0)
        ts = seg.get("target_start", 0)
        ss = seg.get("source_start", 0)
        tt = Timerange(int(ts * US), int(sd * US))
        st = Timerange(int(ss * US), int(sd * US))
        script.add_segment(jyd.VideoSegment(vmat, tt, source_timerange=st, volume=0.0),
                           track_name="Video Track")

    # Track 2: Original audio from video
    script.add_track(jyd.TrackType.audio, track_name="Original Audio")
    for seg in segments:
        sd = seg.get("source_duration", 0)
        ts = seg.get("target_start", 0)
        ss = seg.get("source_start", 0)
        tt = Timerange(int(ts * US), int(sd * US))
        st = Timerange(int(ss * US), int(sd * US))
        script.add_segment(jyd.AudioSegment(vamat, tt, source_timerange=st, volume=0.8),
                           track_name="Original Audio")

    # Track 3: BGM (trimmed to target duration)
    effective_bgm_dur = audio_dur
    script.add_track(jyd.TrackType.audio, track_name="BGM")
    script.add_segment(jyd.AudioSegment(bmat, Timerange(0, int(effective_bgm_dur * US)), volume=1.0),
                       track_name="BGM")

    script.save()
    print(f"   [Save] Draft saved (JYD): {os.path.join(out_dir, draft_name)}")

    # ---- 平台特定同步 ----
    platform_sync_path = None
    platform_label = _get_platform_label(platform)

    if platform in ("jianying", "capcut"):
        # 选择正确的平台目录
        target_dir = config.JIANYING_DRAFT_DIR if platform == "jianying" else config.CAPCUT_DRAFT_DIR
        if target_dir and os.path.exists(os.path.dirname(target_dir)):
            try:
                df2 = jyd.DraftFolder(target_dir)
                s2 = df2.create_draft(draft_name, width, height, fps,
                                      maintrack_adsorb=True, allow_replace=True)
                s2.add_material(vmat)
                s2.add_material(vamat)
                s2.add_material(bmat)

                s2.add_track(jyd.TrackType.video, track_name="Video Track")
                for seg in segments:
                    sd = seg.get("source_duration", 0)
                    ts = seg.get("target_start", 0)
                    ss = seg.get("source_start", 0)
                    tt = Timerange(int(ts * US), int(sd * US))
                    st = Timerange(int(ss * US), int(sd * US))
                    s2.add_segment(jyd.VideoSegment(vmat, tt, source_timerange=st, volume=0.0),
                                   track_name="Video Track")

                s2.add_track(jyd.TrackType.audio, track_name="Original Audio")
                for seg in segments:
                    sd = seg.get("source_duration", 0)
                    ts = seg.get("target_start", 0)
                    ss = seg.get("source_start", 0)
                    tt = Timerange(int(ts * US), int(sd * US))
                    st = Timerange(int(ss * US), int(sd * US))
                    s2.add_segment(jyd.AudioSegment(vamat, tt, source_timerange=st, volume=0.8),
                                   track_name="Original Audio")

                s2.add_track(jyd.TrackType.audio, track_name="BGM")
                s2.add_segment(jyd.AudioSegment(bmat, Timerange(0, int(effective_bgm_dur * US)), volume=1.0),
                               track_name="BGM")
                s2.save()
                platform_sync_path = os.path.join(target_dir, draft_name)
                print(f"   [Sync] Synced to {platform_label}: {platform_sync_path}")
            except Exception as e:
                print(f"   [WARN] Sync to {platform_label} failed: {e}")
        elif platform == "capcut" and not target_dir:
            print(f"   [WARN] CapCut not detected on this system — draft saved to output/ only")
            print(f"   [Hint] Install CapCut to enable auto-sync, or manually copy from output/")
    elif platform == "resolve":
        # DaVinci Resolve: 保存到 resolve/ 目录
        resolve_dir = os.path.join(config.RESOLVE_OUTPUT_DIR, task_id, draft_name)
        os.makedirs(resolve_dir, exist_ok=True)
        # 复制 output 目录的草稿到 resolve 目录
        _copy_draft_to_dir(out_dir, draft_name, resolve_dir)
        platform_sync_path = resolve_dir
        print(f"   [Sync] Saved to {platform_label}: {resolve_dir}")
    elif platform == "universal":
        # Universal: 保存到 universal/ 目录
        universal_dir = os.path.join(config.UNIVERSAL_OUTPUT_DIR, task_id, draft_name)
        os.makedirs(universal_dir, exist_ok=True)
        _copy_draft_to_dir(out_dir, draft_name, universal_dir)
        platform_sync_path = universal_dir
        print(f"   [Sync] Saved to {platform_label}: {universal_dir}")

    mode_label = "视频优先" if editing_mode == "video_first" else "音乐优先"
    smode = "智能" if smart_segments else "节拍"
    hint = (
        f"✨ {smode}剪辑（{mode_label}）：{total} 个视频片段。\n"
        f"🎚️ 3 轨分离：视频轨(静音) | 原声音轨 | BGM音轨。\n"
        f"💡 在{platform_label}中可独立调节每轨音量、拖拽片段、添加转场。"
    )

    return {
        "draft_folder": os.path.join(out_dir, draft_name),
        "capcut_draft_path": platform_sync_path,
        "draft_name": draft_name,
        "editing_hint": hint,
        "platform": platform,
        "platform_label": platform_label,
    }


# ============================================
# 方案 B：手动 JSON（备用 — 无需 pyJianYingDraft）
# ============================================

def _create_draft_manual(
    video_path: str, audio_path: str, video_info: dict, match_result: dict,
    task_id: str, smart_segments: list[dict] = None, editing_mode: str = None,
    custom_output_dir: str = None,
    project_name: str = "", platform: str = "jianying",
    ar_width: int = 1920, ar_height: int = 1080, target_duration: int = 0,
) -> dict:
    """手动创建多轨剪辑草稿 JSON（备用，不依赖 pyJianYingDraft），支持多平台"""
    base_out = custom_output_dir or config.OUTPUT_FOLDER
    out_dir = os.path.join(base_out, task_id)

    safe_name = project_name.strip() if project_name else f"MovieMatch_{task_id[:8]}"
    safe_name = "".join(c for c in safe_name if c not in r'<>:"/\|?*')
    safe_name = safe_name[:60] or f"MovieMatch_{task_id[:8]}"
    draft_name = f"{safe_name}_{task_id[:4]}"
    draft_dir = os.path.join(out_dir, draft_name)
    os.makedirs(draft_dir, exist_ok=True)

    vid = str(uuid.uuid4()).replace("-", "")[:32]
    vaid = str(uuid.uuid4()).replace("-", "")[:32]
    aid = str(uuid.uuid4()).replace("-", "")[:32]
    did = str(uuid.uuid4()).upper()
    tid = str(uuid.uuid4()).replace("-", "")[:32]  # transition material id

    vid_dur = video_info.get("duration", 30)
    aud_dur = float(match_result.get("duration_seconds", 30))
    aud_dur_us = int(aud_dur * US)
    w = ar_width or video_info.get("width", 1920)
    h = ar_height or video_info.get("height", 1080)
    fps = round(video_info.get("fps", 30)) or 30
    bpm = match_result.get("tempo_bpm", 120) or 120

    if smart_segments:
        segments = smart_segments
    else:
        segments = _compute_beat_segments(vid_dur, aud_dur, bpm)

    # ---- 按目标时长裁剪片段 ----
    if target_duration > 0:
        trimmed = []
        for seg in segments:
            ts = seg.get("target_start", 0)
            dur = seg.get("source_duration", 0)
            if dur <= 0:
                continue
            seg_end = ts + dur
            if seg_end > target_duration:
                remaining = target_duration - ts
                if remaining > 0.3:
                    trimmed.append({**seg, "source_duration": remaining})
                break
            trimmed.append(seg)
        if trimmed:
            segments = trimmed
            aud_dur = min(aud_dur, target_duration)
            aud_dur_us = int(aud_dur * US)
            print(f"   [Duration] Trimmed (Manual) to {target_duration}s, {len(segments)} clips, BGM capped at {aud_dur:.0f}s")
    else:
        ct = 0.0
        for seg in segments:
            if "target_start" not in seg:
                seg["target_start"] = ct
            ct = seg.get("target_start", ct) + seg.get("source_duration", 0)

    total = len(segments)

    # ---- 视频素材 ----
    video_mat = {
        "id": vid, "type": "video", "has_audio": True,
        "material_name": os.path.basename(video_path),
        "path": video_path.replace("\\", "/"),
        "width": w, "height": h,
        "duration": int(vid_dur * US),
        "category_name": "local", "source": 0, "source_platform": 0,
        "check_flag": 62978047, "is_copyright": False,
        "aigc_type": "none", "is_ai_generate_content": False,
        "audio_fade": None, "crop": {
            "lower_left_x": 0.0, "lower_left_y": 1.0,
            "lower_right_x": 1.0, "lower_right_y": 1.0,
            "upper_left_x": 0.0, "upper_left_y": 0.0,
            "upper_right_x": 1.0, "upper_right_y": 0.0,
        }, "crop_ratio": "free", "crop_scale": 1.0,
        "extra_type_option": 0, "formula_id": "",
        "freeze": None, "has_sound_separated": False,
        "intensifies_audio_path": "", "intensifies_path": "",
        "is_text_edit_overdub": False, "is_unified_beauty_mode": False,
        "local_id": "", "local_material_from": "", "local_material_id": "",
        "material_id": "", "material_url": "",
        "matting": {"custom_matting_id": "", "expansion": 0, "feather": 0,
                    "flag": 0, "has_use_quick_brush": False,
                    "has_use_quick_eraser": False, "interactiveTime": [],
                    "path": "", "reverse": False, "strokes": []},
        "media_path": "", "multi_camera_info": None, "object_locked": None,
        "origin_material_id": "", "picture_from": "none",
        "picture_set_category_id": "", "picture_set_category_name": "",
        "request_id": "", "reverse_intensifies_path": "", "reverse_path": "",
        "smart_match_info": None, "smart_motion": None,
        "stable": {"matrix_path": "", "stable_level": 0,
                   "time_range": {"duration": 0, "start": 0}},
        "team_id": "", "video_algorithm": {
            "ai_background_configs": [], "aigc_generate": None,
            "algorithms": [], "complement_frame_config": None,
            "deflicker": None, "gameplay_configs": [],
            "motion_blur_config": None, "mouth_shape_driver": None,
            "noise_reduction": None, "path": "",
            "quality_enhance": None, "smart_complement_frame": None,
            "super_resolution": None, "time_range": None,
        },
    }

    _ameta = lambda p, name: {
        "id": name, "type": "audio",
        "material_name": os.path.basename(p) + (f" ({name})" if "原声" in str(name) else ""),
        "path": p.replace("\\", "/"), "duration": int((vid_dur if "va" in str(name) else aud_dur) * US),
        "category_name": "local", "source": 0, "source_platform": 0,
        "check_flag": 62978047, "is_copyright": False,
        "aigc_type": "none", "is_ai_generate_content": False,
        "audio_fade": None, "extra_type_option": 0, "formula_id": "",
        "intensifies_audio_path": "", "intensifies_path": "",
        "is_text_edit_overdub": False, "is_unified_beauty_mode": False,
        "local_id": "", "local_material_from": "", "local_material_id": "",
        "material_id": "", "material_url": "",
        "multi_camera_info": None, "name": os.path.basename(p),
        "object_locked": None, "origin_material_id": "",
        "picture_from": "none", "picture_set_category_id": "",
        "picture_set_category_name": "", "request_id": "",
        "reverse_intensifies_path": "", "reverse_path": "",
        "team_id": "", "video_algorithm": None,
    }
    video_audio_mat = _ameta(video_path, vaid)
    audio_mat = _ameta(audio_path, aid)

    # ---- 转场素材 ----
    transition_dur_us = 500000
    transition_mat = {
        "id": tid, "name": "fade", "type": "fade",
        "duration": transition_dur_us, "overlap": False,
        "category_id": "", "category_name": "local",
        "platform": "all", "source": 0,
    }

    # ---- 构建视频 + 原声 segment ----
    video_segs = []
    video_audio_segs = []
    for i, seg in enumerate(segments):
        ss = int(seg["source_start"] * US)
        sd = int(seg["source_duration"] * US)
        ts = int(seg["target_start"] * US)
        rationale = seg.get("match_rationale", "")
        desc = f"[{i+1}/{total}] {rationale}" if rationale else f"片段 #{i+1}/{total}"

        vs = {
            "id": str(uuid.uuid4()).upper(), "material_id": vid,
            "target_timerange": {"start": ts, "duration": sd},
            "source_timerange": {"start": ss, "duration": sd},
            "speed": 1.0, "volume": 0.0, "visible": True, "desc": desc,
            "clip": {"alpha": 1.0, "flip": {"horizontal": False, "vertical": False},
                     "rotation": 0.0, "scale": {"x": 1.0, "y": 1.0},
                     "transform": {"x": 0.0, "y": 0.0}},
            "hdr_settings": {"intensity": 1.0, "mode": 1, "nits": 1000},
            "common_keyframes": [], "extra_material_refs": [], "keyframe_refs": [],
            "render_index": 0, "track_render_index": 0,
            "is_loop": False, "reverse": False, "last_nonzero_volume": 1.0,
            "enable_adjust": True, "enable_color_curves": True,
            "enable_color_wheels": True, "enable_lut": True,
            "enable_hsl": False, "enable_adjust_mask": False,
            "enable_color_correct_adjust": False,
            "enable_color_match_adjust": False,
            "enable_smart_color_adjust": False, "enable_video_mask": True,
            "template_scene": "default",
            "uniform_scale": {"on": True, "value": 1.0},
            "responsive_layout": {"enable": False, "horizontal_pos_layout": 0,
                                  "size_layout": 0, "target_follow": "",
                                  "vertical_pos_layout": 0},
            "state": 0, "caption_info": None, "cartoon": False,
            "group_id": "", "intensifies_audio": False,
            "is_placeholder": False, "is_tone_modify": False,
            "raw_segment_id": "", "template_id": "",
            "track_attribute": 0, "desc_alt": "",
            "lyric_keyframes": None,
        }
        # 最后一个片段不加转场
        if i < total - 1:
            vs["transition"] = {"id": tid, "duration": transition_dur_us,
                                "name": "fade", "type": "fade"}
        video_segs.append(vs)

        vas = {
            "id": str(uuid.uuid4()).upper(), "material_id": vaid,
            "target_timerange": {"start": ts, "duration": sd},
            "source_timerange": {"start": ss, "duration": sd},
            "speed": 1.0, "volume": 0.8, "visible": True,
            "common_keyframes": [], "extra_material_refs": [], "keyframe_refs": [],
            "render_index": 0, "track_render_index": 0,
            "is_loop": False, "reverse": False, "last_nonzero_volume": 0.8,
            "enable_adjust": False, "enable_color_curves": True,
            "enable_color_wheels": True, "enable_lut": False,
            "enable_hsl": False, "enable_adjust_mask": False,
            "enable_color_correct_adjust": False,
            "enable_color_match_adjust": False,
            "enable_smart_color_adjust": False, "enable_video_mask": True,
            "template_scene": "default",
            "responsive_layout": {"enable": False, "horizontal_pos_layout": 0,
                                  "size_layout": 0, "target_follow": "",
                                  "vertical_pos_layout": 0},
            "state": 0, "caption_info": None, "cartoon": False,
            "group_id": "", "intensifies_audio": False,
            "is_placeholder": False, "is_tone_modify": False,
            "raw_segment_id": "", "template_id": "",
            "track_attribute": 0, "desc": "",
            "lyric_keyframes": None, "hdr_settings": None,
            "uniform_scale": None, "clip": None,
        }
        video_audio_segs.append(vas)

    bgm_seg = {
        "id": str(uuid.uuid4()).upper(), "material_id": aid,
        "target_timerange": {"start": 0, "duration": aud_dur_us},
        "source_timerange": {"start": 0, "duration": aud_dur_us},
        "speed": 1.0, "volume": 1.0, "visible": True,
        "common_keyframes": [], "extra_material_refs": [], "keyframe_refs": [],
        "render_index": 0, "track_render_index": 0,
        "is_loop": False, "reverse": False, "last_nonzero_volume": 1.0,
        "enable_adjust": False, "enable_color_curves": True,
        "enable_color_wheels": True, "enable_lut": False,
        "enable_hsl": False, "enable_adjust_mask": False,
        "enable_color_correct_adjust": False,
        "enable_color_match_adjust": False,
        "enable_smart_color_adjust": False, "enable_video_mask": True,
        "template_scene": "default",
        "responsive_layout": {"enable": False, "horizontal_pos_layout": 0,
                              "size_layout": 0, "target_follow": "",
                              "vertical_pos_layout": 0},
        "state": 0, "caption_info": None, "cartoon": False,
        "group_id": "", "intensifies_audio": False,
        "is_placeholder": False, "is_tone_modify": False,
        "raw_segment_id": "", "template_id": "",
        "track_attribute": 0, "desc": "",
        "lyric_keyframes": None, "hdr_settings": None,
        "uniform_scale": None, "clip": None,
    }

    # ---- draft_content.json ----
    draft_content = {
        "canvas_config": {"background": None, "height": h, "ratio": "original", "width": w},
        "color_space": 0,
        "config": {
            "adjust_max_index": 1, "attachment_info": [],
            "combination_max_index": 1, "export_range": None,
            "extract_audio_last_index": 1, "lyrics_recognition_id": "",
            "lyrics_sync": True, "lyrics_taskinfo": [],
            "maintrack_adsorb": True, "material_save_mode": 0,
            "multi_language_current": "none", "multi_language_list": [],
            "multi_language_main": "none", "multi_language_mode": "none",
            "original_sound_last_index": 1, "record_audio_last_index": 1,
            "sticker_max_index": 1, "subtitle_keywords_config": None,
            "subtitle_recognition_id": "", "subtitle_sync": True,
            "subtitle_taskinfo": [], "system_font_list": [],
            "video_mute": True, "zoom_info_params": None,
        },
        "cover": None, "create_time": 0, "duration": aud_dur_us,
        "extra_info": None, "fps": float(fps),
        "free_render_index_mode_on": False, "group_container": None,
        "id": did, "is_drop_frame_timecode": False,
        "keyframe_graph_list": [],
        "keyframes": {"adjusts": [], "audios": [], "effects": [],
                      "filters": [], "handwrites": [], "stickers": [],
                      "texts": [], "videos": []},
        "last_modified_platform": {
            "app_id": 359289, "app_source": "cc", "app_version": "5.2.0",
            "device_id": "", "hard_disk_id": "", "mac_address": "",
            "os": "windows", "os_version": "10.0.22631",
        },
        "lyrics_effects": [],
        "materials": {
            "ai_translates": [], "audio_balances": [], "audio_effects": [],
            "audio_fades": [], "audio_track_indexes": [],
            "audios": [video_audio_mat, audio_mat],
            "beats": [], "canvases": [], "chromas": [], "color_curves": [],
            "common_mask": [], "digital_humans": [], "drafts": [],
            "effects": [], "flowers": [], "green_screens": [],
            "handwrites": [], "hsl": [], "images": [],
            "log_color_wheels": [], "loudnesses": [],
            "manual_deformations": [], "material_animations": [],
            "material_colors": [], "multi_language_refs": [],
            "placeholder_infos": [], "placeholders": [],
            "plugin_effects": [], "primary_color_wheels": [],
            "realtime_denoises": [], "shapes": [], "smart_crops": [],
            "smart_relights": [], "sound_channel_mappings": [],
            "speeds": [], "stickers": [], "tail_leaders": [],
            "text_templates": [], "texts": [], "time_marks": [],
            "transitions": [transition_mat],
            "video_effects": [], "video_trackings": [],
            "videos": [video_mat],
            "vocal_beautifys": [], "vocal_separations": [],
        },
        "mutable_config": None, "name": "", "new_version": "125.0.0",
        "path": "", "platform": {
            "app_id": 359289, "app_source": "cc", "app_version": "5.2.0",
            "device_id": "", "hard_disk_id": "", "mac_address": "",
            "os": "windows", "os_version": "10.0.22631",
        },
        "relationships": [], "render_index_track_mode_on": True,
        "retouch_cover": None, "source": "default",
        "static_cover_image_path": "", "time_marks": None,
        "tracks": [
            {"attribute": 0, "flag": 0, "id": str(uuid.uuid4()).upper(),
             "is_default_name": True, "name": "视频轨",
             "segments": video_segs, "type": "video"},
            {"attribute": 0, "flag": 0, "id": str(uuid.uuid4()).upper(),
             "is_default_name": True, "name": "原声音轨",
             "segments": video_audio_segs, "type": "audio"},
            {"attribute": 0, "flag": 0, "id": str(uuid.uuid4()).upper(),
             "is_default_name": True, "name": "BGM音轨",
             "segments": [bgm_seg], "type": "audio"},
        ],
        "update_time": 0, "version": 360000,
    }

    import json as _json
    import time as _time

    # draft_content.json
    with open(os.path.join(draft_dir, "draft_content.json"), "w", encoding="utf-8") as f:
        _json.dump(draft_content, f, ensure_ascii=False, indent=2)

    # draft_meta_info.json
    now_us = int(_time.time() * US)
    meta = {
        "draft_id": did, "draft_name": draft_name,
        "draft_fold_path": draft_dir.replace("\\", "/"),
        "draft_root_path": base_out.replace("\\", "/"),
        "draft_cover": "draft_cover.jpg",
        "draft_is_invisible": False, "draft_is_ai_shorts": False,
        "draft_is_ai_translate": False, "draft_is_article_video_draft": False,
        "draft_cloud_last_action_download": False,
        "draft_new_version": "", "draft_type": "",
        "draft_timeline_materials_size_": 0,
        "tm_draft_create": now_us, "tm_draft_modified": now_us,
        "tm_draft_removed": 0, "tm_duration": aud_dur_us,
    }
    with open(os.path.join(draft_dir, "draft_meta_info.json"), "w", encoding="utf-8") as f:
        _json.dump(meta, f, ensure_ascii=False, indent=2)

    # ---- 平台特定同步 ----
    platform_sync_path = None
    platform_label = _get_platform_label(platform)

    if platform in ("jianying", "capcut"):
        target_dir = config.JIANYING_DRAFT_DIR if platform == "jianying" else config.CAPCUT_DRAFT_DIR
        if target_dir and os.path.exists(os.path.dirname(target_dir)):
            platform_sync_path = os.path.join(target_dir, draft_name)
            try:
                if os.path.exists(platform_sync_path):
                    shutil.rmtree(platform_sync_path)
                shutil.copytree(draft_dir, platform_sync_path)
                print(f"   [Sync] Synced to {platform_label}: {platform_sync_path}")
            except Exception as e:
                print(f"   [WARN] Sync to {platform_label} failed: {e}")
                platform_sync_path = None
        elif platform == "capcut" and not target_dir:
            print(f"   [WARN] CapCut not detected — draft in output/ only")
    elif platform == "resolve":
        resolve_dir = os.path.join(config.RESOLVE_OUTPUT_DIR, task_id, draft_name)
        os.makedirs(resolve_dir, exist_ok=True)
        _copy_draft_to_dir(os.path.dirname(draft_dir), draft_name, resolve_dir)
        platform_sync_path = resolve_dir
        print(f"   [Sync] Saved to {platform_label}: {resolve_dir}")
    elif platform == "universal":
        universal_dir = os.path.join(config.UNIVERSAL_OUTPUT_DIR, task_id, draft_name)
        os.makedirs(universal_dir, exist_ok=True)
        _copy_draft_to_dir(os.path.dirname(draft_dir), draft_name, universal_dir)
        platform_sync_path = universal_dir
        print(f"   [Sync] Saved to {platform_label}: {universal_dir}")

    mode_label = "Video First" if editing_mode == "video_first" else "Music First"
    smode = "Smart" if smart_segments else "Beat"
    hint = (
        f"{smode} edit ({mode_label}): {total} clips.\n"
        f"3-track: Video(muted) | Original Audio | BGM.\n"
        f"Open in {platform_label} to adjust volume, drag clips, add transitions."
    )

    return {
        "draft_folder": draft_dir,
        "capcut_draft_path": platform_sync_path,
        "draft_name": draft_name,
        "editing_hint": hint,
        "platform": platform,
        "platform_label": platform_label,
    }
