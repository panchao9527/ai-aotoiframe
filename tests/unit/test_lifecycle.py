"""验证升级不会覆盖公司修改，冲突时不留下半次升级。"""

import json
import shutil

import pytest

from autotest.lifecycle import CATALOG, STATE, digest, upgrade_project, write_state

pytestmark = pytest.mark.unit


@pytest.fixture
def projects(tmp_path):
    source, target = tmp_path / "framework", tmp_path / "company"
    source.mkdir()
    target.mkdir()
    for name, text in {
        "src/autotest/a.py": "old-a",
        "docs/guide.md": "old-guide",
        "pyproject.toml": "old-deps",
    }.items():
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
    catalog = {
        "schema_version": 1,
        "framework_version": "0.2.0",
        "managed": ["src/autotest/a.py", "docs/guide.md"],
        "bootstrap": ["pyproject.toml"],
    }
    (source / CATALOG).write_text(json.dumps(catalog), encoding="utf-8")
    write_state(target, catalog, {name: digest(target / name) for name in catalog["managed"]})
    return source, target, catalog


def test_preview_then_upgrade_preserves_business_and_local_only_changes(projects):
    source, target, catalog = projects
    business = target / "src/project_business/orders.py"
    business.parent.mkdir()
    business.write_text("company-orders", encoding="utf-8")
    (target / "docs/guide.md").write_text("company-guide", encoding="utf-8")
    (source / "src/autotest/a.py").write_text("new-a", encoding="utf-8")
    before = (target / STATE).read_bytes()
    report = upgrade_project(source, target)
    assert report["changes"] == [{"path": "src/autotest/a.py", "action": "write"}]
    assert not report["applied"] and (target / STATE).read_bytes() == before
    assert report["preserved_local_changes"] == ["docs/guide.md"]
    assert (target / "src/autotest/a.py").read_text() == "old-a"
    assert upgrade_project(source, target, apply=True)["applied"]
    assert (target / "src/autotest/a.py").read_text() == "new-a"
    assert (target / "docs/guide.md").read_text() == "company-guide"
    assert business.read_text() == "company-orders"
    assert not upgrade_project(source, target)["changes"]


def test_conflict_blocks_entire_batch_then_accepts_manual_merge(projects):
    source, target, catalog = projects
    for name in catalog["managed"]:
        (source / name).write_text("new", encoding="utf-8")
    (target / "docs/guide.md").write_text("local-change", encoding="utf-8")
    report = upgrade_project(source, target, apply=True)
    assert report["conflicts"] == ["docs/guide.md"] and not report["applied"]
    assert (target / "src/autotest/a.py").read_text() == "old-a"
    shutil.copyfile(source / "docs/guide.md", target / "docs/guide.md")
    assert upgrade_project(source, target, apply=True)["applied"]


def test_additions_deletions_and_modified_removed_file(projects):
    source, target, catalog = projects
    catalog["managed"] = ["src/autotest/a.py", "docs/new.md"]
    (source / "docs/new.md").write_text("new-guide", encoding="utf-8")
    (source / CATALOG).write_text(json.dumps(catalog), encoding="utf-8")
    (target / "docs/guide.md").write_text("company-own-guide", encoding="utf-8")
    assert upgrade_project(source, target, apply=True)["conflicts"] == ["docs/guide.md"]
    (target / "docs/guide.md").write_text("old-guide", encoding="utf-8")
    assert upgrade_project(source, target, apply=True)["applied"]
    assert not (target / "docs/guide.md").exists()
    assert (target / "docs/new.md").read_text() == "new-guide"


def test_write_error_rolls_back_files_and_keeps_version(projects, monkeypatch):
    source, target, catalog = projects
    (source / "src/autotest/a.py").write_text("new-a", encoding="utf-8")
    before = (target / STATE).read_bytes()

    def fail(*args):
        raise OSError("disk full")

    monkeypatch.setattr("autotest.lifecycle.write_state", fail)
    with pytest.raises(OSError):
        upgrade_project(source, target, apply=True)
    assert (target / "src/autotest/a.py").read_text() == "old-a"
    assert (target / STATE).read_bytes() == before


@pytest.mark.parametrize(
    "path",
    [
        "../outside.py",
        "src/../../secret",
        "C:/private",
        "docs\\bad.py",
        "src/project_business/orders.py",
        "configs/environments/company.yaml",
    ],
)
def test_invalid_baseline_paths_never_write_outside_project(projects, path):
    source, target, catalog = projects
    state = json.loads((target / STATE).read_text())
    state["files"][path] = "0" * 64
    (target / STATE).write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(ValueError):
        upgrade_project(source, target, apply=True)


def test_legacy_project_is_not_adopted_without_baseline(tmp_path, projects):
    source, _, _ = projects
    with pytest.raises(ValueError, match="迁移手册"):
        upgrade_project(source, tmp_path / "old-project", apply=True)
