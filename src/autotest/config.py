"""集中管理配置：命令行环境名 > 系统环境变量 > .env > YAML > 默认值。

配置只是数据，不包含启动浏览器等副作用。单测可独立验证配置错误。
"""

import json
import math
import os
import re
import ssl
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import certifi
import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, field_validator


class Settings(BaseModel):
    """Pydantic 会把环境变量字符串转换为正确类型，并尽早报告错误。"""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    env: str = "demo"
    api_base_url: str | None = None
    web_base_url: str | None = None
    api_token: str | None = Field(default=None, repr=False)
    api_auth_file: str = ""  # 可选角色配置；未配置时保留原有 api_client / API_TOKEN 用法。
    api_ca_bundle: str = ""  # 默认可信根之外，公司 CA 的 PEM 文件；不关闭 TLS 校验。
    api_trust_env: bool = False  # 显式允许 HTTPX 使用环境代理和 SSL_CERT_FILE / SSL_CERT_DIR。
    timeout_seconds: float = Field(default=20, gt=0, le=300)
    web_timeout_ms: int = Field(default=10000, gt=0, le=300000)
    web_storage_state: str = ""  # 本地 Playwright 登录态，包含凭据，不能提交。
    appium_server_url: str = "http://127.0.0.1:4723"
    app_platform: str = "android"
    app_caps_file: str = ""
    app_wait_seconds: float = Field(default=15, gt=0, le=300)
    artemis_base_url: str | None = None
    artemis_token: str | None = Field(default=None, repr=False)
    artemis_device_serial: str | None = None
    artemis_profile: Literal["flash", "pro"] = "flash"
    artemis_timeout_seconds: float = Field(default=600, gt=0, le=7200)

    @field_validator("api_base_url", "web_base_url", "appium_server_url")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("地址必须是完整的 http:// 或 https:// URL")
        _ = parsed.port  # 非数字端口或越界端口会在这里明确报错。
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("基础地址不能包含账号密码、查询参数或 #fragment")
        return value.rstrip("/")

    @field_validator("app_platform")
    @classmethod
    def validate_platform(cls, value: str) -> str:
        if value.lower() not in {"android", "ios"}:
            raise ValueError("APP_PLATFORM 只支持 android 或 ios")
        return value.lower()

    @field_validator("artemis_base_url")
    @classmethod
    def validate_artemis_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("ARTEMIS_BASE_URL 必须是完整 HTTP(S) URL")
        _ = parsed.port
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("ARTEMIS_BASE_URL 不能包含凭据、查询参数或片段")
        loopback = parsed.hostname.lower() in {"127.0.0.1", "localhost", "::1"}
        if parsed.scheme == "http" and not loopback:
            raise ValueError("远程 ARTEMIS 必须使用 HTTPS；无认证服务请通过 SSH 隧道连接 localhost")
        return value.rstrip("/")


def build_api_ssl_context(ca_bundle: str) -> ssl.SSLContext | bool:
    """保留 HTTPX 默认可信根，追加公司 CA；无配置时保留 HTTPX 原生验证行为。

    此配置只影响 API，浏览器 HTTPS 仍使用浏览器/系统的信任库。
    显式 CA 配置优先于 API_TRUST_ENV 开启后的 SSL_CERT_FILE / SSL_CERT_DIR。
    """
    if not ca_bundle:
        return True
    try:
        context = ssl.create_default_context(cafile=certifi.where())
        context.load_verify_locations(cafile=ca_bundle)
    except (OSError, ValueError):
        raise ValueError("API_CA_BUNDLE 必须指向存在、可读取的 PEM CA 证书文件") from None
    return context


def load_web_storage_state(path: str) -> dict:
    """在创建浏览器上下文前校验登录态文件，错误不带出 Cookie/Token 内容。

    只检查 Playwright 状态的必要结构，保留 IndexedDB 等可选扩展字段。
    登录态有效期和实际权限仍需业务用例验证。
    """
    try:
        state = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        raise ValueError(
            "WEB_STORAGE_STATE 必须指向存在、可读取的 Playwright JSON 登录态文件"
        ) from None
    if not _valid_storage_state(state):
        raise ValueError(
            "WEB_STORAGE_STATE 格式无效，需要 Playwright storage_state 的 cookies/origins"
        )
    return state


def _valid_storage_state(state: object) -> bool:
    if not isinstance(state, dict):
        return False
    cookies, origins = state.get("cookies"), state.get("origins")
    if not isinstance(cookies, list) or not isinstance(origins, list):
        return False
    for cookie in cookies:
        if not isinstance(cookie, dict):
            return False
        if any(not isinstance(cookie.get(key), str) for key in ("name", "value", "domain", "path")):
            return False
        expires = cookie.get("expires")
        if type(expires) not in {int, float} or (
            isinstance(expires, float) and not math.isfinite(expires)
        ):
            return False
        if any(not isinstance(cookie.get(key), bool) for key in ("httpOnly", "secure")):
            return False
        if cookie.get("sameSite") not in ("Strict", "Lax", "None"):
            return False
    for origin in origins:
        if not isinstance(origin, dict) or not isinstance(origin.get("origin"), str):
            return False
        storage = origin.get("localStorage")
        if not isinstance(storage, list):
            return False
        if any(
            not isinstance(item, dict)
            or any(not isinstance(item.get(key), str) for key in ("name", "value"))
            for item in storage
        ):
            return False
        if "indexedDB" in origin and not isinstance(origin["indexedDB"], list):
            return False
    return True


def load_settings(
    env_name: str | None = None,
    config_dir: str | Path = "configs/environments",
    dotenv_path: str | Path | None = ".env",
) -> Settings:
    """读取一个环境，保留系统/CI 注入的变量；拼错的配置字段直接报错。"""
    if dotenv_path is not None:
        load_dotenv(dotenv_path, override=False)
    name = env_name or os.getenv("TEST_ENV", "demo")
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", name):
        raise ValueError("环境名只能包含字母、数字、下划线和短横线")
    path = Path(config_dir) / f"{name}.yaml"
    if not path.is_file():
        raise ValueError(f"环境配置不存在：{path}；复制 test.yaml 新建你的环境")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"环境文件不是有效 YAML：{path}") from exc
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} 必须是 YAML 键值对象")
    data["env"] = name
    for field in Settings.model_fields:
        if field != "env" and field.upper() in os.environ:
            data[field] = os.environ[field.upper()]
    return Settings.model_validate(data)
