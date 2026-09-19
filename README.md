<p align="center">
  <img src="asset/weread2notion-banner.svg" alt="NotionHub" width="100%">
</p>

<p align="center">
  <img alt="免费开源" src="https://img.shields.io/badge/%E5%85%8D%E8%B4%B9%E5%BC%80%E6%BA%90-Free%20%26%20Open%20Source-brightgreen?style=for-the-badge">
</p>

<p align="center">
  <a href="https://github.com/wslh/NotionHub/actions/workflows/ci.yml"><img alt="Tests" src="https://github.com/wslh/NotionHub/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://github.com/wslh/NotionHub/actions/workflows/weread.yml"><img alt="Sync workflow" src="https://github.com/wslh/NotionHub/actions/workflows/weread.yml/badge.svg"></a>
  <a href="https://github.com/wslh/NotionHub/tree/v1.0.0"><img alt="Version" src="https://img.shields.io/github/v/tag/wslh/NotionHub?label=version"></a>
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/github/license/wslh/NotionHub"></a>
  <a href="https://github.com/wslh/NotionHub/stargazers"><img alt="Stars" src="https://img.shields.io/github/stars/wslh/NotionHub?style=flat"></a>
</p>

<p align="center">
  <a href="https://app.notion.com/p/wph/Template-3a329affe5af800b8581f98b71e948fb">复制 Notion 模板</a> ·
  <a href="#开始使用">开始使用</a> ·
  <a href="https://github.com/wslh/NotionHub/issues/new/choose">反馈问题</a>
</p>

# NotionHub

