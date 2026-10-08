"""从源码框架导出可独立安装的公司项目，只复制明确列出的工程资产。"""

from __future__ import annotations

import re
import shutil
from pathlib import Path


def _source_root() -> Path:
    root = Path(__file__).resolve().parents[2]
    if not (root / "uv.lock").is_file() or not (root / "templates/company").is_dir():
        raise ValueError("project init 需要源码仓库，请在克隆的 ai-aotoiframe 中执行")
    return root


def _files(root: Path, folder: str, suffixes: set[str]) -> list[Path]:
    directory = root / folder
    if directory.resolve() != directory:
        raise ValueError(f"项目模板不允许符号链接：{folder}")
    result = []
    for path in sorted(directory.rglob("*")):
        if path.is_symlink() or path.resolve() != path:
            raise ValueError(f"项目模板不允许符号链接：{path.relative_to(root)}")
        if not _exportable(path, directory):
            continue
        if path.is_file() and (path.suffix in suffixes or path.name == "Jenkinsfile"):
            result.append(path)
    return result


def _exportable(path: Path, root: Path) -> bool:
    """模板也可能被本地编辑过，禁止把常见凭据、会话与缓存带出。"""
    if any(
        part in {".auth", ".secrets", ".git", ".venv", "__pycache__", "artifacts"}
        for part in path.relative_to(root).parts
    ):
        return False
    if path.name == ".env" or (path.name.startswith(".env.") and path.name != ".env.example"):
        return False
    return path.suffix not in {".pem", ".key", ".pfx", ".p12", ".apk", ".ipa", ".pyc"}


def init_project(name: str, output: str | Path) -> Path:
    """保留锁文件与框架自测，替换业务入口；已有目录一律拒绝覆盖。"""
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", name):
        raise ValueError("项目名以小写字母开头，只含小写字母、数字、_、-，最长 64 字符")
    if name.lower() in {
        "con",
        "prn",
        "aux",
        "nul",
        *[f"com{i}" for i in range(1, 10)],
        *[f"lpt{i}" for i in range(1, 10)],
    }:
        raise ValueError("项目名不能使用系统保留名")
    source = _source_root()
    raw_target = Path(output).expanduser()
    if raw_target.is_symlink() or raw_target.exists():
        raise ValueError("输出目录已存在，不会覆盖；请指定新的目录")
    target = raw_target.resolve()
    if target.is_relative_to(source):
        raise ValueError("输出目录必须在框架仓库外，例如 --output ../company-qa")

    # 不复制整个工作区：.git、.env、现有公司配置、报告、安装包和缓存都不在名单中。
    files = [
        source / item
        for item in (
            "pyproject.toml",
            "uv.lock",
            ".python-version",
            ".gitignore",
            ".gitattributes",
            "AGENTS.md",
            ".playwright/cli.config.json",
        )
    ]
    for folder, suffixes in (
        ("src/autotest", {".py"}),
        ("tests/unit", {".py"}),
        ("docs", {".md"}),
        ("templates", {".md", ".yaml", ".yml", ".py", ".tmpl", ".example", ".json"}),
        ("examples", {".md", ".py", ".json"}),
        (".agents/skills", {".md"}),
    ):
        files.extend(_files(source, folder, suffixes))
    # demo 环境仅用于框架单测；不会带出演示业务测试和私人配置。
    files.append(source / "configs/environments/demo.yaml")
    # 框架单测需要演示角色文件；公司角色配置由模板另行生成。
    files.append(source / "configs/auth/demo.yaml")
    for path in files:
        if not path.is_file() or path.is_symlink():
            raise ValueError("框架源码资产不完整，请从完整源码仓库执行初始化")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.mkdir()  # 并发执行也不能覆盖已有项目。
    for path in files:
        destination = target / path.relative_to(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
    for path in _files(source, "templates/company", {".md", ".yaml", ".tmpl", ".example", ".json"}):
        relative = path.relative_to(source / "templates/company")
        destination = target / relative
        if destination.name.endswith(".tmpl"):
            destination = destination.with_suffix("")
        destination.parent.mkdir(parents=True, exist_ok=True)
        content = path.read_text(encoding="utf-8").replace("__PROJECT_NAME__", name)
        destination.write_text(content, encoding="utf-8")
    return target
