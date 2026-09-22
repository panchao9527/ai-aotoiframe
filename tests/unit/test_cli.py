"""模板输出约束与入口转发测试。"""

import ast
import json
import subprocess

import pytest

from autotest.cli import main, new_test, run_tests

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("kind", ["api", "web", "app"])
def test_scaffold_contains_real_failure_until_completed(tmp_path, monkeypatch, kind):
    monkeypatch.chdir(tmp_path)
    path = new_test(kind, "order", None)
    source = path.read_text(encoding="utf-8")
    ast.parse(source)
    assert "pytest.fail" in source
    assert path == tmp_path / "tests" / kind / "test_order.py"
    with pytest.raises(ValueError, match="不会覆盖"):
        new_test(kind, "order", None)


def test_scaffold_rejects_outside_tests(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="tests/"):
        new_test("api", "order", "src/order.py")


def test_pytest_arguments_are_forwarded_without_shell(monkeypatch):
    import autotest.cli as cli

    calls = []
    monkeypatch.setattr(cli, "run_tests", lambda suite, extra: calls.append((suite, extra)) or 7)
    assert main(["run", "--suite", "api", "--", "-n", "2", "-m", "smoke"]) == 7
    assert calls == [("api", ["-n", "2", "-m", "smoke"])]


def test_browser_arguments_are_forwarded_to_project_wrapper(monkeypatch):
    import autotest.browser_cli as browser_cli

    calls = []
    monkeypatch.setattr(browser_cli, "main", lambda args: calls.append(args) or 8)
    assert main(["browser", "--session", "order", "snapshot"]) == 8
    assert calls == [["--session", "order", "snapshot"]]


def test_artemis_arguments_are_forwarded_to_optional_client(monkeypatch):
    import autotest.mobile.artemis as artemis

    calls = []
    monkeypatch.setattr(artemis, "main", lambda args: calls.append(args) or 9)
    assert main(["artemis", "--env", "test", "devices"]) == 9
    assert calls == [["--env", "test", "devices"]]


def test_run_command_tees_redacted_console_and_records_log_paths(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    class Process:
        stdout = iter(["starting\n", "password='console-secret'\n"])

        @staticmethod
        def wait():
            return 5

    calls = []

    def popen(command, **options):
        calls.append((command, options))
        return Process()

    monkeypatch.setattr("autotest.cli.subprocess.Popen", popen)
    assert run_tests("unit", ["-q"]) == 5
    run_directory = next((tmp_path / "artifacts").iterdir())
    console = (run_directory / "console.log").read_text(encoding="utf-8")
    assert "console-secret" not in console and "[REDACTED]" in console
    metadata = json.loads((run_directory / "run.json").read_text(encoding="utf-8"))
    assert metadata["exit_code"] == 5
    assert metadata["logs"]["events"] == "events.jsonl"
    assert calls[0][1]["stderr"] is subprocess.STDOUT
    assert "shell" not in calls[0][1]
