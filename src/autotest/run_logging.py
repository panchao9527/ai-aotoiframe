"""每次 pytest 运行的结构化事件日志。

xdist worker 各写独立 JSONL，控制进程在结束时合并成 events.jsonl 和可读 run.log，
避免多个进程竞争同一个文件。正文默认不记录请求/响应体，所有文本先经过基础脱敏。
"""

from __future__ import annotations

import hashlib
import heapq
import json
import logging
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from autotest.redaction import redact, redact_text

_LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
_MAX_MESSAGE = 4000
_MAX_EVENT_BYTES = 32 * 1024
_active_sink: EventSink | None = None
_test_context: ContextVar[dict[str, str] | None] = ContextVar("autotest_log_context", default=None)


class EventSink:
    def __init__(
        self, directory: Path, *, run_id: str, environment: str, worker: str, level: str = "INFO"
    ) -> None:
        self.directory = directory
        self.run_id = run_id
        self.environment = environment
        self.worker = worker
        self.threshold = _LEVELS[level]
        self._lock = threading.Lock()
        logs = directory / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        self.path = logs / f"events-{worker}.jsonl"
        self._stream = self.path.open("a", encoding="utf-8", buffering=1)

    def emit(self, event: str, message: str = "", *, level: str = "INFO", **data: Any) -> None:
        normalized_level = level.upper()
        if _LEVELS.get(normalized_level, 20) < self.threshold:
            return
        record: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": normalized_level,
            "event": event,
            "message": redact_text(str(message))[:_MAX_MESSAGE],
            "run_id": self.run_id,
            "environment": self.environment,
            "worker": self.worker,
            **(_test_context.get() or {}),
            "data": redact(data),
        }
        encoded = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        if len(encoded.encode()) > _MAX_EVENT_BYTES:
            digest = hashlib.sha256(encoded.encode()).hexdigest()
            record["data"] = {"truncated": True, "sha256": digest}
            encoded = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            self._stream.write(encoded + "\n")
            self._stream.flush()

    def close(self) -> None:
        with self._lock:
            if not self._stream.closed:
                self._stream.close()


class StructuredLogHandler(logging.Handler):
    """把业务 logger 写入同一事件流；异常堆栈只保留脱敏后的有限文本。"""

    def __init__(self, sink: EventSink, level: int) -> None:
        super().__init__(level)
        self.sink = sink

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.sink.emit(
                "python.log",
                record.getMessage(),
                level=record.levelname,
                logger=record.name,
                exception=self.formatException(record.exc_info) if record.exc_info else None,
            )
        except Exception:
            self.handleError(record)

    @staticmethod
    def formatException(exc_info) -> str:  # noqa: N802 - 与 logging Formatter 命名保持一致
        return logging.Formatter().formatException(exc_info)[:_MAX_MESSAGE]


def configure_logging(
    directory: Path, *, run_id: str, environment: str, worker: str, level: str
) -> tuple[EventSink, StructuredLogHandler, int, EventSink | None]:
    global _active_sink
    previous_sink = _active_sink
    sink = EventSink(directory, run_id=run_id, environment=environment, worker=worker, level=level)
    _active_sink = sink
    handler = StructuredLogHandler(sink, level=_LEVELS[level])
    root = logging.getLogger()
    previous_level = root.level
    root.addHandler(handler)
    if root.level > _LEVELS[level]:
        root.setLevel(_LEVELS[level])
    return sink, handler, previous_level, previous_sink


def shutdown_logging(
    sink: EventSink,
    handler: StructuredLogHandler,
    previous_root_level: int,
    previous_sink: EventSink | None,
) -> None:
    global _active_sink
    root = logging.getLogger()
    root.removeHandler(handler)
    root.setLevel(previous_root_level)
    sink.close()
    if _active_sink is sink:
        _active_sink = previous_sink


def emit_event(event: str, message: str = "", *, level: str = "INFO", **data: Any) -> None:
    if _active_sink is not None:
        _active_sink.emit(event, message, level=level, **data)


