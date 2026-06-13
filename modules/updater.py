"""
更新检测与执行模块
===================
- 检测已安装的剪映/JianYingPro 版本
- 兼容性矩阵管理
- Git 自动更新（推荐）或 URL 下载更新
"""
import os
import re
import sys
import json
import shutil
import subprocess
import tempfile
import zipfile
import urllib.request
from typing import Optional, Dict, Any, List, Tuple


# ============================================
# 版本定义
# ============================================

APP_VERSION = "2.0.0"

# 兼容性矩阵
# 每个 app 版本定义其支持的剪映/CapCut 版本范围
COMPATIBILITY: Dict[str, Dict[str, Any]] = {
    "1.0.0": {
        "jianyingpro": {"min": "10.0.0", "max": "10.7.0"},
        "capcut": {"min": "5.0.0", "max": "5.2.0"},
        "description": "初始版本，支持剪映 10.x 和 CapCut 5.x",
    },
    "1.1.0": {
        "jianyingpro": {"min": "10.5.0", "max": "11.0.0"},
        "capcut": {"min": "5.0.0", "max": "6.0.0"},
        "description": "改进节拍检测算法，新增剪映 11.x 支持",
    },
    "2.0.0": {
        "jianyingpro": {"min": "10.0.0", "max": "12.0.0"},
        "capcut": {"min": "5.0.0", "max": "7.0.0"},
        "description": (
            "🎬 智能剪辑引擎：AI 识别电影内容+场景检测+高光评分+音乐结构分析。"
            "支持视频优先/音乐优先双模式。上传体积提升至 2GB。"
        ),
    },
}

# 标记远程最新版本（与 Git 仓库中的版本保持一致）
_REMOTE_LATEST_VERSION = "2.0.0"

# 项目根目录
_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ============================================
# 版本解析工具
# ============================================

def _parse_version(version_str: str) -> Tuple[int, ...]:
    """将版本字符串解析为可比较的元组"""
    parts = re.findall(r"\d+", version_str)
    if not parts:
        return (0,)
    return tuple(int(p) for p in parts)


def _version_in_range(version: str, min_ver: str, max_ver: str) -> bool:
    """检查版本是否在 min~max 范围内（包含两端）"""
    v = _parse_version(version)
    v_min = _parse_version(min_ver)
    v_max = _parse_version(max_ver)

    # 截断 v 使其与边界精度一致后比较
    v_for_min = v[:len(v_min)] if len(v) > len(v_min) else v
    v_for_max = v[:len(v_max)] if len(v) > len(v_max) else v

    return v_min <= v_for_min and v_for_max <= v_max


# ============================================
# Git 工具函数
# ============================================

def _run_git(args: List[str], cwd: str = None) -> Tuple[int, str, str]:
    """
    运行 git 命令。

    Returns:
        (returncode, stdout, stderr)
    """
    if cwd is None:
        cwd = _PROJECT_DIR
    try:
        proc = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=60,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except FileNotFoundError:
        return -1, "", "Git 未安装"
    except subprocess.TimeoutExpired:
        return -1, "", "Git 命令超时"


def is_git_repo() -> bool:
    """检查项目目录是否是一个 Git 仓库"""
    code, _, _ = _run_git(["rev-parse", "--git-dir"])
    return code == 0


def get_git_remote_url() -> Optional[str]:
    """获取 Git 远程仓库地址"""
    code, stdout, _ = _run_git(["remote", "get-url", "origin"])
    if code == 0 and stdout:
        return stdout
    return None


def get_git_current_branch() -> Optional[str]:
    """获取当前 Git 分支名"""
    code, stdout, _ = _run_git(["rev-parse", "--abbrev-ref", "HEAD"])
    if code == 0 and stdout:
        return stdout
    return None


def get_git_remote_branch() -> str:
    """获取跟踪的远程分支名"""
    # 从 config 读取，或使用默认值
    try:
        from config import GIT_BRANCH as branch
    except ImportError:
        branch = "main"
    return branch or "main"


