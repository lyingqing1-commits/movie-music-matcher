"""
配置文件 - 在这里设置你的 API Key 和路径
=======================================
优先从 .env 文件读取配置，不存在时使用默认值。
复制 .env.example → .env 后填入你的密钥即可。
"""
import os

# ============================================
# 📦 加载 .env 文件（如果存在）
# ============================================
def _load_dotenv():
    """从 .env 文件加载环境变量（不依赖 python-dotenv 库）"""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                # 不移除引号（保持原样）
                if key and key not in os.environ:
                    os.environ[key] = value

_load_dotenv()


def _env(key: str, default: str = "") -> str:
    """从环境变量读取配置，回退到默认值"""
    return os.environ.get(key, default)

# ============================================
# 📦 应用版本
# ============================================
APP_VERSION = "3.0.0"

# ============================================
# 🔄 Git 自动更新配置
# ============================================
# 配置 Git 远程仓库地址后，即可使用一键自动更新
# 支持 GitHub / Gitee / 私有 Git 服务器
# 示例:
#   GIT_REMOTE_URL = "https://github.com/yourname/movie-music-matcher.git"
#   GIT_BRANCH = "main"
GIT_REMOTE_URL = _env("GIT_REMOTE_URL", "https://github.com/lyingqing1-commits/movie-music-matcher.git")
GIT_BRANCH = _env("GIT_BRANCH", "master")  # 跟踪的分支名

# ============================================
# 🔑 API 配置
# ============================================

# ---- 使用你已有的 DeepSeek API（通过 Anthropic 兼容协议）----
# 在 .env 文件中设置 ANTHROPIC_API_KEY=sk-xxx
# 如果 .env 不存在，使用下面的默认值
ANTHROPIC_API_KEY = _env("ANTHROPIC_API_KEY", "")
ANTHROPIC_BASE_URL = _env("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic")
# DeepSeek Anthropic 兼容端点支持的模型:
#   deepseek-chat      → DeepSeek-V3（推荐，日常使用）
#   deepseek-reasoner  → DeepSeek-R1（深度推理）
AI_MODEL = _env("AI_MODEL", "deepseek-chat")

# DeepSeek 的 Anthropic 兼容端点不支持 Vision/图片输入
# 设为 False 后，图片分析模块会直接走回退路径（元数据模式），
# 避免浪费 API 调用和等待时间
VISION_SUPPORTED = False

# ---- 如果你有 Anthropic 官方 API Key，可以改用以下配置 ----
# ANTHROPIC_API_KEY = "sk-ant-..."  # 替换为你的 Anthropic Key
# ANTHROPIC_BASE_URL = None  # None 表示使用 Anthropic 官方地址
# AI_MODEL = "claude-sonnet-4-6"

# ⚠️ 注意：如果 DeepSeek 不支持图片分析（Vision），
#    视频帧分析将回退到"元数据模式"（分析颜色、亮度、运动等数值特征）

# ============================================
# 📁 路径配置
# ============================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
FRAME_FOLDER = os.path.join(BASE_DIR, "frames")
OUTPUT_FOLDER = os.path.join(BASE_DIR, "output")

# 剪映草稿目录（自动检测，根据实际情况修改）
def _detect_capcut_draft_dir() -> str:
    """自动检测 CapCut / 剪映专业版草稿目录"""
    candidates = [
        r"%LOCALAPPDATA%\JianyingPro\User Data\Projects\com.lveditor.draft",  # 剪映专业版（中国版）
        r"%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft",       # CapCut（国际版）
    ]
    for path in candidates:
        expanded = os.path.expandvars(path)
        parent = os.path.dirname(expanded)
        if os.path.exists(parent):
            return expanded
    # 回退：优先尝试 JianyingPro（剪映专业版）
    return os.path.expandvars(r"%LOCALAPPDATA%\JianyingPro\User Data\Projects\com.lveditor.draft")

CAPCUT_DRAFT_DIR = _detect_capcut_draft_dir()

# ============================================
# 📂 v3.0 工作空间配置 (DaVinci-AutoEdit-Agent 风格)
# ============================================
WORKSPACE_DIR = os.path.join(BASE_DIR, "workspace")
MAX_RUN_FOLDERS = 50               # 最多保留的运行目录数
DEFAULT_PLATFORM = "jianying"      # 默认目标平台
DEFAULT_ASPECT_RATIO = "16:9"      # 默认画幅比
BLUEPRINT_SCHEMA_VERSION = "1.0.0" # 蓝图 schema 版本

# ============================================
# 🎬 视频处理配置
# ============================================
FRAME_EXTRACT_INTERVAL = 1      # 每隔多少秒提取一帧
MAX_FRAMES = 60                  # 最多提取帧数
FRAME_QUALITY = 2                # JPEG 质量 (1-31, 越小越好)
FRAME_MAX_WIDTH = 640            # 帧最大宽度（降低分辨率以节省 API 费用）

# ============================================
# 📤 上传限制
# ============================================
MAX_VIDEO_SIZE_MB = 2000         # 视频最大大小 (MB)，支持 2GB 以内大文件
MAX_AUDIO_SIZE_MB = 200          # 音频最大大小 (MB)
ALLOWED_VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv', '.webm'}
ALLOWED_AUDIO_EXTENSIONS = {'.mp3', '.wav', '.flac', '.aac', '.m4a', '.ogg'}

# ============================================
# 🎨 分析配置
# ============================================
SAMPLE_FRAMES = 10               # 发送给 AI 分析的采样帧数

# ============================================
# ✂️ 智能剪辑配置
# ============================================
SMART_EDITING_ENABLED = True         # 启用智能剪辑（False 时回退到节拍等分模式）
DEFAULT_EDITING_MODE = "video_first" # 默认剪辑模式: "video_first"（视频优先）| "music_first"（音乐优先）
SCENE_DETECTION_THRESHOLD = 0.3     # FFmpeg 场景检测敏感度 (0.0-1.0, 越低越敏感)
MIN_SEGMENT_DURATION = 1.0          # 最小片段时长（秒），避免过短碎片

# ============================================
# 🤖 AI 音乐生成配置
# ============================================
# HuggingFace Inference API (免费)
# 在 https://huggingface.co/settings/tokens 创建 Token（免费注册）
HUGGINGFACE_API_TOKEN = _env("HUGGINGFACE_API_TOKEN", "")
AI_MUSIC_MODEL = "facebook/musicgen-small"  # 可选: facebook/musicgen-medium
AI_MUSIC_COUNT = 3           # 生成几首备选曲目
AI_MUSIC_DURATION = 15       # 每首时长（秒），建议 10-30
AI_MUSIC_MAX_RETRIES = 3     # API 调用最大重试次数（模型冷启动需要等待）

# 备选：Replicate API（质量更高，需付费）
# REPLICATE_API_TOKEN = ""   # 在 https://replicate.com/account 获取
