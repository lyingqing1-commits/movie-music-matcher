"""
AI 音乐生成模块 - 根据电影风格分析生成匹配的 AI 音乐
=====================================================
使用 HuggingFace Inference API (facebook/musicgen-small)
免费，每日 ~1000 次调用

备选：Replicate API (meta/musicgen)，质量更高但需付费
"""
import os
import time
import json
import requests
import config


def build_prompt_from_style(rec: dict, variant: str = "main") -> str:
    """
    将电影风格推荐的音乐参数转换为英文 text-to-music prompt。
    MusicGen 需要英文描述，格式: "genre, mood, instruments, tempo"

    参数：
        rec: style_analysis 中的 recommended_music 字典
             {genre, tempo_bpm, instruments, mood_match, lyrics_theme}
        variant: "main" | "softer" | "dramatic" — 控制风格变体

    返回：
        英文 prompt 字符串
    """
    genre = rec.get("genre", "cinematic").lower()
    tempo = rec.get("tempo_bpm", 120)
    instruments = rec.get("instruments", ["piano", "strings"])
    mood = rec.get("mood_match", "emotional")
    if isinstance(instruments, list):
        instruments_str = ", ".join(instruments)
    else:
        instruments_str = str(instruments)

    # 根据变体调整 prompt
    variant_modifiers = {
        "main": f"{genre} music, {mood}, featuring {instruments_str}, {tempo} bpm, cinematic quality",
        "softer": f"soft and gentle {genre}, ambient and atmospheric {mood}, light {instruments_str}, slow {max(60, tempo - 20)} bpm, dreamy",
        "dramatic": f"dramatic and intense {genre}, powerful {mood}, grand {instruments_str}, {min(180, tempo + 20)} bpm, epic orchestral crescendo",
    }

    prompt = variant_modifiers.get(variant, variant_modifiers["main"])
    return prompt


def build_music_prompts(style_analysis: dict, count: int = 3) -> list[dict]:
    """
    根据电影风格分析构建多个不同风格偏向的音乐 prompt。

    参数：
        style_analysis: 风格分析结果（来自 style_analyzer.analyze_style()）
        count: 生成 prompt 数量（2-3 个）

    返回：
        [{"label": "选项名", "prompt": "英文描述", "variant": "main|softer|dramatic"}, ...]
    """
    rec = style_analysis.get("recommended_music", {})

    # 定义变体
    variants = [
        {"variant": "main", "label": f"🎯 标准匹配 — {rec.get('genre', '电影配乐')}风格"},
        {"variant": "softer", "label": f"🌙 柔和氛围 — 舒缓{rec.get('genre', '氛围')}变奏"},
        {"variant": "dramatic", "label": f"🔥 戏剧张感 — 激昂{rec.get('genre', '史诗')}演绎"},
    ]

    prompts = []
    for i, v in enumerate(variants[:count]):
        prompt_text = build_prompt_from_style(rec, v["variant"])
        prompts.append({
            "label": v["label"],
            "prompt": prompt_text,
            "variant": v["variant"],
            "index": i,
        })

    return prompts