def git_fetch_remote() -> Tuple[bool, str]:
    """
    从远程仓库获取最新信息。

    Returns:
        (成功, 错误信息)
    """
    code, stdout, stderr = _run_git(["fetch", "origin", "--prune", "--quiet"])
    if code == 0:
        return True, ""
    return False, stderr or "Git fetch 失败"


def git_check_for_updates(branch: str = None) -> Dict[str, Any]:
    """
    通过 Git 检查是否有新提交。

    Args:
        branch: 要检查的分支名

    Returns:
        {
            "available": bool,        # 是否有可用更新
            "behind_count": int,      # 落后多少提交
            "current_commit": str,    # 当前 HEAD 提交
            "remote_commit": str,     # 远程最新提交
            "error": str | None,
        }
    """
    if branch is None:
        branch = get_git_remote_branch()

    result = {
        "available": False,
        "behind_count": 0,
        "current_commit": "",
        "remote_commit": "",
        "remote_url": "",
        "error": None,
    }

    # 检查是否是 Git 仓库
    if not is_git_repo():
        result["error"] = "项目未初始化为 Git 仓库"
        return result

    remote_url = get_git_remote_url()
    result["remote_url"] = remote_url or ""

    if not remote_url:
        result["error"] = "未配置 Git 远程仓库"
        return result

    # 获取当前提交
    _, current, _ = _run_git(["rev-parse", "HEAD"])
    result["current_commit"] = current[:12] if current else ""

    # Fetch 远程
    ok, err = git_fetch_remote()
    if not ok:
        result["error"] = err
        return result

    # 比较本地和远程
    remote_ref = f"origin/{branch}"
    _, remote_commit, _ = _run_git(["rev-parse", remote_ref])
    result["remote_commit"] = remote_commit[:12] if remote_commit else ""

    if not remote_commit:
        result["error"] = f"远程分支 {remote_ref} 不存在"
        return result

    # 计算落后多少提交
    code, behind, _ = _run_git(["rev-list", "--count", f"HEAD..{remote_ref}"])
    if code == 0:
        try:
            result["behind_count"] = int(behind)
        except ValueError:
            result["behind_count"] = 0

    result["available"] = result["behind_count"] > 0
    return result


def git_pull_update(branch: str = None) -> Dict[str, Any]:
    """
    执行 git pull 更新。

    流程：
    1. 保存本地修改 (git stash)
    2. git pull origin <branch>
    3. 恢复本地修改 (git stash pop，如果有 stash)

    Args:
        branch: 分支名

    Returns:
        {
            "success": bool,
            "message": str,
            "new_commits": list[str],  # 新拉取的提交信息
        }
    """
    if branch is None:
        branch = get_git_remote_branch()

    result = {
        "success": False,
        "message": "",
        "new_commits": [],
    }

    if not is_git_repo():
        result["message"] = "项目未初始化为 Git 仓库"
        return result

    remote_url = get_git_remote_url()
    if not remote_url:
        result["message"] = "未配置 Git 远程仓库"
        return result

    # 记录更新前的 HEAD
    _, old_head, _ = _run_git(["rev-parse", "HEAD"])

    # Step 1: Stash 本地修改
    has_stash = False
    code, _, _ = _run_git(["stash", "--include-untracked"])
    if code == 0:
        # 检查 stash 是否真的创建了
        code2, stash_list, _ = _run_git(["stash", "list"])
        if code2 == 0 and stash_list:
            has_stash = True

    try:
        # Step 2: git pull
        remote_ref = f"origin/{branch}"
        code, stdout, stderr = _run_git(["pull", "origin", branch])
        if code != 0:
            result["message"] = f"Git pull 失败: {stderr}"
            return result

        # Step 3: 获取新提交列表
        if old_head:
            _, log, _ = _run_git([
                "log", "--oneline", f"{old_head}..HEAD",
                "--no-merges", "-n", "20"
            ])
            if log:
                result["new_commits"] = log.split("\n")

        result["success"] = True
        if result["new_commits"]:
            result["message"] = (
                f"✅ 更新完成！已拉取 {len(result['new_commits'])} 个新提交。\n\n"
                f"新提交:\n" + "\n".join(f"  • {c}" for c in result["new_commits"][:10]) +
                "\n\n请重启应用使更新生效。"
            )
        else:
            result["message"] = "✅ 已是最新版本，无需更新。"

        return result

    finally:
        # Step 4: 恢复 stash
        if has_stash:
            _run_git(["stash", "pop"])


