"""pytest 的 App 入口。默认跳过需要设备的用例，显式启用后配置错误即失败。"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from appium.webdriver.webdriver import WebDriver

from autotest.evidence import safe_url
from autotest.mobile.driver import MobileConfigurationError, driver_session, load_capabilities
from autotest.run_logging import emit_event


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("mobile", "Android / iOS Appium 自动化")
    group.addoption("--run-app", action="store_true", default=False, help="启用真实 App 设备测试")
    group.addoption("--app-platform", choices=("android", "ios"), default=None)
    group.addoption("--app-caps", default=None, help="capabilities YAML 文件路径")
    group.addoption("--appium-url", default=None, help="Appium 服务地址，默认根路径为 /")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "app: 需要真实 Appium Server 和 Android/iOS 设备")
    if not config.getoption("run_app"):
        return
    workers = config.getoption("numprocesses", default=0)
    worker_info = getattr(config, "workerinput", {})
    if (
        workers in {"auto", "logical"}
        or (isinstance(workers, int) and workers > 1)
        or (worker_info.get("workercount", 1) > 1)
    ):
        raise pytest.UsageError(
            "App 配置只绑定一台设备，禁止多个 xdist worker 共用。请使用 -n 0，"
            "多设备请用独立 CI job，分别设置 udid、服务地址和驱动端口。"
        )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("run_app"):
        return
    disabled = pytest.mark.skip(reason="App 需要设备：配置 capabilities 后使用 --run-app 启用")
    for item in items:
        if item.get_closest_marker("app"):
            item.add_marker(disabled)


@pytest.fixture
def app_driver(request: pytest.FixtureRequest, settings: Any) -> Iterator[WebDriver]:
    """每个用例建立独立会话；pytest 会在失败后继续执行 finally 中的 quit。

    settings 由公共框架提供；命令行参数优先于 .env/config 中的设置。
    延迟连接保证 API/Web 或单元测试不需要启动 Appium。
    """
    if not request.config.getoption("run_app"):
        pytest.skip("使用 --run-app 并提供设备 capabilities 后运行真实 App 测试")
    platform = request.config.getoption("app_platform") or settings.app_platform
    caps_path = request.config.getoption("app_caps") or settings.app_caps_file
    server_url = request.config.getoption("appium_url") or settings.appium_server_url
    try:
        if not caps_path:
            raise MobileConfigurationError("--run-app 需要 --app-caps 或 APP_CAPS_FILE")
        if not server_url:
            raise MobileConfigurationError("--run-app 需要 --appium-url 或 APPIUM_SERVER_URL")
        capabilities = load_capabilities(caps_path, platform)
    except MobileConfigurationError as exc:
        emit_event("app.configuration", str(exc), level="ERROR", platform=platform)
        pytest.fail(str(exc), pytrace=False)
    # 连接失败保留 Appium 原始错误；不把服务不可达、包安装失败等情况标记为 skip。
    emit_event(
        "app.session.connecting",
        "connecting to Appium",
        platform=platform,
        server=safe_url(server_url),
    )
    connected = False
    try:
        with driver_session(server_url, platform, capabilities) as driver:
            connected = True
            emit_event("app.session.started", "Appium session started", platform=platform)
            yield driver
    except Exception as exc:
        emit_event(
            "app.session.error",
            "Appium session failed",
            level="ERROR",
            platform=platform,
            error_type=type(exc).__name__,
        )
        raise
    finally:
        if connected:
            emit_event("app.session.closed", "Appium session closed", platform=platform)
