"""验证清理失败不会中断其他资源清理，也不会覆盖原本的测试失败。"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from autotest.data import CleanupError, DataFactory

pytestmark = pytest.mark.unit


def test_cleanup_is_lifo_continues_after_failure_and_does_not_retry():
    factory = DataFactory()
    calls = []

    def fail():
        calls.append("child")
        raise RuntimeError("unlabelled-private-value")

    factory.defer("parent", lambda: calls.append("parent"))
    factory.defer("child", fail)
    with pytest.raises(CleanupError, match="1 个") as error:
        factory.cleanup()
    assert calls == ["child", "parent"]
    assert [row["status"] for row in factory.results] == ["failed", "cleaned"]
    assert "unlabelled-private-value" not in str(error.value) + json.dumps(factory.results)
    factory.cleanup()
    assert len(calls) == 2
    with pytest.raises(RuntimeError, match="已清理"):
        factory.defer("new", lambda: None)


def test_names_and_factories_are_independent():
    first, second = DataFactory(), DataFactory()
    names = {factory.unique() for factory in (first, second) for _ in range(10)}
    assert len(names) == 20
    assert first.run_id != second.run_id


@pytest.mark.parametrize("failure", [pytest.fail, pytest.skip])
def test_pytest_outcome_in_callback_does_not_skip_remaining_cleanup(failure):
    factory = DataFactory()
    cleaned = []
    factory.defer("parent", lambda: cleaned.append("parent"))
    factory.defer("child", lambda: failure("cleanup did not complete"))
    with pytest.raises(CleanupError):
        factory.cleanup()
    assert cleaned == ["parent"]
    assert factory.results[0]["status"] == "failed"


def test_user_interrupt_is_not_swallowed():
    factory = DataFactory()

    def interrupted():
        raise KeyboardInterrupt

    factory.defer("interrupt", interrupted)
    with pytest.raises(KeyboardInterrupt):
        factory.cleanup()


def test_business_failure_and_cleanup_failure_both_survive(tmp_path):
    (tmp_path / "test_failure.py").write_text(
        """from pathlib import Path
def test_failure(data_factory):
    def broken():
        raise RuntimeError("unlabelled-private-value")
    data_factory.defer("parent", lambda: Path("cleaned.txt").write_text("cleaned"))
    data_factory.defer("child", broken)
    assert False, "original-business-failure"
""",
        encoding="utf-8",
    )
    root = Path(__file__).resolve().parents[2]
    child_temp = tmp_path / "child-temp"
    child_temp.mkdir()
    environment = {
        **os.environ,
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "PYTHONUTF8": "1",
        "PYTHONPATH": str(root / "src"),
        "TEMP": str(child_temp),
        "TMP": str(child_temp),
    }
    environment.pop("PYTEST_ADDOPTS", None)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "test_failure.py",
            "-p",
            "autotest.pytest_plugin",
            "--env",
            "demo",
            "--config-dir",
            str(root / "configs/environments"),
            "--artifact-dir",
            str(tmp_path / "evidence"),
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
    assert result.returncode == 1, result.stdout + result.stderr
    assert "original-business-failure" in result.stdout
    assert (tmp_path / "cleaned.txt").read_text() == "cleaned"
    reports = list((tmp_path / "evidence/data-cleanup").glob("*.json"))
    assert len(reports) == 1
    rows = json.loads(reports[0].read_text(encoding="utf-8"))["resources"]
    assert [row["status"] for row in rows] == ["failed", "cleaned"]
    failures = list((tmp_path / "evidence/failures").glob("*/*.json"))
    assert {file.stem for file in failures} == {"call", "teardown"}
