"""
音乐匹配模块 - 分析音乐特征并与电影风格匹配
"""
import os
import json
from anthropic import Anthropic
import numpy as np
import config


def _safe_float(value) -> float:
    """安全地将 numpy 值转换为 Python float"""
    if isinstance(value, np.ndarray):
        if value.ndim == 0:
            return value.item()
        elif value.ndim == 1 and value.shape[0] == 1:
            return value[0].item()
        else:
            raise ValueError(f"Cannot convert array of shape {value.shape} to float")
    return float(value)


def _safe_int(value) -> int:
    """安全地将 numpy 值转换为 Python int"""
    if isinstance(value, np.ndarray):
        if value.ndim == 0:
            return value.item()
        elif value.ndim == 1 and value.shape[0] == 1:
            return value[0].item()
        else:
            raise ValueError(f"Cannot convert array of shape {value.shape} to int")
    return int(value)


def _get_response_text(response) -> str:
    """从 API 响应中提取文本（跳过 ThinkingBlock 思考链）"""
    for block in response.content:
        if getattr(block, "type", None) == "text":
            return getattr(block, "text", "") or ""
    return str(response.content[0]) if response.content else ""

# 尝试导入 librosa，如果未安装则提示
try:
    import librosa
    HAS_LIBROSA = True
except ImportError:
    HAS_LIBROSA = False
    print("⚠️ librosa 未安装。音频分析功能将受限。")


def analyze_audio(audio_path: str) -> dict:
    """
    使用 librosa 分析音频特征
    返回节拍、能量、频谱等基础特征
    """
    if not HAS_LIBROSA:
        return {
            "error": "librosa 未安装，无法分析音频。请运行: pip install librosa",
            "file_path": audio_path,
        }

    print(f"🎵 正在分析音频: {os.path.basename(audio_path)}")

    # 加载音频（librosa 自动处理重采样）
    y, sr = librosa.load(audio_path, sr=22050, duration=120)  # 最多分析 2 分钟

    # 时长
    duration = librosa.get_duration(y=y, sr=sr)

    # 节拍检测
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    tempo = _safe_float(tempo)

    # 能量（RMS）
    rms = librosa.feature.rms(y=y)
    energy = _safe_float(np.mean(rms))

    # 频谱质心（音色明亮度）
    spectral_centroid = librosa.feature.spectral_centroid(y=y, sr=sr)
    brightness = _safe_float(np.mean(spectral_centroid))

    # 频谱带宽
    spectral_bandwidth = librosa.feature.spectral_bandwidth(y=y, sr=sr)
    bandwidth = _safe_float(np.mean(spectral_bandwidth))

    # 过零率（与音高/噪音相关）
    zcr = librosa.feature.zero_crossing_rate(y)
    zcr_mean = _safe_float(np.mean(zcr))

    # 估算调性（简化版：基于 chroma 特征）
    chroma = librosa.feature.chroma_stft(y=y, sr=sr)
    chroma_mean = np.mean(chroma, axis=1)
    pitch_classes = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    dominant_pitch_idx = _safe_int(np.argmax(chroma_mean))
    estimated_key = pitch_classes[dominant_pitch_idx]

    result = {
        "file_path": audio_path,
        "duration_seconds": round(duration, 1),
        "tempo_bpm": round(tempo, 1),
        "energy": round(energy, 4),
        "brightness": round(brightness, 1),
        "bandwidth": round(bandwidth, 1),
        "zcr_mean": round(zcr_mean, 4),
        "estimated_key": estimated_key,
        "sample_rate": sr,
    }

    print(f"   BPM: {result['tempo_bpm']}, 能量: {result['energy']}, 调性: {estimated_key}")
    return result


# 音乐匹配的系统提示词
MATCHING_PROMPT = """你是一位专业的影视配乐师。你需要根据电影风格分析结果和音乐特征数据，评估音乐与电影的匹配程度。

请从以下角度进行评估：
1. **情绪匹配度**：音乐的情绪是否与电影画面一致？
2. **节奏匹配度**：音乐的 BPM 是否适合画面的节奏感？
3. **风格协调性**：音乐风格是否与电影类型协调？
4. **主题契合度**：音乐的调性和能量是否支持电影的主题表达？

返回严格的 JSON 格式：
{
  "match_score": 0-100的匹配评分,
  "is_good_match": true/false,
  "analysis": "详细的匹配分析（1-2句话）",
  "editing_suggestion": "剪辑建议：如何将视频与音乐配合（如：在高潮段落使用画面A，在间奏使用画面B）",
  "music_mood": "这首音乐传达的情绪",
  "key_moments": ["音乐的关键转折点1（秒）", "关键转折点2（秒）"]
}"""


def match_music_to_style(
    movie_style: dict,
    audio_features_list: list[dict],
) -> list[dict]:
    """
    将多首音乐与电影风格进行匹配，返回排序后的匹配结果
    """
    if not config.ANTHROPIC_API_KEY:
        raise ValueError("请先在 config.py 中设置 ANTHROPIC_API_KEY。")

    # 创建客户端（支持自定义 base_url）
    client_kwargs = {"api_key": config.ANTHROPIC_API_KEY}
    if config.ANTHROPIC_BASE_URL:
        client_kwargs["base_url"] = config.ANTHROPIC_BASE_URL
    client = Anthropic(**client_kwargs)
    results = []

    for i, audio_feat in enumerate(audio_features_list):
        audio_name = audio_feat.get("file_path", f"音乐{i+1}")
        print(f"🎼 正在匹配: {os.path.basename(audio_name)}")

        # 构建用户消息
        user_message = f"""请评估以下电影和音乐的匹配度：

【电影风格分析】
{json.dumps(movie_style, ensure_ascii=False, indent=2)}

【音乐特征】
{json.dumps(audio_feat, ensure_ascii=False, indent=2)}

请返回 JSON 格式的匹配评估。"""

        response = client.messages.create(
            model=config.AI_MODEL,
            max_tokens=2048,
            system=MATCHING_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        response_text = _get_response_text(response)

        # 安全检查
        if not response_text or not isinstance(response_text, str):
            response_text = str(response_text) if response_text else ""

        # 提取 JSON
        if "```json" in response_text:
            json_start = response_text.find("```json") + 7
            json_end = response_text.find("```", json_start)
            response_text = response_text[json_start:json_end].strip()
        elif "```" in response_text:
            json_start = response_text.find("```") + 3
            json_end = response_text.find("```", json_start)
            response_text = response_text[json_start:json_end].strip()

        try:
            match_result = json.loads(response_text) if response_text else {}
        except json.JSONDecodeError:
            match_result = {
                "match_score": 50,
                "is_good_match": False,
                "analysis": "分析失败",
                "editing_suggestion": "请手动调整",
                "music_mood": "未知",
                "key_moments": [],
                "raw": response_text,
            }

        # 合并音频特征和匹配结果
        combined = {**audio_feat, "match": match_result}
        results.append(combined)

    # 按匹配分数降序排列
    results.sort(key=lambda x: x["match"].get("match_score", 0), reverse=True)

    print(f"✅ 音乐匹配完成，共 {len(results)} 首")
    if results:
        best = results[0]
        print(f"   最佳匹配: {os.path.basename(best['file_path'])} (评分: {best['match'].get('match_score', '?')})")

    return results
