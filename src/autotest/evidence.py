"""小而有用的失败上下文；不默认保存认证头、URL 查询串或请求/响应正文。"""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from autotest.ai import AIError, read_input
from autotest.redaction import redact, redact_text


def safe_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
        # 去掉用户信息及全部查询/fragment；路径仍可能含业务 ID，分享前需要复核。
        return urlunsplit((parsed.scheme, parsed.netloc.rsplit("@", 1)[-1], parsed.path, "", ""))
    except ValueError:
        return "[invalid-url]"


class BrowserEvidence:
    def __init__(self, page):
        self.events: deque[dict] = deque(maxlen=60)
        page.on("console", self.console)
        page.on("pageerror", self.error)
        page.on("response", self.response)
        page.on("requestfailed", self.failed_request)

    def console(self, message):
        if message.type in {"error", "warning"}:
            self.events.append(
                {
                    "type": "console",
                    "level": message.type,
                    "message": redact_text(message.text[:2000]),
                }
            )

    def error(self, error):
        self.events.append({"type": "pageerror", "message": redact_text(str(error)[:2000])})

    def response(self, response):
        if response.request.resource_type in {"xhr", "fetch", "document"}:
            self.events.append(
                {
                    "type": "response",
                    "method": response.request.method,
                    "url": safe_url(response.url),
                    "status": response.status,
                }
            )

    def failed_request(self, request):
        self.events.append(
            {
                "type": "requestfailed",
                "method": request.method,
                "url": safe_url(request.url),
                "error": redact_text(str(request.failure)),
            }
        )


def export_evidence(run_directory: Path, output: Path) -> Path:
    """显式指定一次运行后生成文本清单；二进制附件只列相对路径，不自动上传。"""
    root = run_directory.resolve()
    if not root.is_dir() or root.is_symlink():
        raise AIError("请指定实际存在的运行报告目录。")
    records = []
    for path in sorted(root.glob("failures/*/*.json")):
        if path.resolve().is_relative_to(root) and not path.is_symlink():
            records.append(
                {"path": path.relative_to(root).as_posix(), "content": json.loads(read_input(path))}
            )
    artifacts = [
        p.relative_to(root).as_posix()
        for p in sorted(root.rglob("*"))
        if p.is_file() and not p.is_symlink() and p.suffix in {".zip", ".png", ".webm", ".xml"}
    ]
    payload = {
        "failures": records,
        "attachments": artifacts,
        "note": "附件未读取。Trace 与失败按报告目录定位；仅列表不保证逐用例一一映射。",
        "triage": ["产品缺陷", "用例问题", "环境或数据问题", "证据不足"],
    }
    text = json.dumps(redact(payload), ensure_ascii=False, indent=2)
    if len(text.encode()) > 128 * 1024:
        raise AIError("失败摘要超过 128 KiB，请按更小运行范围导出。")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        stream.write(text + "\n")
    return output
