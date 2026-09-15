# Web 用例需求：本仓库 iframe 练习页

请使用 `page` 和 `base_url` fixture 生成 Playwright 同步 pytest 用例。
这些是本仓库 demo 页面的约定；只用于 demo 环境，增加 `pytest.mark.demo` 和 `pytest.mark.web`。

- 打开 `base_url + "/iframe"`。
- 页面内有 `title="联系表单"` 的 iframe，可用 `page.frame_locator('iframe[title="联系表单"]')` 进入。
- iframe 内输入框的 label 是“留言”；按钮的 accessible name 是“提交留言”。
- 输入“自动化练习”，提交后 iframe 内 `role="status"` 元素应显示“已收到：自动化练习”。
- 使用 Playwright `expect` 等待并断言文本，不使用 `time.sleep`。
- 当前页面只是内存中的表单反馈，不写数据库；page fixture 会关闭页面。

无需账号。不要跨 iframe 在外层 page 查找 iframe 内部元素。
