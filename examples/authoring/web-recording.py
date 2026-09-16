"""教学录制素材；不属于 pytest 测试集合。"""

from playwright.sync_api import Page, expect


def recorded_flow(page: Page):
    page.goto("http://127.0.0.1:8765/iframe")
    contact = page.frame_locator('iframe[title="联系表单"]')
    contact.get_by_label("留言").fill("第一次自动化测试")
    contact.get_by_role("button", name="提交留言").click()
    expect(contact.get_by_role("status")).to_have_text("已收到：第一次自动化测试")
