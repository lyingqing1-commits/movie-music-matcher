# 剪映/草稿生成已知问题与规避方案

Documenting known issues with pyJianYingDraft and JianYing/CapCut draft generation.

## pyJianYingDraft 已知限制

### 1. 素材路径

- **绝对路径必须可访问**：草稿中的素材路径在剪映打开时必须有效
- **路径分隔符**：Windows 上使用 `/` 而非 `\`（剪映内部使用 Unix 风格路径）
- **网络路径**：不支持 UNC 路径 (`\\server\share`)，素材必须在本地磁盘

### 2. 微秒精度

- 剪映时间轴使用微秒 (`US = 1_000_000`)
- `Timerange` 的 start 和 duration 必须在有效范围内
- 单帧时长 = `1_000_000 / fps` 微秒

### 3. 素材格式兼容

- 视频：H.264/H.265 编码最佳；ProRes/DNxHD 可能无法导入
- 音频：AAC/MP3 无问题；FLAC/OGG 需测试
- 图片：JPEG/PNG 标准支持；HEIC/WebP 可能不被识别

### 4. Draft 目录结构

```
{capcut_draft_dir}/
  {draft_name}/
    draft_content.json    # 核心内容（轨道、片段、素材）
    draft_meta_info.json  # 元数据（封面、修改时间、时长）
    draft_cover.jpg       # 可选：封面缩略图
```

⚠️ **关键**：`draft_content.json` 中 `materials` 部分的 `id` 必须与 `tracks.segments[].material_id` 严格匹配。

### 5. 已知问题表

| 问题 | 症状 | 规避方案 |
|------|------|---------|
| 素材 ID 不匹配 | 剪映打开草稿后素材离线 | 使用 UUID (32位 hex) 作为 material_id，确保 tracks 引用一致 |
| 时间范围越界 | timeline_out 超过素材实际时长 | 构建前验证所有 source_out <= 素材实际时长 |
| 轨道类型错误 | 音频片段出现在视频轨道 | `TrackType.video` / `TrackType.audio` 必须匹配片段类型 |
| FPS 不匹配 | 片段时码错位 | 使用 FFprobe 检测的实际 FPS，不要假设 30fps |
| 同时打开冲突 | 剪映锁定草稿文件 | 生成前确保剪映未打开该草稿；使用唯一名称 |
| 版本不兼容 | 旧版剪映无法打开新版草稿 | `draft_content.json` 中 `version` 字段匹配目标版本 |
| 手动 JSON 模式路径错误 | 草稿无法定位素材 | 确保 `materials.videos[].path` 使用正斜杠 |
| 大文件导入慢 | 剪映启动时扫描大素材 | 使用代理/低分辨率版本作为草稿，后期替换 |

### 6. 验证检查清单

生成草稿后，在剪映中打开前检查：

- [ ] `draft_content.json` 是有效 JSON（`json.loads` 可解析）
- [ ] `draft_meta_info.json` 存在且 `tm_duration > 0`
- [ ] 所有 `material_id` 在 `tracks` 和 `materials` 之间一致
- [ ] `source_timerange.start + source_timerange.duration` ≤ 素材总时长
- [ ] `target_timerange` 的总和覆盖完整时间线（总时长匹配）
- [ ] 视频素材的 `path` 在本地文件系统存在
- [ ] 草稿目录名不包含特殊字符（中文 OK，避免 `:/\*?<>|`）

### 7. 调试技巧

在剪映中查看草稿日志：
```
%LOCALAPPDATA%\JianyingPro\User Data\Projects\logs\
```

常见日志关键词：
- `draft_parse_error` — JSON 格式问题
- `material_not_found` — 素材路径无效
- `track_overflow` — 轨道数量超出
- `segment_invalid` — 片段参数无效
