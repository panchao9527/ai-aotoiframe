"""项目内 Playwright CLI 入口：固定版本、命名会话、无 shell 参数转发。

它只用于 AI 页面探索和诊断。正式回归仍由 Python pytest-playwright 执行。
首次调用 npx 可能下载固定版本的 npm 包，不会写入 Python 依赖或 package.json。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

PLAYWRIGHT_CLI_VERSION = "0.1.21"
PLAYWRIGHT_CLI_PACKAGE = f"@playwright/cli@{PLAYWRIGHT_CLI_VERSION}"
SESSION_PATTERN = re.compile(r"[a-z][a-z0-9_-]{0,63}")
SENSITIVE_URL_KEY = re.compile(
    r"password|passwd|token|secret|authorization|session|api[_-]?key", re.I
)
SESSIONLESS_COMMANDS = {
    "--help",
    "--version",
    "close-all",
    "install",
    "install-browser",
    "kill-all",
    "list",
}


def find_npx() -> str:
    """Windows 优先使用可由 subprocess 直接执行的 npx.cmd。"""
    executable = shutil.which("npx.cmd") or shutil.which("npx")
    if not executable:
        raise ValueError("未找到 npx；请先安装 Node.js/npm，再运行 node --version 和 npm --version")
    return executable


def project_root() -> Path:
    root = Path.cwd().resolve()
    if not (root / "pyproject.toml").is_file() or not (root / "src/autotest").is_dir():
        raise ValueError("请从 autoiframe 项目根目录运行 qa browser")
    return root


def validate_arguments(arguments: list[str]) -> None:
    """阻止 URL 内嵌凭据；其他 CLI 参数保持原样交给官方命令校验。"""
    if not arguments:
        raise ValueError("缺少 Playwright CLI 命令，例如 open、snapshot、click 或 requests")
    for value in arguments:
        if not value.startswith(("http://", "https://")):
            continue
        parsed = urlsplit(value)
        if parsed.username or parsed.password:
            raise ValueError("浏览器 URL 不能内嵌账号密码；登录态使用测试账号或 state-load")
        sensitive_query = any(SENSITIVE_URL_KEY.search(key) for key, _ in parse_qsl(parsed.query))
        if sensitive_query or SENSITIVE_URL_KEY.search(parsed.fragment):
            raise ValueError("浏览器 URL 不能携带密码、Token 或会话参数；使用测试登录态")


def build_command(arguments: list[str], session: str) -> list[str]:
    if not SESSION_PATTERN.fullmatch(session):
        raise ValueError("会话名需以小写字母开头，只含小写字母、数字、_、-，最长 64 字符")
    validate_arguments(arguments)
    command = [
        find_npx(),
        "-y",
        "--package",
        PLAYWRIGHT_CLI_PACKAGE,
        "playwright-cli",
    ]
    if arguments[0] not in SESSIONLESS_COMMANDS:
        command.append(f"-s={session}")
    return [*command, *arguments]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="固定版本的 Playwright CLI 页面探索入口；正式回归继续使用 pytest"
    )
    parser.add_argument("--session", default="autoiframe", help="隔离浏览器会话名")
    parser.add_argument(
        "--print-command", action="store_true", help="只打印参数，不启动 npx/浏览器"
    )
    parser.add_argument("arguments", nargs=argparse.REMAINDER, help="传给 playwright-cli 的参数")
    args = parser.parse_args(argv)
    forwarded = args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
    try:
        root = project_root()
        command = build_command(forwarded, args.session)
        if args.print_command:
            print(json.dumps(command, ensure_ascii=False))
            return 0
        # 保持 cwd 为项目根目录，确保自动加载 .playwright/cli.config.json，且输出进入 artifacts。
        return subprocess.run(command, cwd=root, check=False).returncode
    except (OSError, ValueError) as exc:
        print(f"Playwright CLI 启动失败：{exc}")
        return 2