# ============================================
# 剪映版本检测
# ============================================

def detect_jianyingpro_version() -> Optional[str]:
    """
    检测已安装的 JianYingPro / CapCut 版本。

    检测位置：
    1. %LOCALAPPDATA%\\JianyingPro\\Apps\\ 下的版本目录名
    2. %LOCALAPPDATA%\\CapCut\\Apps\\ 下的版本目录名

    Returns:
        版本字符串 (如 "10.7.0.14095")，或 None
    """
    candidates = [
        os.path.expandvars(r"%LOCALAPPDATA%\\JianyingPro\\Apps"),
        os.path.expandvars(r"%LOCALAPPDATA%\\CapCut\\Apps"),
    ]

    version_pattern = re.compile(r"^\d+\.\d+\.\d+\.\d+$")
    all_versions: List[Tuple[int, ...]] = []
    version_strings: Dict[Tuple[int, ...], str] = {}

    for apps_dir in candidates:
        if not os.path.isdir(apps_dir):
            continue
        try:
            for entry in os.listdir(apps_dir):
                entry_path = os.path.join(apps_dir, entry)
                if os.path.isdir(entry_path) and version_pattern.match(entry):
                    parsed = _parse_version(entry)
                    all_versions.append(parsed)
                    version_strings[parsed] = entry
        except PermissionError:
            continue

    if not all_versions:
        return None

    # 返回最高版本
    best = max(all_versions)
    return version_strings[best]


def detect_editor_info() -> Dict[str, Any]:
    """
    综合检测编辑器信息。

    Returns:
        {
            "jianyingpro_version": str | None,
            "capcut_version": str | None,
            "editor_name": str,
            "editor_version": str | None,
        }
    """
    result: Dict[str, Any] = {
        "jianyingpro_version": None,
        "capcut_version": None,
        "editor_name": "未检测到",
        "editor_version": None,
    }

    version_pattern = re.compile(r"^\d+\.\d+\.\d+\.\d+$")

    # 检测 JianYingPro
    jyp_dir = os.path.expandvars(r"%LOCALAPPDATA%\JianyingPro\Apps")
    if os.path.isdir(jyp_dir):
        try:
            versions = []
            for entry in os.listdir(jyp_dir):
                if version_pattern.match(entry) and os.path.isdir(os.path.join(jyp_dir, entry)):
                    versions.append((_parse_version(entry), entry))
            if versions:
                versions.sort(key=lambda x: x[0])
                best = versions[-1][1]
                result["jianyingpro_version"] = best
                result["editor_name"] = "剪映专业版"
                result["editor_version"] = best
        except PermissionError:
            pass

    # 检测 CapCut
    capcut_dir = os.path.expandvars(r"%LOCALAPPDATA%\CapCut\Apps")
    if os.path.isdir(capcut_dir):
        try:
            versions = []
            for entry in os.listdir(capcut_dir):
                if version_pattern.match(entry) and os.path.isdir(os.path.join(capcut_dir, entry)):
                    versions.append((_parse_version(entry), entry))
            if versions:
                versions.sort(key=lambda x: x[0])
                best = versions[-1][1]
                result["capcut_version"] = best
                if result["editor_name"] == "未检测到":
                    result["editor_name"] = "CapCut"
                    result["editor_version"] = best
        except PermissionError:
            pass

    return result


