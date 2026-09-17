"""新增 AI 草稿需要逐条依据，历史 schema v1 保留兼容且不伪造记录。"""

import ast
import json

import pytest

from autotest.authoring.models import write_json
from autotest.authoring.provenance import case_records, material_versions
from autotest.authoring.validation import static_check

pytestmark = pytest.mark.unit


def marked_test(source="requirement", basis="requirement", case_id="CASE-1"):
    return (
        "import pytest\n"
        f'@pytest.mark.case(id="{case_id}", purpose="verify result", expected="exact value", '
        f'basis="{basis}", source="{source}")\n'
        "def test_sample():\n    assert 2 == 2\n"
    )


@pytest.mark.parametrize("source,basis", [("missing", "source"), ("requirement", "source")])
def test_fabricated_or_mislabeled_evidence_is_rejected(source, basis):
    versions = material_versions({"requirement": "business rule"})
    records, errors = case_records(
        ast.parse(marked_test(source, basis)), "tests/api/test_x.py", versions
    )
    assert not records and errors


def test_source_basis_is_explicitly_distinct_from_requirement():
    versions = material_versions({"sources": [{"source": "source-1/Service.java", "text": "code"}]})
    records, errors = case_records(
        ast.parse(marked_test("source-1/Service.java", "source")),
        "tests/api/test_x.py",
        versions,
    )
    assert not errors
    assert records[0]["basis"] == "source"
    assert len(records[0]["material"]["sha256"]) == 64


def test_marker_expressions_are_not_executed():
    tree = ast.parse(marked_test().replace('"CASE-1"', '__import__("os").getcwd()'))
    records, errors = case_records(
        tree, "tests/api/test_x.py", material_versions({"requirement": "x"})
    )
    assert not records and errors


def test_snapshot_changes_and_missing_markers_block_new_drafts(tmp_path):
    path = tmp_path / "draft/tests/api/test_example.py"
    path.parent.mkdir(parents=True)
    path.write_text(marked_test(), encoding="utf-8")
    context = {"requirement": "original rule"}
    write_json(tmp_path / "context.json", context)
    manifest = {
        "schema_version": 2,
        "kind": "api",
        "files": ["tests/api/test_example.py"],
        "materials": material_versions(context),
    }
    assert not static_check(tmp_path, manifest)[0]
    write_json(tmp_path / "context.json", {"requirement": "changed rule"})
    assert any("材料快照" in error for error in static_check(tmp_path, manifest)[0])
    write_json(tmp_path / "context.json", context)
    path.write_text("def test_untracked():\n    assert 2 == 2\n", encoding="utf-8")
    assert any("预期依据" in error for error in static_check(tmp_path, manifest)[0])
    manifest["schema_version"] = 1
    assert not static_check(tmp_path, manifest)[0], "已有 v1 草稿不应强制按新协议重建"


def test_duplicate_case_ids_are_rejected_across_files(tmp_path):
    context = {"requirement": "rule"}
    write_json(tmp_path / "context.json", context)
    files = ["tests/api/test_one.py", "tests/api/test_two.py"]
    for name in files:
        path = tmp_path / "draft" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(marked_test(), encoding="utf-8")
    manifest = {
        "schema_version": 2,
        "kind": "api",
        "files": files,
        "materials": material_versions(context),
    }
    assert any("重复 case id" in error for error in static_check(tmp_path, manifest)[0])
    assert "rule" not in json.dumps(manifest["materials"])
