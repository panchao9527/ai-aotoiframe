"""Page Object 把页面定位与操作集中起来，业务断言留在测试中。

优先用角色、标签、test-id。不要靠长 XPath、坐标或固定 sleep。
"""

from playwright.sync_api import Page


class LoginPage:
    def __init__(self, page: Page):
        self.page = page
        self.username = page.get_by_label("用户名")
        self.password = page.get_by_label("密码", exact=True)
        self.submit = page.get_by_role("button", name="登录", exact=True)
        self.error = page.get_by_role("alert")

    def open(self, base_url: str) -> None:
        self.page.goto(base_url + "/")

    def login(self, username: str, password: str) -> None:
        self.username.fill(username)
        self.password.fill(password)
        self.submit.click()


class ItemsPage:
    def __init__(self, page: Page):
        self.page = page
        self.heading = page.get_by_role("heading", name="我的项目")
        self.name_input = page.get_by_label("项目名称")
        self.create_button = page.get_by_role("button", name="创建项目")

    def create(self, name: str) -> None:
        self.name_input.fill(name)
        self.create_button.click()

    def item(self, name: str):
        """返回 Locator，让调用者使用 expect(...).to_be_visible() 自动等待。"""
        return self.page.get_by_test_id("item-name").filter(has_text=name)
