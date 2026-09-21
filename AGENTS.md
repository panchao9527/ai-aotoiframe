# 项目维护说明

这是 Python 3.11 的 pytest 自动化测试框架，覆盖 HTTPX 接口、Playwright Web、
Appium Android/iOS。中文注释和 docs 面向刚开始写 Python 的测试工程师。

## 修改时遵循的结构

- 底层能力在 `src/autotest/`；业务用例在 `tests/api/`、`tests/web/`、`tests/app/`。
- 元素定位集中在 Page/Screen 对象，业务断言保留在测试函数中。
- 环境优先级：CLI 环境名 > TEST_ENV；系统变量 > .env > YAML > 默认值。
- 练习系统用例标记 `demo`，公司用例不要加 `demo`。不要自动把公司环境换回 demo。
- 新增用例以具体预期验证业务。修复失败需基于需求或页面证据，保留有意义的断言。
- AI 草稿保存到 `artifacts/ai/`，需要检查后再放进正式测试目录。
- 新增用例使用 `author prepare/generate/validate/promote` 工作流；模板在
  `templates/authoring`，项目编写与维护 Skill 在 `.agents/skills`。
- 用户已授权编写、执行和入库时，完成业务审查和验证后持续完成，不重复索取授权。
- 需求定义业务预期；源码与页面记录提供实现证据，冲突写入 `unresolved`。
- 草稿执行的临时目录隔离不是安全沙箱；执行前检查代码。`promote` 只新增文件，
  已有代码维护使用普通 Git diff 与目标回归。
- 测试数据独立创建和清理；界面同步使用显式等待，不能用固定 sleep 掩盖问题。
- AI 页面探索默认使用 `qa browser --session <任务名>` 的固定 Playwright CLI；复杂长会话才用
  Playwright MCP，网络/控制台/性能深度诊断才用 Chrome DevTools MCP。临时 ref 不进入 POM。
- Android AI 探索可用独立 ARTEMIS 主机；必须明确测试设备和 package，结果仅作 observation。
  正式 App 用例仍使用 Appium；不自动安装 Helper、修改全局 MCP 或操作个人手机。
- `.env`、真实账号、Token、App 包、报告不提交；新增配置同步更新示例和中文手册。

## 本地验证

```text
uv sync --frozen
uv run python -m playwright install chromium
uv run ruff check .
uv run ruff format --check .
uv run python -m autotest run --suite all -- -n 2
```

Windows 也可直接使用 `.venv/Scripts/python.exe`，Linux/Mac 使用 `.venv/bin/python`。
根据改动范围运行对应测试；底层配置/报告变更需覆盖框架单测。
App 默认跳过，启用前须有具体应用与设备；跳过和 mock 验证不代表真机验证通过。
`examples/failure_demo.py` 是故意失败的教学用例，不属于日常默认集合。
CI、真实设备、在线 AI 没有运行时，在交付说明中明确实际验证范围。
