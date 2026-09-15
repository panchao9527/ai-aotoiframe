"""数据驱动登录：一个测试函数覆盖成功、密码错误、账号不存在等场景。"""

from pathlib import Path

import pytest
import yaml

pytestmark = [pytest.mark.api, pytest.mark.demo]
CASES = yaml.safe_load(
    (Path(__file__).parents[1] / "data" / "login_cases.yaml").read_text(encoding="utf-8")
)


@pytest.mark.smoke
@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_login(api_client, case):
    # Arrange（准备）：从 YAML 取本组输入。
    payload = {"username": case["username"], "password": case["password"]}
    # Act（操作）：使用普通 Python/HTTPX 发请求。
    response = api_client.post("/api/login", json=payload)
    # Assert（断言）：除状态码，还检查返回的业务结果。
    assert response.status_code == case["expected_status"]
    if case["expected_status"] == 200:
        assert response.json()["user"]["name"] == "demo"
        assert isinstance(response.json()["token"], str)
        assert response.json()["token"]
    else:
        assert response.json() == {"error": "invalid_credentials"}
