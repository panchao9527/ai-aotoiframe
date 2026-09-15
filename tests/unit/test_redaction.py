"""脱敏保护的是输出边界；用真实形状的嵌套数据和日志验证它。"""

import pytest

from autotest.redaction import REDACTED, redact, redact_text

pytestmark = pytest.mark.unit


def test_nested_secrets_are_removed_without_mutating_input():
    source = {
        "headers": {"Authorization": "Bearer secret-a", "X-Api-Key": "secret-b"},
        "users": [{"password": "secret-c", "accessToken": "secret-d", "name": "小明"}],
        "metadata": {"client_secret": "secret-e", "status": 200, "active": True},
    }
    result = redact(source)
    assert result["headers"] == {"Authorization": REDACTED, "X-Api-Key": REDACTED}
    assert result["users"][0] == {"password": REDACTED, "accessToken": REDACTED, "name": "小明"}
    assert result["metadata"]["status"] == 200
    assert result["metadata"]["active"] is True
    assert source["users"][0]["password"] == "secret-c"
    assert "secret-" not in str(result)


@pytest.mark.parametrize(
    ("source", "secret"),
    [
        ('{"password": "word with spaces"}', "word with spaces"),
        ("api_key=abc123", "abc123"),
        ("access_token=abc123&result=ok", "abc123"),
        ("AI_API_KEY='abc123'", "abc123"),
        ("Authorization: Bearer abc123\nStatus: 401", "abc123"),
        ("Cookie: session=abc123; other=topsecret", "topsecret"),
        ("headers={'Set-Cookie': 'abc123; path=/'}", "abc123"),
        ("server rejected Bearer abc123", "abc123"),
        ("headers Authorization: Bearer abc123", "abc123"),
        ("server rejected Basic YWJjMTIz", "YWJjMTIz"),
        ("https://demo:abc123@example.test/path?token=xyz", "abc123"),
        ("https://abc123@example.test/path", "abc123"),
    ],
)
def test_common_text_credentials_are_redacted(source, secret):
    clean = redact_text(source)
    assert secret not in clean
    assert REDACTED in clean
    assert redact_text(clean) == clean


def test_non_sensitive_facts_remain_useful():
    source = {
        "status": 403,
        "path": "/api/items",
        "message": "expected 200, got 403",
        "optional": None,
    }
    assert redact(source) == source


def test_shared_and_circular_references_are_handled():
    item = {"password": "secret"}
    shared = [item, item]
    assert redact(shared) == [{"password": REDACTED}, {"password": REDACTED}]
    shared.append(shared)
    assert redact(shared)[-1] == "[CIRCULAR]"
    assert redact((item,)) == ({"password": REDACTED},)
