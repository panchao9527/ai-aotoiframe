"""故意失败的教学用例：验证截图 / Trace / 视频 / AI 摘要是否能生成。

这个文件不在 tests/，不会进入默认测试集合。只在你要体验失败排查时显式运行：
python -m autotest run --suite web -- examples/failure_demo.py -k expected_web_failure
预期退出码为 1，表示这个错误断言被正确发现，而不是框架安装失败。
"""

import pytest
from playwright.sync_api import expect

pytestmark = [pytest.mark.web, pytest.mark.demo]


def test_expected_web_failure(page, base_url):
    page.goto(base_url)
    # 页面真实标题是“自动化练习系统”，故意检查另一个标题制造失败。
    expect(page.get_by_role("heading", name="这个标题故意不存在")).to_be_visible(timeout=500)
