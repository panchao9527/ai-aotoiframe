"""编写闭环的实际隔离执行与失败边界；所有联网模型调用均用假响应。"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from autotest.ai import AIError
from autotest.authoring.cli import main
from autotest.authoring.context import collect_sources, load_spec, recording_text
from autotest.authoring.models import destination, read_manifest
from autotest.authoring.validation import promote, static_check, validate
from autotest.authoring.workflow import generate, prepare

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def author_project(tmp_path, monkeypatch):
    for name in ("src", "tests", "configs", "templates", "examples"):
        shutil.copytree(
            ROOT / name, tmp_path / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
        )
    for name in ("pyproject.toml", "conftest.py"):
        shutil.copy2(ROOT / name, tmp_path / name)
    monkeypatch.chdir(tmp_path)
    for key in ("API_BASE_URL", "WEB_BASE_URL", "API_TOKEN", "PYTEST_ADDOPTS"):
        monkeypatch.delenv(key, raising=False)
    return tmp_path


def prepare_sample(name="sample", kind="api", mode="scenario"):
    return prepare(
        name,
        kind,
        mode,
        requirement=f"examples/authoring/{kind}-requirement.md",
        sources=[],
        match=None,
        recording=None,
        observation=None,
        spec="examples/authoring/openapi.json" if kind == "api" else None,
        operations=[],
        spec_auth_env=None,
    )


def test_api_draft_runs_in_overlay_and_promotion_requires_current_content(author_project):
    workspace = prepare_sample()
    generate("sample", response="examples/authoring/responses/api-scenario.json")
    target = author_project / "tests/api/authored_items/test_lifecycle.py"
    assert not target.exists()
    report = validate("sample", execute=True, environment="demo")
    assert report["passed"], (workspace / "validation.log").read_text(encoding="utf-8")
    assert not target.exists(), "隔离执行不能先把草稿放进正式目录"
    with pytest.raises(AIError, match="reviewed"):
        promote("sample")
    draft = workspace / "draft/tests/api/authored_items/test_lifecycle.py"
    original = draft.read_text(encoding="utf-8")
    draft.write_text(original + "\n# changed\n", encoding="utf-8")
    with pytest.raises(AIError, match="重新验证"):
        promote("sample", reviewed=True)
    draft.write_text(original, encoding="utf-8")
    dependency = author_project / "src/autotest/api/services.py"
    # 按字节恢复，避免 Windows 文本写入把 LF 改成 CRLF，造成文件其实没有还原。
    previous = dependency.read_bytes()
    dependency.write_bytes(previous + b"\n# dependency changed\n")
    with pytest.raises(AIError, match="源码、fixture"):
        promote("sample", reviewed=True)
    dependency.write_bytes(previous)
    written = promote("sample", reviewed=True)
    assert len(written) == 2 and target.is_file()
    with pytest.raises(AIError, match="已存在"):
        promote("sample", reviewed=True)


def test_invalid_runtime_does_not_pass_validation(author_project):
    workspace = prepare_sample()
    response = {
        "files": [
            {
                "path": "tests/api/new_case/test_wrong.py",
                "content": "import pytest\npytestmark = pytest.mark.api\n"
                "def test_wrong():\n    assert 1 == 2\n",
            }
        ]
    }
    Path("reply.json").write_text(json.dumps(response), encoding="utf-8")
    generate("sample", response="reply.json")
    result = validate("sample", execute=True, environment="demo")
    assert result["executed"] and not result["passed"]
    assert (workspace / "validation-artifacts").is_dir()
    with pytest.raises(AIError):
        promote("sample", reviewed=True)


def test_app_unknowns_block_execution_without_device(author_project):
    workspace = prepare_sample(kind="app", mode="single")
    generate("sample", response="examples/authoring/responses/app.json")
    errors, tests = static_check(workspace, read_manifest(workspace))
    assert tests and any("业务条件待确认" in error for error in errors)
    with pytest.raises(AIError, match="run-app"):
        validate("sample", execute=True, environment="test")
    assert not validate("sample")["passed"]


@pytest.mark.parametrize(
    "path",
    [
        "../outside.py",
        "tests/web/test_wrong.py",
        "src/autotest/cli.py",
        "tests/api/../test_escape.py",
        "tests/api/CON.py",
        "tests/api/test_foo.py:bar",
        "C:/outside.py",
    ],
)
def test_generated_paths_cannot_escape_business_layer(path):
    with pytest.raises(AIError):
        destination(path, "api")


def test_whole_response_validated_before_any_draft_is_written(author_project):
    workspace = prepare_sample()
    payload = {
        "files": [
            {"path": "tests/api/new_case/test_ok.py", "content": "x = 1"},
            {"path": "../bad.py", "content": "x = 2"},
        ]
    }
    Path("bad.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(AIError):
        generate("sample", response="bad.json")
    assert not (workspace / "draft").exists()


def test_plain_python_is_not_a_test(author_project):
    workspace = prepare_sample()
    Path("reply.json").write_text(
        json.dumps({"files": [{"path": "tests/api/test_nothing.py", "content": "x = 1"}]}),
        encoding="utf-8",
    )
    generate("sample", response="reply.json")
    assert any("没有" in error for error in validate("sample")["static_errors"])
    assert not (workspace / "validation.log").exists()


def test_openapi_selects_operations_and_keeps_schema_references(author_project):
    spec = load_spec("examples/authoring/openapi.json", ["POST /api/items"])
    assert list(spec["paths"]) == ["/api/items"]
    assert "NewItem" in spec["components"]["schemas"]
    with pytest.raises(AIError, match="没有操作"):
        load_spec("examples/authoring/openapi.json", ["PUT /missing"])
    Path("ui.html").write_text("<html>Swagger UI</html>", encoding="utf-8")
    with pytest.raises(AIError, match="不是 OpenAPI"):
        load_spec("ui.html", [])


def test_openapi_keeps_sensitive_field_contract_but_not_example(tmp_path):
    path = tmp_path / "openapi.json"
    path.write_text(
        json.dumps(
            {
                "openapi": "3.0.3",
                "paths": {},
                "components": {
                    "schemas": {
                        "Login": {
                            "type": "object",
                            "required": ["password"],
                            "properties": {
                                "password": {
                                    "type": "string",
                                    "minLength": 8,
                                    "example": "private-example",
                                    "default": "private-default",
                                }
                            },
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    material = load_spec(str(path), [])
    password = material["components"]["schemas"]["Login"]["properties"]["password"]
    assert password["type"] == "string" and password["minLength"] == 8
    assert "private-example" not in json.dumps(material)
    assert "private-default" not in json.dumps(material)


@pytest.mark.parametrize("status", [200, 302])
def test_openapi_url_reads_explicit_auth_without_following_redirects(monkeypatch, status):
    monkeypatch.setenv("SPEC_TEST_AUTH", "Bearer test-document-secret")
    seen = []
    original_client = httpx.Client

    def handle(request):
        seen.append(request)
        assert request.headers["Authorization"] == "Bearer test-document-secret"
        return httpx.Response(
            status,
            headers={"location": "https://other.example.test/private"},
            json={"openapi": "3.0.3", "paths": {}},
        )

    monkeypatch.setattr(
        "autotest.authoring.context.httpx.Client",
        lambda **kwargs: original_client(transport=httpx.MockTransport(handle), **kwargs),
    )
    if status == 200:
        material = load_spec(
            "https://spec.example.test/openapi.json", [], header_env="SPEC_TEST_AUTH"
        )
        assert "test-document-secret" not in json.dumps(material)
    else:
        with pytest.raises(AIError, match="HTTP 302"):
            load_spec("https://spec.example.test/openapi.json", [], header_env="SPEC_TEST_AUTH")
    assert len(seen) == 1


def test_source_scope_and_prompt_do_not_read_unselected_secrets(author_project):
    source = author_project / "backend"
    source.mkdir()
    (source / "Order.java").write_text(
        'class Order { String password = "hidden-value"; }', encoding="utf-8"
    )
    (source / "Unrelated.java").write_text("unrelated-internal-data", encoding="utf-8")
    (source / ".env").write_text("never-read-this", encoding="utf-8")
    with pytest.raises(AIError, match="--match"):
        collect_sources([str(source)], None)
    records = collect_sources([str(source)], "class Order")
    content = json.dumps(records)
    assert len(records) == 1
    assert "hidden-value" not in content and "unrelated-internal-data" not in content
    assert "never-read-this" not in content


def test_generate_send_uses_same_multifile_protocol(author_project, monkeypatch):
    prepare_sample()
    payload = Path("examples/authoring/responses/api-scenario.json").read_text(encoding="utf-8")
    seen = []

    def fake_completion(prompt):
        seen.append(prompt)
        return payload

    monkeypatch.setattr("autotest.authoring.workflow.ai.request_completion", fake_completion)
    workspace = generate("sample", send=True)
    assert seen and "ItemsService" in seen[0] and "NewItem" in seen[0]
    assert len(read_manifest(workspace)["files"]) == 2


def test_record_print_command_does_not_open_browser(author_project, capsys):
    assert main(["record", "web", "--url", "http://127.0.0.1:8765", "--print-command"]) == 0
    command = json.loads(capsys.readouterr().out)
    assert "python-pytest" in command
    assert not (author_project / "artifacts/recordings/recording.py").exists()


def test_recording_password_calls_are_redacted(tmp_path):
    path = tmp_path / "recording.py"
    path.write_text(
        'page.get_by_label("密码").fill("recorded-secret")\n'
        'control = page.get_by_label("password")\n'
        'control.fill("second-secret")\n'
        'page.get_by_label("留言").fill("hello")\n',
        encoding="utf-8",
    )
    text = recording_text(path)
    assert "recorded-secret" not in text and "second-secret" not in text
    assert "hello" in text


def test_partial_runtime_skip_does_not_validate_whole_draft(author_project):
    prepare_sample()
    # fixture 的动态 skip 不在草稿 AST 中，仍必须由实际执行统计识别出来。
    fixture = Path("tests/api/conftest.py")
    fixture.write_text(
        fixture.read_text(encoding="utf-8")
        + '\n@pytest.fixture\ndef unavailable():\n    pytest.skip("no data")\n',
        encoding="utf-8",
    )
    payload = {
        "files": [
            {
                "path": "tests/api/test_partial.py",
                "content": "def test_ready():\n    assert len([1]) == 1\n"
                "def test_missing(unavailable):\n    assert unavailable == 1\n",
            }
        ]
    }
    Path("reply.json").write_text(json.dumps(payload), encoding="utf-8")
    generate("sample", response="reply.json")
    report = validate("sample", execute=True, environment="demo")
    assert report["exit_code"] == 0
    assert report["counts"]["skipped"] == 1 and not report["passed"]


def test_all_skipped_business_returns_nonzero_even_with_passing_unit(author_project):
    environment = {**os.environ, "PYTHONPATH": str(author_project / "src"), "PYTHONUTF8": "1"}
    command = [
        sys.executable,
        "-m",
        "pytest",
        "tests/web",
        "tests/unit/test_cli.py",
        "--env",
        "test",
        "--require-business",
        "--business-kind",
        "web",
        "-q",
    ]
    result = subprocess.run(
        command,
        cwd=author_project,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "没有实际执行" in result.stdout
