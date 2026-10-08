"""公司 CI 共用入口：先离线预检，再执行一个业务端，保留子进程退出码。"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", required=True)
    parser.add_argument("--suite", choices=("api", "web", "app"), required=True)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--app-platform", choices=("android", "ios"), default="android")
    parser.add_argument("--app-caps")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.env) or args.env.lower() == "demo":
        parser.error("公司 CI 必须使用明确的公司环境名，不能使用 demo")
    if args.workers < 0:
        parser.error("--workers 必须大于或等于 0")
    if args.suite == "app" and args.app_platform == "ios" and sys.platform != "darwin":
        parser.error("此 CI 模板的 iOS lane 必须使用配置了 Xcode/WDA 的 macOS 设备节点")

    # Jenkins 可绑定 Secret file，格式与 .env 一致；文件不复制进项目或报告目录。
    environment = dict(os.environ)
    secret_file = environment.get("CI_ENV_FILE", "")
    if secret_file:
        if not Path(secret_file).is_file():
            parser.error("无法读取 Jenkins 绑定的 CI_ENV_FILE")
        environment.update(
            (name, value) for name, value in dotenv_values(secret_file).items() if value is not None
        )
    # GitHub 未配置的 vars 返回空串。只应用非空覆盖，保留 YAML 中其他端的配置。
    for name in ("API_BASE_URL", "WEB_BASE_URL", "APPIUM_SERVER_URL", "API_AUTH_FILE"):
        value = environment.get(f"CI_{name}", "")
        if value.strip():
            environment[name] = value
    environment["TEST_ENV"] = args.env
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONUNBUFFERED"] = "1"

    device_args: list[str] = []
    if args.suite == "app":
        caps = args.app_caps or f"configs/devices/{args.app_platform}.yaml"
        device_args = ["--app-platform", args.app_platform, "--app-caps", caps]
    command = [sys.executable, "-m", "autotest"]
    checked = subprocess.run(
        [*command, "project", "check", "--env", args.env, "--suite", args.suite, *device_args],
        check=False,
        env=environment,
    )
    if checked.returncode:
        return checked.returncode

    # 一个 job 只跑一个端，避免 API 通过掩盖 Web/App 未执行；设备固定单进程。
    runtime_args = ["--run-app", *device_args] if args.suite == "app" else []
    tested = subprocess.run(
        [
            *command,
            "run",
            "--suite",
            args.suite,
            "--",
            "--env",
            args.env,
            "-n",
            "0" if args.suite == "app" else str(args.workers),
            *runtime_args,
        ],
        check=False,
        env=environment,
    )
    return tested.returncode


if __name__ == "__main__":
    raise SystemExit(main())
