"""全部使用临时目录/MockTransport：单元测试不会调用付费 AI 服务。"""

import json

import httpx
import pytest

from autotest import ai

pytestmark = pytest.mark.unit


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "requirement.md"
    path.write_text("POST /api/items 创建任务后应返回 201。password=very-secret", encoding="utf-8")
    return tmp_path, path


@pytest.fixture
def ai_config(monkeypatch):
    monkeypatch.setenv("AI_BASE_URL", "https://ai.example.test/v1")
    monkeypatch.setenv("AI_MODEL", "test-model")
    monkeypatch.setenv("AI_API_KEY", "only-for-unit-test")


def test_default_is_offline_and_only_selected_input_is_used(workspace, monkeypatch, capsys):
    root, path = workspace
    (root / ".env").write_text("AI_API_KEY=never-send-this", encoding="utf-8")
    (root / "other.txt").write_text("unselected-company-secret", encoding="utf-8")

    def network_forbidden(*args, **kwargs):
        pytest.fail("离线模式不得调用网络或加载 .env")

    monkeypatch.setattr(ai, "request_completion", network_forbidden)
    monkeypatch.setattr(ai, "load_dotenv", network_forbidden)
    assert ai.main(["generate", "--kind", "api", "--input", str(path)]) == 0
    saved = (root / "artifacts/ai/prompt.md").read_text(encoding="utf-8")
    assert "POST /api/items" in saved
    assert "very-secret" not in saved
    assert "never-send-this" not in saved
    assert "unselected-company-secret" not in saved
    assert "没有调用 AI 服务" in capsys.readouterr().out


def test_output_cannot_escape_artifacts_directory(workspace, capsys):
    root, path = workspace
    assert (
        ai.main(
            [
                "generate",
                "--kind",
                "api",
                "--input",
                str(path),
                "--output",
                "tests/test_generated.py",
            ]
        )
        == 1
    )
    assert "artifacts/ai" in capsys.readouterr().err
    assert not (root / "tests/test_generated.py").exists()
    with pytest.raises(ai.AIError, match="artifacts/ai"):
        ai.resolve_output("artifacts/ai/../../outside.md", "analyze", False)


def test_output_requires_expected_extension():
    with pytest.raises(ai.AIError, match=".md"):
        ai.resolve_output("artifacts/ai/prompt.py", "generate", False)


def test_no_overwrite_without_force(workspace):
    root, path = workspace
    target = root / "artifacts/ai/prompt.md"
    target.parent.mkdir(parents=True)
    target.write_text("keep my draft", encoding="utf-8")
    args = ["generate", "--kind", "web", "--input", str(path)]
    assert ai.main(args) == 1
    assert target.read_text(encoding="utf-8") == "keep my draft"
    assert ai.main(args + ["--force"]) == 0
    assert "POST /api/items" in target.read_text(encoding="utf-8")


def test_json_input_redacts_nested_values(workspace):
    root, _ = workspace
    path = root / "failure.json"
    path.write_text(json.dumps({"error": {"password": "a b c", "token": "abc"}, "status": 401}))
    clean = json.loads(ai.read_input(path))
    assert clean == {"error": {"password": "[REDACTED]", "token": "[REDACTED]"}, "status": 401}


@pytest.mark.parametrize(
    "name,content,message",
    [
        ("empty.txt", b"  ", "为空"),
        ("binary.txt", b"\xff\xfe", "UTF-8"),
        ("large.txt", b"x" * (ai.MAX_INPUT_BYTES + 1), "128 KiB"),
        ("bad.json", b"{oops", "解析失败"),
        ("aliases.yaml", b"a: &a [x]\nb: [*a, *a]", "别名"),
        ("trace.zip", b"binary", "只支持"),
    ],
    ids=["empty", "binary", "oversize", "invalid-json", "yaml-alias", "unsupported-type"],
)
def test_invalid_inputs_fail_before_network(workspace, name, content, message):
    root, _ = workspace
    path = root / name
    path.write_bytes(content)
    with pytest.raises(ai.AIError, match=message):
        ai.read_input(path)


def test_send_uses_selected_endpoint_model_and_only_redacted_prompt(ai_config):
    seen = []

    def handler(request):
        seen.append(request)
        assert request.url == "https://ai.example.test/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer only-for-unit-test"
        body = json.loads(request.content)
        assert body["model"] == "test-model"
        assert body["messages"][1]["content"] == "test input"
        assert body["stream"] is False
        return httpx.Response(200, json={"choices": [{"message": {"content": "检查 HTTP 状态码"}}]})

    assert (
        ai.request_completion("test input", transport=httpx.MockTransport(handler))
        == "检查 HTTP 状态码"
    )
    assert len(seen) == 1


