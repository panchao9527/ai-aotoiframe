"""项目角色鉴权：配置引用环境变量，不在 YAML、日志和 repr 中保存凭据。

每个用例单独创建客户端，各角色 Cookie/Token 隔离。JSON 登录只在初始化执行一次，
收到 401 后不自动重放业务请求，避免把非幂等操作重复提交。SSO/签名协议可在项目
fixture 内扩展，不把业务协议变成通用执行脚本。
"""

import os
import re
from pathlib import Path
from typing import Literal

import httpx
import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from autotest.api.client import ApiClient


class RoleAuth(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    mode: Literal["none", "bearer", "login"] = "none"
    token_env: str | None = None
    login_path: str | None = None
    credentials_env: dict[str, str] = Field(default_factory=dict)
    token_field: str = "token"  # 嵌套响应可使用 data.accessToken。
    expected_status: int = Field(default=200, ge=200, le=299)
    success_fields: dict[str, str | int | bool | None] = Field(default_factory=dict)
    headers_env: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_mode(self):
        if self.mode == "bearer" and not self.token_env:
            raise ValueError("bearer 角色必须配置 token_env")
        if self.mode == "login" and (not self.login_path or not self.credentials_env):
            raise ValueError("login 角色必须配置 login_path 和 credentials_env")
        if self.mode != "login" and (
            self.login_path or self.credentials_env or self.success_fields
        ):
            raise ValueError("只有 login 模式能配置登录参数")
        if self.mode != "bearer" and self.token_env:
            raise ValueError("只有 bearer 模式能配置 token_env")
        if self.login_path:
            # 复用客户端的相对路径边界，防止把凭据发送到外部域名。
            from urllib.parse import urlsplit

            parsed = urlsplit(self.login_path)
            if parsed.scheme or parsed.netloc or "\\" in self.login_path:
                raise ValueError("login_path 必须是相对路径")
            if parsed.query or parsed.fragment:
                raise ValueError("login_path 不能包含查询参数或片段")
        names = [*self.credentials_env.values(), *self.headers_env.values()]
        if self.token_env:
            names.append(self.token_env)
        if any(not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", name) for name in names):
            raise ValueError("凭据配置只允许引用环境变量名称")
        for header in self.headers_env:
            if not re.fullmatch(r"[A-Za-z0-9-]+", header):
                raise ValueError("请求头名称无效")
            if header.lower() in {"authorization", "cookie", "host", "content-length"}:
                raise ValueError("鉴权或传输请求头不能通过 headers_env 覆盖")
        return self


class AuthProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    default_role: str = "default"
    roles: dict[str, RoleAuth]

    @model_validator(mode="after")
    def validate_roles(self):
        if self.default_role not in self.roles:
            raise ValueError("default_role 必须对应一个已配置角色")
        if any(not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", name) for name in self.roles):
            raise ValueError("角色名只允许英文、数字、下划线和短横线")
        return self


def load_profile(path: str | Path) -> AuthProfile:
    try:
        value = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return AuthProfile.model_validate(value)
    except (yaml.YAMLError, ValueError):
        # 不回显 YAML 内容，即使用户误把明文凭据放进去。
        raise ValueError("鉴权配置无效，请检查角色、模式和环境变量引用") from None


def resolve_role(profile: AuthProfile, role: str | None = None) -> tuple[RoleAuth, dict, dict]:
    """预检和实际执行共用解析，缺失变量时在任何 HTTP 请求之前失败。"""
    name = role or profile.default_role
    if name not in profile.roles:
        raise ValueError(f"未配置鉴权角色：{name}")
    config = profile.roles[name]
    names = set(config.credentials_env.values()) | set(config.headers_env.values())
    if config.token_env:
        names.add(config.token_env)
    missing = sorted(name for name in names if not os.getenv(name, "").strip())
    if missing:
        raise ValueError("缺少环境变量：" + ", ".join(missing))
    credentials = {key: os.environ[var] for key, var in config.credentials_env.items()}
    headers = {key: os.environ[var] for key, var in config.headers_env.items()}
    for value in headers.values():
        _check_header_value(value)
    if config.token_env:
        _check_header_value(os.environ[config.token_env])
    return config, credentials, headers


def _check_header_value(value: str) -> None:
    """配置预检即发现不可编码/含换行的凭据，异常不回显实际 Header 值。"""
    if not value.isascii() or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("请求头或 Token 必须是无控制字符的 ASCII 文本")


def _field(body: object, path: str) -> object:
    for key in path.split("."):
        if not isinstance(body, dict) or key not in body:
            raise ValueError("登录响应缺少配置的字段")
        body = body[key]
    return body


def role_client(
    profile: AuthProfile,
    base_url: str,
    *,
    role: str | None = None,
    timeout: float = 20,
    transport: httpx.BaseTransport | None = None,
) -> ApiClient:
    """返回已鉴权的独立客户端；调用者负责关闭，fixture 会自动管理生命周期。"""
    config, credentials, headers = resolve_role(profile, role)
    token = os.environ[config.token_env] if config.token_env else None
    client = ApiClient(base_url, token=token, timeout=timeout, transport=transport)
    try:
        client.raw_client.headers.update(headers)
        if config.mode == "login":
            response = client.post(config.login_path, json=credentials)
            if response.status_code != config.expected_status:
                raise ValueError(f"登录失败：HTTP {response.status_code}")
            try:
                body = response.json()
                for path, expected in config.success_fields.items():
                    actual = _field(body, path)
                    if type(actual) is not type(expected) or actual != expected:
                        raise ValueError("登录业务结果与配置不一致")
                token = _field(body, config.token_field)
                if not isinstance(token, str) or not token.strip():
                    raise ValueError("登录 Token 必须是非空字符串")
                _check_header_value(token)
            except (ValueError, TypeError):
                raise ValueError("登录响应未满足 Token/业务字段约定，请检查配置与响应") from None
            # 不混用 Cookie 与 Bearer；负向权限测试不会被残留 Cookie 干扰。
            client.raw_client.cookies.clear()
            client.raw_client.headers["Authorization"] = f"Bearer {token}"
        return client
    except Exception:
        client.close()
        raise
