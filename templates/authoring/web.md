# Web 录制/探索转 POM

录制与 observation 是页面行为证据，需求是业务预期；二者分开核对。

1. 识别页面边界与重复动作，优先复用现有 LoginPage/ItemsPage 等对象。
2. 录制的浏览器 launch/context/new_page/close 转交给 page fixture，不复制到测试。
3. role/label/test-id 经页面验证后放 Page Object；iframe 使用 frame_locator。
   CLI/MCP snapshot ref 是临时标识，不能写入长期定位器；必要时使用 CLI generate-locator
   验证可维护定位器。不要默认使用坐标、nth 或长 XPath。
4. 删除误操作、重复导航和录制中的明文密码；环境地址来自 base_url。
5. 登录和数据准备放 fixture；界面测试只执行要验证的动作，API 可用于准备和清理。
6. 使用 Playwright expect 等待可观察状态，必要时 expect_response 与动作配对。
7. 断言留测试中，除了提示文字，还验证当前需求的对象、状态、数量或接口结果。
8. CLI/MCP 当前页面行为是实现证据，不自动成为需求预期；冲突写入 unresolved。

新对象放 src/autotest/web/<业务名>.py，测试与 fixture 放 tests/web/<name>/。
测试使用 pytest.mark.web；公司业务禁止 demo 标记。参考 tests/web/test_items.py。
