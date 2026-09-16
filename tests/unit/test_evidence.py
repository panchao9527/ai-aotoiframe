"""证据摘要只包含必要请求元数据，文本可直接交给旧 ai analyze 入口。"""

import json

import pytest

from autotest.evidence import BrowserEvidence, export_evidence, safe_url

pytestmark = pytest.mark.unit


def test_url_does_not_expose_auth_or_query():
    assert (
        safe_url("https://user:password@example.test/items?token=secret#private")
        == "https://example.test/items"
    )
    assert (
        safe_url("http://user:pass@127.0.0.1:8765/items?token=secret")
        == "http://127.0.0.1:8765/items"
    )


def test_browser_ring_buffer_and_console_redaction():
    class Page:
        def on(self, event, callback):
            pass

    class Message:
        type = "error"
        text = "Authorization: Bearer hidden-token"

    evidence = BrowserEvidence(Page())
    for _ in range(80):
        evidence.console(Message())
    assert len(evidence.events) == 60
    assert "hidden-token" not in json.dumps(list(evidence.events))


def test_export_lists_binary_without_reading_it(tmp_path):
    failures = tmp_path / "run/failures/case"
    failures.mkdir(parents=True)
    (failures / "call.json").write_text(json.dumps({"password": "not-for-ai", "phase": "call"}))
    (failures / "web.png").write_bytes(b"private-image-do-not-read")
    output = export_evidence(tmp_path / "run", tmp_path / "summary.json")
    text = output.read_text(encoding="utf-8")
    assert "not-for-ai" not in text and "private-image-do-not-read" not in text
    assert "web.png" in text
    with pytest.raises(FileExistsError):
        export_evidence(tmp_path / "run", output)
