# 剪辑蓝图 Schema v1.0

Movie Music Matcher 标准剪辑蓝图格式。所有 `blueprint_generator` 输出必须符合此 schema。

## 顶层结构

```json
{
  "schema_version": "1.0",
  "project": {
    "name": "项目名称",
    "fps": 30,
    "width": 1920,
    "height": 1080,
    "target_duration_seconds": 120,
    "platform": "jianying",
    "aspect_ratio": "16:9"
  },
  "tracks": {
    "video": ["V1"],
    "audio": ["A1", "A2"]
  },
  "clips": [...],
  "narration": [...],
  "music": [...],
  "captions": [...],
  "notes": []
}
```

## Clip 字段规范

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | ✅ | 唯一标识，如 `clip-001` |
| `media_type` | string | ✅ | `"video"` / `"audio"` / `"image"` |
| `source_path` | string | ✅ | 绝对路径 |
| `source_in_seconds` | float | ✅ | 素材入点（秒） |
| `source_out_seconds` | float | ✅ | 素材出点（秒） |
| `timeline_in_seconds` | float | ✅ | 时间线入点（秒） |
| `timeline_out_seconds` | float | ✅ | 时间线出点（秒） |
| `video_track` | int | ✅ | 视频轨道编号 (1-based) |
| `audio_track` | int | ✅ | 音频轨道编号 (1-based) |
| `purpose` | string | ✅ | 此片段的作用说明 |
| `source_group` | string | ❌ | 素材来源分组（如 `"camera-a"`） |
| `emotional_tone` | string | ❌ | 情感基调 |
| `highlight_score` | float | ❌ | 高光度评分 (0-100) |
| `confidence` | float | ❌ | AI 对此放置的置信度 (0-1) |
| `speed` | float | ❌ | 变速倍率（默认 1.0） |
| `volume` | float | ❌ | 音量 (0-1，默认 1.0) |
| `transition` | object | ❌ | 转场效果 |

## 验证规则

1. **时长一致性**：`source_out - source_in` 应等于 `timeline_out - timeline_in`（除非声明了变速）
2. **素材边界**：`source_out_seconds` ≤ 素材实际时长
3. **连续无间隙**：相邻 clip 的 `timeline_out` 与下一个 `timeline_in` 之间的间隙 < 1 帧
4. **正向时长**：所有 duration > 0
5. **轨道范围**：轨道编号在 `tracks` 声明的范围内
6. **路径存在**：构建时 `source_path` 必须可访问
7. **不重复相邻**：连续两个 clip 不应来自同一素材的相邻范围（防止"伪切"）
8. **图片时长声明**：`media_type == "image"` 时 `source_out - source_in` 必须明确声明（默认 5 秒）

## 音乐轨道

```json
{
  "source_path": "/path/to/bgm.mp3",
  "timeline_in_seconds": 0,
  "timeline_out_seconds": 120,
  "volume": 0.8,
  "fade_in_seconds": 2.0,
  "fade_out_seconds": 3.0
}
```

## 旁白/TTS 轨道

```json
{
  "text": "旁白文本",
  "timeline_in_seconds": 5.0,
  "timeline_out_seconds": 8.5,
  "audio_path": "/path/to/tts/segment_001.wav",
  "speaker": "default"
}
```
