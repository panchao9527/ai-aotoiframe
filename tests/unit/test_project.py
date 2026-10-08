"""公司接入预检必须按套件检查，且离线、不输出配置中的凭据。"""

import json
import os
import sys
from types import ModuleType

import httpx
import pytest
import yaml

from autotest import project
from autotest.config import Settings

pytestmark = pytest.mark.unit


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(os, "environ", dict(os.environ))
    for key in Settings.model_fields:
        monkeypatch.delenv(key.upper(), raising=False)

    def no_connection(*args, **kwargs):
        pytest.fail("project check 必须完全离线，不得创建网络或设备会话")

    monkeypatch.setattr(httpx.Client, "request", no_connection)
    monkeypatch.setattr("autotest.mobile.driver.create_driver", no_connection)
    return tmp_path


def write_environment(workspace, **values):
    (workspace / "company.yaml").write_text(yaml.safe_dump(values), encoding="utf-8")


def check(workspace, *arguments):
    return project.main(["check", "--env", "company", "--config-dir", str(workspace), *arguments])


def write_device(workspace, **overrides):
    capabilities = {
        "platformName": "Android",
        "appium:automationName": "UiAutomator2",
        "appium:app": "/remote/builds/company.apk",
        "appium:udid": "controlled-test-device",
        **overrides,
    }
    path = workspace / "device.yaml"
    path.write_text(yaml.safe_dump(capabilities), encoding="utf-8")
    return path


def test_default_api_does_not_require_web_or_device(workspace, capsys):
    write_environment(workspace, api_base_url="https://api.internal")
    assert check(workspace) == 0
    output = capsys.readouterr().out
    assert "API 配置预检通过" in output
    assert "Web" not in output and "App" not in output
    assert "未启用鉴权" in output and "未验证网络" in output


def test_web_does_not_require_api_credentials_or_app(workspace, capsys):
    write_environment(workspace, web_base_url="http://portal.internal", api_auth_file="absent.yaml")
    assert check(workspace, "--suite", "web") == 0
    assert "WEB_STORAGE_STATE" in capsys.readouterr().out


def test_app_does_not_require_api_or_web_and_overrides_platform_and_caps(workspace):
    device = write_device(workspace)
    write_environment(workspace, app_platform="ios", app_caps_file="absent.yaml")
    assert (
        check(workspace, "--suite", "app", "--app-platform", "android", "--app-caps", str(device))
        == 0
    )


@pytest.mark.parametrize(("suite", "field"), [("api", "API_BASE_URL"), ("web", "WEB_BASE_URL")])
def test_missing_selected_address_fails_without_demo_fallback(workspace, capsys, suite, field):
    write_environment(workspace)
    assert check(workspace, "--suite", suite) == 1
    assert field in capsys.readouterr().out


def test_all_collects_every_suite_failure(workspace, capsys):
    write_environment(workspace)
    assert check(workspace, "--suite", "all") == 1
    output = capsys.readouterr().out
    assert "API_BASE_URL" in output and "WEB_BASE_URL" in output and "APP_CAPS_FILE" in output
    assert "0 项通过，3 项失败" in output


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "https://api.test.example.com",
        "https://EXAMPLE.ORG.:443/v1",
        "https://example.net",
        "https://api.example",
        "https://test.invalid",
        "https://example.invalid",
    ],
)
@pytest.mark.parametrize("suite", ["api", "web"])
def test_documentation_addresses_cannot_pass_company_preflight(workspace, capsys, suite, url):
    write_environment(workspace, **{f"{suite}_base_url": url})
    assert check(workspace, "--suite", suite) == 1
    assert "占位地址" in capsys.readouterr().out


@pytest.mark.parametrize("url", ["http://127.0.0.1:8080", "https://api.internal", "http://qa-host"])
def test_local_and_internal_company_addresses_remain_supported(workspace, url):
    write_environment(workspace, api_base_url=url)
    assert check(workspace) == 0


def test_demo_can_use_automatic_local_server_without_starting_it(workspace, capsys):
    (workspace / "demo.yaml").write_text("{}", encoding="utf-8")
    assert project.main(["check", "--env", "demo", "--config-dir", str(workspace)]) == 0
    assert "未验证网络" in capsys.readouterr().out


