"""
一键安装脚本 — 在新电脑上自动配置 Movie Music Matcher
=====================================================
用法：
    python install.py           # 交互式安装
    python install.py --auto    # 自动安装（不询问）
    python install.py --check   # 仅检查，不安装
"""
import os
import sys
import subprocess
import shutil

# Force UTF-8
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def step(msg: str):
    print(f"\n  >>> {msg}")


def ok(msg: str = ""):
    print(f"  [OK] {msg}")


def fail(msg: str):
    print(f"  [FAIL] {msg}")


def warn(msg: str):
    print(f"  [WARN] {msg}")


def ask(msg: str, default: str = "y") -> bool:
    """询问用户 yes/no"""
    prompt = f"\n  [?] {msg} [y/n] (默认: {default}): "
    try:
        answer = input(prompt).strip().lower()
        if not answer:
            answer = default
        return answer in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False


def check_python() -> bool:
    """检查 Python 版本"""
    step("检查 Python 版本...")
    v = sys.version_info
    if v >= (3, 10):
        ok(f"Python {v.major}.{v.minor}.{v.micro}")
        return True
    fail(f"需要 Python 3.10+，当前 {v.major}.{v.minor}")
    return False


def check_pip() -> bool:
    """检查 pip"""
    try:
        subprocess.run([sys.executable, "-m", "pip", "--version"],
                       capture_output=True, timeout=10)
        ok("pip 可用")
        return True
    except Exception:
        fail("pip 不可用")
        return False


def check_ffmpeg() -> bool:
    """检查 FFmpeg"""
    if shutil.which("ffmpeg"):
        ok("FFmpeg 已安装")
        return True
    warn("FFmpeg 未安装")
    print("    视频抽帧和场景检测需要 FFmpeg")
    print("    Windows: winget install Gyan.FFmpeg")
    print("    或下载: https://ffmpeg.org/download.html")
    return False


def install_pip_deps(auto: bool = False) -> bool:
    """安装 pip 依赖"""
    step("安装 Python 依赖...")
    req_file = os.path.join(BASE_DIR, "requirements.txt")
    if not os.path.exists(req_file):
        fail("找不到 requirements.txt")
        return False

    print(f"    从 {req_file} 安装...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", req_file],
        capture_output=False,  # 显示安装进度
        timeout=300,
    )
    if result.returncode == 0:
        ok("依赖安装完成")
        return True
    fail("依赖安装失败")
    return False


def setup_env_file(auto: bool = False) -> bool:
    """帮助用户配置 .env 文件"""
    step("配置 API Key...")

    env_path = os.path.join(BASE_DIR, ".env")
    example_path = os.path.join(BASE_DIR, ".env.example")

    if os.path.exists(env_path):
        ok(".env 文件已存在，跳过")
        return True

    if not os.path.exists(example_path):
        warn(".env.example 不存在，跳过")
        return True

    if not auto:
        print("\n  Movie Music Matcher 使用 DeepSeek API 进行 AI 分析。")
        print("  你需要在 https://platform.deepseek.com/api_keys 创建 API Key。")
        print("  如果你已有 API Key，现在可以输入。没有也可以稍后在 .env 文件中配置。\n")

        api_key = input("  请输入你的 DeepSeek API Key (直接回车跳过): ").strip()
    else:
        api_key = ""

    # 复制模板并替换
    with open(example_path, "r", encoding="utf-8") as f:
        content = f.read()

    if api_key:
        content = content.replace(
            "ANTHROPIC_API_KEY=sk-your-deepseek-api-key-here",
            f"ANTHROPIC_API_KEY={api_key}"
        )

    with open(env_path, "w", encoding="utf-8") as f:
        f.write(content)

    if api_key:
        ok("API Key 已配置")
    else:
        ok(".env 文件已创建（请稍后编辑填入 API Key）")
    return True


def run_health_check() -> bool:
    """运行健康检查"""
    step("运行环境健康检查...")
    check_script = os.path.join(BASE_DIR, "check_setup.py")
    if os.path.exists(check_script):
        subprocess.run([sys.executable, check_script], timeout=60)
        return True
    warn("check_setup.py 不存在，跳过")
    return True


def add_to_gitignore():
    """确保 .env 在 .gitignore 中"""
    gitignore = os.path.join(BASE_DIR, ".gitignore")
    entry = ".env"
    try:
        if os.path.exists(gitignore):
            with open(gitignore, "r") as f:
                if entry in f.read():
                    return
        with open(gitignore, "a") as f:
            f.write(f"\n{entry}\n")
        print(f"  [OK] 已将 .env 添加到 .gitignore")
    except Exception:
        pass


def install(auto: bool = False, check_only: bool = False) -> bool:
    """主安装流程"""
    print("=" * 60)
    print("  Movie Music Matcher v3.0 — 安装向导")
    print("=" * 60)

    # 1. 检查 Python
    if not check_python():
        return False

    # 2. 检查 pip
    if not check_pip():
        return False

    if check_only:
        # 3. 检查 FFmpeg
        check_ffmpeg()
        # 4. 运行健康检查
        run_health_check()
        return True

    # 3. FFmpeg
    ffmpeg_ok = check_ffmpeg()

    # 4. 安装 pip 依赖
    if not install_pip_deps(auto):
        if not auto:
            if not ask("依赖安装失败。是否继续？"):
                return False

    # 5. 配置 .env
    setup_env_file(auto)

    # 6. .gitignore
    add_to_gitignore()

    # 7. 健康检查
    run_health_check()

    # 完成
    print("\n" + "=" * 60)
    print("  安装完成！")
    print("=" * 60)
    print(f"  cd {BASE_DIR}")
    print("  python app.py")
    print("  然后在浏览器打开: http://localhost:5000")
    print()

    if not ffmpeg_ok:
        print("  !! FFmpeg 未安装。视频处理功能需要 FFmpeg。")
        print("     Windows: winget install Gyan.FFmpeg")
        print()

    print("  运行 python check_setup.py 可随时检查环境状态。")
    print()

    return True


if __name__ == "__main__":
    auto_mode = "--auto" in sys.argv
    check_mode = "--check" in sys.argv

    success = install(auto=auto_mode, check_only=check_mode)
    sys.exit(0 if success else 1)
