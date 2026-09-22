"""按明确范围收集需求、源码、录制和 OpenAPI，避免把整个仓库塞给模型。"""

from __future__ import annotations

import ast
import json
import os
import re
from pathlib import Path

import httpx
import yaml

from autotest.ai import AIError, read_input
from autotest.authoring.swagger_source import MAX_SPEC_BYTES, read_remote_spec
from autotest.redaction import redact, redact_text

MAX_CONTEXT_BYTES = 384 * 1024
SOURCE_SUFFIXES = {".py", ".java", ".kt", ".js", ".jsx", ".ts", ".tsx", ".vue", ".go", ".cs"}
EXCLUDED = {".git", ".venv", "node_modules", "target", "build", "dist", "artifacts", "__pycache__"}


def bounded_text(path: Path, limit: int = 128 * 1024) -> str:
    if path.is_symlink():
        raise AIError(f"不读取符号链接：{path.name}")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise AIError(f"文件过大，请缩小材料：{path.name}")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise AIError(f"材料必须是 UTF-8：{path.name}") from exc


def recording_text(path: Path) -> str:
    """录制的 fill/send_keys 参数不一定被普通赋值脱敏覆盖，补充语义识别。

    只识别明确密码/令牌定位器；原始录制不改写。其余业务敏感信息仍需检查。
    """
    try:
        tree = ast.parse(bounded_text(path))
    except SyntaxError as exc:
        raise AIError("录制 Python 语法无效，请导出完整代码。") from exc
    sensitive = re.compile(r"password|passwd|secret|token|密码|authorization|cookie", re.I)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and sensitive.search(ast.unparse(node.value)):
            names.update(target.id for target in node.targets if isinstance(target, ast.Name))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            owner = ast.unparse(node.func.value)
            if node.func.attr in {"fill", "send_keys", "type"} and (
                sensitive.search(owner) or owner in names
            ):
                node.args = [ast.Constant("[REDACTED]") for _ in node.args]
                for keyword in node.keywords:
                    if keyword.arg in {"value", "text"}:
                        keyword.value = ast.Constant("[REDACTED]")
    return redact_text(ast.unparse(tree))


def contract_material(value, sensitive: bool = False):
    """保留 password/token 等字段的 schema，只移除示例和敏感默认值。

    不能对 OpenAPI 直接按业务 JSON 脱敏：properties.password 是字段定义，删除它会丢失
    必填/类型/长度契约。示例值不作为造数来源，真实账号从环境或 fixture 获得。
    """
    if isinstance(value, dict):
        sensitive = sensitive or bool(
            re.search(
                r"password|passwd|secret|token|authorization|cookie",
                str(value.get("name", "")),
                re.I,
            )
        )
        result = {}
        for key, item in value.items():
            if key in {"example", "examples"} or (key == "default" and sensitive):
                result[key] = "[OMITTED]"
            else:
                child_sensitive = sensitive or bool(
                    re.search(r"password|passwd|secret|token|authorization|cookie", str(key), re.I)
                )
                result[key] = contract_material(item, child_sensitive)
        return result
    if isinstance(value, list):
        return [contract_material(item, sensitive) for item in value]
    return redact_text(value) if isinstance(value, str) else value


def load_spec(
    source: str,
    operations: list[str],
    *,
    header_env: str | None = None,
    group: str | None = None,
) -> dict:
    """读取原始 OpenAPI 或发现 Swagger UI 的同源文档；不跟随远程 $ref。

    发现只读取有限的同源文档配置和规范，不执行 UI 的 JavaScript 或文档中的业务操作。
    认证头仅从指定环境变量取得，不保存到上下文或传给跨 origin 地址。
    """
    if source.startswith(("http://", "https://")):
        header = None
        if header_env:
            header = os.getenv(header_env)
            if not header:
                raise AIError(f"未设置文档认证环境变量 {header_env}")
        text = read_remote_spec(source, header=header, group=group, client_factory=httpx.Client)
    else:
        text = bounded_text(Path(source), MAX_SPEC_BYTES)
    try:
        if any(isinstance(event, yaml.AliasEvent) for event in yaml.parse(text)):
            raise AIError("OpenAPI YAML 不接受别名引用，请导出 JSON。")
        spec = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise AIError("无法解析 OpenAPI；Swagger UI 网页需要换成原始 JSON/YAML 地址。") from exc
    if not isinstance(spec, dict) or not (spec.get("openapi") or spec.get("swagger")):
        raise AIError("输入不是 OpenAPI/Swagger 文档；请提供原始 JSON/YAML。")
    paths = spec.get("paths", {})
    if not isinstance(paths, dict):
        raise AIError("OpenAPI paths 必须为对象。")
    selected: dict = {}
    for operation in operations:
        pieces = operation.split(maxsplit=1)
        if len(pieces) != 2:
            raise AIError("--operation 使用 'GET /api/items' 格式。")
        method, path = pieces[0].lower(), pieces[1]
        if path not in paths or method not in paths[path]:
            raise AIError(f"OpenAPI 中没有操作：{operation}")
        selected.setdefault(path, {})[method] = paths[path][method]
        for shared in ("parameters", "servers", "$ref"):
            if shared in paths[path]:
                selected[path][shared] = paths[path][shared]
    result = {key: value for key, value in spec.items() if key != "paths"}
    result["paths"] = selected if operations else paths
    # 保留完整 components/definitions 供内部 $ref 解析，禁止把外部引用偷偷联网展开。
    return contract_material(result)


