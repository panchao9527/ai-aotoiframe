"""iframe 内元素要先 frame_locator；不能把主页面 Locator 直接用于子页面。"""

import pytest
from playwright.sync_api import expect

pytestmark = [pytest.mark.web, pytest.mark.demo]


def test_submit_inside_iframe(page, base_url):
    page.goto(base_url + "/iframe")
    contact = page.frame_locator('iframe[title="联系表单"]')
    contact.get_by_label("留言").fill("第一次自动化测试")
    contact.get_by_role("button", name="提交留言").click()
    expect(contact.get_by_role("status")).to_have_text("已收到：第一次自动化测试")
