"""
环境健康检查脚本 — 检查运行 Movie Music Matcher 所需的所有依赖
==============================================================
用法：
    python check_setup.py          # 检查所有依赖
    python check_setup.py --json   # JSON 格式输出
    python check_setup.py --fix    # 尝试自动修复
"""
import os
import sys

# Force UTF-8 encoding for stdout/stderr on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
import json
import subprocess
import shutil
import platform


def check_python() -> dict:
    """检查 Python 版本"""
    version = sys.version_info
    ok = version >= (3, 10)
    return {
        "name": "Python",
        "required": "3.10+",
        "installed": f"{version.major}.{version.minor}.{version.micro}",
        "ok": ok,
        "fix": "请安装 Python 3.10 或更高版本: https://www.python.org/downloads/",
    }


def check_ffmpeg() -> dict:
    """检查 FFmpeg 是否可用"""
    ok = shutil.which("ffmpeg") is not None
    version = ""
    if ok:
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"], capture_output=True, text=True, timeout=5
            )
            version = result.stdout.split("\n")[0] if result.stdout else ""
        except Exception:
            pass
    return {
        "name": "FFmpeg",
        "required": "任意版本",
        "installed": version[:80] if version else "未安装",
        "ok": ok,
        "fix": "请安装 FFmpeg: https://ffmpeg.org/download.html\n"
               "Windows: winget install Gyan.FFmpeg",
    }


def check_ffprobe() -> dict:
    """检查 FFprobe 是否可用"""
    ok = shutil.which("ffprobe") is not None
    version = ""
    if ok:
        try:
            result = subprocess.run(
                ["ffprobe", "-version"], capture_output=True, text=True, timeout=5
            )
            version = result.stdout.split("\n")[0] if result.stdout else ""
        except Exception:
            pass
    return {
        "name": "FFprobe",
        "required": "任意版本（随 FFmpeg 安装）",
        "installed": version[:80] if version else "未安装",
        "ok": ok,
        "fix": "FFprobe 随 FFmpeg 一起安装。请安装 FFmpeg。",
    }


def check_packages() -> list[dict]:
    """检查 Python 依赖包"""
    required = {
        "flask": "flask>=3.0",
        "anthropic": "anthropic>=0.40.0",
        "librosa": "librosa>=0.10.0",
        "soundfile": "soundfile>=0.12.0",
        "PIL": "Pillow>=10.0.0",
        "numpy": "numpy",
        "requests": "requests",
    }
    results = []
    for module, package in required.items():
        try:
            __import__(module)
            ok = True
            version = "已安装"
        except ImportError:
            ok = False
            version = "未安装"
        results.append({
            "name": package,
            "required": package,
            "installed": version,
            "ok": ok,
            "fix": f"pip install {package.split('>=')[0]}" if not ok else None,
        })
    return results


def check_capcut() -> dict:
    """检查剪映/CapCut 是否安装"""
    candidates = [
        ("剪映专业版", r"%LOCALAPPDATA%\JianyingPro"),
        ("CapCut", r"%LOCALAPPDATA%\CapCut"),
    ]
    found = []
    for name, path in candidates:
        expanded = os.path.expandvars(path)
        if os.path.isdir(expanded):
            # 检查可执行文件
            exe_candidates = [
                os.path.join(expanded, "JianyingPro.exe"),
                os.path.join(expanded, "CapCut.exe"),
            ]
            for exe in exe_candidates:
                if os.path.isfile(exe):
                    found.append(f"{name}: {exe}")
                    break
            if not found or name not in str(found):
                # 搜索 Apps 目录
                apps_dir = os.path.join(expanded, "Apps")
                if os.path.isdir(apps_dir):
                    versions = sorted(os.listdir(apps_dir), reverse=True)
                    if versions:
                        found.append(f"{name} (版本: {versions[0]})")

    ok = len(found) > 0
    return {
        "name": "剪映 / CapCut",
        "required": "剪映专业版 或 CapCut（推荐最新版）",
        "installed": ", ".join(found) if found else "未检测到",
        "ok": ok,
        "fix": "请安装剪映专业版: https://www.capcut.cn/",
    }


