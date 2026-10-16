"""静态回归范围建议。解析 import 和 fixture 作用域，不导入或执行业务代码。"""

from __future__ import annotations

import ast
from collections import defaultdict, deque
from pathlib import Path

from autotest.lifecycle import safe_path


def analyze_impact(root: Path, changed: list[str]) -> dict:
    root = root.resolve()
    changes = []
    for value in changed:
        safe_path(root, value)  # 允许已删除文件，但拒绝越界/符号链接。
        changes.append(value)
    paths = sorted({*root.glob("src/**/*.py"), *root.glob("tests/**/*.py"), root / "conftest.py"})
    paths = [p for p in paths if p.is_file() and "__pycache__" not in p.parts]
    modules, trees = {}, {}
    for path in paths:
        relative = path.relative_to(root).as_posix()
        safe_path(root, relative)
        pieces = list(path.relative_to(root).with_suffix("").parts)
        if pieces[0] == "src":
            pieces.pop(0)
        if pieces[-1] == "__init__":
            pieces.pop()
        modules[relative] = ".".join(pieces)
        # 不解析已删除模块，也不把语法错误静默当作无影响。
        trees[relative] = ast.parse(path.read_text(encoding="utf-8-sig"), filename=relative)
    reverse = defaultdict(set)
    for relative, tree in trees.items():
        module = modules[relative]
        package = module if relative.endswith("/__init__.py") else module.rpartition(".")[0]
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                prefix = ""
                if node.level:
                    parts = package.split(".")
                    prefix = ".".join(parts[: len(parts) - node.level + 1])
                base = ".".join(filter(None, (prefix, node.module)))
                imports.add(base)
                imports.update(".".join(filter(None, (base, alias.name))) for alias in node.names)
        # 包 __init__ 的变化也影响导入其子模块的用例。
        expanded = {
            ".".join(name.split(".")[:i])
            for name in imports
            for i in range(1, len(name.split(".")) + 1)
        }
        for dependency in expanded:
            reverse[dependency].add(relative)
    all_tests = sorted(
        p for p in modules if p.startswith("tests/") and Path(p).name.startswith("test_")
    )
    reasons = defaultdict(set)
    global_change = any(
        p in {"pyproject.toml", "uv.lock", "conftest.py", ".env", ".qa-framework.json"}
        or p.startswith("configs/")
        or p.startswith("src/autotest/")
        for p in changes
    )
    if global_change:
        for test in all_tests:
            reasons[test].add("公共底座、依赖或环境变化，建议完整回归")
    for changed_path in changes:
        if Path(changed_path).name == "conftest.py":
            parent = str(Path(changed_path).parent).replace("\\", "/")
            for test in all_tests:
                if parent == "." or test.startswith(parent + "/"):
                    reasons[test].add(f"fixture 作用域变化：{changed_path}")
        # 模块即使被删除，也按原路径推导模块名来查反向引用。
        parts = list(Path(changed_path).with_suffix("").parts)
        if parts and parts[0] == "src":
            parts.pop(0)
        if parts and parts[-1] == "__init__":
            parts.pop()
        queue, seen = deque([".".join(parts)]), set()
        if changed_path in all_tests:
            reasons[changed_path].add(f"用例自身变化：{changed_path}")
        while queue:
            module = queue.popleft()
            if module in seen:
                continue
            seen.add(module)
            for importer in reverse[module]:
                if importer in all_tests:
                    reasons[importer].add(f"直接或间接导入：{changed_path}")
                elif Path(importer).name == "conftest.py":
                    parent = Path(importer).parent.as_posix()
                    for test in all_tests:
                        if parent == "." or test.startswith(parent + "/"):
                            reasons[test].add(f"fixture 间接依赖：{changed_path}")
                queue.append(modules[importer])
    return {
        "schema_version": 1,
        "changed": sorted(set(changes)),
        "tests": sorted(reasons),
        "reasons": {key: sorted(reasons[key]) for key in sorted(reasons)},
        "limitations": "静态建议未执行测试；动态 import、字符串插件、外部需求变化需人工补充范围。",
    }
