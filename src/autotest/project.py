"""项目初始化与离线接入预检；不登录、不连接设备，也不输出凭据值。"""

import argparse
import re
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError

from autotest.api.auth import load_profile, resolve_role
from autotest.config import (
    Settings,
    build_api_ssl_context,
    load_settings,
    load_web_storage_state,
)
from autotest.mobile.driver import load_capabilities
from autotest.redaction import redact_text


def _reject_placeholder_url(value: str, field: str) -> None:
    """保留内网/localhost 地址；仅拒绝文档保留域名，不能用 DNS 判断公司地址。"""
    hostname = (urlsplit(value).hostname or "").lower().rstrip(".")
    reserved = ("example.com", "example.net", "example.org", "example", "invalid")
    if any(hostname == domain or hostname.endswith("." + domain) for domain in reserved):
        raise ValueError(f"{field} 仍为示例占位地址，请填写公司测试环境的真实地址")


def _require_base_url(settings: Settings, suite: str) -> None:
    value = getattr(settings, f"{suite}_base_url")
    field = f"{suite.upper()}_BASE_URL / {suite}_base_url"
    if not value:
        if settings.env == "demo":
            return  # demo fixture 会启动本地练习系统；公司环境绝不回退。
        raise ValueError(f"缺少 {field}")
    _reject_placeholder_url(value, field)


def _check_api(settings: Settings, args: argparse.Namespace) -> None:
    _require_base_url(settings, "api")
    verify = build_api_ssl_context(settings.api_ca_bundle)
    if settings.api_trust_env:
        try:
            # 只构造/关闭客户端来解析代理和环境 CA，不发出任何请求。
            with httpx.Client(verify=verify, trust_env=True):
                pass
        except (OSError, ValueError, ImportError, httpx.InvalidURL):
            raise ValueError(
                "API_TRUST_ENV 配置无法加载，请检查代理、SSL_CERT_FILE/SSL_CERT_DIR 和依赖"
            ) from None
    if settings.api_auth_file:
        profile = load_profile(settings.api_auth_file)
        for name in args.role or sorted(profile.roles):
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", name):
                raise ValueError("角色名只允许英文开头，包含英文、数字、下划线和短横线")
            resolve_role(profile, name)
            print(f"[OK] API 角色 {name} 的配置和环境变量齐全")
    elif args.role:
        raise ValueError("指定角色前需要配置 api_auth_file / API_AUTH_FILE")
    elif settings.api_token:
        if not settings.api_token.isascii() or any(
            ord(char) < 32 or ord(char) == 127 for char in settings.api_token
        ):
            raise ValueError("API_TOKEN 必须是无控制字符的 ASCII 文本")
        print("[OK] API_TOKEN 已配置；有效性需执行真实接口用例验证")
    else:
        print(
            "[提示] API 未启用鉴权；公开接口可直接使用，其他接口需配置 API_AUTH_FILE 或 API_TOKEN"
        )


def _check_web(settings: Settings, args: argparse.Namespace) -> None:
    _require_base_url(settings, "web")
    if settings.web_storage_state:
        load_web_storage_state(settings.web_storage_state)
        print("[OK] Web 登录态文件格式有效；登录是否过期需执行真实页面用例验证")
    else:
        print("[提示] Web 未配置 WEB_STORAGE_STATE；可测试公开页面或在项目 fixture 中登录")


def _capability(capabilities: dict, name: str) -> str:
    value = capabilities.get(f"appium:{name}", capabilities.get(name))
    return value.strip() if isinstance(value, str) else ""


