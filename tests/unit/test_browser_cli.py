"""Playwright CLI 包装入口只验证命令边界，不在框架单测中下载 npm 包或启动浏览器。"""

import json

import pytest

from autotest.browser_cli import PLAYWRIGHT_CLI_PACKAGE, build_command, main

pytestmark = pytest.mark.unit


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    (tmp_path / "src/autotest").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_command_uses_pinned_package_named_session_and_no_shell(project, monkeypatch):
    monkeypatch.setattr("autotest.browser_cli.find_npx", lambda: "npx.cmd")
    calls = []

    class Result:
        returncode = 7

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return Result()

    monkeypatch.setattr("autotest.browser_cli.subprocess.run", run)
    assert main(["--session", "order-flow", "open", "https://example.test", "--headed"]) == 7
    command, options = calls[0]
    assert command == [
        "npx.cmd",
        "-y",
        "--package",
        PLAYWRIGHT_CLI_PACKAGE,
        "playwright-cli",
        "-s=order-flow",
        "open",
        "https://example.test",
        "--headed",
    ]
    assert options == {"cwd": project, "check": False}


def test_print_command_does_not_start_process(project, monkeypatch, capsys):
    monkeypatch.setattr("autotest.browser_cli.find_npx", lambda: "npx")
    monkeypatch.setattr(
        "autotest.browser_cli.subprocess.run", lambda *args, **kwargs: pytest.fail("不应启动进程")
    )
    assert main(["--print-command", "--", "snapshot", "--depth=5"]) == 0
    command = json.loads(capsys.readouterr().out)
    assert command[-2:] == ["snapshot", "--depth=5"]


@pytest.mark.parametrize("global_command", ["--version", "list", "close-all"])
def test_global_commands_do_not_require_an_open_session(project, monkeypatch, global_command):
    monkeypatch.setattr("autotest.browser_cli.find_npx", lambda: "npx")
    command = build_command([global_command], "unused")
    assert not any(part.startswith("-s=") for part in command)


@pytest.mark.parametrize("session", ["", "Order", "../order", "order flow", "x" * 65])
def test_invalid_session_is_rejected(project, monkeypatch, session):
    monkeypatch.setattr("autotest.browser_cli.find_npx", lambda: "npx")
    with pytest.raises(ValueError, match="会话名"):
        build_command(["snapshot"], session)


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["open", "https://user:secret@example.test"],
        ["goto", "http://user@example.test"],
        ["goto", "https://example.test/callback?access_token=secret"],
        ["goto", "https://example.test/#session=secret"],
    ],
)
def test_missing_command_or_inline_credentials_are_rejected(project, monkeypatch, arguments):
    monkeypatch.setattr("autotest.browser_cli.find_npx", lambda: "npx")
    with pytest.raises(ValueError):
        build_command(arguments, "safe")


def test_missing_npx_returns_actionable_error(project, monkeypatch, capsys):
    monkeypatch.setattr("autotest.browser_cli.shutil.which", lambda name: None)
    assert main(["snapshot"]) == 2
    output = capsys.readouterr().out
    assert "Node.js/npm" in output and "npx" in output


def test_requires_project_root(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["--print-command", "snapshot"]) == 2
    assert "项目根目录" in capsys.readouterr().out


def test_regular_business_query_is_allowed(project, monkeypatch):
    monkeypatch.setattr("autotest.browser_cli.find_npx", lambda: "npx")
    command = build_command(["goto", "https://example.test/items?page=2"], "safe")
    assert command[-1].endswith("?page=2")