# ============================================
# 兼容性检查
# ============================================

def get_compatibility_info(jyp_version: Optional[str]) -> Dict[str, Any]:
    """
    检查当前 app 版本与指定剪映版本的兼容性。
    """
    editor = detect_editor_info()
    current = COMPATIBILITY.get(APP_VERSION, {})

    jyp_range = "—"
    capcut_range = "—"
    if current:
        jyp_info = current.get("jianyingpro", {})
        capcut_info = current.get("capcut", {})
        if jyp_info:
            jyp_range = f"{jyp_info['min']} ~ {jyp_info['max']}"
        if capcut_info:
            capcut_range = f"{capcut_info['min']} ~ {capcut_info['max']}"

    is_compatible = False
    status_message = ""

    effective_version = jyp_version or editor.get("editor_version")

    if effective_version:
        if current:
            jyp_info = current.get("jianyingpro", {})
            if jyp_info:
                is_compatible = _version_in_range(
                    effective_version,
                    jyp_info["min"],
                    jyp_info["max"],
                )

        if is_compatible:
            status_message = f"✅ 当前版本兼容 {editor['editor_name']} {effective_version}"
        else:
            status_message = f"⚠️ 当前版本不完全兼容 {editor['editor_name']} {effective_version}，建议更新"
    else:
        status_message = "ℹ️ 未检测到剪映/CapCut 安装，草稿生成功能仍可正常使用"
        is_compatible = True

    return {
        "app_version": APP_VERSION,
        "editor_name": editor["editor_name"],
        "editor_version": effective_version,
        "jianyingpro_version": editor["jianyingpro_version"],
        "capcut_version": editor["capcut_version"],
        "is_compatible": is_compatible,
        "compatible_jyp_range": jyp_range,
        "compatible_capcut_range": capcut_range,
        "description": current.get("description", ""),
        "status_message": status_message,
    }


def _find_best_compatible_version(editor_version: Optional[str]) -> Optional[Tuple[str, Dict[str, Any]]]:
    """
    在兼容性矩阵中查找最适合当前剪映版本的最新应用版本。

    遍历 COMPATIBILITY 中所有版本，筛选出：
    1. 版本号 > 当前 APP_VERSION
    2. 兼容已安装的剪映版本

    Returns:
        (version_string, version_info_dict) 或 None
    """
    if not editor_version:
        # 未检测到剪映，返回全局最新版本
        best_ver = _REMOTE_LATEST_VERSION
        best_info = COMPATIBILITY.get(best_ver)
        if best_info and _parse_version(best_ver) > _parse_version(APP_VERSION):
            return (best_ver, best_info)
        return None

    current_ver = _parse_version(APP_VERSION)
    candidates = []

    for ver_str, ver_info in COMPATIBILITY.items():
        parsed = _parse_version(ver_str)
        if parsed <= current_ver:
            continue  # 不比当前版本新

        jyp_info = ver_info.get("jianyingpro", {})
        if not jyp_info:
            continue

        if _version_in_range(editor_version, jyp_info["min"], jyp_info["max"]):
            candidates.append((parsed, ver_str, ver_info))

    if not candidates:
        return None

    # 返回版本号最高的
    candidates.sort(key=lambda x: x[0], reverse=True)
    best = candidates[0]
    return (best[1], best[2])