def check_api_config() -> dict:
    """检查 API 配置"""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import config
        has_key = bool(config.ANTHROPIC_API_KEY and config.ANTHROPIC_API_KEY not in ("your-api-key-here", ""))
        model = config.AI_MODEL
        vision = getattr(config, "VISION_SUPPORTED", True)
        base_url = config.ANTHROPIC_BASE_URL or "https://api.anthropic.com"

        return {
            "name": "AI API 配置",
            "required": "有效的 API Key + 正确的模型名",
            "installed": (
                f"Key: {'已配置' if has_key else '未配置'}, "
                f"模型: {model}, "
                f"Base URL: {base_url}, "
                f"Vision: {'支持' if vision else '不支持'}"
            ),
            "ok": has_key,
            "fix": "请在 config.py 中设置 ANTHROPIC_API_KEY" if not has_key else None,
        }
    except Exception as e:
        return {
            "name": "AI API 配置",
            "required": "config.py 可正常导入",
            "installed": f"导入失败: {e}",
            "ok": False,
            "fix": "检查 config.py 文件是否完整",
        }


def check_workspace() -> dict:
    """检查工作目录结构"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    required_dirs = ["uploads", "frames", "output", "workspace", "modules", "static", "templates", "references"]
    missing = []
    for d in required_dirs:
        if not os.path.isdir(os.path.join(base_dir, d)):
            missing.append(d)
            try:
                os.makedirs(os.path.join(base_dir, d), exist_ok=True)
            except Exception:
                pass

    return {
        "name": "工作目录结构",
        "required": ", ".join(required_dirs),
        "installed": f"完整 ({len(required_dirs)} 个目录)" if not missing else f"缺少: {', '.join(missing)}",
        "ok": len(missing) == 0,
        "fix": "运行 python app.py 会自动创建缺失目录" if missing else None,
    }


def check_git() -> dict:
    """检查 Git 配置"""
    import config
    has_remote = bool(getattr(config, "GIT_REMOTE_URL", ""))
    git_ok = shutil.which("git") is not None

    return {
        "name": "Git 自动更新",
        "required": "Git + 远程仓库配置",
        "installed": (
            f"Git: {'已安装' if git_ok else '未安装'}, "
            f"远程仓库: {'已配置' if has_remote else '未配置'}"
        ),
        "ok": git_ok,
        "fix": "安装 Git: https://git-scm.com/downloads" if not git_ok else None,
    }


def run_all_checks(json_output: bool = False) -> dict:
    """运行所有检查"""
    checks = [
        check_python(),
        check_ffmpeg(),
        check_ffprobe(),
        *check_packages(),
        check_capcut(),
        check_api_config(),
        check_workspace(),
        check_git(),
    ]

    all_ok = all(c["ok"] for c in checks)
    failed = [c for c in checks if not c["ok"]]

    if json_output:
        return {
            "overall": "PASS" if all_ok else "FAIL",
            "total": len(checks),
            "passed": len(checks) - len(failed),
            "failed": len(failed),
            "checks": checks,
            "fixes_needed": [c["fix"] for c in failed if c.get("fix")],
        }

    # 人类可读输出
    print("=" * 60)
    print("Movie Music Matcher - Environment Health Check")
    print("=" * 60)

    for c in checks:
        icon = "[OK]" if c["ok"] else "[FAIL]"
        print(f"\n{icon} {c['name']}")
        print(f"   需要: {c['required']}")
        print(f"   当前: {c['installed'][:120]}")
        if not c["ok"] and c.get("fix"):
            print(f"   [FIX] 修复: {c['fix']}")

    print("\n" + "=" * 60)
    if all_ok:
        print("[OK] 所有检查通过！环境已就绪。")
    else:
        print(f"[FAIL] {len(failed)} 项未通过。请根据上述提示修复。")
    print(f"   总计: {len(checks)} 项, 通过: {len(checks) - len(failed)}, 失败: {len(failed)}")
    print("=" * 60)

    return {"overall": "PASS" if all_ok else "FAIL"}


if __name__ == "__main__":
    json_mode = "--json" in sys.argv
    fix_mode = "--fix" in sys.argv

    if fix_mode:
        print("[FIX] 自动修复模式：尝试安装缺失的依赖...")
        # 尝试安装缺失的 pip 包
        failed_packages = [c for c in check_packages() if not c["ok"]]
        for pkg in failed_packages:
            pkg_name = pkg["name"].split(">=")[0]
            print(f"   安装 {pkg_name}...")
            subprocess.run(
                [sys.executable, "-m", "pip", "install", pkg_name],
                capture_output=True,
            )
        print("修复完成，请重新运行 check_setup.py 验证。")
    else:
        run_all_checks(json_output=json_mode)
