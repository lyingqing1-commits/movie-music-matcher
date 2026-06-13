"""
工作空间管理器 — 管理 workspace/runs/{project-slug}/ 目录结构
============================================================
负责创建运行目录、版本化写入阶段产物、加载已批准产物。
遵循 DaVinci-AutoEdit-Agent 的 run folder 设计模式。
"""
import os
import re
import json
import config


def generate_project_slug(topic: str) -> str:
    """
    从项目主题生成文件系统安全的 slug。

    示例：
        "Inception 梦境分析混剪" → "inception-analysis-mashup"
        "The Matrix (1999) Highlights" → "the-matrix-1999-highlights"
    """
    # 转小写，保留字母数字空格连字符
    slug = topic.lower()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[-\s]+', '-', slug).strip('-')

    # 限制长度
    if len(slug) > 60:
        slug = slug[:60].rstrip('-')

    return slug or "untitled-project"


def create_run_folder(project_slug: str) -> str:
    """
    创建 workspace/runs/{project_slug}/ 目录结构。

    参数：
        project_slug: 项目 slug 标识符

    返回：
        运行目录的绝对路径
    """
    workspace_dir = getattr(config, "WORKSPACE_DIR", os.path.join(config.BASE_DIR, "workspace"))
    run_path = os.path.join(workspace_dir, "runs", project_slug)

    # 确保所有子目录存在
    subdirs = ["scan", "review", "script", "blueprint", "resolve", "drafts"]
    for sub in subdirs:
        os.makedirs(os.path.join(run_path, sub), exist_ok=True)

    # 清理旧运行目录（保留最近 MAX_RUN_FOLDERS 个）
    _cleanup_old_runs(workspace_dir)

    return run_path


def _cleanup_old_runs(workspace_dir: str):
    """清理超过 MAX_RUN_FOLDERS 的旧运行目录"""
    max_runs = getattr(config, "MAX_RUN_FOLDERS", 50)
    runs_dir = os.path.join(workspace_dir, "runs")

    if not os.path.exists(runs_dir):
        return

    run_folders = []
    for entry in os.listdir(runs_dir):
        entry_path = os.path.join(runs_dir, entry)
        if os.path.isdir(entry_path):
            run_folders.append((os.path.getmtime(entry_path), entry_path))

    if len(run_folders) > max_runs:
        # 按修改时间排序，保留最新的 max_runs 个
        run_folders.sort(reverse=True)
        for _, path in run_folders[max_runs:]:
            try:
                import shutil
                shutil.rmtree(path, ignore_errors=True)
                print(f"   Cleaned up old run: {os.path.basename(path)}")
            except Exception as e:
                print(f"   Failed to clean up {path}: {e}")


def get_next_version(run_path: str, phase: str) -> int:
    """
    获取某阶段产物的下一个版本号。

    参数：
        run_path: 运行目录路径
        phase: 阶段名称（如 "material-review"）

    返回：
        下一个版本号（首次为 1，之后递增）
    """
    version = 1
    for filename in os.listdir(run_path):
        # 匹配 {phase}.json 和 {phase}-v{NNN}.json
        pattern = rf'^{re.escape(phase)}(?:-v(\d+))?\.json$'
        match = re.match(pattern, filename)
        if match:
            v = int(match.group(1)) if match.group(1) else 1
            version = max(version, v + 1)

    return version


def save_artifact(run_path: str, phase: str, data: dict, version: int = None) -> str:
    """
    保存阶段产物 JSON 文件。如果同名文件已存在，自动版本化。

    参数：
        run_path: 运行目录路径
        phase: 阶段名称
        data: 要保存的数据字典
        version: 指定版本号（None 时自动递增）

    返回：
        保存的文件绝对路径
    """
    if version is None:
        version = get_next_version(run_path, phase)

    if version <= 1:
        # 检查是否已有未版本化的文件
        default_path = os.path.join(run_path, f"{phase}.json")
        if os.path.exists(default_path):
            # 将现有文件重命名为 v001，新文件用 v002
            v001_path = os.path.join(run_path, f"{phase}-v001.json")
            try:
                os.rename(default_path, v001_path)
            except OSError:
                pass
            version = max(version, 2)

    if version == 1:
        filename = f"{phase}.json"
    else:
        filename = f"{phase}-v{version:03d}.json"

    filepath = os.path.join(run_path, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"   Artifact saved: {filepath}")
    return filepath


def load_artifact(run_path: str, phase: str) -> dict:
    """
    加载某阶段的最新版本产物。

    参数：
        run_path: 运行目录路径
        phase: 阶段名称

    返回：
        产物的数据字典；不存在时返回空字典
    """
    # 查找最新版本
    latest_version = 0
    latest_file = None

    for filename in os.listdir(run_path):
        pattern = rf'^{re.escape(phase)}(?:-v(\d+))?\.json$'
        match = re.match(pattern, filename)
        if match:
            v = int(match.group(1)) if match.group(1) else 1
            if v >= latest_version:
                latest_version = v
                latest_file = os.path.join(run_path, filename)

    if latest_file and os.path.exists(latest_file):
        with open(latest_file, "r", encoding="utf-8") as f:
            return json.load(f)

    return {}


def get_run_path(project_slug: str) -> str:
    """获取运行目录路径（不创建）"""
    workspace_dir = getattr(config, "WORKSPACE_DIR", os.path.join(config.BASE_DIR, "workspace"))
    return os.path.join(workspace_dir, "runs", project_slug)


def run_exists(project_slug: str) -> bool:
    """检查运行目录是否存在"""
    return os.path.isdir(get_run_path(project_slug))


def list_runs() -> list[dict]:
    """列出所有运行目录及其基本信息"""
    workspace_dir = getattr(config, "WORKSPACE_DIR", os.path.join(config.BASE_DIR, "workspace"))
    runs_dir = os.path.join(workspace_dir, "runs")

    if not os.path.exists(runs_dir):
        return []

    runs = []
    for entry in os.listdir(runs_dir):
        entry_path = os.path.join(runs_dir, entry)
        if os.path.isdir(entry_path):
            brief_path = os.path.join(entry_path, "project-brief.json")
            brief = {}
            if os.path.exists(brief_path):
                try:
                    with open(brief_path, "r", encoding="utf-8") as f:
                        brief = json.load(f)
                except Exception:
                    pass

            runs.append({
                "slug": entry,
                "path": entry_path,
                "created_at": os.path.getctime(entry_path),
                "modified_at": os.path.getmtime(entry_path),
                "topic": brief.get("topic", entry),
            })

    runs.sort(key=lambda r: r["modified_at"], reverse=True)
    return runs
