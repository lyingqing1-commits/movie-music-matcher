"""
配置文件模板 — 复制为 config.py 并填入你的 API Key
"""
import os

# ============================================
# 📦 应用版本
# ============================================
APP_VERSION = "1.0.0"

# ============================================
# 🔄 Git 自动更新配置
# ============================================
# 配置 Git 远程仓库地址后，即可使用一键自动更新
# 支持 GitHub / Gitee / 私有 Git 服务器
GIT_REMOTE_URL = ""   # Git 远程仓库地址（留空则使用手动下载更新）
GIT_BRANCH = "main"   # 跟踪的分支名

# ============================================
# 🔑 API 配置
# ============================================

# ---- DeepSeek API（通过 Anthropic 兼容协议）----
ANTHROPIC_API_KEY = "sk-your-deepseek-api-key"
ANTHROPIC_BASE_URL = "https://api.deepseek.com/anthropic"
AI_MODEL = "deepseek-v4-pro"

# ---- 或使用 Anthropic 官方 API ----
# ANTHROPIC_API_KEY = "sk-ant-..."
# ANTHROPIC_BASE_URL = None
# AI_MODEL = "claude-sonnet-4-6"

# ============================================
# 📁 路径配置
# ============================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
FRAME_FOLDER = os.path.join(BASE_DIR, "frames")
OUTPUT_FOLDER = os.path.join(BASE_DIR, "output")

# 剪映草稿目录（自动检测）
def _detect_capcut_draft_dir() -> str:
    candidates = [
        r"%LOCALAPPDATA%\JianyingPro\User Data\Projects\com.lveditor.draft",
        r"%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft",
    ]
    for path in candidates:
        expanded = os.path.expandvars(path)
        parent = os.path.dirname(expanded)
        if os.path.exists(parent):
            return expanded
    return os.path.expandvars(r"%LOCALAPPDATA%\JianyingPro\User Data\Projects\com.lveditor.draft")

CAPCUT_DRAFT_DIR = _detect_capcut_draft_dir()

# ============================================
# 🎬 视频处理配置
# ============================================
FRAME_EXTRACT_INTERVAL = 1
MAX_FRAMES = 60
FRAME_QUALITY = 2
FRAME_MAX_WIDTH = 640

# ============================================
# 📤 上传限制
# ============================================
MAX_VIDEO_SIZE_MB = 500
MAX_AUDIO_SIZE_MB = 50
ALLOWED_VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv', '.webm'}
ALLOWED_AUDIO_EXTENSIONS = {'.mp3', '.wav', '.flac', '.aac', '.m4a', '.ogg'}

# ============================================
# 🎨 分析配置
# ============================================
SAMPLE_FRAMES = 10

# ============================================
# 🤖 AI 音乐生成配置
# ============================================
HUGGINGFACE_API_TOKEN = "hf_your-huggingface-token"
AI_MUSIC_MODEL = "facebook/musicgen-small"
AI_MUSIC_COUNT = 3
AI_MUSIC_DURATION = 15
AI_MUSIC_MAX_RETRIES = 3
