# 部署指南 — 让其他电脑通过网址直接访问

四种方式，从最简单到最专业。

---

## 方式 1：局域网共享（最快，适合同一 WiFi 下）

你和朋友在同一个 WiFi 下时，让朋友直接访问你的电脑。

### 步骤

```bash
# 1. 以局域网模式启动（允许外部访问）
set FLASK_HOST=0.0.0.0       # Windows CMD
$env:FLASK_HOST="0.0.0.0"    # PowerShell
export FLASK_HOST=0.0.0.0    # Mac/Linux

python app.py
```

```
# 2. 查看你的 IP 地址
ipconfig                      # Windows，找「IPv4 地址」如 192.168.1.105
ifconfig                      # Mac/Linux
```

### 访问

其他人在同一 WiFi 下打开浏览器访问：
```
http://192.168.1.105:5000
```

> ⚠️ 你的电脑必须保持开机，Python 必须保持运行。

---

## 方式 2：ngrok 隧道（最快，适合临时分享）

生成一个公网网址，任何人通过互联网都能访问你的本地应用。**无需部署服务器**。

### 步骤

```bash
# 1. 下载 ngrok（一次性）
# https://ngrok.com/download
# 或 Windows 用 winget:
winget install ngrok

# 2. 启动应用（保持运行）
python app.py

# 3. 另开一个终端，启动隧道
ngrok http 5000
```

你会看到：
```
Forwarding  https://xxxx-xxx-xxx.ngrok-free.app -> http://localhost:5000
```

### 访问

任何人在浏览器打开 `https://xxxx-xxx-xxx.ngrok-free.app` 即可使用。

| 优点 | 缺点 |
|------|------|
| 无需服务器 | 你的电脑必须开机 |
| 免费 | 免费版网址每次重启会变 |
| 无需配置 | 免费版有带宽限制 |
| 自动 HTTPS | 不适合长期使用 |

---

## 方式 3：Docker 部署（一次构建，到处运行）

在**任何安装了 Docker 的电脑**上一键启动。

### 构建镜像（只需要做一次）

```bash
cd movie-music-matcher
docker build -t movie-music-matcher .
```

### 启动容器

```bash
# 基础启动（使用 .env 中的配置）
docker run -p 5000:5000 \
  -v ${PWD}/uploads:/app/uploads \
  -v ${PWD}/output:/app/output \
  movie-music-matcher

# 指定 API Key
docker run -p 5000:5000 \
  -e ANTHROPIC_API_KEY=sk-你的key \
  -v ${PWD}/uploads:/app/uploads \
  -v ${PWD}/output:/app/output \
  movie-music-matcher
```

### 在其他电脑上

其他电脑只需安装 Docker，然后运行 `docker run` 命令即可。访问 `http://localhost:5000`。

> 💡 可以把镜像推送到 Docker Hub，其他电脑直接 `docker pull`。

---

## 方式 4：Render.com 免费云部署（永久在线的网址）

[Render](https://render.com) 提供免费 Flask 托管，应用 24 小时在线。

### 步骤

1. 将项目推送到 GitHub
2. 注册 https://render.com（用 GitHub 登录）
3. 点击 **New + → Web Service**
4. 连接你的 GitHub 仓库
5. 配置：

```
Name:        movie-music-matcher
Runtime:     Python 3
Build Command:  pip install -r requirements.txt
Start Command:  gunicorn app:app -b 0.0.0.0:$PORT
```

6. 在 Environment Variables 中添加：
```
FLASK_HOST=0.0.0.0
ANTHROPIC_API_KEY=sk-你的key
AI_MODEL=deepseek-chat
```

7. 点击 **Create Web Service**

几分钟后你会得到一个永久网址：
```
https://movie-music-matcher.onrender.com
```

| 优点 | 缺点 |
|------|------|
| 24 小时在线 | 免费版 15 分钟无请求会休眠 |
| 免费 HTTPS | 文件存储有限 |
| 自动部署 | 不适合超大视频上传 |

> ⚠️ Render 免费版没有 FFmpeg。需要添加 `Dockerfile` 部署方式（选择 Docker runtime）。

---

## 方式对比

| | 局域网 | ngrok | Docker | Render |
|------|--------|-------|--------|--------|
| **难度** | ⭐ | ⭐ | ⭐⭐ | ⭐⭐⭐ |
| **需要服务器** | 不需要 | 不需要 | 不需要 | 免费云 |
| **需要开机** | 你的电脑 | 你的电脑 | 运行Docker的电脑 | 不必 |
| **永久网址** | ❌ | ❌(免费版) | ❌ | ✅ |
| **局域网分享** | ✅ | ✅ | ✅ | ✅ |
| **互联网分享** | ❌ | ✅ | 需额外配置 | ✅ |
| **适用场景** | 宿舍/办公室 | 远程演示 | 多机部署 | 长期使用 |

---

## 推荐方案（按场景）

| 你的场景 | 推荐 |
|---------|------|
| 室友/同学在同一个 WiFi | **方式 1** — 启动 `0.0.0.0` |
| 远程给朋友演示 1 小时 | **方式 2** — ngrok |
| 实验室多台电脑都要用 | **方式 3** — Docker |
| 想有一个永久在线的网址 | **方式 4** — Render.com |

---

## 补充：生成 Windows 桌面快捷方式

在目标电脑上创建一键启动脚本 `启动应用.bat`：

```batch
@echo off
cd /d C:\path\to\movie-music-matcher
set FLASK_HOST=0.0.0.0
start http://localhost:5000
python app.py
pause
```

双击即启动并自动打开浏览器。