def test_model_code_assignments_are_not_corrupted_by_text_redaction(ai_config):
    code = 'token = response.json()["token"]\npassword = os.environ["APP_TEST_PASSWORD"]'
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, json={"choices": [{"message": {"content": code}}]})
    )
    reply = ai.request_completion("already redacted input", transport=transport)
    assert reply == code
    assert "token = response.json()" in ai.validate_python(reply)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"choices": []},
        {"choices": [{"message": {"content": " "}}]},
        {"choices": [{"message": {"content": None}}]},
        {"choices": [{"message": {"content": [{"text": "unsupported shape"}]}}]},
    ],
)
def test_missing_or_empty_response_is_friendly(ai_config, payload):
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    with pytest.raises(ai.AIError):
        ai.request_completion("test", transport=transport)


def test_http_error_does_not_disclose_provider_body_or_retry(ai_config):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(401, text="key only-for-unit-test rejected")

    with pytest.raises(ai.AIError) as error:
        ai.request_completion("test", transport=httpx.MockTransport(handler))
    assert "401" in str(error.value)
    assert "only-for-unit-test" not in str(error.value)
    assert len(seen) == 1


def test_timeout_does_not_disclose_request_details(ai_config):
    def handler(request):
        raise httpx.ReadTimeout("only-for-unit-test leaked by upstream", request=request)

    with pytest.raises(ai.AIError) as error:
        ai.request_completion("test", transport=httpx.MockTransport(handler))
    assert "超时" in str(error.value)
    assert "only-for-unit-test" not in str(error.value)


@pytest.mark.parametrize(
    "base",
    [
        "",
        "http://remote.example.test/v1",
        "https://user:secret@example.test/v1",
        "https://example.test/v1?token=secret",
    ],
)
def test_send_rejects_missing_or_unsafe_base(ai_config, monkeypatch, base):
    monkeypatch.setenv("AI_BASE_URL", base)
    with pytest.raises(ai.AIError):
        ai.request_completion(
            "test", transport=httpx.MockTransport(lambda _: pytest.fail("禁止请求"))
        )


def test_send_requires_model(ai_config, monkeypatch):
    monkeypatch.delenv("AI_MODEL")
    with pytest.raises(ai.AIError, match="AI_MODEL"):
        ai.request_completion("test")


def test_generate_saves_syntax_checked_code_without_execution(workspace, monkeypatch):
    root, path = workspace
    # 若生成代码被误执行，这里会在临时目录产生 forbidden.txt。
    code = 'from pathlib import Path\nPath("forbidden.txt").write_text("executed")\n'
    monkeypatch.setattr(ai, "request_completion", lambda _: "```python\n" + code + "```")
    assert ai.main(["generate", "--kind", "api", "--input", str(path), "--send"]) == 0
    saved = (root / "artifacts/ai/draft.py").read_text(encoding="utf-8")
    assert "尚未执行" in saved
    assert "Path(" in saved
    assert not (root / "forbidden.txt").exists()


def test_invalid_generated_python_is_not_saved(workspace, monkeypatch, capsys):
    root, path = workspace
    monkeypatch.setattr(ai, "request_completion", lambda _: "def broken(:")
    assert ai.main(["generate", "--kind", "api", "--input", str(path), "--send"]) == 1
    assert "有效 Python" in capsys.readouterr().err
    assert not (root / "artifacts/ai/draft.py").exists()


def test_analyze_saves_markdown(workspace, monkeypatch):
    root, path = workspace
    monkeypatch.setattr(ai, "request_completion", lambda _: "# 失败分析\n\n证据不足，请核对响应。")
    assert ai.main(["analyze", "--input", str(path), "--send"]) == 0
    assert "证据不足" in (root / "artifacts/ai/analysis.md").read_text(encoding="utf-8")


def test_existing_environment_beats_dotenv(workspace, ai_config, monkeypatch):
    root, path = workspace
    (root / ".env").write_text("AI_MODEL=must-not-override\n", encoding="utf-8")

    def fake_request(prompt):
        assert ai.os.environ["AI_MODEL"] == "test-model"
        return "# 报告\n证据不足"

    monkeypatch.setattr(ai, "request_completion", fake_request)
    assert ai.main(["analyze", "--input", str(path), "--send"]) == 0