def check_for_updates(jyp_version: Optional[str] = None) -> Dict[str, Any]:
    """
    检查是否有可用的应用更新。

    智能匹配：找到兼容当前剪映版本的最新应用版本。
    更新方式：
    1. Git 远程仓库拉取（推荐）
    2. URL 下载
    3. 手动指引
    """
    compat = get_compatibility_info(jyp_version)

    # ---- 找到最适合已安装剪映的版本 ----
    editor_version = compat.get("editor_version")
    best_match = _find_best_compatible_version(editor_version)

    target_version = None
    target_info = None
    matrix_has_update = False

    if best_match:
        target_version, target_info = best_match
        matrix_has_update = True

    # ---- Git 检查 ----
    git_check = None
    git_available = False

    if is_git_repo() and get_git_remote_url():
        git_check = git_check_for_updates()
        git_available = git_check.get("available", False)

    # ---- 构建更新信息 ----
    has_update = git_available or matrix_has_update

    update_info = None
    if has_update and target_info:
        update_info = {
            "version": target_version,
            "description": target_info.get("description", ""),
            "download_url": target_info.get("download_url", ""),
            "compatible_jyp_range": "—",
            "compatible_capcut_range": "—",
            "update_method": "git" if git_available else "manual",
            "best_for_editor": f"{compat.get('editor_name', '')} {editor_version or '未知'}",
        }
        jyp_info = target_info.get("jianyingpro", {})
        capcut_info = target_info.get("capcut", {})
        if jyp_info:
            update_info["compatible_jyp_range"] = f"{jyp_info['min']} ~ {jyp_info['max']}"
        if capcut_info:
            update_info["compatible_capcut_range"] = f"{capcut_info['min']} ~ {capcut_info['max']}"

        # 附加 Git 详情
        if git_check:
            update_info["git_remote_url"] = git_check.get("remote_url", "")
            update_info["git_behind_count"] = git_check.get("behind_count", 0)

    # 确定更新方式
    if git_available:
        update_method = "git"
    elif has_update:
        update_method = "manual"
    else:
        update_method = None

    return {
        "app_version": APP_VERSION,
        "latest_version": target_version or _REMOTE_LATEST_VERSION,
        "target_version": target_version,
        "has_update": has_update,
        "update_info": update_info,
        "compatibility": compat,
        "update_compatible": target_version is not None,
        "git_check": git_check,
        "update_method": update_method,
    }


# ============================================
# 更新执行
# ============================================

_update_status: Dict[str, Any] = {
    "in_progress": False,
    "progress": 0,
    "message": "",
    "error": None,
}


def get_update_status() -> Dict[str, Any]:
    """获取当前更新进度"""
    return dict(_update_status)


def perform_update() -> Dict[str, Any]:
    """
    执行应用更新。

    更新策略（按优先级）：
    1. Git pull — 如果项目是 Git 仓库且有远程，直接 git pull
    2. URL 下载 — 如果有 download_url，下载 zip 包解压覆盖
    3. 手动指引 — 显示下载地址供用户手动操作
    """
    global _update_status

    if _update_status["in_progress"]:
        return {
            "success": False,
            "message": "更新已在进行中",
        }

    check = check_for_updates()
    if not check["has_update"]:
        return {
            "success": False,
            "message": "当前已是最新版本，无需更新",
        }

    update_info = check.get("update_info")
    if not update_info:
        return {
            "success": False,
            "message": "没有可用的更新信息",
        }

    # ---- 策略 1: Git pull ----
    if is_git_repo() and get_git_remote_url():
        _update_status["in_progress"] = True
        _update_status["progress"] = 0
        _update_status["message"] = "正在通过 Git 拉取更新..."
        _update_status["error"] = None

        try:
            _update_status["progress"] = 20
            _update_status["message"] = "正在从远程仓库获取更新..."

            result = git_pull_update()

            _update_status["progress"] = 100
            _update_status["in_progress"] = False

            if result["success"]:
                _update_status["message"] = result["message"]
                return {"success": True, "message": result["message"]}
            else:
                _update_status["message"] = result["message"]
                return {"success": False, "message": result["message"]}

        except Exception as e:
            _update_status["in_progress"] = False
            _update_status["error"] = str(e)
            _update_status["message"] = f"Git 更新失败: {e}"
            # 继续尝试 URL 下载方式

    # ---- 策略 2: URL 下载 ----
    download_url = update_info.get("download_url", "")
    if download_url and download_url.startswith("http"):
        _update_status["in_progress"] = True
        _update_status["progress"] = 0
        _update_status["message"] = "正在准备下载更新..."
        _update_status["error"] = None

        try:
            _do_download_and_update(download_url, update_info["version"])
            _update_status["progress"] = 100
            _update_status["message"] = f"✅ 更新完成！已更新至 v{update_info['version']}，请重启应用使更新生效。"
            _update_status["in_progress"] = False
            return {"success": True, "message": _update_status["message"]}
        except Exception as e:
            _update_status["in_progress"] = False
            _update_status["error"] = str(e)
            _update_status["message"] = f"❌ 下载更新失败: {e}"
            return {"success": False, "message": _update_status["message"]}

    # ---- 策略 3: 手动指引 ----
    return {
        "success": True,
        "is_guidance": True,
        "message": _build_guidance_message(update_info, check.get("git_check")),
    }


