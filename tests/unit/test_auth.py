"""鉴权隔离、严格登录预期、无凭据时零请求和离线预检。"""

import json

import httpx
import pytest
from pydantic import ValidationError

from autotest.api.auth import AuthProfile, RoleAuth, load_profile, role_client
from autotest.config import Settings
from autotest.project import main

pytestmark = pytest.mark.unit


@pytest.fixture
def profile(monkeypatch):
    monkeypatch.setenv("TEST_AUTH_USER", "member")
    monkeypatch.setenv("TEST_AUTH_PASS", "unlabelled-private-value")
    return AuthProfile(
        roles={
            "default": RoleAuth(
                mode="login",
                login_path="/login",
                credentials_env={"username": "TEST_AUTH_USER", "password": "TEST_AUTH_PASS"},
                token_field="data.token",
                success_fields={"code": 0},
            ),
            "anonymous": RoleAuth(),
        }
    )


def test_login_business_contract_cookie_isolation_and_no_request_replay(profile):
    requests = []

    def handle(request):
        requests.append(request)
        if request.url.path == "/login":
            assert json.loads(request.content)["username"] == "member"
            return httpx.Response(
                200,
                json={"code": 0, "data": {"token": "session-value"}},
                headers={"set-cookie": "session=must-not-survive; Path=/"},
            )
        return httpx.Response(401)

    transport = httpx.MockTransport(handle)
    with role_client(profile, "https://test.invalid", transport=transport) as member:
        assert not member.raw_client.cookies
        assert member.post("/orders", json={}).status_code == 401
        assert len(requests) == 2, "不能在 401 后重新登录并重放写请求"
        assert requests[-1].headers["authorization"] == "Bearer session-value"
        with role_client(
            profile, "https://test.invalid", role="anonymous", transport=transport
        ) as guest:
            assert "authorization" not in guest.raw_client.headers
            assert not guest.raw_client.cookies
    assert member.raw_client.is_closed


@pytest.mark.parametrize(
    "body",
    [
        {"code": 1, "data": {"token": "unlabelled-private-value"}},
        {"code": False, "data": {"token": "unlabelled-private-value"}},
        {"code": 0, "data": {"token": ""}},
        {"code": 0, "data": {"token": 123}},
        {"code": 0},
        {"code": 0, "data": {"token": "private\x00value"}},
        ["unlabelled-private-value"],
    ],
)
def test_http_200_is_not_enough_for_authentication(profile, body):
    with pytest.raises(ValueError, match="登录响应") as error:
        role_client(
            profile,
            "https://test.invalid",
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body)),
        )
    assert "unlabelled-private-value" not in str(error.value)


def test_missing_credentials_fail_before_network(profile, monkeypatch):
    monkeypatch.delenv("TEST_AUTH_PASS")

    def handle(request):
        pytest.fail("缺少凭据时不应发送 HTTP 请求")

    with pytest.raises(ValueError, match="TEST_AUTH_PASS"):
        role_client(profile, "https://test.invalid", transport=httpx.MockTransport(handle))


@pytest.mark.parametrize(
    "path", ["https://other.invalid/login", "//other.invalid", "\\other", "/login?token=x"]
)
def test_login_cannot_send_credentials_outside_configured_host(path):
    with pytest.raises(ValidationError):
        RoleAuth(mode="login", login_path=path, credentials_env={"password": "TEST_AUTH_PASS"})


def test_bearer_and_project_headers_are_read_from_environment(monkeypatch):
    monkeypatch.setenv("ROLE_TOKEN", "private-value")
    monkeypatch.setenv("TENANT", "tenant-a")
    profile = AuthProfile(
        roles={
            "default": RoleAuth(
                mode="bearer",
                token_env="ROLE_TOKEN",
                headers_env={"X-Tenant": "TENANT"},
            )
        }
    )
    with role_client(profile, "https://test.invalid") as client:
        assert client.raw_client.headers["authorization"] == "Bearer private-value"
        assert client.raw_client.headers["x-tenant"] == "tenant-a"
    assert "private-value" not in repr(profile)


def test_bad_profile_does_not_echo_inline_secret(tmp_path):
    path = tmp_path / "auth.yaml"
    path.write_text("password: unlabelled-private-value", encoding="utf-8")
    with pytest.raises(ValueError) as error:
        load_profile(path)
    assert "unlabelled-private-value" not in str(error.value)


@pytest.mark.parametrize("value", ["private\r\nvalue", "私密值"])
def test_invalid_header_value_is_rejected_before_network(monkeypatch, value):
    monkeypatch.setenv("ROLE_HEADER", value)
    profile = AuthProfile(roles={"default": RoleAuth(headers_env={"X-Client": "ROLE_HEADER"})})
    with pytest.raises(ValueError, match="控制字符") as error:
        role_client(profile, "https://test.invalid")
    assert value not in str(error.value)


def test_failed_login_closes_client_without_exposing_response(profile, monkeypatch):
    from autotest.api.client import ApiClient

    client = ApiClient(
        "https://test.invalid",
        transport=httpx.MockTransport(lambda request: httpx.Response(401, text="private-response")),
    )
    monkeypatch.setattr("autotest.api.auth.ApiClient", lambda *args, **kwargs: client)
    with pytest.raises(ValueError, match="HTTP 401") as error:
        role_client(profile, "https://test.invalid")
    assert client.raw_client.is_closed
    assert "private-response" not in str(error.value)


def test_project_check_reports_missing_variables_without_logging_values(
    tmp_path, monkeypatch, capsys
):
    path = tmp_path / "auth.yaml"
    path.write_text(
        "roles:\n  default:\n    mode: bearer\n    token_env: ROLE_TOKEN\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        "autotest.project.load_settings",
        lambda *args: Settings(
            env="test",
            api_base_url="https://test.invalid",
            api_auth_file=str(path),
        ),
    )
    monkeypatch.delenv("ROLE_TOKEN", raising=False)
    assert main(["check", "--env", "test"]) == 1
    monkeypatch.setenv("ROLE_TOKEN", "unlabelled-private-value")
    assert main(["check", "--env", "test"]) == 0
    output = capsys.readouterr().out
    assert "未验证网络" in output and "unlabelled-private-value" not in output
