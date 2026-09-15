"""在没有手机、Mac 或 Appium Server 的机器上验证 App 框架自身的约定。

只替换网络会话；Options 与 ClientConfig 使用真实 Appium 类，防止 API 用法漂移。
这些单测通过不代表任何 APK/IPA 已在设备上通过业务测试。
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest
from appium.options.android import UiAutomator2Options
from appium.options.ios import XCUITestOptions

from autotest.mobile import driver as mobile_driver
from autotest.mobile import plugin
from autotest.mobile.driver import (
    MobileConfigurationError,
    create_driver,
    driver_session,
    load_capabilities,
)
from autotest.mobile.screens import BaseScreen, LoginScreen

pytestmark = pytest.mark.unit


def android_caps():
    return {
        "platformName": "Android",
        "appium:automationName": "UiAutomator2",
        "appium:app": "/remote-builds/company.apk",
    }


def test_yaml_expands_environment_without_interpreting_its_contents(tmp_path):
    path = tmp_path / "device.yaml"
    path.write_text(
        "platformName: Android\nappium:automationName: UiAutomator2\n"
        'appium:app: "${APP_PATH}"\nappium:noReset: false\n'
        'vendor:options:\n  labels: ["${BUILD_NAME}"]\n',
        encoding="utf-8",
    )
    actual = load_capabilities(
        path,
        "android",
        environment={"APP_PATH": "https://builds.example/app.apk", "BUILD_NAME": "build: #123"},
    )
    assert actual["appium:app"] == "https://builds.example/app.apk"
    assert actual["appium:noReset"] is False
    assert actual["vendor:options"]["labels"] == ["build: #123"]


@pytest.mark.parametrize("environment", [{}, {"APP_PATH": ""}])
def test_yaml_missing_or_empty_environment_is_error(tmp_path, environment):
    path = tmp_path / "device.yaml"
    path.write_text(
        'platformName: Android\nappium:automationName: UiAutomator2\nappium:app: "${APP_PATH}"',
        encoding="utf-8",
    )
    with pytest.raises(MobileConfigurationError, match="APP_PATH"):
        load_capabilities(path, "android", environment=environment)


@pytest.mark.parametrize("yaml_text", ["[]", "{}", "null", "bad: [", "1: value"])
def test_yaml_rejects_malformed_or_wrong_structure(tmp_path, yaml_text):
    path = tmp_path / "invalid.yaml"
    path.write_text(yaml_text, encoding="utf-8")
    with pytest.raises(MobileConfigurationError):
        load_capabilities(path, "android")


def test_yaml_missing_file_gives_configuration_error(tmp_path):
    with pytest.raises(MobileConfigurationError, match="无法读取"):
        load_capabilities(tmp_path / "missing.yaml", "android")


def test_platform_mismatch_is_rejected_before_any_connection():
    with pytest.raises(MobileConfigurationError, match="platformName"):
        create_driver("http://127.0.0.1:4723", "ios", android_caps())


@pytest.mark.parametrize(
    ("platform", "caps", "expected_type"),
    [
        ("android", android_caps(), UiAutomator2Options),
        (
            "ios",
            {
                "platformName": "iOS",
                "appium:automationName": "XCUITest",
                "appium:bundleId": "com.company.app",
            },
            XCUITestOptions,
        ),
    ],
)
def test_create_driver_uses_platform_options_and_client_timeout(
    monkeypatch, platform, caps, expected_type
):
    remote = MagicMock()
    monkeypatch.setattr(mobile_driver.webdriver, "Remote", remote)
    driver = create_driver("http://127.0.0.1:4723", platform, caps, command_timeout=42)
    kwargs = remote.call_args.kwargs
    assert isinstance(kwargs["options"], expected_type)
    assert kwargs["options"].to_capabilities()["platformName"].lower() == platform
    assert kwargs["client_config"].remote_server_addr == "http://127.0.0.1:4723"
    assert kwargs["client_config"].timeout == 42
    driver.implicitly_wait.assert_called_once_with(0)


@pytest.mark.parametrize("server_url", ["", "localhost:4723", "file:///tmp/server"])
def test_driver_rejects_invalid_server_address(server_url):
    with pytest.raises(MobileConfigurationError, match="appium-url"):
        create_driver(server_url, "android", android_caps())


def test_driver_quits_when_initial_setup_fails(monkeypatch):
    remote = MagicMock()
    remote.return_value.implicitly_wait.side_effect = RuntimeError("setup failed")
    monkeypatch.setattr(mobile_driver.webdriver, "Remote", remote)
    with pytest.raises(RuntimeError, match="setup failed"):
        create_driver("http://127.0.0.1:4723", "android", android_caps())
    remote.return_value.quit.assert_called_once_with()


@pytest.mark.parametrize("test_fails", [False, True])
def test_session_quits_on_success_and_assertion_failure(monkeypatch, test_fails):
    driver = MagicMock()
    monkeypatch.setattr(mobile_driver, "create_driver", lambda *args: driver)
    if test_fails:
        with pytest.raises(AssertionError, match="business assertion"):
            with driver_session("http://127.0.0.1:4723", "android", android_caps()):
                raise AssertionError("business assertion")
    else:
        with driver_session("http://127.0.0.1:4723", "android", android_caps()) as actual:
            assert actual is driver
    driver.quit.assert_called_once_with()


@pytest.mark.parametrize("test_fails", [False, True])
def test_webview_restores_native_context_even_on_failure(test_fails):
    driver = MagicMock()
    driver.contexts = ["NATIVE_APP", "WEBVIEW_com.company.app"]
    screen = BaseScreen(driver, timeout=0.01)
    if test_fails:
        with pytest.raises(AssertionError, match="web assertion"):
            with screen.webview():
                raise AssertionError("web assertion")
    else:
        with screen.webview() as actual:
            assert actual is screen
    assert driver.switch_to.context.call_args_list == [
        call("WEBVIEW_com.company.app"),
        call("NATIVE_APP"),
    ]


def test_webview_requires_name_when_multiple_contexts_exist():
    driver = MagicMock()
    driver.contexts = ["NATIVE_APP", "WEBVIEW_checkout", "WEBVIEW_ads"]
    screen = BaseScreen(driver, timeout=0.01)
    with pytest.raises(ValueError, match="多个 WebView"):
        with screen.webview():
            pytest.fail("must not choose a random WebView")
    driver.switch_to.context.assert_not_called()
    with screen.webview("WEBVIEW_checkout"):
        pass
    assert driver.switch_to.context.call_args_list == [call("WEBVIEW_checkout"), call("NATIVE_APP")]


def test_webview_attempts_native_restore_if_switch_fails():
    driver = MagicMock()
    driver.contexts = ["NATIVE_APP", "WEBVIEW_com.company.app"]
    driver.switch_to.context.side_effect = [RuntimeError("switch failed"), None]
    with pytest.raises(RuntimeError, match="switch failed"):
        with BaseScreen(driver, timeout=0.01).webview():
            pytest.fail("switch must succeed before entering the block")
    assert driver.switch_to.context.call_args_list == [
        call("WEBVIEW_com.company.app"),
        call("NATIVE_APP"),
    ]


def test_login_screen_waits_for_visible_fields_and_clickable_button():
    driver = MagicMock()
    username, password, submit = MagicMock(), MagicMock(), MagicMock()
    # Selenium 检查 is_displayed() == True；Mock 必须模拟实际的布尔返回值。
    for element in (username, password, submit):
        element.is_displayed.return_value = True
        element.is_enabled.return_value = True
    driver.find_element.side_effect = [username, password, submit]
    LoginScreen(driver, timeout=0.01).login("test-user", "test-password")
    username.clear.assert_called_once_with()
    username.send_keys.assert_called_once_with("test-user")
    password.clear.assert_called_once_with()
    password.send_keys.assert_called_once_with("test-password")
    submit.is_displayed.assert_called()
    submit.is_enabled.assert_called_once_with()
    submit.click.assert_called_once_with()


def fake_config(**options):
    defaults = {"run_app": True, "app_platform": None, "app_caps": None, "appium_url": None}
    defaults.update(options)
    return SimpleNamespace(
        getoption=lambda name, default=None: defaults.get(name, default),
        addinivalue_line=lambda *args: None,
    )


@pytest.mark.parametrize("workers", [2, 4, "auto", "logical"])
def test_app_disallows_multiple_workers_on_one_device(workers):
    with pytest.raises(pytest.UsageError, match="一台设备"):
        plugin.pytest_configure(fake_config(numprocesses=workers))


def test_worker_side_also_disallows_shared_device():
    config = fake_config(numprocesses=None)
    config.workerinput = {"workercount": 2}
    with pytest.raises(pytest.UsageError):
        plugin.pytest_configure(config)


def test_app_can_run_serially_or_with_one_worker():
    plugin.pytest_configure(fake_config(numprocesses=0))
    plugin.pytest_configure(fake_config(numprocesses=1))
    # 默认未启用 App 时，API/Web 仍可使用多 worker。
    plugin.pytest_configure(fake_config(run_app=False, numprocesses="auto"))


def test_only_app_marked_tests_skip_by_default():
    app_item, api_item = MagicMock(), MagicMock()
    app_item.get_closest_marker.return_value = object()
    api_item.get_closest_marker.return_value = None
    plugin.pytest_collection_modifyitems(fake_config(run_app=False), [app_item, api_item])
    app_item.add_marker.assert_called_once()
    assert app_item.add_marker.call_args.args[0].name == "skip"
    api_item.add_marker.assert_not_called()


@pytest.mark.parametrize(
    ("caps_file", "server_url", "error"),
    [("", "http://127.0.0.1:4723", "app-caps"), ("device.yaml", "", "appium-url")],
)
def test_explicit_app_run_with_missing_config_fails_not_skips(caps_file, server_url, error):
    settings = SimpleNamespace(
        app_platform="android", app_caps_file=caps_file, appium_server_url=server_url
    )
    request = SimpleNamespace(config=fake_config())
    fixture = plugin.app_driver.__wrapped__(request, settings)
    with pytest.raises(pytest.fail.Exception, match=error):
        next(fixture)


def test_app_fixture_does_not_connect_without_run_app():
    request = SimpleNamespace(config=fake_config(run_app=False))
    fixture = plugin.app_driver.__wrapped__(request, SimpleNamespace())
    with pytest.raises(pytest.skip.Exception, match="run-app"):
        next(fixture)


def test_cli_overrides_settings_and_fixture_always_closes_session(monkeypatch):
    driver = MagicMock()
    create = MagicMock(return_value=driver)
    monkeypatch.setattr(mobile_driver, "create_driver", create)
    load = MagicMock(return_value=android_caps())
    monkeypatch.setattr(plugin, "load_capabilities", load)
    settings = SimpleNamespace(
        app_platform="ios", app_caps_file="old.yaml", appium_server_url="http://old:4723"
    )
    request = SimpleNamespace(
        config=fake_config(
            app_platform="android", app_caps="new.yaml", appium_url="http://new:4723"
        )
    )
    fixture = plugin.app_driver.__wrapped__(request, settings)
    assert next(fixture) is driver
    load.assert_called_once_with("new.yaml", "android")
    create.assert_called_once_with("http://new:4723", "android", android_caps())
    fixture.close()
    driver.quit.assert_called_once_with()


def test_explicit_app_run_propagates_connection_failure(monkeypatch):
    create = MagicMock(side_effect=ConnectionError("Appium unreachable"))
    monkeypatch.setattr(mobile_driver, "create_driver", create)
    monkeypatch.setattr(plugin, "load_capabilities", lambda *args: android_caps())
    settings = SimpleNamespace(
        app_platform="android",
        app_caps_file="device.yaml",
        appium_server_url="http://localhost:4723",
    )
    fixture = plugin.app_driver.__wrapped__(SimpleNamespace(config=fake_config()), settings)
    with pytest.raises(ConnectionError, match="Appium unreachable"):
        next(fixture)