> 本项目基于 [hodgekou/notionhub](https://github.com/hodgekou/notionhub) 派生修改并独立发布（当前仓库：`wslh/NotionHub`），遵循其开源许可证，原作者保留相关版权。

> **永久免费、完整开源。** 将你的微信读书书架、阅读进度、章节、划线、个人想法和阅读统计，自动同步到一套完整的 Notion 阅读管理模板。

无需在电脑上长期运行程序。完成一次配置后，GitHub Actions 会每天自动同步。

<p align="center">
  <a href="https://app.notion.com/p/wph/Template-3a329affe5af800b8581f98b71e948fb">
    <img src="asset/notion-dashboard.png" alt="NotionHub 同步后的 Notion 阅读仪表盘" width="100%">
  </a>
</p>

<p align="center"><sub>同步后的 Notion 首页：原生阅读图表、书架状态、统计、分类、作者与设置。</sub></p>

## 为什么使用它

- **无需服务器**：只需 Notion、GitHub Actions 和微信读书 API Key。
- **一次配置，自动运行**：每天定时同步，也支持随时手动触发。
- **Notion 原生体验**：使用数据库、视图、分组、公式和 Chart，不依赖外部 Embed 服务。
- **划线直接进入书籍正文**：按章节整理划线和个人想法，不把内容做成大量 Tag。
- **书架口径清晰**：以微信读书当前书架为权威来源，人工“读完”标记决定已读状态。
- **每日阅读快照**：每天保存每本书的累计时长、当日新增时长、进度、状态和当前章节。
- **安全重建**：全量同步前导出 JSON 备份，再归档旧记录。

如果这个项目帮你省下了配置和维护时间，欢迎点击右上角 **Star**。这会帮助更多有相同需求的人发现它。

## 开始使用

### 第一步：复制 Notion 模板

打开下面的模板页面，然后点击右上角的 `Duplicate`，将它复制到你自己的 Notion Workspace：

[复制 NotionHub Template](https://app.notion.com/p/wph/Template-3a329affe5af800b8581f98b71e948fb)

复制完成后，请保存新页面的完整 URL。后面配置 `NOTION_PAGE` 时会用到它。

> 请使用 Duplicate 后的新页面，不要填写上面的公共模板地址。每次 Duplicate 都会生成一个新的页面 ID。

### 第二步：创建并连接 Notion Integration

1. 打开 [Notion Integrations](https://www.notion.so/profile/integrations)。
2. 点击 `New integration`。
3. 名称填写 `NotionHub`。
4. Workspace 选择刚才复制模板所在的 Workspace。
5. 在 Capabilities 中启用：
   - `Read content`
   - `Insert content`
   - `Update content`
6. 保存并复制生成的 Internal Integration Secret，后面将它配置为 `NOTION_TOKEN`。
7. 返回 Duplicate 后的 Notion 页面，点击右上角 `••• → Connections`，添加 `NotionHub`。

Integration 必须连接到最外层的“微信读书”模板页面，这样才能访问页面内的书架和统计数据库，以及各书籍页面中的章节化划线与笔记。

### 第三步：Fork 项目并配置 Secrets

点击 GitHub 页面右上角的 `Fork`，将本项目 Fork 到你自己的 GitHub 账号。

进入你 Fork 后的仓库，然后打开：

`Settings → Secrets and variables → Actions → New repository secret`

依次创建以下三个 Repository secrets：

| Secret 名称 | 填写内容 |
| --- | --- |
| `WEREAD_API_KEY` | 你的微信读书 Gateway API Key，可前往 [微信读书助手](https://weread.qq.com/r/weread-skills) 获取 |
| `NOTION_TOKEN` | 第二步创建的 `NotionHub` Integration Secret |
| `NOTION_PAGE` | 第一步 Duplicate 后的新 Notion 页面完整 URL |

Secret 名称必须完全一致，并注意以下对应关系：

- `NOTION_TOKEN` 所属的 Integration 必须是你在页面 Connections 中添加的同一个 Integration。
- `NOTION_PAGE` 必须是你自己的 Duplicate 页面，不能使用公共 Template 页面。
- 不要把任何 Token 或 API Key 写进 README、代码或 `.env` 后提交到 GitHub。

### 第四步：测试同步

1. 打开你 Fork 仓库的 `Actions` 页面。
2. 在左侧选择 `weread sync`。
3. 点击 `Run workflow`。
4. 首次测试保持 `full` 未勾选。
5. 再次点击绿色的 `Run workflow` 开始同步。

等待 `Sync` 任务显示绿色勾号后，刷新 Duplicate 后的 Notion 页面。你的书架、阅读进度、阅读时长和统计数据将出现在模板中；划线和笔记会按章节直接写入对应书籍的正文，不需要单独的章节数据库。

首次运行新版同步器时，会在主页底部自动创建“阅读快照”数据库。每天每本当前书架条目最多生成一条快照；同一天重复运行会更新原记录，并累计当天新增阅读时长。历史快照不会因全量同步或书籍移出书架而删除，可用于制作单书阅读趋势、每日阅读书目和进度变化图表。

微信读书当前书架是同步范围的唯一依据。书籍从微信读书书架移除后，下一次成功同步会将它在 Notion 中的书籍页面、划线和笔记移入回收站。

“已读”状态以微信读书书架中的人工“读完”标记为准，不根据阅读进度是否达到 100% 推断。未标记读完但已有阅读记录的书会显示为“在读”。

工作流还会每天自动运行一次。只有需要备份并重新生成全部数据库记录时，才使用 `full` 模式。

## 命令行与维护

除 GitHub Actions 自动运行外，也可在本机用 `weread2notion` 命令操作，需要 `WEREAD_API_KEY`、`NOTION_TOKEN`、`NOTION_PAGE` 三个环境变量。

| 命令 | 说明 |
| --- | --- |
| `weread2notion sync` | 增量同步（默认）：只更新变化书籍，保留 Notion 页面结构，并自动清理移出书架的书 |
| `weread2notion sync --full` | 全量更新：先导出 JSON 备份再归档重建全部记录；完成后终端会打印备份路径与回滚命令 |
| `weread2notion sync --dry-run` | 只读预览同步计划，不写入 |
| `weread2notion sync --quiet` | 关闭阶段进度打印，仅输出最终结果 |
| `weread2notion check` | 校验模板数据库与属性 |
| `weread2notion repair` | 检测数据不一致（设置库缺失、阅读快照缺失、正文版本过期、孤立笔记/划线、当日快照缺失），仅输出报告 |
| `weread2notion repair --apply` | 在检测基础上执行修复（重建设置/快照库、重生成过期正文、归档孤立记录、补齐当日快照） |
| `weread2notion restore <备份.json>` | 从全量备份 JSON 取消归档被回收的页面，用于全量同步失败后的回滚 |
| `weread2notion status` | 显示工作区健康状态、待修复项与同步版本（退出码 0=健康，1=待修复） |
| `weread2notion export --target books --format csv` | 导出书架为 CSV/Markdown（`--target snapshots` 导出阅读快照，`--out` 指定路径） |
| `weread2notion sync --book <id>` / `--tag <tag>` | 选择性同步：只处理指定书籍或标签（可重复传参） |
| `weread2notion sync --verbose` | 开启调试日志（同时写入 `logs/`） |
| `weread2notion sync --no-self-heal` | 关闭失败自愈（默认失败会自动 `repair --apply` 后重试一次） |
| `weread2notion sync --source kindle:/MyClippings.txt` | 使用 Kindle 标注文件作为数据源（`apple:/export.csv` 同理；已内置 weread/local/kindle/apple 四种来源，均可扩展） |
| `weread2notion insights` | 汇总阅读洞察：总时长、连续/最长阅读天数、Top 书目、日均 |

自动同步频率由 `.github/workflows/weread.yml` 中的 `cron` 控制（默认每日北京时间 04:00）；`workflow_dispatch` 支持手动触发并可选择 `full` 与重试次数，失败时自动创建 Issue 通知。此外该工作流支持 `repository_dispatch`（`event_type: weread-sync`），可被外部系统以 Webhook 方式近实时触发。除微信读书外，其它数据源由 `.github/workflows/sync.yml` 负责（默认每日北京时间 05:00 对所有「已配置」插件执行 `plugins sync --all --exclude weread`，同样支持手动选择单一插件与 `event_type: notionhub-sync` Webhook 触发）。两者都使用本仓库自身的 `action.yml` 封装、在本仓库的 GitHub Actions 上运行，不依赖 NotionHub 云端运行器。

### 增量策略与去重

同步不是简单新增，分两级跳过无效写入：

1. **记录级**：先按唯一 ID 匹配已有记录，未命中才创建。各库使用的键为——书架 `BookId`、阅读快照 `SnapshotKey`（`日期:BookId`）、日/周/月/年统计为标题（如 `2026-03-11`）、阅读记录为 `时间戳`、作者/分类为名称。
2. **字段级**：命中已有记录后，逐属性比对现有值与待写入值（标题、富文本、数字、勾选、状态、多选、日期、关联、链接各有对应的归一化比较），**只对真正变化的属性发起更新**；完全无变化时连请求都不发。

字段级 diff 覆盖所有写入路径：书架、阅读快照、日/周/月/年统计、阅读记录，统一由 `NotionWorkspace.changed_properties()` 计算差异。

三点边界需要注意：

- 当拿不到目标页的现有属性时（例如调用方只传了 `existing_id`），会退回整页属性覆盖，不会为了做 diff 额外发一次读取请求。
- 无法可靠比较的属性类型一律按「有变化」处理，宁可多写一次也不会漏更新；`formula`、`rollup`、`created_time` 等由 Notion 计算的只读属性不参与写入。
- 现有记录里缺失的属性（例如模板刚新增的字段）视为需要写入。

书籍是否进入本次处理由书级门控决定（对比 `Sort` 时间戳与 `同步版本`），这不是字段级比较，只是避免逐本拉取详情。

## Edge / Chrome 浏览器扩展

项目自带一个 **MV3 浏览器扩展**（根目录的 `manifest.json` + `background.js` 服务工作线程 + `panel.html` / `panel.css` / `panel.js` 控制面板 + `icons/`），直接在 Edge 或 Chrome 加载解包目录即可使用。点击工具栏 **N** 图标会在**新标签页**打开完整控制面板（而非弹窗）。

> 扩展只是「触发器 + 配置界面」。**真正的同步逻辑由本机 `notionhub` CLI 执行**，请先 `pip install -e .` 并在终端配置好 `.env`（见上方四步流程）。

**安装步骤（Edge）**：

1. 打开 `edge://extensions/`，开启右上角"开发人员模式"。
2. 点击"加载解压缩的扩展"，选择本项目根目录（含 `manifest.json` 的目录）。
3. 工具栏出现 **N** 图标即成功。

**打开控制面板的方式**：

- 点击工具栏 **N** 图标 → 自动在新标签页打开 `panel.html`。
- 快捷键 `Ctrl+Shift+H` → 同样打开面板。
- 快捷键 `Ctrl+Shift+S` 或任意页面右键 → "Copy 'notionhub sync --quiet'" → 直接把同步命令复制到剪贴板（不发任何请求）。

**控制面板四个标签页**：

1. **同步服务（默认）**：以卡片墙展示全部 33 个内置插件，支持「搜索」框 +「分类」下拉（阅读/播客/笔记/影音/效率/学习/待办/运动/其他）筛选；每张卡片的「使用文档」链到 GitHub 对应接入说明；`Copy sync` 按钮一键复制 `notionhub sync --quiet`，回终端粘贴运行即可同步。卡片上会显示「已配置 / 未配置」状态，点击卡片打开右侧**配置抽屉**（`Esc` 或点遮罩关闭）：
   - **WeRead** 提供完整四步配置：**Notion 模板**（填 Duplicate 后的页面 URL）、**微信读书**（填 `wrk_` 开头的 Gateway API Key）、**Notion 接入**（填 `ntn_` / `secret_` 开头的 Integration Token）、**同步设置**（阅读统计起始年份 + `.env` 预览，可一键复制真实值粘贴到项目 `.env`）。保存时会校验页面 ID 与 Token 前缀；底部「开始同步」会先保存再把 `notionhub sync --quiet` 复制到剪贴板。细粒度开关（划线/快照/阅读记录/人物卡片/AI 导读）仍在 Notion「设置」数据库中勾选。
   - **模板校验**：Notion 模板页 URL 旁新增「验证模板」按钮，保存配置时也会自动校验。插件会调用 Notion API 遍历该页面下的子数据库，确认含全部 7 个必需数据库（书架/日/周/月/年/分类/作者）；若不是标准模板会立即提示缺少哪些库，避免同步时才报「模板缺少数据库」。> 注意：NotionHub 集成不能自动 duplicate 未共享给它的公共模板，官方模板仍需手动 Duplicate 并在页面 `••• → Connections` 中连上你的 integration。
   - 其余插件暂无可视化配置页，抽屉会提示查看「使用文档」。

**三种同步触发方式**：

1. **本机同步**（默认）：底部「开始同步」经本机桥接直接运行 `notionhub sync --quiet`，日志实时展示在抽屉里。
2. **GitHub Actions 自托管同步**（推荐，无需 notionhub-runner）：直接用本仓库自带的 GitHub Actions 工作流跑同步，代码与逻辑全部来自本仓库（经根目录 `action.yml` 封装），不依赖 NotionHub 云端运行器，也不使用 `<SERVICE>_CONFIG` 这类集中凭证。
   - 微信读书：`weread.yml`（每天北京时间 04:00 定时，或手动 `workflow_dispatch` / Webhook `repository_dispatch` 触发）。
   - 其它数据源：`sync.yml`（每天北京时间 05:00 定时对「所有已配置插件」执行 `plugins sync --all --exclude weread`；也可手动选择单一插件，或经 Webhook `event_type: notionhub-sync` 触发）。
   - 各数据源凭证直接存为各自独立的 Repository Secret（如 `GH_TOKEN`、`DOUBAN_COOKIE`、`FLOMO_EXPORT`），未配置的插件会被自动安全跳过，不会报错。
3. **自有 Worker（长毛象）**：在「Worker（长毛象）」标签页启动一个常驻进程 `notionhub worker`，按固定间隔（默认 5 分钟）在本机自动触发同步，完全脱离 GitHub。可在 `.env` 配置 `MASTODON_INSTANCE` + `MASTODON_ACCESS_TOKEN`，让每轮同步结果以「嘟文」发布到你的长毛象（Mastodon）账号作为播报与心跳。面板可直接启停该 Worker 并实时查看运行状态。

**本机桥接（可选，推荐）**：默认面板只把配置存在浏览器、并把 `.env` 内容复制到剪贴板。装了桥接后，面板能**直接读写项目根目录的 `.env` 并一键运行同步**：

```powershell
powershell -ExecutionPolicy Bypass -File native\install.ps1   # 自动探测 Python / 扩展 ID，写入 HKCU 注册表
powershell -ExecutionPolicy Bypass -File native\uninstall.ps1 # 卸载
```

安装后重新加载扩展，抽屉里会显示「本机桥接：已连接」+ 实际 `.env` 路径：保存配置即写入 `.env`；第 5 步「运行同步」直接后台执行 `notionhub sync --quiet`，输出追加到 `logs/native-sync.log` 并每 3 秒自动刷新。未安装时自动降级为剪贴板模式，不影响其它功能。

桥接由 `native/notionhub_host.py` 实现（Chrome Native Messaging，4 字节长度前缀 + JSON），支持 `ping` / `env_read` / `env_write` / `sync_start` / `sync_log` / `worker_start` / `worker_stop` / `worker_status`。安全性：可写 key 为白名单（非法 key 直接拒绝整次写入），`.env` 路径由安装脚本固定（`--env-file`），同步参数只允许 `--quiet/--full/--dry-run/--verbose/--no-self-heal`，无法被网页劫持去写任意文件。
2. **账号**：Notion OAuth 登录入口。**已内置 NotionHub 官方 Public Integration 的 Client ID 与 Client Secret**，因此无需任何填写——直接点「登录账号」即跳转 **Notion 官方授权页**（选 workspace + 授权模板/页面），授权后由扩展直连 `api.notion.com/v1/oauth/token` 用内置凭据换 `access_token` 并自动复制模板——前提是 NotionHub 集成在 Notion 后台 `Configuration` 里配置了「模板页 URL」（指向 `https://app.notion.com/p/wph/Template-3a329affe5af800b8581f98b71e948fb`），且你在授权弹窗里选择「复制模板」。授权成功后，扩展会自动把复制出的页面设为 WeRead 同步目标并写入 `.env`，无需手动粘贴。结果存到本机 `chrome.storage.local`。高级设置里的「自定义 OAuth 应用（可选）」可覆盖为**你自己的** Public Integration（填写自己的 Client ID + Secret 同样直连 Notion 换 token）。GitHub 卡片为外链入口。
3. **通知**：4 个渠道卡片（Telegram / Bark / 飞书 / Webhook），点选其一为默认，填写 Bot Token / Chat ID（带眼睛显隐切换）后「保存」或「删除」。（注：当前仅保存配置，实际消息推送逻辑尚未在扩展内实现。）
4. **关于**：列出 33 个内置插件、CLI 安装方式、GitHub Actions 自动同步说明、安全声明。

**安全说明**：

- 扩展请求的 host permission 仅限 `api.notion.com`、`api.github.com`、`github.com`、`weread.qq.com`；同步触发通过本仓库自带的 GitHub Actions 工作流（`weread.yml` / `sync.yml`）以 `workflow_dispatch` 运行，全程只与 `github.com` 通信，不访问任何第三方域名，也不依赖外部 `notionhub-runner`。
- **凭据与 Token（微信读书 API Key、Notion Integration Token、GitHub Token、OAuth Client Secret）只写 `chrome.storage.local`**，不会进入 `chrome.storage.sync`，因此不会随浏览器账号跨设备同步。早期版本误写入 sync 的凭据会在读取时自动迁移回 local。
- 非敏感的普通配置（如统计起始年份）使用 `chrome.storage.sync` 以便跨设备同步；sync 写入失败时自动回退 local。
- 真正的同步仍由本机 `notionhub` CLI 执行，扩展只是便捷触发器与配置面板。

## VS Code 扩展

项目自带一个轻量 VS Code 扩展包装（根目录的 `package.json` + `extension.js`），把上面的命令变成命令面板里可直接点选的操作。

1. **安装 Python 包**（让 `notionhub` 命令可用）：
   ```bash
   pip install -e .
   ```
2. **复制项目到 VS Code 扩展目录** 或在 VS Code 中按 `Ctrl+Shift+P` → `Developer: Install Extension from Location` 选这个文件夹。
3. **命令面板**（`Ctrl+Shift+P`）里会出现 5 条以 `NotionHub:` 开头的命令：
   - `NotionHub: Sync Now` — 触发增量同步（带 `--quiet`，输出在 Output 面板的 `NotionHub` 频道）。
   - `NotionHub: Check Databases` — 校验 Notion 模板库结构。
   - `NotionHub: Show Workspace Status` — 打印工作区健康 JSON。
   - `NotionHub: List Plugins` — 列出全部 33 个内置插件及配置状态。
   - `NotionHub: Open Settings` — 跳到 VS Code 设置中的 NotionHub 节点。

可配置项（`File → Preferences → Settings → notionhub`）：

| 项 | 默认值 | 说明 |
| --- | --- | --- |
| `notionhub.pythonPath` | `notionhub` | 调用 Python CLI 的命令（保证在 PATH 中）。 |
| `notionhub.envFile` | 空 | 可选的 `.env` 绝对路径，会以 `NOTIONHUB_ENV_FILE` 透传给 CLI。 |
| `notionhub.workingDirectory` | 空 | 调用 CLI 时的工作目录；留空则使用打开的工作区根目录。 |

扩展没有任何 Node 端业务逻辑，只是把 CLI 子进程 stdout/stderr 实时流到 Output 面板并以通知报告退出码——所有数据/同步逻辑都跑在已有的 Python 实现里。

## 功能增强总览

本项目除基础同步外，还在以下维度持续完善：

- **核心功能**：选择性同步（`--book`/`--tag`）、设置库四项范围开关（快照/记录/人物卡片/AI 导读）真正可配置且变化会触发全量重算、按书籍修复。
- **用户体验**：分级日志与 `logs/` 文件、`--verbose`/`--quiet`、`status` 健康概览、`export` 数据可携、`insights` 阅读洞察。
- **性能与稳定性**：书籍 bundle 并发拉取（`CONCURRENCY`）、指数退避+抖动+`Retry-After`、检查点续传。
- **安全性**：`NOTION_TOKEN` 格式校验、日志/输出密钥脱敏、最小权限说明。
- **数据管理与分析**：数据质量计数、CSV/Markdown 导出、阅读快照对比、`insights` 洞察汇总与 `snapshot_diff` 增量。
- **系统集成与扩展性**：Webhook（`repository_dispatch`）触发、`action.yml` 可配置 `verbose`/`concurrency`、`sources.py` 数据源插件抽象（已内置 `weread`/`local`/`kindle`/`apple` 四种来源，`--source` 切换，可继续扩展）。
- **自动化与智能化**：失败自愈（`repair`+重试）、版本自检；可选 AI 书摘摘要真正调用 OpenAI 并写入 Notion「AI 导读」块（`OPENAI_API_KEY`）。
- **运营与维护**：失败 Issue 通知、匿名遥测（`WEREAD2NOTION_TELEMETRY=1`，默认关闭）、CI 测试矩阵。

> 涉及外部凭证的能力（AI 摘要、遥测）均为**默认关闭、优雅降级**：未配置时不影响任何同步流程。

## 注意：同步内容可能覆盖 Notion 中的手动修改

NotionHub 会把微信读书作为同步数据的来源。下列内容由同步器管理，如果你直接在 Notion 中修改，后续普通同步或全量同步可能使用微信读书返回的数据重新更新或覆盖：

- 书架数据库中的书名、作者、分类、阅读状态、阅读进度、阅读时间等同步属性
- 日、周、月、年等阅读统计数据
- 书籍页面中标记为“由 NotionHub 自动同步”的划线和笔记区域
- `同步配置版本（不可删除）` 系统字段

你自行添加在自动同步区域之外的普通页面内容，普通增量同步会尽量保留；模板主页的布局、分栏、数据库视图、筛选、排序和图表也不会被同步器重写。但 `full` 全量同步会备份并归档旧数据库记录，再重新创建记录，因此不要把需要长期保留的私人内容只存放在这些自动管理的数据库记录中。

“设置”数据库中的用户配置会被同步器读取，不会被系统默认值反复覆盖；只有系统维护的 `同步配置版本（不可删除）` 会在成功同步后自动更新。

## 个性化同步设置

最新模板包含一个“设置”数据库，其中的“同步设置”页面用于调整同步行为。每次同步都会先读取这些属性：

| 设置 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `阅读完成进度强制改为100%` | Checkbox | 关闭 | 已人工标记读完的书在 Notion 中显示为 100%，不修改微信读书真实进度 |
| `只同步我的书架书籍` | Checkbox | 开启 | 仅保留微信读书当前书架中的书籍；其他书籍及自动同步内容移入 Notion 回收站 |
| `同步划线和笔记` | Checkbox | 开启 | 将划线和个人想法按章节写入书籍正文 |
| `同步快照` | Checkbox | 开启 | 生成每日/周期阅读快照；关闭可节省 Notion 配额 |
| `同步阅读记录` | Checkbox | 开启 | 同步阅读记录（日/周/月/年）；关闭则跳过该阶段 |
| `同步人物卡片` | Checkbox | 开启 | 生成书中人物卡片；大书目可关闭以加速同步 |
| `生成 AI 导读` | Checkbox | 关闭 | 需配置 `OPENAI_API_KEY`；开启后为每本书写入一段 AI 导读（可选） |
| `阅读统计起始年份` | Number | 2023 | 从该年份开始生成阅读统计 |

配置值遵循统一规则：开关只使用 Checkbox 的 `true / false`；数值只使用 Number 的实数，例如 `-1`、`0`、`1`、`2` 或 `0.5`。不要使用 `"true"`、`"false"`、`""` 或其他字符串模拟开关和数值。`同步配置版本（不可删除）` 是同步器维护的数字，用于识别设置变化，请勿删除或手动修改。

旧模板中没有“设置”数据库也无需手动升级：下一次联网同步会使用系统默认值，并自动创建数据库、默认配置页面和说明。修改设置后，下一次普通同步会自动刷新受影响的书籍，不需要运行全量同步。

## 常见问题

### 提示 `Could not find block with ID`

请检查：

- `NOTION_PAGE` 是否为 Duplicate 后的新页面 URL。
- 页面右上角 `••• → Connections` 中是否已经添加 `NotionHub`。
- GitHub 的 `NOTION_TOKEN` 是否属于该 Integration。
- Integration 和 Notion 页面是否位于同一个 Workspace。

### 日志显示了其他 Integration 名称

日志中的名称由 `NOTION_TOKEN` 决定，与 GitHub 仓库名称无关。请将 `NOTION_TOKEN` 替换为你自己创建的 `NotionHub` Integration Secret。

### “全部”视图没有数据

确认你使用的是最新 Template，并检查 Actions 是否已成功完成。不要在“全部”视图中添加空的年份筛选。

### “阅读时长格式化”显示“还未阅读”

请确认仓库已经同步到最新版本，然后重新运行一次 Actions。同步器会使用微信读书返回的累计阅读时长更新该字段。

## 问题反馈与功能建议

请通过 [GitHub Issues](https://github.com/wslh/NotionHub/issues/new/choose) 提交问题或需求。仓库提供了面向维护者和 AI 的 Issue 模板，建议尽可能提供：

- 当前结果与期望结果
- 可以复现问题的操作步骤
- 脱敏后的 GitHub Actions 运行链接或日志
- 相关 Notion 页面、书名和 BookId
- 使用普通同步还是全量同步
- 可以判断问题已经解决的验收标准

除问题或需求描述外，其余信息可以留空或填写“不清楚”。请勿提交 `WEREAD_API_KEY`、`NOTION_TOKEN`、Cookie、`.env` 内容或其他敏感信息。

## 更多文档

- [项目使用操作指南](docs/使用指南.md) — 三种使用方式、首次配置四步法、命令速查、插件启用、维护排错
- [从零到首次同步流程图](docs/diagrams/first-sync-flow.svg)
- [技术文档与本地运行说明](docs/TECHNICAL.md)
- [v1.0.0 版本说明](docs/RELEASE_NOTES_v1.0.0.md)
- [社区发布文案](docs/COMMUNITY_POST.md)
- [GitHub 仓库发布设置](docs/GITHUB_PUBLISHING.md)
- [微信读书助手](https://weread.qq.com/r/weread-skills)
- [提交问题或功能建议](https://github.com/wslh/NotionHub/issues/new/choose)

## AI 生成声明

本项目的代码、文档以及 Notion 模板适配工作完全由 OpenAI ChatGPT（Codex，GPT-5 系列模型）生成。

## License

MIT


## Plugins

NotionHub 把每个数据源（WeRead、Flomo、GitHub、Keep、Douban、小宇宙、B站、网易云音乐……）都当成一个**插件**。所有插件遵循同一个 `Plugin` 协议（`meta` + `is_configured` + `setup` + `discover` + `sync` + `health`），通过 `PluginRegistry` 注册，由 `run_plugin` 执行。

新增数据源的步骤：

1. 复制 `src/weread2notion/plugins/template.py` 到新文件。
2. 继承 `BasePlugin`，声明库结构（`DB_NAME`/`TITLE_PROP`/`KEY_PROP`/`SCHEMA`），实现 `is_configured` 与 `_items(ctx) -> Iterable[(key, raw)]`；建库/同步/探测均复用基类。
3. 在 `src/weread2notion/plugins/__init__.py` 的 `_instances` 里注册。
4. 在 `tests/` 下用 FakeNotion 补测试（参考 `test_plugin_framework.py`）。
5. 文本/日期解析复用 `src/weread2notion/utils.py` 的现成函数（`strip_html`、`parse_date_to_timestamp`、`parse_date_to_iso`、`parse_kindle_clipping_date`），不要各插件重复实现——具体用法见 `template.py` 与 `plugins/README.md`。

Python API：

```python
from weread2notion import build_default_registry, run_plugin, PluginContext

for plugin in build_default_registry():
    result = run_plugin(plugin, notion, settings)
```

详见 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) 与 [`plugins/README.md`](src/weread2notion/plugins/README.md)。

### 内置插件

33 个内置插件（与浏览器扩展控制面板一致）：

| id | name | category | env |
|----|------|----------|-----|
| weread | WeRead | 阅读 | `WEREAD_API_KEY` |
| flomo | Flomo | 笔记 | `FLOMO_EXPORT` |
| github | GitHub Stars | 效率 | `GH_TOKEN` |
| rss | RSS | 其他 | `RSS_FEEDS` |
| douban | Douban | 阅读 | `DOUBAN_BOOK_URLS` |
| telegram | Telegram Saved | 笔记 | `TELEGRAM_EXPORT` |
| netease | NetEase Playlist | 影音 | `NETEASE_PLAYLIST` |
| xiaoyuzhou | 小宇宙 | 播客 | `XIAOYUZHOU_FEEDS` |
| keep | Keep | 运动 | `KEEP_EXPORT` |
| toggl | Toggl | 效率 | `TOGGL_API_TOKEN` |
| forest | Forest | 效率 | `FOREST_EXPORT` |
| applemusic | Apple Music | 影音 | `APPLEMUSIC_EXPORT` |
| douyin | 抖音 | 影音 | `DOUYIN_EXPORT` |
| youtube | YouTube | 影音 | `YOUTUBE_EXPORT` / `YOUTUBE_API_KEY` |
| gutu | 古文岛 | 学习 | `GUTU_EXPORT` |
| trakt | Trakt | 影音 | `TRAKT_TOKEN` + `TRAKT_CLIENT_ID` |
| dayone | 生成日记 | 效率 | `DAYONE_EXPORT` |
| ticktick | 滴答清单 | 待办 | `TICKTICK_EXPORT` |
| duolingo | 多邻国 | 学习 | `DUOLINGO_EXPORT` |
| bilibili | B站 | 影音 | `BILIBILI_EXPORT` |
| beidanci | 不背单词 | 学习 | `BEIDANCI_EXPORT` |
| spotify | Spotify | 影音 | `SPOTIFY_TOKEN`（或 `SPOTIFY_CLIENT_ID` + `SPOTIFY_CLIENT_SECRET`） |
| strava | Strava | 运动 | `STRAVA_TOKEN` |
| weibo | 微博 | 笔记 | `WEIBO_UID`（可选 `WEIBO_COOKIE`） |
| xiaohongshu | 小红书 | 笔记 | `XIAOHONGSHU_EXPORT`（可选 `XIAOHONGSHU_COOKIE`） |
| jike | 即刻 | 笔记 | `JIKE_EXPORT`（可选 `JIKE_COOKIE`） |
| podcast | 播客（通用） | 播客 | `PODCAST_OPML` |
| applepodcast | Apple 播客 | 播客 | `APPLEPODCAST_OPML` |
| daily | 日记 | 笔记 | `DAILY_NOTES_DIR` |
| daily-weather | 每日天气 | 其他 | `DAILY_WEATHER_LOCATION` |
| daily-location | 每日位置 | 其他 | `DAILY_LOCATION_LOCATION` |
| guwendao | 古文岛 | 学习 | `GUWENDAO_EXPORT` |
| fix | 修复工具 | 效率 | —（无需凭证，重跑各库 `ensure_database` 修复结构） |

CLI：

```bash
notionhub plugins list          # 列出所有插件及配置状态
notionhub plugins info flomo     # 查看单个插件详情
notionhub plugins sync flomo     # 运行单个插件
notionhub plugins sync --all     # 运行所有已配置的插件
```