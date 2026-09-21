"""可选 ARTEMIS 远程客户端入口。

完整 ARTEMIS Agent、模型和设备工具链留在独立 Python 3.12+ 主机。本模块只加载
零运行依赖的 artemis-client，把 Android 探索结果保存为本地 AI 编写素材。
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from autotest.config import Settings, load_settings
from autotest.redaction import redact, redact_text

MAX_GOAL_BYTES = 64 * 1024


def client_class():
    try:
        from artemis_client import ArtemisClient
    except ImportError as exc:
        raise RuntimeError(
            "未安装可选 artemis-client；运行 uv sync --extra artemis。"
            "完整 ARTEMIS 服务应部署在独立设备主机。"
        ) from exc
    return ArtemisClient


def make_client(settings: Settings):
    if not settings.artemis_base_url:
        raise ValueError("请配置 ARTEMIS_BASE_URL；本机服务通常为 http://127.0.0.1:8000")
    return client_class()(
        settings.artemis_base_url,
        token=settings.artemis_token,
        request_timeout=min(settings.artemis_timeout_seconds, 300),
        device_serial=settings.artemis_device_serial,
        default_profile=settings.artemis_profile,
    )


def read_goal(path: str) -> str:
    source = Path(path)
    if source.is_symlink():
        raise ValueError("ARTEMIS 任务文件不存在或是符号链接")
    source = source.resolve()
    if not source.is_file():
        raise ValueError("ARTEMIS 任务文件不存在或是符号链接")
    if source.stat().st_size > MAX_GOAL_BYTES:
        raise ValueError("ARTEMIS 任务文件超过 64 KiB，请缩小单次探索范围")
    text = source.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError("ARTEMIS 任务文件不能为空")
    return text


def _result_payload(result: Any) -> dict:
    """不保存原始响应和原始 goal；它们可能包含模型上下文或设备隐私数据。"""
    return redact(
        {
            "task_id": result.task_id,
            "status": result.status,
            "succeeded": result.succeeded,
            "profile": result.profile,
            "device_serial": result.device_serial,
            "turns": result.turns,
            "output": result.output,
            "error": result.error,
        }
    )


def _artifact_path() -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    path = Path("artifacts/artemis") / stamp / "result.json"
    path.parent.mkdir(parents=True, exist_ok=False)
    return path.resolve()


async def execute(args, settings: Settings) -> tuple[int, dict]:
    if args.action == "check":
        client = make_client(settings)
        payload = await (client.readiness() if args.deep else client.health())
        return 0, {"check": "readiness" if args.deep else "health", "result": redact(payload)}
    if args.action == "devices":
        client = make_client(settings)
        devices = await client.list_devices()
        return 0, {
            "devices": [
                {
                    "serial": item.serial,
                    "state": item.state,
                    "model": item.model,
                    "product": item.product,
                    "busy": item.busy,
                }
                for item in devices
            ]
        }

    profile = args.profile or settings.artemis_profile
    device = args.device or (None if args.allow_auto_device else settings.artemis_device_serial)
    if not device and not args.allow_auto_device:
        raise ValueError(
            "运行任务必须通过 --device/ARTEMIS_DEVICE_SERIAL 指定测试设备，或显式 --allow-auto-device"
        )
    if not args.package and not args.allow_cross_app:
        raise ValueError(
            "运行任务必须用 --package 限定被测 App，跨 App 场景需显式 --allow-cross-app"
        )
    if profile == "flash" and (args.verification_level or args.explorer_mode):
        raise ValueError("verification-level/explorer-mode 仅适用于 pro 模式")
    if args.package:
        package_parts = args.package.split(".")
        valid_package = len(package_parts) >= 2 and all(
            part and part.replace("_", "a").isalnum() and not part[0].isdigit()
            for part in package_parts
        )
        if not valid_package:
            raise ValueError("--package 应为 Android applicationId，例如 com.example.app")
    timeout = args.timeout or settings.artemis_timeout_seconds
    if timeout <= 0 or timeout > 7200:
        raise ValueError("ARTEMIS 任务超时必须为 1 到 7200 秒")
    goal = read_goal(args.goal_file)
    if args.dry_run:
        return 0, {
            "dry_run": True,
            "profile": profile,
            "device_serial": device,
            "auto_device": device is None,
            "locked_app_package": args.package,
            "cross_app": args.allow_cross_app,
            "goal_file": str(Path(args.goal_file).resolve()),
            "goal_sha256": hashlib.sha256(goal.encode()).hexdigest(),
            "timeout": timeout,
        }
    client = make_client(settings)
    result = await client.run(
        goal,
        profile=profile,
        device_serial=device,
        expected_output=args.expected_output,
        locked_app_package=args.package,
        verification_level=args.verification_level,
        explorer_mode=args.explorer_mode,
        timeout=timeout,
    )
    payload = _result_payload(result)
    output = _artifact_path()
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    payload["artifact"] = str(output)
    return (0 if result.succeeded else 1), payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="ARTEMIS Android AI 探索客户端（正式回归仍用 Appium）"
    )
    parser.add_argument("--env", required=True, help="configs/environments 下的环境名")
    actions = parser.add_subparsers(dest="action", required=True)
    check = actions.add_parser("check", help="检查服务；--deep 同时检查设备和工具链")
    check.add_argument("--deep", action="store_true")
    actions.add_parser("devices", help="只读列出 ARTEMIS 主机可用 Android 设备")
    run = actions.add_parser("run", help="执行一次明确范围的 Android 探索任务")
    run.add_argument(
        "--goal-file", required=True, help="UTF-8 任务说明文件，避免长指令进入命令历史"
    )
    run.add_argument("--device", help="ADB device serial；默认读取 ARTEMIS_DEVICE_SERIAL")
    run.add_argument(
        "--allow-auto-device", action="store_true", help="明确允许服务自动选择空闲设备"
    )
    run.add_argument("--package", help="限制在指定 Android package 内")
    run.add_argument("--allow-cross-app", action="store_true", help="明确允许跨 App/系统设置操作")
    run.add_argument("--profile", choices=("flash", "pro"))
    run.add_argument("--verification-level", choices=("off", "final", "checkpoints", "strict"))
    run.add_argument("--explorer-mode", choices=("flash", "pro", "ultra"))
    run.add_argument("--expected-output", help="期望 ARTEMIS 返回的结构或证据描述")
    run.add_argument("--timeout", type=float, help="等待终态秒数；默认读取环境配置")
    run.add_argument("--dry-run", action="store_true", help="只检查范围和任务摘要，不连接服务/设备")
    args = parser.parse_args(argv)
    try:
        settings = load_settings(args.env)
        code, payload = asyncio.run(execute(args, settings))
        print(json.dumps(redact(payload), ensure_ascii=False, indent=2))
        return code
    except (OSError, RuntimeError, ValueError) as exc:
        print("ARTEMIS 操作失败：" + redact_text(str(exc)))
        return 2
    except Exception as exc:
        # 可选客户端有独立错误基类，但没有安装 extra 时不能静态导入。
        if exc.__class__.__module__.startswith("artemis_client"):
            print("ARTEMIS 客户端错误：" + redact_text(str(exc)))
            return 2
        raise
