# Movie Music Matcher Docker 镜像
# ================================
# 本地使用:
#   docker build -t movie-music-matcher .
#   docker run -p 5000:5000 -e ANTHROPIC_API_KEY=sk-xxx movie-music-matcher
#
# Render.com 部署:
#   推送到 GitHub 后自动构建，无需手动操作

FROM python:3.12-slim

# 安装 FFmpeg + 音频处理依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 安装 Python 依赖（分层缓存）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 创建必要目录
RUN mkdir -p uploads frames output workspace/runs

# Render 使用 $PORT 环境变量（默认 10000），本地默认 5000
EXPOSE 5000 10000

ENV FLASK_HOST=0.0.0.0
ENV FLASK_DEBUG=false

# 启动命令：优先使用 Render 的 $PORT，否则用 5000
CMD ["sh", "-c", "python app.py"]