def _build_guidance_message(update_info: dict, git_check: dict = None) -> str:
    """构建手动更新指引信息"""
    lines = [
        "📋 更新指引",
        "",
        f"当前版本：v{APP_VERSION}",
        f"最新版本：v{update_info['version']}",
        f"更新内容：{update_info.get('description', '—')}",
        "",
        f"兼容剪映：{update_info.get('compatible_jyp_range', '—')}",
        f"兼容 CapCut：{update_info.get('compatible_capcut_range', '—')}",
        "",
    ]

    if git_check and git_check.get("error"):
        lines.append(f"⚠️ Git 自动更新不可用：{git_check['error']}")
        lines.append("")
        lines.append("💡 解决方法：")
        lines.append("1. 确保已安装 Git: https://git-scm.com/download/win")
        lines.append("2. 为项目配置远程仓库：")
        lines.append(f"   cd {_PROJECT_DIR}")
        lines.append('   git init')
        lines.append('   git remote add origin <你的仓库地址>')
        lines.append("3. 首次推送后即可使用一键自动更新")
        lines.append("")
        lines.append("或直接重新下载覆盖项目目录。")

    elif not is_git_repo():
        lines.append("💡 启用 Git 自动更新（推荐）：")
        lines.append(f"   cd {_PROJECT_DIR}")
        lines.append('   git init')
        lines.append('   git remote add origin <你的仓库地址>')
        lines.append("3. 首次推送后即可使用一键自动更新")
        lines.append("")
        lines.append("或手动下载最新版本覆盖。")

    return "\n".join(lines)


def _do_download_and_update(download_url: str, target_version: str):
    """
    下载并执行更新（后备方案）。

    流程：
    1. 下载 zip 包到临时目录
    2. 备份当前应用目录
    3. 解压并覆盖
    4. 清理临时文件
    """
    _update_status["progress"] = 10
    _update_status["message"] = "正在下载更新包..."

    tmp_dir = tempfile.mkdtemp(prefix="mmm_update_")
    zip_path = os.path.join(tmp_dir, f"update_v{target_version}.zip")

    urllib.request.urlretrieve(download_url, zip_path)

    _update_status["progress"] = 50
    _update_status["message"] = "正在备份当前版本..."

    backup_dir = os.path.join(tmp_dir, "backup")
    shutil.copytree(_PROJECT_DIR, backup_dir,
                    ignore=shutil.ignore_patterns("uploads", "frames", "output", "__pycache__", ".git"))

    _update_status["progress"] = 70
    _update_status["message"] = "正在安装更新..."

    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(_PROJECT_DIR)

    _update_status["progress"] = 90
    _update_status["message"] = "正在清理..."

    try:
        shutil.rmtree(tmp_dir)
    except Exception:
        pass

    _update_status["progress"] = 100
