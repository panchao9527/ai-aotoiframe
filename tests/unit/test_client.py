"""HTTPX MockTransport 验证网络封装，不连接第三方服务。"""

import httpx
import pytest

from autotest.api.client import ApiClient

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
