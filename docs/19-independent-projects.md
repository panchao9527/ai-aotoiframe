# 19 · API、Web、App 独立工程与 GitHub 组织

公共框架维护一份源码；公司测试按业务端独立组织，各自管理依赖、运行和 CI。
创建独立本地工程不需要先创建 GitHub 仓库。

## 1. 生成三个独立工程

在 ai-aotoiframe 框架源码目录执行：

```text
uv run --frozen qa project init --type api --name api-tests --output ../api-tests
uv run --frozen qa project init --type web --name web-tests --output ../web-tests
uv run --frozen qa project init --type app --name app-tests --output ../app-tests
```

未指定 `--type` 时默认 API；`--type all` 显式生成三端组合。输出目录必须是仓库外的
新目录，生成不覆盖旧项目，不复制真实公司配置、会话或附件，也不初始化 Git。

| 工程 | 业务目录 | 默认安装 | CI |
| --- | --- | --- | --- |
| API | `tests/api`、`project_business/api` | 公共 API 依赖 | API lane，无浏览器/设备安装 |
| Web | `tests/web`、`project_business/web` | 公共 API + Playwright | Web lane，安装浏览器 |
| App | `tests/app`、`project_business/mobile` | 公共 API + Appium | Android/iOS 设备 lane，串行执行 |

每个工程有独立 `pyproject.toml`、锁文件、环境配置、冒烟预期、README、GitHub Actions
和 Jenkinsfile。公共源码中仍保留三端执行能力与框架单测，作为可升级底座；
这些模块不等于把其他端的公司业务用例放进本工程，也不会默认安装其他端依赖。
`templates/` 中的通用参考材料不参与业务用例默认收集。

## 2. 每个工程分别安装、配置、执行

进入对应工程后运行 `uv sync --frozen`，无需再加 `--extra` 或 `--no-dev`。
Web 首次安装还需 `uv run --frozen python -m playwright install chromium`。
填写本工程 README 指定的配置后：

```text
uv run --frozen qa doctor
uv run --frozen qa project check --env company_test --suite all
uv run --frozen qa run -- --env company_test
```

API/Web 工程最后一条直接执行本端测试；App 工程必须显式带设备执行参数：

```text
uv run --frozen qa run -- --env company_test --run-app --app-platform android --app-caps configs/devices/android.yaml -n 0
```

默认 `qa run`、`qa run --suite all`、直接 pytest 都只执行本工程业务。
框架单测独立，开发公共底座时先 `uv sync --group dev --frozen`，再明确选择 unit。
部分跳过或仅收集不能作为完整业务验收；App 未提供设备时不宣称真机通过。

## 3. Web/App 需要接口造数时

直接在各自工程的 fixture 中使用 `ApiClient`、`role_clients` 和 `data_factory`。
需要复用业务造数逻辑时，在本工程增加 API 辅助模块，或由团队发布专用业务辅助包。
每条用例独立造数并登记清理；禁止通过导入另一个测试工程、依赖另一条用例先执行，
或从其他工程报告中读取固定任务 ID 来建立前置条件。

## 4. GitHub 要不要创建三个仓库

框架仓库 `ai-aotoiframe` 继续承载公共底座和模板，拆分功能在此维护。
公司工程可以各建一个公司批准的私有仓库，适合团队、权限、设备和发布周期不同的情况；
同一团队也可以一个私有仓库下放三个独立工程，每个目录分别安装与配置 CI 工作目录。
采用哪种方式由公司代码托管和权限要求决定，拆分本地工程不依赖新仓库。

生成的 GitHub 工作流是手动触发模板，尚需配置公司 Environment、Secret 和可访问
公司系统的 runner。App lane 需明确设备；Jenkins App lane 使用跨 job 共享设备锁。
公司业务代码、真实账号和附件不要推送到公共框架仓库。

## 5. 升级和已有项目

升级仍从新版公共框架源码目录执行 `qa project upgrade --target 工程目录`，先预览再应用。
版本基线记录工程类型，公共升级保留本端默认配置，不重建其他端业务目录，
不覆盖工程 README、环境、业务对象和根 CI 文件。
旧的 0.2 工程未记录类型，继续按原始三端布局升级；要改成单端，先生成独立新工程，
迁入本端业务、fixture 和本地配置并验证，不自动删除已有测试。
