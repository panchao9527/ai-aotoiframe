"""把 YAML 配置转换成 Appium Options，并明确管理会话的生命周期。

这里不启动 Appium 服务、不安装 SDK、不偷偷寻找设备。开发机或 CI 应先准备好
设备和 Appium Server；这样环境故障不会被当作业务用例通过。
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml
from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.options.ios import XCUITestOptions
from appium.webdriver.client_config import AppiumClientConfig

_ENV_REFERENCE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_AUTOMATION_NAMES = {"android": "UiAutomator2", "ios": "XCUITest"}


class MobileConfigurationError(ValueError):
    """配置不足或平台不匹配；在发起设备连接前给出可操作的错误。"""


def _expand_environment(value: Any, environment: Mapping[str, str]) -> Any:
    """递归替换 ${NAME}；在 YAML 解析后替换，避免路径/密码改变 YAML 结构。"""
    if isinstance(value, str):

        def replace(match: re.Match[str]) -> str:
            name = match.group(1)
            if not environment.get(name):
                raise MobileConfigurationError(f"设备配置需要非空环境变量：{name}")
            return environment[name]

        return _ENV_REFERENCE.sub(replace, value)
    if isinstance(value, list):
        return [_expand_environment(item, environment) for item in value]
    if isinstance(value, dict):
        return {key: _expand_environment(item, environment) for key, item in value.items()}
    return value


def validate_capabilities(capabilities: Mapping[str, Any], platform: str) -> None:
    """验证框架支持的原生 App 配置；不把远端服务器上的 App 路径当成本机路径。"""
    platform = platform.lower()
    if platform not in _AUTOMATION_NAMES:
        raise MobileConfigurationError("App 平台必须是 android 或 ios")
    if str(capabilities.get("platformName", "")).lower() != platform:
        raise MobileConfigurationError("capabilities 的 platformName 与 --app-platform 不一致")
    automation = capabilities.get("appium:automationName", capabilities.get("automationName"))
    if str(automation).lower() != _AUTOMATION_NAMES[platform].lower():
        raise MobileConfigurationError(
            f"{platform} 的 appium:automationName 必须是 {_AUTOMATION_NAMES[platform]}"
        )
    # 已安装 App 可以只提供包名；Android 显式 appActivity 通常更稳定。
    app = capabilities.get("appium:app", capabilities.get("app"))
    identifier_key = "appPackage" if platform == "android" else "bundleId"
    identifier = capabilities.get(f"appium:{identifier_key}", capabilities.get(identifier_key))
    if not (isinstance(app, str) and app.strip()) and not (
        isinstance(identifier, str) and identifier.strip()
    ):
        raise MobileConfigurationError(
            f"设备配置必须提供 appium:app 或预装 App 的 appium:{identifier_key}"
        )


def load_capabilities(
    path: str | Path, platform: str, *, environment: Mapping[str, str] | None = None
) -> dict[str, Any]:
    """读取一个平铺的 capabilities YAML。环境变量通常由项目的 .env 加载器提供。"""
    if not str(path).strip():
        raise MobileConfigurationError("请通过 --app-caps 或 APP_CAPS_FILE 指定设备 YAML")
    try:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise MobileConfigurationError(f"无法读取设备配置文件：{path}") from exc
    except yaml.YAMLError as exc:
        raise MobileConfigurationError(f"设备配置不是有效 YAML：{path}") from exc
    if not isinstance(raw, dict) or not raw or not all(isinstance(key, str) for key in raw):
        raise MobileConfigurationError("设备 YAML 顶层必须是非空的 capabilities 键值映射")
    capabilities = _expand_environment(raw, os.environ if environment is None else environment)
    validate_capabilities(capabilities, platform)
    return capabilities


def create_driver(
    server_url: str,
    platform: str,
    capabilities: Mapping[str, Any],
    *,
    command_timeout: float = 120,
) -> webdriver.Remote:
    """创建真实 Appium 会话。HTTP 超时与页面显式等待是两种不同的超时。

    Appium 2/3 默认服务根路径为 /，所以地址通常为 http://127.0.0.1:4723。
    使用厂商云设备时可以显式传厂商要求的完整路径；框架不会改写它。
    """
    parsed = urlsplit(server_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise MobileConfigurationError("请提供有效的 --appium-url，例如 http://127.0.0.1:4723")
    if command_timeout <= 0:
        raise MobileConfigurationError("Appium HTTP command_timeout 必须大于 0 秒")
    validate_capabilities(capabilities, platform)
    options_type = UiAutomator2Options if platform.lower() == "android" else XCUITestOptions
    options = options_type().load_capabilities(dict(capabilities))
    client_config = AppiumClientConfig(remote_server_addr=server_url, timeout=command_timeout)
    driver = webdriver.Remote(options=options, client_config=client_config)
    try:
        # 不混用隐式与显式等待，否则实际等待时间容易超出预期。
        driver.implicitly_wait(0)
    except BaseException:
        driver.quit()
        raise
    return driver


@contextmanager
def driver_session(
    server_url: str, platform: str, capabilities: Mapping[str, Any]
) -> Iterator[webdriver.Remote]:
    """无论断言成功或失败，都退出会话，避免下个用例占用到遗留会话。"""
    driver = create_driver(server_url, platform, capabilities)
    try:
        yield driver
    finally:
        driver.quit()