def bind_test(nodeid: str, case_id: str | None) -> Token:
    context = {"nodeid": nodeid}
    if case_id:
        context["case_id"] = case_id
    return _test_context.set(context)


def reset_test(token: Token) -> None:
    _test_context.reset(token)


@contextmanager
def business_step(name: str, **data: Any):
    """记录有业务意义的阶段；不用于包装每一行代码，也不接收密码或完整请求正文。"""
    if not name.strip():
        raise ValueError("业务步骤名称不能为空")
    started = time.perf_counter()
    emit_event("step.start", name, **data)
    try:
        yield
    except BaseException as exc:
        emit_event(
            "step.finish",
            name,
            level="ERROR",
            outcome="failed",
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
            error_type=type(exc).__name__,
        )
        raise
    else:
        emit_event(
            "step.finish",
            name,
            outcome="passed",
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )


def _iter_records(path: Path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            yield (record.get("timestamp", ""), record)


def merge_worker_logs(directory: Path) -> dict[str, int]:
    """合并已按时间写入的 worker 文件；坏行跳过且不影响原始分片。"""
    sources = sorted((directory / "logs").glob("events-*.jsonl"))
    merged = heapq.merge(*(_iter_records(path) for path in sources), key=lambda item: item[0])
    counts = {"events": 0, "warnings": 0, "errors": 0}
    events_path = directory / "events.jsonl"
    human_path = directory / "run.log"
    with (
        events_path.open("w", encoding="utf-8") as events,
        human_path.open("w", encoding="utf-8") as human,
    ):
        for _, record in merged:
            events.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
            counts["events"] += 1
            level = record.get("level", "INFO")
            if level == "WARNING":
                counts["warnings"] += 1
            elif level in {"ERROR", "CRITICAL"}:
                counts["errors"] += 1
            context = record.get("nodeid") or "-"
            message = record.get("message") or ""
            data = record.get("data") or {}
            suffix = " " + json.dumps(data, ensure_ascii=False) if data else ""
            human.write(
                f"{record.get('timestamp')} {level:<8} {record.get('worker')} "
                f"{context} {record.get('event')} {message}{suffix}\n"
            )
    (directory / "log-summary.json").write_text(
        json.dumps(counts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return counts


class PytestRunLogging:
    def __init__(
        self,
        config: pytest.Config,
        sink: EventSink,
        handler: StructuredLogHandler,
        previous_root_level: int,
        previous_sink: EventSink | None,
    ) -> None:
        self.config = config
        self.sink = sink
        self.handler = handler
        self.previous_root_level = previous_root_level
        self.previous_sink = previous_sink

    @pytest.hookimpl(hookwrapper=True, tryfirst=True)
    def pytest_runtest_protocol(self, item, nextitem):
        marker = item.get_closest_marker("case")
        case_id = str(marker.kwargs.get("id")) if marker and marker.kwargs.get("id") else None
        token = bind_test(item.nodeid, case_id)
        emit_event("test.start", item.name)
        try:
            yield
        finally:
            reset_test(token)

    @pytest.hookimpl(hookwrapper=True, trylast=True)
    def pytest_runtest_makereport(self, item, call):
        outcome = yield
        report = outcome.get_result()
        level = "ERROR" if report.failed else "INFO"
        emit_event(
            "test.phase",
            f"{report.when}: {report.outcome}",
            level=level,
            phase=report.when,
            outcome=report.outcome,
            duration_ms=round(report.duration * 1000, 2),
            error=report.longreprtext[:_MAX_MESSAGE] if report.failed else None,
        )

    @pytest.hookimpl(trylast=True)
    def pytest_sessionfinish(self, session, exitstatus):
        emit_event("session.finish", "pytest session finished", exit_code=int(session.exitstatus))
        if not hasattr(self.config, "workerinput"):
            merge_worker_logs(self.sink.directory)

    def pytest_unconfigure(self, config):
        shutdown_logging(self.sink, self.handler, self.previous_root_level, self.previous_sink)
