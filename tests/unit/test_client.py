"""HTTPX MockTransport 验证网络封装，不连接第三方服务。"""

import certifi
import httpx
import pytest

from autotest.api.client import ApiClient
from autotest.config import Settings
from autotest.pytest_plugin import api_client

pytestmark = pytest.mark.unit


def test_auth_base_path_and_no_automatic_retry():
    received = []

    def handler(request):
        received.append(request)
        return httpx.Response(503, json={"error": "temporary"})

    with ApiClient(
        "https://example.test/v2", token="test-key", transport=httpx.MockTransport(handler)
    ) as client:
        response = client.post("/items", json={"name": "one"})
        assert response.status_code == 503
    assert len(received) == 1, "POST 不应自动重试，否则可能创建重复数据"
    assert str(received[0].url) == "https://example.test/v2/items"
    assert received[0].headers["Authorization"] == "Bearer test-key"
    assert client.raw_client.is_closed


@pytest.mark.parametrize("path", ["https://evil.test/", "//evil.test/a", "\\evil.test"])
def test_absolute_paths_do_not_send_token_to_other_host(path):
    def handler(request):
        pytest.fail("非法 URL 不应该触发网络请求")

    with ApiClient("https://example.test", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="相对路径"):
            client.get(path)


def test_redirects_are_not_followed_by_default():
    urls = []

    def handler(request):
        urls.append(str(request.url))
        return httpx.Response(302, headers={"Location": "https://another.test/"})

    with ApiClient("https://example.test", transport=httpx.MockTransport(handler)) as client:
        assert client.get("/start").status_code == 302
    assert len(urls) == 1


def test_client_closes_on_assertion_failure():
    with pytest.raises(AssertionError), ApiClient("https://example.test") as client:
        raise AssertionError("模拟业务断言失败")
    assert client.raw_client.is_closed


def test_environment_ca_is_only_used_when_explicitly_enabled(tmp_path, monkeypatch):
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"):
        monkeypatch.delenv(key, raising=False)
        monkeypatch.delenv(key.lower(), raising=False)
    monkeypatch.setenv("SSL_CERT_FILE", str(tmp_path / "missing.pem"))
    with ApiClient("https://example.test"):
        pass
    with pytest.raises(OSError):
        ApiClient("https://example.test", trust_env=True)
    # 显式公司 CA 优先于 HTTPX 环境 CA，证书校验仍启用。
    with ApiClient("https://example.test", ca_bundle=certifi.where(), trust_env=True):
        pass


def test_invalid_company_ca_fails_before_any_request(tmp_path):
    def handle(request):
        pytest.fail("CA 不存在时不能请求公司接口")

    with pytest.raises(ValueError, match="API_CA_BUNDLE"):
        ApiClient(
            "https://example.test",
            ca_bundle=str(tmp_path / "missing.pem"),
            transport=httpx.MockTransport(handle),
        )


def test_api_fixture_applies_company_ca_setting(tmp_path):
    settings = Settings(api_ca_bundle=str(tmp_path / "missing.pem"))
    fixture = api_client.__wrapped__(settings, "https://api.internal")
    with pytest.raises(ValueError, match="API_CA_BUNDLE"):
        next(fixture)
