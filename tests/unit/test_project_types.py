"""独立工程必须在目录、默认依赖、执行范围和 CI 中保持同一类型。"""

import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml

from autotest.config import Settings
from autotest.lifecycle import STATE, upgrade_project
from autotest.project import main as project_main
from autotest.project_layout import asset_bytes, github_workflow
from autotest.scaffold import init_project

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("kind", ["api", "web", "app", "all"])
def test_project_type_selects_business_configuration_and_default_dependencies(tmp_path, kind):
    target = init_project(f"company-{kind}", tmp_path / kind, project_type=kind)
    active = {"api", "web", "app"} if kind == "all" else {kind}
    for suite, layer in (("api", "api"), ("web", "web"), ("app", "mobile")):
        assert (target / f"tests/{suite}").is_dir() == (suite in active)
        assert (target / f"src/project_business/{layer}").is_dir() == (suite in active)
    assert (target / "configs/devices").exists() == ("app" in active)
    assert (
        set(yaml.safe_load((target / "configs/business/smoke.yaml").read_text(encoding="utf-8")))
        == active
    )
    config = tomllib.loads((target / "pyproject.toml").read_text(encoding="utf-8"))
    assert config["tool"]["uv"]["default-groups"] == [kind]
    assert set(config["tool"]["pytest"]["ini_options"]["testpaths"]) == {
        f"tests/{s}" for s in active
    }
    assert json.loads((target / STATE).read_text(encoding="utf-8"))["project_type"] == kind
    readme = (target / "README.md").read_text(encoding="utf-8")
    assert "__PROJECT" not in readme
    assert "company-" + kind in readme
    assert (target / "Jenkinsfile").is_file()
    assert "__PROJECT" not in (target / "Jenkinsfile").read_text(encoding="utf-8")
    assert (target / ".github/workflows/company-tests.yml").is_file()
    # 原始与已渲染的 pyproject 使用同一函数重复渲染也必须保持有效。
    assert asset_bytes(target, "pyproject.toml", kind) == (target / "pyproject.toml").read_bytes()


@pytest.mark.parametrize("kind", ["api", "web", "app"])
def test_company_ci_exposes_only_selected_lane(kind):
    text = github_workflow(ROOT, kind)
    workflow = yaml.safe_load(text)
    dispatch = workflow["on"]["workflow_dispatch"]
    assert dispatch["inputs"]["suite"]["options"] == [kind]
    assert set(workflow["jobs"]) == ({"android", "ios"} if kind == "app" else {kind})
    if kind != "app":
        assert "app_platform" not in dispatch["inputs"]
    if kind == "api":
        assert "Install browser" not in text


def test_profile_survives_upgrade_and_does_not_restore_other_business(tmp_path):
    target = init_project("api-company", tmp_path / "api-company", project_type="api")
    before = (target / "pyproject.toml").read_bytes()
    report = upgrade_project(ROOT, target, apply=True)
    assert report["applied"] and not report["changes"] and not report["conflicts"]
    assert (target / "pyproject.toml").read_bytes() == before
    assert json.loads((target / STATE).read_text(encoding="utf-8"))["project_type"] == "api"
    assert not (target / "tests/web").exists() and not (target / "tests/app").exists()


def test_changed_public_dependency_file_still_renders_selected_type(tmp_path, monkeypatch):
    source = tmp_path / "source"
    catalog = json.loads((ROOT / "framework-assets.json").read_text(encoding="utf-8"))
    for name in catalog["managed"] + catalog["bootstrap"]:
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, path)
    monkeypatch.setattr("autotest.scaffold._source_root", lambda: source)
    target = init_project("web-project", tmp_path / "web-project", project_type="web")
    dependency_file = source / "pyproject.toml"
    dependency_file.write_text(
        dependency_file.read_text(encoding="utf-8") + "\n# New public revision\n", encoding="utf-8"
    )
    result = upgrade_project(source, target, apply=True)
    assert result["applied"] and {item["path"] for item in result["changes"]} == {"pyproject.toml"}
    config = tomllib.loads((target / "pyproject.toml").read_text(encoding="utf-8"))
    assert config["tool"]["uv"]["default-groups"] == ["web"]
    assert config["tool"]["pytest"]["ini_options"]["testpaths"] == ["tests/web"]


def test_api_default_execution_does_not_collect_framework_or_other_ends(tmp_path):
    target = init_project("api-company", tmp_path / "api-company", project_type="api")
    # collect-only 不访问网络，也不把仅收集结果作为业务通过证据。
    environment = dict(os.environ, PYTHONPATH=str(target / "src"), PYTHONUTF8="1")
    environment.pop("PYTEST_ADDOPTS", None)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=target,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "tests/api/test_company_smoke.py" in result.stdout
    assert "tests/unit/" not in result.stdout
    assert "tests/web/" not in result.stdout and "tests/app/" not in result.stdout


def test_web_default_preflight_does_not_require_api_or_device(tmp_path, monkeypatch, capsys):
    target = init_project("web-company", tmp_path / "web-company", project_type="web")
    monkeypatch.chdir(target)
    for name in (*[key.upper() for key in Settings.model_fields], "TEST_ENV"):
        monkeypatch.delenv(name, raising=False)
    (target / "configs/environments/company_test.yaml").write_text(
        "web_base_url: https://web.company.internal\n", encoding="utf-8"
    )
    assert project_main(["check", "--env", "company_test"]) == 0
    output = capsys.readouterr().out
    assert "WEB 配置预检通过" in output
    assert "API 配置预检通过" not in output and "APP 配置预检通过" not in output


def test_invalid_type_does_not_create_project(tmp_path):
    with pytest.raises(ValueError):
        init_project("invalid", tmp_path / "invalid", project_type="desktop")
    assert not (tmp_path / "invalid").exists()
