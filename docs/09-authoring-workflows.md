# 09 · 源码、接口文档、录制到正式用例

重构增加 author 工作区与四类模板，保留 pytest/API/Web/App 执行能力。
命令可使用 uv run qa，也可使用 uv run python -m autotest。

## 1. 流程和产物

材料 → prepare → context.json / prompt.md → Agent 或模型 → 多文件回复 → generate →
draft → validate → 审查 → promote → 正式 pytest 回归。

每个任务保存在 artifacts/ai/任务名/：

| 文件 | 用途 |
|---|---|
| context.json / prompt.md | 脱敏材料、对象签名、模板和生成协议 |
| manifest.json | 类型、文件清单、未知项 unresolved、说明 |
| response.json | 编程助手保存的标准 JSON 回复，也可从其他位置导入 |
| draft/ | 按最终项目目录组织的 Python 草稿 |
| validation.json / .log | 指纹、静态错误、执行范围、环境、结果和日志 |
| validation-artifacts/ | 草稿运行的失败证据 |
| promotion.json | 实际入库文件与通过验证的指纹 |

prepare 不调用模型；传入 OpenAPI URL 时只下载指定文档。generate --response 导入 Agent 回复；
generate --send 才调用 .env 的 AI_BASE_URL/AI_MODEL，复用 chat/completions 适配器。
模型需能输出 prompt.md 规定的 files/unresolved/notes JSON。

validate 默认静态检查，不 import 草稿。--execute --env ENV 复制 src/tests/configs 到临时项目，
应用候选文件，并以 PYTHONPATH 指向该完整副本执行目标测试，正式目录不受影响。
目录隔离不是恶意代码沙箱，执行前需检查代码；静态规则也不证明业务正确或代码安全。

## 2. 接口单接口与业务场景

你提供需求 Markdown、前后端业务源码、原始 OpenAPI JSON/YAML。Swagger UI 网页本身
不能作为契约，应提供它加载的 JSON/YAML 地址。

以下示例不调用在线模型、不连接公司环境：

```powershell
uv run qa author prepare item-flow --kind api --mode scenario --requirement examples/authoring/api-requirement.md --openapi examples/authoring/openapi.json --source src/autotest/demo.py --operation "POST /api/items" --operation "GET /api/items/{id}" --operation "DELETE /api/items/{id}"
uv run qa author generate item-flow --response examples/authoring/responses/api-scenario.json
uv run qa author validate item-flow
uv run qa author validate item-flow --execute --env demo
# 检查业务预期、代码和结果后入库
uv run qa author promote item-flow --reviewed
```

examples/authoring/responses 是人工维护的离线协议样例，不冒充在线 AI 输出。
真实项目由编程助手阅读 prompt.md 生成回复，或者使用 author generate item-flow --send。
已有草稿不会被覆盖，全新生成用新的任务名；可直接修改 draft 后重新 validate。

--source 可重复。文件仅读取指定文件；目录必须加 --match 内容关键字，排除依赖/构建目录。
最多扫描 5000 候选、选取 24 个文件；支持 Python/Java/TS/Vue 等源码文本，不声称完成全局调用图。
单源码 128 KiB，OpenAPI 2 MiB，上下文 384 KiB，超限需缩小模块。
--operation 可重复，保留 components/definitions，但不会自动下载外部 $ref。
私有文档 --spec-auth-env OPENAPI_AUTHORIZATION 从环境变量读取完整认证头值，不写进材料。
URL 不接受内嵌凭据/查询串，不跟随重定向。

单接口选 --mode single，业务场景选 --mode scenario。
场景在一条独立测试内传递动态 ID，用 fixture/finally 清理，不依赖其他 test 顺序。
文档、需求、源码冲突写 unresolved，验证阻止未确认草稿进入执行或入库。

## 3. Web：人工录制或 AI 操作

一个终端启动 uv run qa demo --port 8765，另一个终端：

```powershell
uv run qa record web --name contact-record --url http://127.0.0.1:8765/iframe
```

关闭窗口后检查 artifacts/recordings/contact-record.py。原始录制可能含输入账号/数据，不提交 Git。
--storage-state 可使用已有登录态，状态文件不会进入 AI 上下文；--print-command 只打印不启动浏览器。

AI 操作时通过宿主 Playwright MCP/CLI 观察页面，把 URL 路径、iframe、真实 locator、
观察行为、需求预期和未知项记录到 observation.md，通过 --observation 提供。
工具在编程助手一侧，正式测试继续用 Python page fixture。

可直接验证附带 iframe 样例：

```powershell
uv run qa author prepare contact-flow --kind web --requirement examples/authoring/web-requirement.md --recording examples/authoring/web-recording.py
uv run qa author generate contact-flow --response examples/authoring/responses/web.json
uv run qa author validate contact-flow --execute --env demo
uv run qa author promote contact-flow --reviewed
```

产物为 ContactPage 和测试。录制里的固定 URL、浏览器启动和重复操作转为 fixture 与 POM。
真实项目先查已有签名，优先复用登录、导航和公共页面对象。

## 4. App 和已有用例维护

App 共用协议，详见 [App 编写](10-mobile-authoring.md)。维护已有文件使用正常分支、diff 与目标回归；
promote 只新增，不能覆盖已有文件、框架插件或配置。修复流程见 [工具与维护](11-tool-integration.md)。

## 5. 验收规则

- 必须存在测试函数与可识别断言；常见 sleep/skip/xfail/吞异常被阻止。
- 执行必须显式选环境；App 需要 --run-app。静态通过不会标记执行通过。
- execution.json 按 API/Web/App/unit 统计，框架单测不能顶替业务执行。
- qa run --suite api/web/app/all 默认要求目标业务实际执行；全跳过返回非零。
  初始化时可明确使用 --allow-empty，例如 qa run --suite web -- --env test --allow-empty。
- promote --reviewed 表示已审查业务预期和清理，同时必须有当前草稿通过执行的记录。
  内容、manifest 或依赖的源码/fixture/配置改动后指纹失效，必须重跑。
- 目标冲突整批拒绝，写入中断仅撤回本次新建文件。
- 模板位于 templates/authoring，项目 Skill 位于 .agents/skills。
  支持该目录的助手可加载；其他宿主直接读取 Skill/prompt.md，不要求更改全局配置。
