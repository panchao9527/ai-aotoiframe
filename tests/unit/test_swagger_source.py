"""Swagger UI 发现仅通过 MockTransport 读取同源文档，不访问真实业务地址。"""

import json

import httpx
import pytest

from autotest.ai import AIError
from autotest.authoring.context import load_spec

pytestmark = pytest.mark.unit


def _mock_client(monkeypatch, handler):
    original = httpx.Client
    monkeypatch.setattr(
        "autotest.authoring.context.httpx.Client",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )


def _spec(*paths):
    return {
        "swagger": "2.0",
        "info": {"title": "demo", "version": "1"},
        "paths": {path: {"post": {"responses": {"200": {"description": "ok"}}}} for path in paths},
    }


def test_springfox_ui_deep_link_and_context_path_group(monkeypatch):
    requested = []

    def handle(request):
        requested.append(str(request.url))
        assert request.method == "GET"
        assert request.headers["Authorization"] == "Bearer document-secret"
        if request.url.path == "/fctdata/swagger-ui.html":
            return httpx.Response(200, text="<html><title>Swagger UI</title></html>")
        if request.url.path == "/fctdata/v3/api-docs/swagger-config":
            return httpx.Response(404)
        if request.url.path == "/fctdata/swagger-resources":
            return httpx.Response(
                200,
                json=[
                    {"name": "sales", "location": "/v2/api-docs?group=sales"},
                ],
            )
        if request.url.path == "/v2/api-docs":
            return httpx.Response(404)
        if request.url.path == "/fctdata/v2/api-docs":
            assert request.url.params["group"] == "sales"
            return httpx.Response(200, json=_spec("/api/store/sales/discount/push"))
        pytest.fail("不应探测业务端点或其他域名")

    _mock_client(monkeypatch, handle)
    monkeypatch.setenv("DOC_AUTH", "Bearer document-secret")
    selected = load_spec(
        "https://docs.example.test/fctdata/swagger-ui.html#/StoreSalesDiscountController",
        ["POST /api/store/sales/discount/push"],
        header_env="DOC_AUTH",
    )
    assert list(selected["paths"]) == ["/api/store/sales/discount/push"]
    assert len(requested) == 5
    assert all(url.startswith("https://docs.example.test/") for url in requested)
    assert all("#" not in url for url in requested)


def test_direct_grouped_api_docs_url_is_allowed(monkeypatch):
    received = []

    def handle(request):
        received.append(str(request.url))
        assert request.url.params["group"] == "orders"
        return httpx.Response(200, json=_spec("/orders"))

    _mock_client(monkeypatch, handle)
    result = load_spec("https://docs.example.test/v2/api-docs?group=orders", ["POST /orders"])
    assert "/orders" in result["paths"] and len(received) == 1


def test_springdoc_multi_group_requires_explicit_selection(monkeypatch):
    requested = []

    def handle(request):
        requested.append(str(request.url))
        if request.url.path == "/service/swagger-ui/index.html":
            return httpx.Response(200, text="<html><title>Swagger UI</title></html>")
        if request.url.path == "/service/v3/api-docs/swagger-config":
            return httpx.Response(
                200,
                json={
                    "urls": [
                        {"name": "orders", "url": "/service/v3/api-docs/orders"},
                        {"name": "billing", "url": "/service/v3/api-docs/billing"},
                    ]
                },
            )
        if request.url.path == "/service/v3/api-docs/billing":
            return httpx.Response(200, json=_spec("/bills"))
        pytest.fail("未选择分组时不应下载任何组文档")

    _mock_client(monkeypatch, handle)
    ui = "https://docs.example.test/service/swagger-ui/index.html"
    with pytest.raises(AIError, match="--spec-group") as error:
        load_spec(ui, [])
    assert "orders" in str(error.value) and "billing" in str(error.value)
    assert len(requested) == 2

    result = load_spec(ui, ["POST /bills"], group="billing")
    assert "/bills" in result["paths"]


def test_springdoc_primary_group_is_used_when_configured(monkeypatch):
    def handle(request):
        if request.url.path == "/service/swagger-ui.html":
            return httpx.Response(200, text="<html>Swagger UI</html>")
        if request.url.path == "/service/v3/api-docs/swagger-config":
            return httpx.Response(
                200,
                json={
                    "urls.primaryName": "billing",
                    "urls": [
                        {"name": "orders", "url": "/service/v3/api-docs/orders"},
                        {"name": "billing", "url": "/service/v3/api-docs/billing"},
                    ],
                },
            )
        assert request.url.path == "/service/v3/api-docs/billing"
        return httpx.Response(200, json=_spec("/bills"))

    _mock_client(monkeypatch, handle)
    assert "/bills" in load_spec("https://docs.example.test/service/swagger-ui.html", [])["paths"]


