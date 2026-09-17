"""用例级资源登记：业务工厂创建资源，本模块只管理归属、清理顺序和结果。

资源成功创建后应立即 defer，随后再做业务断言。回调必须检查清理结果；返回了
HTTP 500 却不抛异常的回调无法被框架识别。进程被强制终止时不会保证执行清理。
"""

from collections.abc import Callable
from uuid import uuid4


class CleanupError(RuntimeError):
    """全部清理都尝试完后汇总失败，不泄露回调异常中的请求和凭据。"""


class DataFactory:
    def __init__(self):
        self.run_id = uuid4().hex
        self._pending: list[tuple[str, Callable[[], object]]] = []
        self.results: list[dict[str, str]] = []
        self._closed = False

    def unique(self, prefix: str = "test") -> str:
        """每次调用唯一；不要将姓名、手机号、Token 等敏感值作为前缀。"""
        return f"{prefix}-{uuid4().hex}"

    def defer(self, label: str, cleanup: Callable[[], object]) -> None:
        """登记本用例创建的资源；label 用业务类型名，避免携带真实业务数据。"""
        if self._closed:
            raise RuntimeError("数据工厂已清理，不能再登记资源")
        if not label or not callable(cleanup):
            raise ValueError("清理需要非空名称和可调用方法")
        self._pending.append((label, cleanup))

    def cleanup(self) -> None:
        """逆序清理关联数据；一个失败仍继续清理其他资源，不自动重试写操作。"""
        if self._closed:
            return
        self._closed = True
        failed = 0
        while self._pending:
            label, callback = self._pending.pop()
            try:
                callback()
            except BaseException as exc:
                # pytest.fail/skip 的结果异常并不继承 Exception；清理回调不能借它们
                # 中止剩余资源清理。用户中断或进程退出则必须立即向上传递。
                if isinstance(exc, (KeyboardInterrupt, SystemExit, GeneratorExit)):
                    raise
                failed += 1
                # 只保存异常类型。异常正文可能含没有标签的业务秘密。
                self.results.append(
                    {"resource": label, "status": "failed", "error_type": type(exc).__name__}
                )
            else:
                self.results.append({"resource": label, "status": "cleaned"})
        if failed:
            raise CleanupError(f"{failed} 个测试资源清理失败，详见本次 data-cleanup 报告")
