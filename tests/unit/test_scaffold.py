"""验证导出的公司项目可运行且不会把私密文件/旧业务拷过去。"""

import ast
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from autotest.config import Settings
from autotest.demo import DemoServer
from autotest.scaffold import init_project

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2]


def _run(project, *args):
    environment = dict(os.environ)
    for key in (*[field.upper() for field in Settings.model_fields], "TEST_ENV", "PYTEST_ADDOPTS"):
        environment.pop(key, None)
    environment.update(PYTHONPATH=str(project / "src"), PYTHONUTF8="1")
    return subprocess.run(
        [sys.executable, "-m", "autotest", *args],
        cwd=project,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=90,
        check=False,
    )


def test_export_has_independent_assets_and_no_demo_business(tmp_path):
    project = init_project("company-qa", tmp_path / "company")
    assert (project / "uv.lock").read_bytes() == (ROOT / "uv.lock").read_bytes()
    assert (project / ".env.example").is_file()
    assert (project / "templates/company/.env.example").is_file()
    assert not (project / ".env").exists() and not (project / ".git").exists()
    assert not (project / "artifacts").exists()
    assert not (project / "tests/api/test_items.py").exists()
    assert not (project / "tests/web/test_login.py").exists()
    assert "company-qa" in (project / "README.md").read_text(encoding="utf-8")
    for platform in ("android", "ios"):
        assert (project / f"configs/devices/{platform}.yaml").is_file()
    for path in project.rglob("*.py"):
        ast.parse(path.read_text(encoding="utf-8"))
    checked = _run(project, "project", "check", "--env", "company_test", "--suite", "all")
    assert checked.returncode == 1
    assert "3 项失败" in checked.stdout


@pytest.mark.parametrize("name", ["../private", "Bad Name", "con", "lpt1", "a" * 65])
def test_bad_name_does_not_create_files(tmp_path, name):
    target = tmp_path / "company"
    with pytest.raises(ValueError):
        init_project(name, target)
    assert not target.exists()


def test_existing_directory_is_never_overwritten(tmp_path):
    target = tmp_path / "existing"
    target.mkdir()
    marker = target / ".env"
    marker.write_text("keep-private", encoding="utf-8")
    with pytest.raises(ValueError, match="不会覆盖"):
        init_project("company", target)
    assert marker.read_text() == "keep-private"


def test_destination_cannot_be_inside_framework():
    with pytest.raises(ValueError, match="仓库外"):
        init_project("company", ROOT / "nested-company-output")


def test_template_private_files_are_not_exported(tmp_path, monkeypatch):
    source = tmp_path / "source"
    for folder in ("templates", "src/autotest"):
        shutil.copytree(
            ROOT / folder, source / folder, ignore=shutil.ignore_patterns("__pycache__")
        )
    for name in (
        "pyproject.toml",
        "uv.lock",
        ".python-version",
        ".gitignore",
        ".gitattributes",
        "AGENTS.md",
        ".playwright/cli.config.json",
        "configs/environments/demo.yaml",
        "configs/auth/demo.yaml",
    ):
        destination = source / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
    for name in (
        ".env",
        ".env.production",
        "private.pem",
        ".auth/state.json",
        ".secrets/token.yaml",
    ):
        secret = source / "templates/company" / name
        secret.parent.mkdir(parents=True, exist_ok=True)
        secret.write_text("private-canary", encoding="utf-8")
    monkeypatch.setattr("autotest.scaffold._source_root", lambda: source)
    project = init_project("company", tmp_path / "export")
    for path in project.rglob("*"):
        if path.is_file():
            assert b"private-canary" not in path.read_bytes(), path


def test_generated_api_runs_actual_contract_and_fails_when_expectation_changes(tmp_path):
    project = init_project("integration", tmp_path / "integration")
    with DemoServer() as server:
        config = project / "configs/environments/company_test.yaml"
        config.write_text(
            yaml.safe_dump(
                {"api_base_url": server.base_url, "api_auth_file": "configs/auth/company.yaml"}
            ),
            encoding="utf-8",
        )
        smoke = project / "configs/business/smoke.yaml"
        data = {
            "api": {
                "path": "/health",
                "expected_status": 200,
                "expected_field": "status",
                "expected_value": "ok",
            }
        }
        smoke.write_text(yaml.safe_dump(data), encoding="utf-8")
        passed = _run(project, "run", "--suite", "api", "--", "-q")
        assert passed.returncode == 0, passed.stdout + passed.stderr
        data["api"]["expected_value"] = "wrong-on-purpose"
        smoke.write_text(yaml.safe_dump(data), encoding="utf-8")
        failed = _run(project, "run", "--suite", "api", "--", "-q")
        assert failed.returncode == 1, failed.stdout + failed.stderr
    records = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (project / "artifacts").glob("*/execution.json")
    ]
    assert sorted(record["exit_code"] for record in records) == [0, 1]


def test_unconfigured_company_sample_fails_instead_of_passing(tmp_path):
    project = init_project("unconfigured", tmp_path / "project")
    result = _run(project, "run", "--suite", "api", "--", "-q")
    assert result.returncode == 1
    assert "请补全 smoke.yaml" in result.stdout
    assert "company_test" in next((project / "artifacts").glob("*/events.jsonl")).read_text(
        encoding="utf-8"
    )
