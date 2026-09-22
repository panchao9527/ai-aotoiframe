"""在隔离目录故意制造三种阶段失败，验证证据落盘及 pytest 非零退出码。

这个子进程失败是预期的；外层测试验证正确处理失败后会通过。
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def test_setup_call_and_teardown_failure_evidence(tmp_path):
    test_file = tmp_path / "test_failures.py"
    test_file.write_text(
        """import pytest

@pytest.fixture
def broken_setup():
    pytest.fail("password='setup-secret'")

@pytest.fixture
def broken_teardown():
    yield
    pytest.fail("Authorization: Bearer teardown-secret")

def test_setup(broken_setup):
    pass

def test_call():
    pytest.fail("password='call-secret'")

def test_teardown(broken_teardown):
    assert True
""",
        encoding="utf-8",
    )
    artifact_dir = tmp_path / "evidence"
    html_report = tmp_path / "report.html"
    child_temp = tmp_path / "child-temp"
    child_temp.mkdir()
    config_dir = Path(__file__).resolve().parents[2] / "configs" / "environments"
    environment = {
        **os.environ,
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "TEST_ENV": "demo",
        # xdist worker 中的嵌套 pytest 使用独立临时根，避免并行清理 Playwright 临时目录。
        "TEMP": str(child_temp),
        "TMP": str(child_temp),
    }
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(test_file),
            "-p",
            "autotest.pytest_plugin",
            "-p",
            "pytest_html.plugin",
            "-p",
            "pytest_metadata.plugin",
            "--config-dir",
            str(config_dir),
            "--artifact-dir",
            str(artifact_dir),
            "--html",
            str(html_report),
            "--self-contained-html",
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    assert process.returncode == 1, process.stdout + process.stderr
    files = list(artifact_dir.glob("failures/*/*.json"))
    assert len(files) == 3
    records = [json.loads(path.read_text(encoding="utf-8")) for path in files]
    assert {record["phase"] for record in records} == {"setup", "call", "teardown"}
    for path in files:
        content = path.read_text(encoding="utf-8")
        assert "setup-secret" not in content
        assert "call-secret" not in content
        assert "teardown-secret" not in content
    for name in ("events.jsonl", "run.log", "log-summary.json"):
        assert (artifact_dir / name).is_file()
    structured = (artifact_dir / "events.jsonl").read_text(encoding="utf-8")
    assert '"level":"ERROR"' in structured
    assert "setup-secret" not in structured
    assert "call-secret" not in structured
    assert "teardown-secret" not in structured
    html = html_report.read_text(encoding="utf-8")
    assert "setup-secret" not in html
    assert "call-secret" not in html
    assert "teardown-secret" not in html


def test_allure_parameter_values_are_redacted(tmp_path):
    test_file = tmp_path / "test_parameter.py"
    test_file.write_text(
        """import pytest
@pytest.mark.parametrize("case,password,body,method", [({"username": "demo", "token": "nested-secret"}, "allure-secret", ["unlabelled-private-value"], "GET")])
def test_parameter(case, password, body, method):
    assert case["username"] == "demo"
    assert password and body and method == "GET"
""",
        encoding="utf-8",
    )
    artifact_dir = tmp_path / "evidence"
    allure_dir = tmp_path / "allure-results"
    child_temp = tmp_path / "child-temp"
    child_temp.mkdir()
    root = Path(__file__).resolve().parents[2]
    environment = {
        **os.environ,
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "PYTHONPATH": str(root / "src"),
        "TEMP": str(child_temp),
        "TMP": str(child_temp),
    }
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(test_file),
            "-p",
            "autotest.pytest_plugin",
            "-p",
            "allure_pytest",
            "--env",
            "demo",
            "--config-dir",
            str(root / "configs/environments"),
            "--artifact-dir",
            str(artifact_dir),
            "--alluredir",
            str(allure_dir),
            "-q",
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    assert process.returncode == 0, process.stdout + process.stderr
    content = "\n".join(path.read_text(encoding="utf-8") for path in allure_dir.glob("*.json"))
    assert "allure-secret" not in content and "nested-secret" not in content
    assert "unlabelled-private-value" not in content
    assert "[REDACTED]" in content
    assert '"name": "method", "value": "\'GET\'"' in content