def test_explicit_role_selects_only_requested_credentials(workspace, monkeypatch, capsys):
    auth = workspace / "roles.yaml"
    auth.write_text(
        "default_role: admin\nroles:\n  admin:\n    mode: bearer\n"
        "    token_env: PREFLIGHT_ADMIN_TOKEN\n  anonymous:\n    mode: none\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("PREFLIGHT_ADMIN_TOKEN", raising=False)
    write_environment(workspace, api_base_url="https://api.internal", api_auth_file=str(auth))
    assert check(workspace, "--role", "anonymous") == 0
    assert check(workspace) == 1
    output = capsys.readouterr().out
    assert "PREFLIGHT_ADMIN_TOKEN" in output and "API 角色 anonymous" in output


def test_role_without_api_profile_or_wrong_suite_is_actionable(workspace, capsys):
    write_environment(
        workspace, api_base_url="https://api.internal", web_base_url="https://web.internal"
    )
    assert check(workspace, "--role", "admin") == 1
    assert "API_AUTH_FILE" in capsys.readouterr().out
    assert check(workspace, "--suite", "web", "--role", "admin") == 1
    assert "--suite api 或 all" in capsys.readouterr().out


def test_token_is_checked_but_never_printed(workspace, capsys):
    secret = "unlabelled-preflight-secret"
    write_environment(workspace, api_base_url="https://api.internal", api_token=secret)
    assert check(workspace) == 0
    write_environment(workspace, api_base_url="https://api.internal", api_token=secret + "\n")
    assert check(workspace) == 1
    output = capsys.readouterr().out
    assert secret not in output
    assert "API_TOKEN" in output


def test_invalid_settings_and_profile_do_not_echo_inline_secrets(workspace, capsys):
    secret = "unlabelled-preflight-secret"
    write_environment(workspace, api_base_url=f"https://user:{secret}@api.internal")
    assert check(workspace) == 1
    auth = workspace / "auth.yaml"
    auth.write_text(f"password: {secret}", encoding="utf-8")
    write_environment(workspace, api_base_url="https://api.internal", api_auth_file=str(auth))
    assert check(workspace) == 1
    assert secret not in capsys.readouterr().out


def test_web_state_is_validated_only_when_web_is_selected(workspace, capsys):
    secret = "unlabelled-cookie-secret"
    state = workspace / "state.json"
    state.write_text(secret, encoding="utf-8")
    write_environment(
        workspace,
        api_base_url="https://api.internal",
        web_base_url="https://web.internal",
        web_storage_state=str(state),
    )
    assert check(workspace, "--suite", "api") == 0
    assert check(workspace, "--suite", "web") == 1
    state.write_text(
        json.dumps(
            {
                "cookies": [
                    {
                        "name": "session",
                        "value": secret,
                        "domain": "web.internal",
                        "path": "/",
                        "expires": -1,
                        "httpOnly": True,
                        "secure": True,
                        "sameSite": "Lax",
                    }
                ],
                "origins": [],
            }
        ),
        encoding="utf-8",
    )
    assert check(workspace, "--suite", "web") == 0
    assert secret not in capsys.readouterr().out


def test_api_ca_is_validated_only_for_api(workspace, capsys):
    write_environment(
        workspace,
        api_base_url="https://api.internal",
        web_base_url="https://web.internal",
        api_ca_bundle="missing-ca.pem",
    )
    assert check(workspace, "--suite", "web") == 0
    assert check(workspace, "--suite", "api") == 1
    assert "API_CA_BUNDLE" in capsys.readouterr().out


@pytest.mark.parametrize(
    "proxy", ["wrong://user:{secret}@proxy.internal", "http://user:{secret}@proxy.internal:bad"]
)
def test_environment_proxy_errors_do_not_expose_credentials(workspace, monkeypatch, capsys, proxy):
    secret = "unlabelled-proxy-secret"
    monkeypatch.setenv("HTTP_PROXY", proxy.format(secret=secret))
    write_environment(workspace, api_base_url="https://api.internal", api_trust_env=True)
    assert check(workspace) == 1
    output = capsys.readouterr().out
    assert "API_TRUST_ENV" in output and secret not in output


def test_app_configuration_requires_explicit_device_and_matching_platform(workspace, capsys):
    device = write_device(workspace, **{"appium:udid": ""})
    write_environment(workspace, app_caps_file=str(device))
    assert check(workspace, "--suite", "app") == 1
    assert "appium:udid" in capsys.readouterr().out
    write_device(workspace, **{"appium:udid": "auto"})
    assert check(workspace, "--suite", "app") == 1
    assert "auto" in capsys.readouterr().out
    write_device(workspace)
    assert check(workspace, "--suite", "app", "--app-platform", "ios") == 1
    assert "platformName" in capsys.readouterr().out


def test_android_named_avd_and_preinstalled_package_are_supported(workspace):
    device = write_device(
        workspace,
        **{
            "appium:udid": "",
            "appium:avd": "Company_AVD",
            "appium:app": "",
            "appium:appPackage": "com.company.test",
        },
    )
    write_environment(workspace, app_caps_file=str(device))
    assert check(workspace, "--suite", "app") == 0


def test_ios_simulator_selection_and_preinstalled_bundle_are_supported(workspace, capsys):
    device = write_device(
        workspace,
        **{
            "platformName": "iOS",
            "appium:automationName": "XCUITest",
            "appium:udid": "",
            "appium:deviceName": "iPhone Test Simulator",
            "appium:platformVersion": "18.0",
            "appium:app": "",
            "appium:bundleId": "com.company.test",
        },
    )
    write_environment(workspace, app_platform="ios", app_caps_file=str(device))
    assert check(workspace, "--suite", "app") == 0
    assert "真机必须配置 appium:udid" in capsys.readouterr().out


@pytest.mark.parametrize("target", ["server", "app"])
def test_app_placeholder_urls_are_rejected_without_echoing_signed_urls(workspace, capsys, target):
    secret = "unlabelled-download-secret"
    device = write_device(workspace)
    values = {"app_caps_file": str(device)}
    if target == "server":
        values["appium_server_url"] = "https://appium.example.com"
    else:
        write_device(
            workspace, **{"appium:app": f"https://build.example.com/app.apk?signature={secret}"}
        )
    write_environment(workspace, **values)
    assert check(workspace, "--suite", "app") == 1
    output = capsys.readouterr().out
    assert "占位地址" in output and secret not in output


def test_app_reports_missing_environment_without_echoing_capabilities(
    workspace, monkeypatch, capsys
):
    secret = "unlabelled-device-secret"
    device = write_device(
        workspace, **{"appium:udid": "${PREFLIGHT_DEVICE_ID}", "vendor:key": secret}
    )
    monkeypatch.delenv("PREFLIGHT_DEVICE_ID", raising=False)
    write_environment(workspace, app_caps_file=str(device))
    assert check(workspace, "--suite", "app") == 1
    output = capsys.readouterr().out
    assert "PREFLIGHT_DEVICE_ID" in output and secret not in output


def test_remote_signed_app_url_and_vendor_capabilities_are_not_printed(workspace, capsys):
    secret = "unlabelled-device-secret"
    device = write_device(
        workspace,
        **{
            "appium:app": f"https://builds.internal/test.apk?signature={secret}",
            "vendor:options": {"key": secret},
        },
    )
    write_environment(workspace, app_caps_file=str(device))
    assert check(workspace, "--suite", "app") == 0
    assert secret not in capsys.readouterr().out


def test_all_success_is_only_a_configuration_claim(workspace, capsys):
    device = write_device(workspace)
    write_environment(
        workspace,
        api_base_url="https://api.internal",
        web_base_url="https://web.internal",
        app_caps_file=str(device),
    )
    assert check(workspace, "--suite", "all") == 0
    output = capsys.readouterr().out
    assert "3 项通过，0 项失败" in output
    assert "未验证网络连通性、账号有效性、业务权限或真实设备运行" in output


def test_init_dispatches_name_and_output_without_requiring_environment(
    workspace, monkeypatch, capsys
):
    calls = []
    fake = ModuleType("autotest.scaffold")

    def create(name, output):
        calls.append((name, output))
        return workspace / "new-project"

    fake.init_project = create
    monkeypatch.setitem(sys.modules, "autotest.scaffold", fake)
    assert project.main(["init", "--name", "company-qa", "--output", "new-project"]) == 0
    assert calls == [("company-qa", "new-project")]
    assert "已创建独立测试项目" in capsys.readouterr().out


def test_init_failure_returns_nonzero(workspace, monkeypatch, capsys):
    fake = ModuleType("autotest.scaffold")

    def create(name, output):
        raise ValueError("输出目录已存在，不会覆盖")

    fake.init_project = create
    monkeypatch.setitem(sys.modules, "autotest.scaffold", fake)
    assert project.main(["init", "--name", "company-qa", "--output", "new-project"]) == 1
    assert "不会覆盖" in capsys.readouterr().out
