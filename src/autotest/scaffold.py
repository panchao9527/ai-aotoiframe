"""从源码框架导出可独立安装的公司项目，只复制明确列出的工程资产。"""

from __future__ import annotations

import re
from pathlib import Path

from autotest.lifecycle import digest, read_catalog, write_state
from autotest.project_layout import (
    asset_bytes,
    github_workflow,
    include_template,
    jenkins_pipeline,
    template_text,
    validate_type,
)


def _source_root() -> Path:
    root = Path(__file__).resolve().parents[2]
    if not (root / "uv.lock").is_file() or not (root / "templates/company").is_dir():
        raise ValueError("project init 需要源码仓库，请在克隆的 ai-aotoiframe 中执行")
    return root


def init_project(name: str, output: str | Path, *, project_type: str = "api") -> Path:
    """保留锁文件与框架自测，替换业务入口；已有目录一律拒绝覆盖。"""
    validate_type(project_type)
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
        destination.write_bytes(
            asset_bytes(source, path.relative_to(source).as_posix(), project_type)
        )
    for path in files:
        if not path.is_relative_to(source / "templates/company"):
            continue
        relative = path.relative_to(source / "templates/company")
        if not include_template(relative, project_type):
            continue
        destination = target / relative
        if destination.name.endswith(".tmpl"):
            destination = destination.with_suffix("")
        destination.parent.mkdir(parents=True, exist_ok=True)
        content = template_text(source, relative, name, project_type)
        destination.write_text(content, encoding="utf-8")
    workflow = target / ".github/workflows/company-tests.yml"
    workflow.parent.mkdir(parents=True, exist_ok=True)
    workflow.write_text(github_workflow(source, project_type), encoding="utf-8")
    (target / "Jenkinsfile").write_text(jenkins_pipeline(source, project_type), encoding="utf-8")
    write_state(
        target,
        catalog,
        {name: digest(target / name) for name in catalog["managed"]},
        project_type=project_type,
    )
    return target
