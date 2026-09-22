"""结构化日志的脱敏、上下文、分片合并与人类可读输出。"""

import json
import logging

import pytest

from autotest.run_logging import (
    EventSink,
    bind_test,
    business_step,
    configure_logging,
    emit_event,
    merge_worker_logs,
    reset_test,
    shutdown_logging,
)

pytestmark = pytest.mark.unit


def test_structured_event_and_python_logging_share_context_and_redaction(tmp_path):
    sink, handler, previous_level, previous_sink = configure_logging(
        tmp_path, run_id="run-1", environment="test", worker="gw0", level="INFO"
    )
    token = bind_test("tests/api/test_order.py::test_create", "ORDER-001")
    try:
        emit_event("api.request", "password='private-value'", status=200)
        logging.getLogger("business.order").warning("Authorization: Bearer private-token")
    finally:
        reset_test(token)
        shutdown_logging(sink, handler, previous_level, previous_sink)

    records = [json.loads(line) for line in sink.path.read_text(encoding="utf-8").splitlines()]
    assert [record["event"] for record in records] == ["api.request", "python.log"]
    assert all(record["nodeid"].endswith("test_create") for record in records)
    assert all(record["case_id"] == "ORDER-001" for record in records)
    content = sink.path.read_text(encoding="utf-8")
    assert "private-value" not in content and "private-token" not in content


def test_worker_fragments_merge_in_timestamp_order(tmp_path):
    first = EventSink(tmp_path, run_id="run-1", environment="test", worker="gw0")
    second = EventSink(tmp_path, run_id="run-1", environment="test", worker="gw1")
    first.emit("test.start", "first")
    second.emit("test.phase", "second", level="WARNING")
    first.emit("test.phase", "third", level="ERROR")
    first.close()
    second.close()

    counts = merge_worker_logs(tmp_path)
    records = [
        json.loads(line)
        for line in (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert counts == {"events": 3, "warnings": 1, "errors": 1}
    assert [record["timestamp"] for record in records] == sorted(
        record["timestamp"] for record in records
    )
    assert "gw0" in (tmp_path / "run.log").read_text(encoding="utf-8")
    assert json.loads((tmp_path / "log-summary.json").read_text(encoding="utf-8")) == counts


def test_large_event_is_replaced_by_hash_instead_of_filling_logs(tmp_path):
    sink = EventSink(tmp_path, run_id="run-1", environment="test", worker="main")
    sink.emit("large", "bounded", payload="x" * 100_000)
    sink.close()
    record = json.loads(sink.path.read_text(encoding="utf-8"))
    assert record["data"]["truncated"] is True
    assert len(record["data"]["sha256"]) == 64
    assert sink.path.stat().st_size < 5000


def test_log_level_filters_debug_and_info(tmp_path):
    sink = EventSink(tmp_path, run_id="run-1", environment="test", worker="main", level="WARNING")
    sink.emit("debug", level="DEBUG")
    sink.emit("info", level="INFO")
    sink.emit("warning", level="WARNING")
    sink.close()
    records = [json.loads(line) for line in sink.path.read_text(encoding="utf-8").splitlines()]
    assert [record["event"] for record in records] == ["warning"]


def test_business_step_records_success_failure_and_duration(tmp_path):
    sink, handler, previous_level, previous_sink = configure_logging(
        tmp_path, run_id="run-1", environment="test", worker="main", level="INFO"
    )
    try:
        with business_step("创建订单", order_type="normal"):
            pass
        with pytest.raises(AssertionError), business_step("核对状态"):
            raise AssertionError("password='step-private'")
    finally:
        shutdown_logging(sink, handler, previous_level, previous_sink)
    records = [json.loads(line) for line in sink.path.read_text(encoding="utf-8").splitlines()]
    finishes = [record for record in records if record["event"] == "step.finish"]
    assert [record["data"]["outcome"] for record in finishes] == ["passed", "failed"]
    assert all(record["data"]["duration_ms"] >= 0 for record in finishes)
    assert "step-private" not in sink.path.read_text(encoding="utf-8")
