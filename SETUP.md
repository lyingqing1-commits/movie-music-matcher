# Movie Music Matcher — 安装指南

在其他电脑上运行本应用的完整步骤。

---

## 快速开始（3 步）

### 第 1 步：安装基础环境

| 需要 | 下载地址 | 说明 |
|------|---------|------|
| **Python 3.10+** | https://www.python.org/downloads/ | ⚠️ 安装时勾选「Add Python to PATH」 |
| **FFmpeg** | https://ffmpeg.org/download.html | 视频处理必需 |

**Windows 一键安装 FFmpeg**（推荐）：
```powershell
winget install Gyan.FFmpeg
```

### 第 2 步：获取代码并安装依赖

```bash
# 下载项目
git clone https://github.com/lyingqing1-commits/movie-music-matcher.git
cd movie-music-matcher

# 一键安装所有依赖
python install.py
```

`install.py` 会自动：
- 检查 Python / pip / FFmpeg 是否就绪
- 安装 `requirements.txt` 中的所有包
- 创建 `.env` 配置文件模板
- 运行环境健康检查

### 第 3 步：配置 API Key 并启动

```bash
# 编辑 .env，填入你的 DeepSeek API Key
notepad .env

# 启动应用
python app.py
```

浏览器打开 **http://localhost:5000** 即可使用。

---

## 手动安装（如果自动安装失败）

### 1. 安装 Python 包

```bash
pip install -r requirements.txt
```

`requirements.txt` 包含：
```
flask>=3.0          # Web 框架
anthropic>=0.40.0   # AI API 客户端
librosa>=0.10.0     # 音频分析
soundfile>=0.12.0   # 音频文件读写
Pillow>=10.0.0      # 图片处理
numpy               # 数值计算
requests            # HTTP 请求
```

可选包（非必需）：
```
ffmpeg-python>=0.2.0   # FFmpeg Python 封装（高级功能）
pyJianYingDraft>=0.1.0 # 剪映草稿生成（生成完整草稿）
```

### 2. 配置 API Key

复制模板并编辑：
```bash
copy .env.example .env    # Windows
cp .env.example .env      # Mac/Linux
```

编辑 `.env` 填入你的密钥：
```ini
ANTHROPIC_API_KEY=sk-你的-deepseek-api-key
AI_MODEL=deepseek-chat
```

> 在 https://platform.deepseek.com/api_keys 创建 API Key（新用户有免费额度）

### 3. 验证环境

```bash
python check_setup.py
```

确保 14 项检查全部通过。

### 4. 启动

```bash
python app.py
```

---

## 不使用 Git 的传输方式

### 方式 A：U 盘/移动硬盘

```
1. 复制整个 movie-music-matcher 文件夹到 U 盘
2. 在目标电脑上粘贴到任意位置
3. cd movie-music-matcher
4. python install.py
5. 配置 .env → python app.py
```

### 方式 B：ZIP 压缩包

```
1. 右键 movie-music-matcher 文件夹 → 发送到 → 压缩文件夹
2. 将 .zip 文件发送到目标电脑
3. 解压到任意位置
4. python install.py
5. 配置 .env → python app.py
```

---

## 常见问题

### Q: 启动后显示「网页无法访问」

检查是否成功启动了 Flask：
```bash
python app.py
```
应该看到：
```
 * Running on http://127.0.0.1:5000
```

### Q: 上传文件后处理失败

运行环境检查确认所有依赖就绪：
```bash
python check_setup.py
```

### Q: AI 分析返回错误

- 确认 `.env` 中 `ANTHROPIC_API_KEY` 已正确填入
- 确认 `AI_MODEL=deepseek-chat`（不要用 `deepseek-v4-pro`）
- 在 https://platform.deepseek.com 检查 API 余额

### Q: FFmpeg 找不到

Windows:
```powershell
winget install Gyan.FFmpeg
# 重启终端后生效
```

Mac:
```bash
brew install ffmpeg
```

Linux:
```bash
sudo apt install ffmpeg
```

### Q: pyJianYingDraft 安装失败

这是可选包。安装失败不影响基本功能（会自动回退到手动 JSON 模式）：
```bash
pip install pyJianYingDraft
```

---

## 文件结构说明（便携性）

```
movie-music-matcher/
  install.py          ← 一键安装脚本
  check_setup.py      ← 环境健康检查
  app.py              ← 主程序入口
  config.py           ← 配置文件（从 .env 读取）
  requirements.txt    ← Python 依赖清单
  .env.example        ← 配置模板
  .env                ← 你的实际配置（不提交到 Git）
  modules/            ← 功能模块
  templates/          ← 网页模板
  static/             ← CSS/JS 前端文件
  references/         ← 参考文档
```

核心原则：
- `.env` 包含密钥，**不提交到 Git**
- 其他文件无机器特定路径，可在任意位置运行
- `uploads/` `frames/` `output/` `workspace/` 首次运行时自动创建
