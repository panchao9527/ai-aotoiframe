"""从源码框架导出可独立安装的公司项目，只复制明确列出的工程资产。"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from autotest.lifecycle import digest, read_catalog, write_state


def _source_root() -> Path:
    root = Path(__file__).resolve().parents[2]
    if not (root / "uv.lock").is_file() or not (root / "templates/company").is_dir():
        raise ValueError("project init 需要源码仓库，请在克隆的 ai-aotoiframe 中执行")
    return root


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

    # 精确清单替代目录扫描；本地临时公司模块、文档和模板不会被自动带出。
    catalog = read_catalog(source)
    files = [source / name for name in catalog["managed"] + catalog["bootstrap"]]

    target.parent.mkdir(parents=True, exist_ok=True)
    target.mkdir()  # 并发执行也不能覆盖已有项目。
    for path in files:
        destination = target / path.relative_to(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
    for path in files:
        if not path.is_relative_to(source / "templates/company"):
            continue
        relative = path.relative_to(source / "templates/company")
        destination = target / relative
        if destination.name.endswith(".tmpl"):
            destination = destination.with_suffix("")
        destination.parent.mkdir(parents=True, exist_ok=True)
        content = path.read_text(encoding="utf-8").replace("__PROJECT_NAME__", name)
        destination.write_text(content, encoding="utf-8")
    write_state(target, catalog, {name: digest(target / name) for name in catalog["managed"]})
    return target