def generate_track_hf(
    prompt: str,
    output_path: str,
    token: str = None,
    model: str = None,
    duration: int = 15,
    max_retries: int = 3,
) -> bool:
    """
    调用 HuggingFace Inference API 生成一首 AI 音乐。

    参数：
        prompt: 英文文本描述
        output_path: 输出 WAV 文件路径
        token: HF API token（默认从 config 读取）
        model: 模型 ID（默认从 config 读取）
        duration: 时长（秒）
        max_retries: 最大重试次数

    返回：
        True 成功，False 失败
    """
    token = token or config.HUGGINGFACE_API_TOKEN
    model = model or config.AI_MUSIC_MODEL

    if not token:
        print("❌ HuggingFace API Token 未配置，无法生成 AI 音乐。")
        print("   请在 config.py 中设置 HUGGINGFACE_API_TOKEN")
        print("   免费获取: https://huggingface.co/settings/tokens")
        return False

    api_url = f"https://api-inference.huggingface.co/models/{model}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "inputs": prompt,
        "parameters": {
            "max_new_tokens": duration * 50,  # 粗略估算：每秒 ~50 tokens
            "do_sample": True,
            "temperature": 0.9,
            "top_p": 0.95,
        },
    }

    for attempt in range(max_retries):
        try:
            print(f"   🎵 生成音乐 (尝试 {attempt + 1}/{max_retries}): {prompt[:80]}...")
            response = requests.post(
                api_url,
                headers=headers,
                json=payload,
                timeout=180,  # 模型加载 + 生成可能需要较长时间
            )

            # 模型冷启动：返回 JSON 表示正在加载
            content_type = response.headers.get("content-type", "")
            if "application/json" in content_type:
                resp_json = response.json()
                if isinstance(resp_json, dict) and "estimated_time" in resp_json:
                    wait_time = resp_json.get("estimated_time", 20)
                    print(f"   ⏳ 模型加载中，等待 {wait_time:.0f} 秒...")
                    time.sleep(wait_time + 5)
                    continue
                elif isinstance(resp_json, dict) and "error" in resp_json:
                    error_msg = resp_json["error"]
                    # 模型加载中的错误
                    if "loading" in str(error_msg).lower():
                        wait_time = 30
                        print(f"   ⏳ 模型仍在加载，等待 {wait_time} 秒...")
                        time.sleep(wait_time)
                        continue
                    print(f"   ⚠️ API 错误: {error_msg}")
                    if attempt < max_retries - 1:
                        time.sleep(10)
                        continue
                    return False

            # 成功：响应是音频字节流
            if response.status_code == 200 and len(response.content) > 1000:
                with open(output_path, "wb") as f:
                    f.write(response.content)
                size_kb = len(response.content) / 1024
                print(f"   ✅ 音乐已保存: {os.path.basename(output_path)} ({size_kb:.0f} KB)")
                return True
            elif response.status_code == 503:
                print(f"   ⏳ 服务繁忙 (503)，等待 15 秒...")
                time.sleep(15)
                continue
            else:
                print(f"   ⚠️ HTTP {response.status_code}, body: {response.content[:200]}")
                if attempt < max_retries - 1:
                    time.sleep(10)
                    continue
                return False

        except requests.exceptions.Timeout:
            print(f"   ⚠️ 请求超时（180秒），重试...")
            if attempt < max_retries - 1:
                time.sleep(10)
                continue
            return False
        except Exception as e:
            print(f"   ⚠️ 生成失败: {e}")
            if attempt < max_retries - 1:
                time.sleep(10)
                continue
            return False

    return False


def generate_music_options(
    style_analysis: dict,
    task_id: str,
    count: int = None,
    duration: int = None,
    output_dir: str = None,
) -> list[dict]:
    """
    根据电影风格分析生成多首 AI 音乐备选。

    参数：
        style_analysis: 风格分析结果
        task_id: 任务 ID
        count: 生成数量（默认从 config 读取）
        duration: 每首时长（秒）
        output_dir: 输出目录

    返回：
        [{
            "path": "文件路径",
            "label": "显示名称",
            "prompt": "生成用的 prompt",
            "variant": "main|softer|dramatic",
            "index": 0,
            "duration_seconds": 15,
            "success": True/False,
        }, ...]
    """
    count = count or config.AI_MUSIC_COUNT
    duration = duration or config.AI_MUSIC_DURATION

    # 输出目录
    if output_dir is None:
        output_dir = os.path.join(config.UPLOAD_FOLDER, task_id, "ai_music")
    os.makedirs(output_dir, exist_ok=True)

    # 检查 API Token
    if not config.HUGGINGFACE_API_TOKEN:
        print("❌ AI 音乐生成未配置。请在 config.py 中设置 HUGGINGFACE_API_TOKEN")
        return []

    print(f"\n🎵 开始生成 {count} 首 AI 音乐...")
    print(f"   电影类型: {style_analysis.get('genre', '?')}")
    print(f"   情绪: {style_analysis.get('mood', '?')}")
    rec = style_analysis.get("recommended_music", {})
    print(f"   推荐音乐: {rec.get('genre', '?')}, BPM {rec.get('tempo_bpm', '?')}")

    # 构建 prompts
    prompts = build_music_prompts(style_analysis, count)
    print(f"   生成了 {len(prompts)} 个音乐描述")

    # 逐个生成
    results = []
    for i, p in enumerate(prompts):
        filename = f"ai_track_{i+1}.wav"
        filepath = os.path.join(output_dir, filename)

        print(f"\n   [{i+1}/{count}] {p['label']}")
        print(f"   Prompt: {p['prompt'][:100]}...")

        success = generate_track_hf(
            prompt=p["prompt"],
            output_path=filepath,
            duration=duration,
        )

        result = {
            "path": filepath if success else None,
            "label": p["label"],
            "prompt": p["prompt"],
            "variant": p["variant"],
            "index": i,
            "duration_seconds": duration,
            "success": success,
        }
        results.append(result)

        if not success:
            print(f"   ❌ 第 {i+1} 首生成失败")

    # 统计
    success_count = sum(1 for r in results if r["success"])
    print(f"\n✅ AI 音乐生成完成: {success_count}/{count} 首成功")

    return results