def test_inline_and_initializer_script_document_urls(monkeypatch):
    def handle(request):
        if request.url.path == "/swagger-ui/index.html":
            return httpx.Response(
                200,
                text=(
                    '<html><script src="./swagger-initializer.js"></script><h1>Swagger UI</h1></html>'
                ),
            )
        if request.url.path == "/swagger-ui/swagger-initializer.js":
            return httpx.Response(
                200, text=("window.ui = SwaggerUIBundle({ url: '/openapi.json' });")
            )
        assert request.url.path == "/openapi.json"
        return httpx.Response(200, json=_spec("/items"))

    _mock_client(monkeypatch, handle)
    selected = load_spec("https://docs.example.test/swagger-ui/index.html", ["POST /items"])
    assert "/items" in selected["paths"]


def test_ui_query_config_url_is_resolved_without_cross_origin_redirect(monkeypatch):
    requests = []

    def handle(request):
        requests.append(str(request.url))
        if request.url.path == "/service/swagger-ui.html":
            return httpx.Response(200, text="<html>Swagger UI</html>")
        if request.url.path == "/service/v3/api-docs/swagger-config":
            return httpx.Response(200, json={"url": "/service/v3/api-docs"})
        assert request.url.path == "/service/v3/api-docs"
        return httpx.Response(200, json=_spec("/items"))

    _mock_client(monkeypatch, handle)
    result = load_spec(
        "https://docs.example.test/service/swagger-ui.html?configUrl=/service/v3/api-docs/swagger-config#/",
        ["POST /items"],
    )
    assert "/items" in result["paths"]
    assert len(requests) == 3
    assert all("#" not in url for url in requests)


def test_cross_origin_config_is_rejected_before_auth_header_leaks(monkeypatch):
    received = []

    def handle(request):
        received.append(str(request.url))
        assert request.url.host == "docs.example.test"
        assert request.headers["Authorization"] == "Bearer test-document-secret"
        return httpx.Response(
            200,
            text=(
                "<html>Swagger UI<script>SwaggerUIBundle({url: "
                '"https://evil.example/openapi.json"})</script></html>'
            ),
        )

    _mock_client(monkeypatch, handle)
    monkeypatch.setenv("DOC_AUTH", "Bearer test-document-secret")
    with pytest.raises(AIError, match="同一 origin"):
        load_spec("https://docs.example.test/swagger-ui.html", [], header_env="DOC_AUTH")
    assert len(received) == 1


@pytest.mark.parametrize(
    "url",
    [
        "https://docs.example.test/v2/api-docs?token=secret",
        "https://docs.example.test/v2/api-docs?api_key=secret",
        "https://user:secret@docs.example.test/v2/api-docs",
        "https://docs.example.test/v2/api-docs#fragment",
    ],
)
def test_unsafe_raw_document_url_is_rejected_before_network(monkeypatch, url):
    _mock_client(monkeypatch, lambda request: pytest.fail("不应发送请求"))
    with pytest.raises(AIError):
        load_spec(url, [])


def test_discovery_never_follows_redirects_or_sends_to_destination(monkeypatch):
    visited = []

    def handle(request):
        visited.append(str(request.url))
        return httpx.Response(302, headers={"Location": "https://evil.example/openapi.json"})

    _mock_client(monkeypatch, handle)
    with pytest.raises(AIError, match="HTTP 302"):
        load_spec("https://docs.example.test/swagger-ui.html", [])
    assert len(visited) == 1


def test_spec_field_definition_kept_but_sensitive_examples_removed(monkeypatch):
    spec = {
        "openapi": "3.0.3",
        "paths": {"/login": {"post": {"responses": {}}}},
        "components": {
            "schemas": {
                "Auth": {
                    "properties": {
                        "password": {"type": "string", "example": "private-example"},
                    }
                }
            }
        },
    }
    _mock_client(monkeypatch, lambda request: httpx.Response(200, json=spec))
    parsed = load_spec("https://docs.example.test/v3/api-docs", [])
    assert parsed["components"]["schemas"]["Auth"]["properties"]["password"]["type"] == "string"
    assert "private-example" not in json.dumps(parsed)
