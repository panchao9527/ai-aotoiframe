"""静态提取逐用例依据；只验证记录可追溯，不把实现行为宣称为需求正确。

材料只保存别名和脱敏快照散列；原始源码/录制内容不随正式用例入库。
pytest.mark.case 的参数必须是字面量，检查时不会 import 或执行草稿。
"""

import ast
import hashlib
import json
import re


def material_versions(context: dict) -> dict:
    versions = {}

    def add(name, kind, value):
        text = json.dumps(value, sort_keys=True, ensure_ascii=False)
        versions[name] = {"kind": kind, "sha256": hashlib.sha256(text.encode()).hexdigest()}

    for key, kind in (
        ("requirement", "requirement"),
        ("openapi", "contract"),
        ("observation", "observation"),
        ("recording", "observation"),
    ):
        if key in context:
            add(key, kind, context[key])
    for item in context.get("sources", []):
        add(item["source"], "source", item["text"])
    return versions


def case_records(tree: ast.AST, path: str, materials: dict) -> tuple[list[dict], list[str]]:
    records, errors = [], []

    def visit(nodes, parents=()):
        for node in nodes:
            if isinstance(node, ast.ClassDef):
                visit(node.body, (*parents, node.name))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.name.startswith("test_"):
                    continue
                test = "::".join((path, *parents, node.name))
                decorators = [
                    d
                    for d in node.decorator_list
                    if isinstance(d, ast.Call) and ast.unparse(d.func) == "pytest.mark.case"
                ]
                try:
                    if len(decorators) != 1 or decorators[0].args:
                        raise ValueError("每条用例需要一个 pytest.mark.case 命名参数标记")
                    values = {}
                    for keyword in decorators[0].keywords:
                        if keyword.arg is None or keyword.arg in values:
                            raise ValueError("case 不允许展开或重复字段")
                        values[keyword.arg] = ast.literal_eval(keyword.value)
                    required = {"id", "purpose", "expected", "basis", "source"}
                    if set(values) != required:
                        raise ValueError("case 需要 id/purpose/expected/basis/source 五个字段")
                    if any(
                        not isinstance(value, str) or not value.strip() for value in values.values()
                    ):
                        raise ValueError("case 字段必须是非空字面字符串")
                    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,79}", values["id"]):
                        raise ValueError("case id 使用英文开头的唯一编号，最长 80 字符")
                    source = materials.get(values["source"])
                    if source is None or source["kind"] != values["basis"]:
                        raise ValueError("case source 必须指向本次材料，且与 basis 类型一致")
                    records.append({"test": test, **values, "material": source})
                except (ValueError, TypeError, SyntaxError) as exc:
                    errors.append(f"{test}: 预期依据无效：{exc}")

    visit(tree.body)
    return records, errors
