"""接口业务 fixture：用登录 API 准备身份，测试结束后连接自动关闭。"""

import pytest


@pytest.fixture
def authenticated_client(api_client):
    response = api_client.post("/api/login", json={"username": "demo", "password": "demo123"})
    assert response.status_code == 200, "前置登录失败，请先检查环境和账号"
    # 清除 Cookie，明确演示 Bearer Token 鉴权，而不是误依赖 Cookie 登录态。
    api_client.raw_client.cookies.clear()
    api_client.raw_client.headers["Authorization"] = f"Bearer {response.json()['token']}"
    return api_client