def _check_app(settings: Settings, args: argparse.Namespace) -> None:
    _reject_placeholder_url(settings.appium_server_url, "APPIUM_SERVER_URL / appium_server_url")
    platform = args.app_platform or settings.app_platform
    path = args.app_caps or settings.app_caps_file
    if not path:
        raise ValueError("缺少 --app-caps 或 APP_CAPS_FILE / app_caps_file；请指定设备 YAML")
    capabilities = load_capabilities(path, platform)
    udid = _capability(capabilities, "udid")
    if udid.lower() == "auto":
        raise ValueError("appium:udid 不能为 auto；请明确选择测试设备，避免连接其他手机")
    if not udid:
        if platform == "android" and _capability(capabilities, "avd"):
            print("[OK] App 已指定 Android AVD 模拟器")
        elif (
            platform == "ios"
            and _capability(capabilities, "deviceName")
            and _capability(capabilities, "platformVersion")
        ):
            print("[提示] iOS 按 deviceName + platformVersion 选择模拟器；真机必须配置 appium:udid")
        else:
            raise ValueError(
                "缺少明确的设备选择：真机配置 appium:udid；Android 模拟器也可配置 "
                "appium:avd，iOS 模拟器可配置 deviceName + platformVersion"
            )
    app = _capability(capabilities, "app")
    if app.lower().startswith(("http://", "https://")):
        _reject_placeholder_url(app, "appium:app")
    print(f"[OK] App {platform} capabilities 与设备选择配置齐全")
    print("[提示] App 包路径按 Appium 服务端解释；驱动、包、签名和页面定位需在目标设备验证")


def _error_message(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return "环境配置字段或地址格式无效，请按配置示例检查"
    if isinstance(exc, OSError):
        return "无法读取环境、鉴权或登录态文件，请检查路径与权限"
    # 配置解析器隐藏内容，仅保留缺失变量等可操作信息。
    return redact_text(str(exc))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="创建独立测试项目，或离线检查 API / Web / App 配置"
    )
    sub = parser.add_subparsers(dest="action", required=True)
    init = sub.add_parser("init", help="生成可独立使用的 API / Web / App 公司项目")
    init.add_argument("--name", required=True, help="项目名称，使用小写英文、数字和短横线")
    init.add_argument("--output", required=True, help="新项目输出目录；不覆盖已有内容")
    check = sub.add_parser("check", help="离线检查所选套件；不验证网络或真实设备")
    check.add_argument("--env", required=True)
    check.add_argument("--config-dir", default="configs/environments")
    check.add_argument("--suite", choices=["api", "web", "app", "all"], default="api")
    check.add_argument("--role", action="append", help="只检查指定 API 角色，可重复；默认全部角色")
    check.add_argument("--app-platform", choices=["android", "ios"])
    check.add_argument("--app-caps", help="覆盖 APP_CAPS_FILE 的 capabilities YAML 路径")
    args = parser.parse_args(argv)
    if args.action == "init":
        from autotest.scaffold import init_project

        try:
            destination = init_project(args.name, args.output)
        except OSError:
            print("[失败] 无法创建项目目录，请检查输出路径与权限")
            return 1
        except ValueError as exc:
            print("[失败] " + redact_text(str(exc)))
            return 1
        print(f"[OK] 已创建独立测试项目：{destination}")
        print("下一步：进入项目，按 README 配置环境、账号和设备，再执行 project check。")
        return 0
    if args.role and args.suite not in {"api", "all"}:
        print("[失败] --role 仅适用于 --suite api 或 all")
        return 1
    try:
        settings = load_settings(args.env, args.config_dir)
    except (ValueError, OSError) as exc:
        print("[失败] " + _error_message(exc))
        return 1
    suites = ["api", "web", "app"] if args.suite == "all" else [args.suite]
    checks = {"api": _check_api, "web": _check_web, "app": _check_app}
    failures = 0
    for suite in suites:
        try:
            checks[suite](settings, args)
        except (ValueError, OSError) as exc:
            failures += 1
            print(f"[失败] {suite.upper()}：{_error_message(exc)}")
        else:
            print(f"[OK] {suite.upper()} 配置预检通过")
    print(f"预检汇总：{len(suites) - failures} 项通过，{failures} 项失败。")
    print("仅检查离线配置；未验证网络连通性、账号有效性、业务权限或真实设备运行。")
    return 1 if failures else 0
