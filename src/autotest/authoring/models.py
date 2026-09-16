"""生成协议与路径边界。模型输出是数据，验证前不导入其中的 Python。"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from autotest.ai import AIError

Kind = Literal["api", "web", "app"]


class DraftFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str
    content: str = Field(min_length=1, max_length=131072)


class DraftReply(BaseModel):
    """Agent 和在线模型使用相同 JSON 协议，支持测试、对象和 fixture 一起生成。"""

    model_config = ConfigDict(extra="forbid")
    files: list[DraftFile] = Field(min_length=1, max_length=30)
    unresolved: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def project_root() -> Path:
    root = Path.cwd().resolve()
    if not (root / "pyproject.toml").is_file() or not (root / "src/autotest").is_dir():
        raise AIError("请从 autoiframe 项目根目录执行 author 命令。")
    return root


def workspace_path(name: str, root: Path | None = None) -> Path:
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", name):
        raise AIError("任务名需以小写字母开头，只含小写字母、数字、_、-，最长 64 字符。")
    root = root or project_root()
    target = root / "artifacts" / "ai" / name
    if target.resolve() != target:
        raise AIError("AI 工作区不能通过符号链接指向其他目录。")
    return target


def destination(path: str, kind: str) -> Path:
    """生成器只能增加业务 Python；禁止借路径穿越覆盖配置、插件或其他目录。"""
    pure = PurePosixPath(path)
    if "\\" in path or ":" in path or pure.is_absolute() or ".." in pure.parts:
        raise AIError(f"非法草稿路径：{path}")
    layer = {"api": "api", "web": "web", "app": "mobile"}[kind]
    allowed = (f"tests/{kind}/", f"src/autotest/{layer}/")
    if not path.startswith(allowed) or pure.suffix != ".py":
        raise AIError(f"草稿只允许写入 {allowed} 下的 Python 文件：{path}")
    # Windows 路径不区分大小写；每一段只用常见 Python 文件名，拒绝设备名/ADS。
    reserved = {
        "con",
        "prn",
        "aux",
        "nul",
        *[f"com{i}" for i in range(1, 10)],
        *[f"lpt{i}" for i in range(1, 10)],
    }
    for part in pure.parts:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*(?:\.py)?", part):
            raise AIError(f"草稿路径段不是有效名称：{part}")
        if part.split(".")[0].lower() in reserved:
            raise AIError(f"草稿路径不能使用系统保留名：{part}")
    return Path(*pure.parts)


def read_manifest(workspace: Path) -> dict:
    try:
        data = json.loads((workspace / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AIError("任务不存在或 manifest.json 损坏，请先 author prepare。") from exc
    if data.get("kind") not in {"api", "web", "app"}:
        raise AIError("工作区 kind 无效。")
    return data


def write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def draft_files(workspace: Path, manifest: dict) -> list[tuple[str, Path]]:
    files = manifest.get("files", [])
    if not files:
        raise AIError("任务还没有草稿，请先 author generate --response 或 --send。")
    result = []
    for name in files:
        path = workspace / "draft" / destination(name, manifest["kind"])
        if path.resolve() != path or not path.is_file():
            raise AIError(f"草稿文件丢失或使用了符号链接：{name}")
        result.append((name, path))
    return result


def fingerprint(workspace: Path, manifest: dict) -> str:
    digest = hashlib.sha256()
    digest.update(json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode())
    for name, path in draft_files(workspace, manifest):
        digest.update(name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def dependency_fingerprint(root: Path) -> str:
    """记录本次验证依赖的源码、配置和 fixture，避免依赖已变却沿用旧通过记录。

    只保存散列，不把 .env 内容写入报告。已有普通测试的改动不影响此依赖快照。
    """
    paths = [root / "pyproject.toml", root / "uv.lock", root / "conftest.py", root / ".env"]
    paths += sorted((root / "src").rglob("*.py"))
    paths += sorted((root / "tests").rglob("conftest.py"))
    paths += sorted(path for path in (root / "configs").rglob("*") if path.is_file())
    digest = hashlib.sha256()
    for path in paths:
        if path.is_file():
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()
