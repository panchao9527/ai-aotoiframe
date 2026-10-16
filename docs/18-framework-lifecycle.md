# 18 · 框架边界、升级与用例维护

本框架定位是轻量、可迁移、由 AI 辅助编写的 pytest 框架。运行时仍是普通 Python；
AI 整理材料、生成草稿和辅助诊断，业务预期由需求与契约定义。

## 1. 代码归属与扩展点

| 归属 | 位置 | 扩展方法 |
| --- | --- | --- |
| 公共底座 | `src/autotest/` | 配置、客户端、fixture、数据、日志与证据；使用版本升级 |
| 公司对象 | `src/project_business/api/`、`web/`、`mobile/` | 编写 Service、Page、Screen，通过 import 或继承复用公共能力 |
| 公司用例 | `tests/api/`、`web/`、`app/` | 业务断言、参数化、项目 fixture 与数据准备 |
| 公司环境 | `configs/`、本地 `.env` / `.auth` | 配置地址、角色、会话和设备；敏感文件不提交 |
| 编写素材 | `artifacts/ai/`、`artifacts/recordings/` | 需求、观察、录制和草稿；审查后入库，不直接作为回归代码 |

标准鉴权继续使用 `role_clients`；特殊 SSO、Cookie、签名和原始认证头在公司 fixture
中创建/关闭 `ApiClient`，再注入 Service。Web 通过 `storage_state` 或项目登录 fixture，
App 通过 capabilities 与 Screen 继承。创建数据后立即调用 `data_factory.defer` 登记清理。
这些都是现有 Python 扩展点，不需要为每家公司在公共插件里增加判断分支。

新 AI 任务只允许新增 `project_business` 对象和业务测试。0.1 草稿仍可按旧协议读取；
已有对象维护使用普通 Git diff，`promote` 保持只新增文件。

## 2. 从新工程开始

```text
uv run --frozen qa project init --type api --name company-qa --output ../company-qa
```

导出只读取 `framework-assets.json` 的精确文件清单。临时公司代码、文档和新模板不会
因处于某个目录就被带出。公共文件的初始 SHA-256 与版本记录在 `.qa-framework.json`，
该文件应提交到公司仓库；它只记录文件名和散列，不包含凭据。

0.3 起公司工程通过 `--type api/web/app/all` 选择类型（默认 API），普通
`uv sync --frozen` 安装本端依赖，`qa run` / pytest 默认只运行本端业务。
工程类型保存在版本记录，升级采用同一渲染规则，保留本端依赖和执行范围。
源码框架仍默认完整开发依赖；需要临时补充其他端依赖时可显式选择：

```text
uv sync --frozen --extra web
uv sync --frozen --extra app
uv sync --frozen --group dev              # 完整框架开发环境
```

安装 Web 依赖后仍需安装浏览器，App 仍需准备服务和明确设备。
`qa doctor --suite api/web/app` 按端检查依赖；`qa project check --env ... --suite ...`
检查离线配置；业务权限、登录有效性必须由真实用例确认。
独立工程目录、CI 和 GitHub 分仓方式见 [独立工程指南](19-independent-projects.md)。

## 3. 升级已生成的工程

在**新版框架源码根目录**执行：

```text
uv run --frozen qa project upgrade --target ../company-qa
uv run --frozen qa project upgrade --target ../company-qa --apply
```

第一条只显示差异；第二条在整批无冲突时更新公共文件。执行前保证公司工程的现有
工作已提交，执行后检查 Git diff、依赖变化并重新安装和回归。

- 上游修改、本地仍是初始内容：更新。
- 仅公司修改、上游未修改：保留公司内容。
- 双方同时修改且内容不同：列出冲突，整批不写；不自动合并。
- 新公共文件与本地同名文件冲突：保留本地，停止整批升级。
- 上游删除：只删除仍与初始散列一致的公共文件。

版本号用于识别发行版，实际是否覆盖取决于逐文件散列。无冲突时版本记录最后更新；
普通文件写入错误会回滚本批文件。进程强杀/断电不保证事务恢复，需用 Git 检查和恢复。
不要手动改散列来跳过冲突。公共文件冲突时先比较新旧内容：接受上游版本后可重新运行；
需要保留公司的公共定制时先把定制迁入业务包/fixture，再应用升级。不要把带定制的
旧公共文件误当成已升级。配置、业务对象、测试和项目 README 都不由升级器覆盖。

`pyproject.toml`、`uv.lock` 属于公共依赖基线，公司追加依赖会与上游依赖更新产生冲突，
需按团队依赖策略人工审查。升级不运行迁移 SQL，不登录、不发起业务请求。

## 4. 已有 0.1 公司工程怎样迁移

旧工程没有生成基线，升级器会明确拒绝。不要猜测原版本的散列或直接覆盖旧工程。
先保留 Git 提交或备份，再生成全新 0.2 工程，将业务对象迁入 `project_business`，
调整 import，将公司测试、环境和必要 fixture 移入新工程，凭据通过本地文件单独恢复。
对比旧工程的公共定制并按上一节处理，再按端执行真实回归。

## 5. 变更后维护已有用例

```text
uv run --frozen qa author impact --changed src/project_business/api/orders.py --output artifacts/ai/impact.json
uv run --frozen qa run --suite api --path tests/api/orders/test_submit.py -- --env company_test
uv run --frozen qa evidence --run-dir artifacts/本次运行目录 --output artifacts/ai/triage.json
```

`--changed`、`--path` 均可重复；路径相对工程根目录，`--path` 支持 `文件.py::用例名`。
显式路径执行保留报告和实际业务执行门禁，不额外追加整个套件。

影响分析静态解析直接/间接 import、相对导入、包初始化和 conftest 作用域，不执行源码。
底座、依赖、环境变化建议完整回归。动态 import、字符串插件和外部需求变化可能漏召回，
输出是候选范围，不能作为“其余用例不受影响”的证明。
根据需求与运行证据修改已有 POM/Service/测试，检查 Git diff，先执行失败用例再执行
受影响集合；断言改变需记录依据，不用跳过、扩大成功条件或重试来隐藏产品失败。

## 6. 发行与验收

公共发行修改 `pyproject.toml`、`autotest.__version__`、资产清单版本和 `CHANGELOG.md`，
运行 `uv lock` 更新锁文件。新增公共资产必须显式加入清单，业务文件不能加入。
开发验证需要覆盖升级冲突、导出隔离和公共模块变更；
`scripts/verify_project.py` 会在临时新工程中执行最小 API 安装和本地业务冒烟。

CI 定义 Ubuntu Python 3.11/3.13、Windows 3.11、macOS 3.11 的验证矩阵，覆盖框架单测、
demo API/Web 与新工程安装。矩阵定义不是各系统已通过的证据，应以本次 Actions 结果为准。
App 真机、公司 CI 和在线 AI 调用需要各自的运行记录。

本次 Windows / Python 3.11 本地验证：公共测试集合 **367 passed、1 skipped**，跳过的是
未启用设备的 App 用例；包含框架单测、demo API/Web、xdist 双 worker 和 Web 草稿隔离执行。
另在临时新公司工程中完成 API 最小依赖安装、离线预检、实际本地 API 冒烟及报告生成；
Web 草稿已通过浏览器执行并入库到新业务包。Ruff 检查、格式检查与 Git diff 检查通过。
上述结果不代表 App 真机、公司系统、在线 AI 或远端矩阵已经验收。
