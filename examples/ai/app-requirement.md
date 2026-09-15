# App 用例需求模板：请替换为自有 App 真实契约

这只是与框架 LoginScreen 示例对应的契约，仓库没有 APK/IPA，不能声称已经通过真机验证。

可用的具体类和方法：

- `from autotest.mobile.screens import LoginScreen`
- `LoginScreen(app_driver, timeout=settings.app_wait_seconds)`
- `login.login(username, password)`
- `login.wait_until_logged_in()` 返回等待到可见的首页 WebElement。

业务前提：测试 App 已安装；每次用例启动处于未登录的登录页；测试环境有一个有效测试账号。
凭据只从 `APP_TEST_USERNAME` 和 `APP_TEST_PASSWORD` 环境变量读取，不在生成文件里填写真实值。
缺少凭据时用 `pytest.fail` 明确说明，别悄悄跳过。

先由人用 Inspector 验证以下 accessibility id 确实存在，或修改 LoginScreen 中的定位：

- 用户名：`login.username`
- 密码：`login.password`
- 登录：`login.submit`
- 首页：`home.screen`

生成一个用 `pytest.mark.app` 标记的登录用例，断言首页元素可见。
复用 app_driver fixture 管理会话，不另建 driver，也不在用例里退出共享会话。
用注释说明还需补充账号身份或首页业务信息断言；现在没有这些元素和字段的契约，不能虚构。
同一个契约分别通过 `--app-platform android` 与 `--app-platform ios` 执行；配置的定位必须先适配两端。
