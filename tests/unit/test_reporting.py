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
            "--config-dir",
            str(config_dir),
            "--artifact-dir",
            str(artifact_dir),
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
