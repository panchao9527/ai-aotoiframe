"""框架资产清单和公司工程升级。只管理明确登记的文件，不扫描或覆盖业务目录。"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from pathlib import Path, PurePosixPath

from autotest.project_layout import asset_bytes, validate_type

CATALOG = "framework-assets.json"
STATE = ".qa-framework.json"
MANAGED_ROOTS = (
    "src/autotest/",
    "tests/unit/",
    "docs/",
    "templates/",
    "examples/",
    ".agents/skills/",
    "scripts/",
)
MANAGED_FILES = {
    CATALOG,
    "pyproject.toml",
    "uv.lock",
    ".python-version",
    ".playwright/cli.config.json",
    "CHANGELOG.md",
}


def _managed_name(name: str) -> bool:
    return name in MANAGED_FILES or name.startswith(MANAGED_ROOTS)


def safe_path(root: Path, relative: str) -> Path:
    pure = PurePosixPath(relative)
    if (
        not relative
        or "\\" in relative
        or ":" in relative
        or pure.is_absolute()
        or any(part in {".", ".."} for part in relative.split("/"))
    ):
        raise ValueError("资产路径必须是项目内的相对路径")
    path = root / relative
    if path.resolve() != path:
        raise ValueError(f"资产路径不能包含符号链接：{relative}")
    return path


def digest(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def read_catalog(source: Path) -> dict:
    data = json.loads((source / CATALOG).read_text(encoding="utf-8"))
    if (
        not isinstance(data, dict)
        or data.get("schema_version") != 1
        or not isinstance(data.get("framework_version"), str)
    ):
        raise ValueError("框架资产清单版本无效")
    seen = set()
    for group in ("managed", "bootstrap"):
        entries = data.get(group)
        if not isinstance(entries, list) or not entries:
            raise ValueError("框架资产清单缺少文件列表")
        for name in entries:
            if not isinstance(name, str) or name.lower() in seen:
                raise ValueError("框架资产清单路径无效或重复")
            seen.add(name.lower())
            if group == "managed" and not _managed_name(name):
                raise ValueError("公司业务与配置不能登记为公共升级资产")
            parts = PurePosixPath(name).parts
            if any(
                part in {".env", ".auth", ".secrets", ".git", "artifacts", ".venv"}
                for part in parts
            ) or Path(name).suffix in {".pem", ".key", ".pfx", ".p12", ".apk", ".ipa", ".pyc"}:
                raise ValueError("资产清单不能包含凭据、会话、报告或安装包")
            if not safe_path(source, name).is_file():
                raise ValueError(f"框架源码资产不完整：{name}")
    return data


def write_state(
    target: Path, catalog: dict, files: dict[str, str], *, project_type: str | None = None
) -> None:
    value = {
        "schema_version": 1,
        "framework_version": catalog["framework_version"],
        "files": files,
    }
    validate_type(project_type)
    if project_type is not None:
        value["project_type"] = project_type
    path = safe_path(target, STATE)
    temporary = path.with_name(f"{STATE}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def upgrade_project(source: Path, target: Path, *, apply: bool = False) -> dict:
    """先完整比较基线、本地、上游；存在冲突时整批不写。默认只预览。"""
    source, target = source.resolve(), target.resolve()
    if target == source or target.is_relative_to(source) or source.is_relative_to(target):
        raise ValueError("升级目标必须是框架仓库之外的公司工程")
    catalog = read_catalog(source)
    try:
        state = json.loads(safe_path(target, STATE).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("目标缺少有效的 .qa-framework.json；旧项目需按迁移手册接入") from exc
    if not isinstance(state, dict):
        raise ValueError("目标框架版本记录无效")
    baseline = state.get("files")
    if state.get("schema_version") != 1 or not isinstance(baseline, dict):
        raise ValueError("目标框架版本记录无效")
    project_type = state.get("project_type")
    validate_type(project_type)
    upstream = {
        name: hashlib.sha256(asset_bytes(source, name, project_type)).hexdigest()
        for name in catalog["managed"]
    }
    changes, conflicts, preserved = [], [], []
    for name in sorted(set(baseline) | set(upstream)):
        if not isinstance(name, str) or not _managed_name(name):
            raise ValueError("版本记录含非公共资产，拒绝升级")
        before, after = baseline.get(name), upstream.get(name)
        if before is not None and (
            not isinstance(before, str) or not re.fullmatch(r"[0-9a-f]{64}", before)
        ):
            raise ValueError("目标资产基线散列无效")
        local_path = safe_path(target, name)
        local = digest(local_path)
        if local_path.exists() and not local_path.is_file():
            conflicts.append(name)
        elif before == after:
            if local != before:
                preserved.append(name)
            continue  # 上游未改时保留公司修改，并在预览中明确列出。
        elif local == after:
            continue  # 已经手动合并成上游内容也可接受。
        elif local == before:
            changes.append({"path": name, "action": "delete" if after is None else "write"})
        else:
            conflicts.append(name)
    report = {
        "from_version": state.get("framework_version"),
        "to_version": catalog["framework_version"],
        "changes": changes,
        "conflicts": conflicts,
        "preserved_local_changes": preserved,
        "applied": False,
    }
    if not apply or conflicts:
        return report
    # 保存原始字节，写入错误时撤回本批次，业务文件从未进入写入集合。
    originals = {
        item["path"]: (target / item["path"]).read_bytes()
        if (target / item["path"]).is_file()
        else None
        for item in changes
    }
    try:
        for item in changes:
            destination = safe_path(target, item["path"])
            if item["action"] == "delete":
                destination.unlink()
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(asset_bytes(source, item["path"], project_type))
        write_state(target, catalog, upstream, project_type=project_type)
    except (OSError, ValueError):
        for name, content in originals.items():
            path = target / name
            if content is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(content)
        raise
    report["applied"] = True
    return report
