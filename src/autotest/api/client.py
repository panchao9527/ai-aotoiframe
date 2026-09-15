"""轻量 HTTPX 封装：统一地址/超时/鉴权，保留原生响应方便断言。"""

import logging
from urllib.parse import urlsplit

import httpx

logger = logging.getLogger(__name__)


class ApiClient:
    """每个用例独立连接和 Cookie；负向测试可以直接断言 400/401/404。

    不自动 raise_for_status，不重试 POST/DELETE，避免重复创建业务数据。
    高级需求通过 raw_client 使用 HTTPX 原生功能，不再套一套请求语言。
    """

    def __init__(
        self,
        base_url: str,
        *,
        token: str | None = None,
        timeout: float = 20,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self.raw_client = httpx.Client(
            base_url=base_url.rstrip("/") + "/",
            headers=headers,
            timeout=timeout,
            follow_redirects=False,
            transport=transport,
            trust_env=False,
        )

    def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        """只接受相对路径，避免把默认鉴权头误发到另一个域名。"""
        parsed = urlsplit(path)
        if parsed.scheme or parsed.netloc or path.startswith("//") or "\\" in path:
            raise ValueError("API 路径必须是相对路径，例如 /api/items")
        response = self.raw_client.request(method, path.lstrip("/"), **kwargs)
        # 不记录 URL/参数/请求体/响应体，它们常含密码、手机号、Token。
        logger.info("HTTP %s -> %s", method.upper(), response.status_code)
        return response

    def get(self, path: str, **kwargs) -> httpx.Response:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs) -> httpx.Response:
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs) -> httpx.Response:
        return self.request("PUT", path, **kwargs)

    def patch(self, path: str, **kwargs) -> httpx.Response:
        return self.request("PATCH", path, **kwargs)

    def delete(self, path: str, **kwargs) -> httpx.Response:
        return self.request("DELETE", path, **kwargs)

    def close(self) -> None:
        self.raw_client.close()

    def __enter__(self) -> "ApiClient":
        return self

    def __exit__(self, *args) -> None:
        self.close()
