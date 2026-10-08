"""公司 CI 只模拟子进程，不访问业务地址、CI 服务或真实设备。"""

import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def company_ci():
    path = Path(__file__).resolve().parents[2] / "templates/company-ci/run_company_ci.py"
    spec = importlib.util.spec_from_file_location("company_ci", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # 隔离 CI 配置；保留所有真实进程变量会把开发机凭据带入断言失败输出。
    with patch.dict(os.environ, {}, clear=True):
        yield module


def option(command, name):
    return command[command.index(name) + 1]


@pytest.mark.parametrize("preflight_code", [1, 2, 5])
def test_preflight_failure_does_not_run_business_tests(company_ci, monkeypatch, preflight_code):
    run = Mock(return_value=SimpleNamespace(returncode=preflight_code))
    monkeypatch.setattr(company_ci.subprocess, "run", run)

    assert company_ci.main(["--env", "company_test", "--suite", "web"]) == preflight_code

    run.assert_called_once()
    command = run.call_args.args[0]
    assert command[1:5] == ["-m", "autotest", "project", "check"]
    assert option(command, "--env") == "company_test"
    assert option(command, "--suite") == "web"


@pytest.mark.parametrize("suite", ["api", "web"])
@pytest.mark.parametrize("test_code", [0, 1, 5])
def test_requested_suite_runs_after_preflight_and_preserves_exit_code(
    company_ci, monkeypatch, suite, test_code
):
    run = Mock(side_effect=[SimpleNamespace(returncode=0), SimpleNamespace(returncode=test_code)])
    monkeypatch.setattr(company_ci.subprocess, "run", run)

    actual = company_ci.main(["--env", "company_staging", "--suite", suite, "--workers", "3"])

    assert actual == test_code
    assert run.call_count == 2
    check, test = [call.args[0] for call in run.call_args_list]
    assert check[3:5] == ["project", "check"]
    assert test[3] == "run"
    assert test.index("--") < test.index("--env")
    for call in run.call_args_list:
        assert option(call.args[0], "--suite") == suite
        assert option(call.args[0], "--env") == "company_staging"
        assert "--run-app" not in call.args[0]
        assert call.kwargs["env"]["TEST_ENV"] == "company_staging"
        assert not call.kwargs.get("shell", False)
    assert option(test, "-n") == "3"


def test_only_nonempty_known_ci_overrides_reach_child_environment(company_ci, monkeypatch):
    monkeypatch.setenv("API_BASE_URL", "https://old-api.company.local")
    monkeypatch.setenv("CI_API_BASE_URL", "https://api.company.local")
    monkeypatch.setenv("WEB_BASE_URL", "https://web.company.local")
    monkeypatch.setenv("CI_WEB_BASE_URL", "")
    monkeypatch.setenv("CI_API_AUTH_FILE", "   ")
    monkeypatch.setenv("CI_UNRELATED_SETTING", "do-not-map")
    run = Mock(return_value=SimpleNamespace(returncode=0))
    monkeypatch.setattr(company_ci.subprocess, "run", run)

    assert company_ci.main(["--env", "company_test", "--suite", "api"]) == 0

    child_env = run.call_args.kwargs["env"]
    assert child_env["API_BASE_URL"] == "https://api.company.local"
    assert child_env["WEB_BASE_URL"] == "https://web.company.local"
    assert "API_AUTH_FILE" not in child_env
    assert "UNRELATED_SETTING" not in child_env
    assert child_env["PYTHONUTF8"] == child_env["PYTHONUNBUFFERED"] == "1"
    assert os.environ["API_BASE_URL"] == "https://old-api.company.local"
    assert "TEST_ENV" not in os.environ


def test_jenkins_secret_file_is_loaded_without_echo_or_parent_environment_changes(
    company_ci, monkeypatch, tmp_path, capsys
):
    secret_file = tmp_path / "jenkins-secret.env"
    source = "TEST_ENV=demo\nAPI_TOKEN=ci-secret-token\nAPI_BASE_URL=https://api.company.local\n"
    secret_file.write_text(source, encoding="utf-8")
    monkeypatch.setenv("CI_ENV_FILE", str(secret_file))
    monkeypatch.setenv("API_TOKEN", "parent-token")
    run = Mock(return_value=SimpleNamespace(returncode=0))
    monkeypatch.setattr(company_ci.subprocess, "run", run)

    assert company_ci.main(["--env", "company_test", "--suite", "api"]) == 0

    for call in run.call_args_list:
        environment = call.kwargs["env"]
        assert environment["API_TOKEN"] == "ci-secret-token"
        assert environment["API_BASE_URL"] == "https://api.company.local"
        assert environment["TEST_ENV"] == "company_test"
        assert "ci-secret-token" not in " ".join(call.args[0])
    assert os.environ["API_TOKEN"] == "parent-token"
    assert "TEST_ENV" not in os.environ
    assert secret_file.read_text(encoding="utf-8") == source
    captured = capsys.readouterr()
    assert "ci-secret-token" not in captured.out + captured.err


def test_missing_secret_file_stops_before_preflight(company_ci, monkeypatch, tmp_path):
    monkeypatch.setenv("CI_ENV_FILE", str(tmp_path / "missing.env"))
    run = Mock()
    monkeypatch.setattr(company_ci.subprocess, "run", run)
    with pytest.raises(SystemExit) as error:
        company_ci.main(["--env", "company_test", "--suite", "api"])
    assert error.value.code == 2
    run.assert_not_called()


@pytest.mark.parametrize(
    "arguments",
    [
        ["--env", "demo", "--suite", "api"],
        ["--env", "DEMO", "--suite", "web"],
        ["--env", "../company_test", "--suite", "api"],
        ["--env", "company_test", "--suite", "all"],
        ["--env", "company_test", "--suite", "unit"],
        ["--env", "company_test", "--suite", "api", "--workers", "-1"],
        ["--env", "company_test", "--suite", "app", "--allow-empty"],
    ],
)
def test_invalid_or_bypassing_arguments_are_rejected_before_subprocess(
    company_ci, monkeypatch, arguments
):
    run = Mock()
    monkeypatch.setattr(company_ci.subprocess, "run", run)
    with pytest.raises(SystemExit) as error:
        company_ci.main(arguments)
    assert error.value.code == 2
    run.assert_not_called()


@pytest.mark.parametrize("platform", ["android", "ios"])
@pytest.mark.parametrize("custom_caps", [None, "configs/devices/company lab.yaml"])
def test_app_checks_and_runs_same_device_configuration_serially(
    company_ci, monkeypatch, platform, custom_caps
):
    monkeypatch.setattr(company_ci.sys, "platform", "darwin" if platform == "ios" else "linux")
    run = Mock(return_value=SimpleNamespace(returncode=0))
    monkeypatch.setattr(company_ci.subprocess, "run", run)
    arguments = [
        "--env",
        "company_test",
        "--suite",
        "app",
        "--app-platform",
        platform,
        "--workers",
        "8",
    ]
    if custom_caps:
        arguments += ["--app-caps", custom_caps]

    assert company_ci.main(arguments) == 0

    check, test = [call.args[0] for call in run.call_args_list]
    for command in (check, test):
        assert option(command, "--app-platform") == platform
        assert option(command, "--app-caps") == (custom_caps or f"configs/devices/{platform}.yaml")
    assert "--run-app" not in check
    assert "--run-app" in test
    assert option(test, "-n") == "0"


@pytest.mark.parametrize("host", ["linux", "win32"])
def test_ios_requires_mac_device_node_before_any_subprocess(company_ci, monkeypatch, host):
    monkeypatch.setattr(company_ci.sys, "platform", host)
    run = Mock()
    monkeypatch.setattr(company_ci.subprocess, "run", run)
    with pytest.raises(SystemExit) as error:
        company_ci.main(["--env", "company_test", "--suite", "app", "--app-platform", "ios"])
    assert error.value.code == 2
    run.assert_not_called()
