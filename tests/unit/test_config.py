"""验证优先级和错误输入，防止接入新项目时悄悄测错环境。"""

import os
import ssl

import certifi
import pytest
from pydantic import ValidationError

from autotest.config import Settings, build_api_ssl_context, load_settings

pytestmark = pytest.mark.unit


@pytest.fixture
def clean_env(monkeypatch):
    # load_dotenv 会写 os.environ；隔离整个映射，避免前一个单测影响下一个。
    monkeypatch.setattr(os, "environ", dict(os.environ))
    for key in Settings.model_fields:
        monkeypatch.delenv(key.upper(), raising=False)
    monkeypatch.delenv("TEST_ENV", raising=False)


def test_system_environment_beats_dotenv_and_yaml(tmp_path, monkeypatch, clean_env):
    (tmp_path / "test.yaml").write_text("timeout_seconds: 10\n", encoding="utf-8")
    dotenv = tmp_path / ".env"
    dotenv.write_text("TIMEOUT_SECONDS=11\nWEB_TIMEOUT_MS=12000\n", encoding="utf-8")
    monkeypatch.setenv("TIMEOUT_SECONDS", "12")
    settings = load_settings("test", tmp_path, dotenv)
    assert settings.timeout_seconds == 12
    assert settings.web_timeout_ms == 12000


def test_cli_environment_beats_test_env(tmp_path, monkeypatch, clean_env):
    (tmp_path / "test.yaml").write_text("timeout_seconds: 10", encoding="utf-8")
    monkeypatch.setenv("TEST_ENV", "nonexistent")
    assert load_settings("test", tmp_path, None).env == "test"


@pytest.mark.parametrize("name", ["../test", "a/b", "", "a.yaml"])
def test_invalid_environment_name(tmp_path, name, clean_env):
    with pytest.raises(ValueError):
        load_settings(name, tmp_path, None)


def test_unknown_config_field_fails_fast(tmp_path, clean_env):
    (tmp_path / "test.yaml").write_text("timeot_seconds: 10", encoding="utf-8")
    with pytest.raises(ValidationError, match="timeot_seconds"):
        load_settings("test", tmp_path, None)


def test_malformed_yaml_is_a_friendly_configuration_error(tmp_path, clean_env):
    (tmp_path / "test.yaml").write_text("timeout_seconds: [", encoding="utf-8")
    with pytest.raises(ValueError, match="YAML"):
        load_settings("test", tmp_path, None)


@pytest.mark.parametrize("content", ["[]", "false", "0"])
def test_empty_non_mapping_config_is_not_silently_accepted(tmp_path, clean_env, content):
    (tmp_path / "test.yaml").write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match="键值对象"):
        load_settings("test", tmp_path, None)


@pytest.mark.parametrize(
    "url", ["example.com", "ftp://host", "https://user:pass@host", "https://host?token=x"]
)
def test_invalid_base_url(url):
    with pytest.raises(ValidationError):
        Settings(api_base_url=url)


def test_token_not_in_settings_repr():
    assert "secret-value" not in repr(Settings(api_token="secret-value"))


def test_artemis_token_not_in_settings_repr():
    assert "secret-value" not in repr(Settings(artemis_token="secret-value"))


def test_company_settings_follow_existing_environment_precedence(tmp_path, monkeypatch, clean_env):
    (tmp_path / "test.yaml").write_text(
        "api_ca_bundle: yaml.pem\napi_trust_env: false\nweb_storage_state: yaml.json\n",
        encoding="utf-8",
    )
    dotenv = tmp_path / ".env"
    dotenv.write_text("API_CA_BUNDLE=dotenv.pem\nWEB_STORAGE_STATE=dotenv.json\n", encoding="utf-8")
    monkeypatch.setenv("API_CA_BUNDLE", "company.pem")
    monkeypatch.setenv("API_TRUST_ENV", "true")
    settings = load_settings("test", tmp_path, dotenv)
    assert settings.api_ca_bundle == "company.pem"
    assert settings.web_storage_state == "dotenv.json"
    assert settings.api_trust_env is True
    assert Settings().api_trust_env is False


def test_company_ca_keeps_verification_and_default_roots(monkeypatch, tmp_path):
    # 显式公司 CA 的根集合不会被执行机 SSL_CERT_FILE 悄悄替换。
    monkeypatch.setenv("SSL_CERT_FILE", str(tmp_path / "missing.pem"))
    context = build_api_ssl_context(certifi.where())
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
    default = ssl.create_default_context(cafile=certifi.where())
    assert set(context.get_ca_certs(binary_form=True)) == set(
        default.get_ca_certs(binary_form=True)
    )
    assert build_api_ssl_context("") is True


def test_invalid_ca_file_fails_without_echoing_content(tmp_path):
    path = tmp_path / "company.pem"
    for content in (None, "private-certificate-content"):
        if content is not None:
            path.write_text(content, encoding="utf-8")
        with pytest.raises(ValueError, match="API_CA_BUNDLE") as error:
            build_api_ssl_context(str(path))
        assert "private-certificate-content" not in str(error.value)