def collect_sources(sources: list[str], match: str | None) -> list[dict]:
    records = []
    for index, source in enumerate(sources):
        target = Path(source).resolve()
        if target.is_dir():
            if not match:
                raise AIError("读取源码目录时请传 --match 关键字；也可以显式传多个源码文件。")
            candidates = []
            for folder, directories, names in os.walk(target, followlinks=False):
                directories[:] = sorted(
                    d for d in directories if d not in EXCLUDED and not d.startswith(".")
                )
                for name in sorted(names):
                    path = Path(folder) / name
                    if path.suffix.lower() in SOURCE_SUFFIXES and not path.is_symlink():
                        candidates.append(path)
                    if len(candidates) > 5000:
                        raise AIError("源码范围超过 5000 文件，请缩小 --source 到业务模块。")
        elif target.is_file() and target.suffix.lower() in SOURCE_SUFFIXES:
            candidates = [target]
        else:
            raise AIError(f"源码路径不存在或类型不支持：{target.name}")
        for path in candidates:
            content = bounded_text(path)
            if target.is_dir() and match.lower() not in content.lower():
                continue
            label = str(path.relative_to(target) if target.is_dir() else path.name)
            records.append({"source": f"source-{index + 1}/{label}", "text": redact_text(content)})
            if len(records) > 24:
                raise AIError("匹配超过 24 个源码文件，请缩小模块或使用更准确的 --match。")
    return records


def inventory(root: Path) -> list[dict]:
    """静态提取对象/fixture/用例签名；不 import 业务代码、不执行模块级逻辑。"""
    result = []
    paths = sorted((root / "src/autotest").rglob("*.py")) + sorted((root / "tests").rglob("*.py"))
    for path in paths:
        if path.is_symlink() or any(p in EXCLUDED for p in path.relative_to(root).parts):
            continue
        if "authoring" in path.parts or "unit" in path.parts:
            continue
        tree = ast.parse(bounded_text(path))
        symbols = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols.append(
                    {
                        "name": node.name,
                        "args": ast.unparse(node.args),
                        "decorators": [ast.unparse(d) for d in node.decorator_list],
                    }
                )
            elif isinstance(node, ast.ClassDef):
                symbols.append(
                    {
                        "class": node.name,
                        "methods": [
                            {"name": child.name, "args": ast.unparse(child.args)}
                            for child in node.body
                            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                        ],
                    }
                )
        if symbols:
            result.append({"path": path.relative_to(root).as_posix(), "symbols": symbols})
    return result


def collect_context(
    root: Path,
    *,
    requirement: str,
    sources: list[str],
    match: str | None,
    recording: str | None,
    observation: str | None,
    spec: str | None,
    operations: list[str],
    spec_auth_env: str | None,
    spec_group: str | None = None,
) -> dict:
    context = {
        "requirement": read_input(Path(requirement)),
        "framework": redact(inventory(root)),
        "sources": collect_sources(sources, match),
    }
    if recording:
        if Path(recording).suffix != ".py":
            raise AIError("录制输入使用 Python .py；观察到的页面结构另传 --observation。")
        context["recording"] = recording_text(Path(recording))
    if observation:
        context["observation"] = read_input(Path(observation))
    if spec:
        context["openapi"] = load_spec(spec, operations, header_env=spec_auth_env, group=spec_group)
    elif operations:
        raise AIError("--operation 需要同时提供 --openapi。")
    if len(json.dumps(context, ensure_ascii=False).encode()) > MAX_CONTEXT_BYTES:
        raise AIError("上下文超过 384 KiB，请拆分模块/场景，精简源码与接口文档。")
    return context
