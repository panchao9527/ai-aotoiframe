"""浏览器集成验证：录制材料生成的多文件草稿必须加载新 POM 并真实通过。"""

import shutil
from pathlib import Path

import pytest

from autotest.authoring.validation import validate
from autotest.authoring.workflow import generate, prepare

pytestmark = [pytest.mark.web, pytest.mark.demo]


def test_recording_to_pom_in_isolated_project(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[2]
    for name in ("src", "tests", "configs", "templates", "examples"):
        shutil.copytree(
            root / name, tmp_path / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
        )
    for name in ("pyproject.toml", "conftest.py"):
        shutil.copy2(root / name, tmp_path / name)
    monkeypatch.chdir(tmp_path)
    for key in ("API_BASE_URL", "WEB_BASE_URL", "API_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    workspace = prepare(
        "web-flow",
        "web",
        "single",
        requirement="examples/authoring/web-requirement.md",
        recording="examples/authoring/web-recording.py",
        sources=[],
        match=None,
        observation=None,
        spec=None,
        operations=[],
        spec_auth_env=None,
    )
    generate("web-flow", response="examples/authoring/responses/web.json")
    report = validate("web-flow", execute=True, environment="demo")
    assert report["passed"], (workspace / "validation.log").read_text(encoding="utf-8")
    assert report["counts"]["passed"] == 1
    assert not (tmp_path / "src/autotest/web/contact_page.py").exists()
