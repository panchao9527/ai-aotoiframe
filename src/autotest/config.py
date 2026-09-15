"""集中管理配置：命令行环境名 > 系统环境变量 > .env > YAML > 默认值。

配置只是数据，不包含启动浏览器等副作用。单测可独立验证配置错误。
"""

import os
import re
from pathlib import Path
from urllib.parse import urlsplit

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
    timeout_seconds: float = Field(default=20, gt=0, le=300)
    web_timeout_ms: int = Field(default=10000, gt=0, le=300000)
    appium_server_url: str = "http://127.0.0.1:4723"
    app_platform: str = "android"
    app_caps_file: str = ""
    app_wait_seconds: float = Field(default=15, gt=0, le=300)

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
