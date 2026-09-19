# WeRead2Notion AI 技术文档

将微信读书的书架、阅读进度、章节、划线、个人想法和阅读统计同步到 WeRead2Notion AI 模板，同时保留 Notion 页面原有的分栏、目录、视图、公式和样式。

[返回用户使用指南](../README.md)

## 设计原则

- **不重写主页**：同步器只创建、更新或归档数据库行，不调用整页内容替换。
- **全量同步先备份**：`--full` 会先导出所有数据库行为 JSON，再将旧行移入 Notion 回收站。
- **使用微信读书 Gateway API**：不需要 Cookie，API Key 从环境变量读取。
- **适配模板关系**：支持书架、作者、分类、日、周、月、年，以及可选的阅读记录数据库。
- **正文式笔记**：划线与个人想法按章节直接生成在书籍正文中，不再创建独立标签页或关系标签。
- **完整书架口径**：电子书、专辑/有声书和文章收藏都会进入书架。
- **书架是权威来源**：`/shelf/sync` 决定同步范围；仅存在于历史笔记或阅读记录中的书不会重新加入，已移出书架的书及其关联内容会移入 Notion 回收站。
- **人工状态优先**：只有书架条目的 `finishReading=1` 才同步为“已读”；阅读进度和 `finishTime` 不单独作为读完判据。
- **区分笔记口径**：统计总数包含书签；实际可导出的内容只有划线与个人想法/点评。
- **Notion 驱动配置**：每次联网同步前读取“设置”数据库；不存在时按环境变量和内置默认值运行，并自动创建默认配置。
- **每日书籍快照**：每天为当前书架中的每个条目保存一条累计阅读状态，同日重复同步使用稳定键更新原记录。

## 要求

- Python 3.10+
- 已复制 WeRead2Notion AI 模板
- Notion Integration 已获得目标页面及所有子数据库权限
- 微信读书 Gateway API Key

模板页面必须包含这些数据库：

`书架`、`日`、`周`、`月`、`年`、`分类`、`作者`

数据库可以放在页面分栏或其他容器内；同步器会递归发现它们。数据库视图、筛选、排序、公式和页面布局不会被修改。

“设置”数据库不是模板校验的硬依赖。同步器会在缺失时自动创建，并创建唯一的“同步设置”配置页。对用户开放的配置属性只使用 Notion Checkbox 和 Number：

- `阅读完成进度强制改为100%`：Checkbox，默认 `false`
- `只同步我的书架书籍`：Checkbox，默认 `true`
- `同步划线和笔记`：Checkbox，默认 `true`
- `同步快照`：Checkbox，默认 `true`
- `同步阅读记录`：Checkbox，默认 `true`
- `同步人物卡片`：Checkbox，默认 `true`
- `生成 AI 导读`：Checkbox，默认 `false`（需配置 `OPENAI_API_KEY`）
- `阅读统计起始年份`：Number，默认读取 `START_YEAR`

配置 Schema 只允许两类可编辑值：

- 布尔开关必须使用 Checkbox，读取结果为真正的 `true` 或 `false`。
- 数值配置必须使用 Number，可填写整数或实数，例如 `-1`、`0`、`1`、`2`、`0.5`。
- 禁止使用 Rich Text、Select、`"true"`、`"false"`、空字符串或其他字符串模拟布尔值和数值。

`同步配置版本（不可删除）` 是同步器维护的 Number 属性。它由配置模式版本、起始年份以及四个布尔开关（同步划线和笔记、同步快照、同步阅读记录、同步人物卡片、生成 AI 导读）确定，用于发现设置变化。配置码变化时，普通同步会将当前书架全部加入本次更新范围；成功完成后才写回新的配置码。同步器兼容旧字段名称，已 Duplicate 的旧页面无需立即手动迁移。已有工作区首次升级时，同步器会自动为「设置」库补齐新增的开关列（无需手动迁移）。

“阅读快照”数据库同样不是模板硬依赖，缺失时自动创建。稳定键格式为 `YYYY-MM-DD:BookId`，因此同一天重复执行不会产生重复记录。主要属性包括：

- 日期、BookId、书名和内容类型
- 累计阅读时长及分钟值
- 当日新增阅读时长及分钟值
- 阅读进度、阅读状态、当前章节和最后阅读时间

首次发现一本已经阅读过的书时，只保存其累计值，不会把历史累计时长误记为当天新增时长。之后的增量由当前累计值与上次同步状态的差值计算；同一天多次同步时会继续累加到当天同一条快照。全量同步和移出书架都保留历史快照。

## 本地配置

```bash
cp .env.example .env
```

```dotenv
WEREAD_API_KEY=wrk_xxx
NOTION_TOKEN=ntn_xxx
NOTION_PAGE=https://www.notion.so/your-page-id
```

可选配置：

```dotenv
START_YEAR=2023
BACKUP_DIR=backups
NOTION_VERSION=2026-03-11
NOTION_REQUEST_INTERVAL=0.34
```

## 安装与运行

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

检查模板：

```bash
weread2notion check
```

查看读取范围但不写入 Notion：

```bash
weread2notion sync --dry-run
```

日常同步：

```bash
weread2notion sync
```

安全重建全部数据：

```bash
weread2notion sync --full
```

只查看阶段进度汇总、不打印逐阶段日志：

```bash
weread2notion sync --quiet
```

检测数据不一致（默认仅输出报告，不修改）：

```bash
weread2notion repair
```

检测并执行修复（重建设置/快照库、重生成过期正文、归档孤立记录、补齐当日快照）：

```bash
weread2notion repair --apply
```

从全量备份 JSON 回滚被归档的页面（全量同步失败后的恢复）：

```bash
weread2notion restore backups/YYYY-MM-DD.json
```

全量同步顺序：

1. 读取并验证所有模板数据库。
2. **重建前校验**：确认将要归档的每一个数据数据库均可正常查询，校验失败立即中止，避免误删数据。
3. 将旧数据库行导出到 `backups/*.json`（打印备份路径）。
4. 把旧行移入 Notion 回收站，不删除数据库和视图。
5. 重建年、月、周、日。
6. 重建作者、分类和书架。
7. 写入或更新当天的每本书阅读快照，历史快照保持不变。
8. 把划线与个人想法按章节直接写入书籍正文，不创建独立章节数据库。
9. 写入可用的阅读记录；完成后终端提示备份路径与回滚命令。

普通增量同步也会比较 `/shelf/sync` 与 Notion 书架。默认开启“只同步我的书架书籍”：Notion 中存在、但微信读书当前书架中不存在的条目，会连同旧版独立笔记/划线行和当前页面正文一起移入回收站；关闭后跳过该动作。清理动作只会在本次所需的微信读书请求全部成功后执行。

> 微信读书目前只提供书签数量，不提供书签正文，因此书签不会伪装成划线导入。

## GitHub Actions

仓库 Secrets：

- `WEREAD_API_KEY`
- `NOTION_TOKEN`
- `NOTION_PAGE`

工作流每天自动运行，也可以在 Actions 页面手动选择普通同步或全量同步（可选 `full` 与重试次数）。全量同步生成的 JSON 备份会作为 workflow artifact 上传。工作流具备以下增强：

- **并发控制**：`concurrency` 保证同一分支同一时刻只有一次运行，新触发排队，互不覆盖。
- **失败重试**：`action.yml` 内置重试循环（默认 2 次，间隔 30 秒，可用 `retries`/`retry-delay` 输入调整）。
- **失败通知**：同步失败时自动创建 `sync-failure` 标签的 Issue 通知，避免静默失败。
- **频率可配置**：修改 `weread.yml` 中 `schedule.cron` 即可调整同步频率（默认每日北京时间 04:00）。

## 开发

```bash
pip install -e '.[test]'
pytest
```

代码结构：

- `weread.py`：Gateway API、分页和升级提示处理
- `notion.py`：模板发现、Schema 适配、行级写入与备份、备份恢复（请求含退避+抖动）
- `normalize.py`：时间、状态和书架条目标准化
- `sync.py`：按关系依赖执行同步，含并发拉取、检查点续传、选择性同步、范围开关、进度日志与全量重建前校验
- `repair.py`：检测并修复数据不一致
- `status.py`：工作区健康状态汇总（`status` 命令）
- `export.py`：书架/阅读快照导出为 CSV/Markdown（`export` 命令）
- `ai_summary.py`：可选 AI 书摘摘要（需 `OPENAI_API_KEY`，真正调用 OpenAI 并优雅降级）
- `telemetry.py`：可选匿名遥测（需 `WEREAD2NOTION_TELEMETRY=1`，默认关闭）
- `logging_utils.py`：统一日志与密钥脱敏
- `cli.py`：`check`、`sync`、`repair`、`restore`、`status`、`export`、`insights` 子命令及 `--dry-run`、`--full`、`--quiet`、`--verbose`、`--book`、`--tag`、`--no-self-heal`、`--apply`、`--source` 选项
- `sources.py`：数据源插件抽象（`BookSource` 接口 + `WeReadBookSource` 适配 + `LocalBookSource`/`KindleSource`/`AppleBooksSource` 可运行示例），`--source weread|local:/path|kindle:/MyClippings.txt|apple:/export.csv` 可切换来源
- `analytics.py`：阅读洞察汇总与快照差异（`insights` 命令与看板数据源）

## 故障排查 FAQ

- **同步中途失败**：已写入的书会在 `backups/.checkpoint.json` 记录，重跑 `sync` 将从已完成处续传；默认还会自动 `repair --apply` 后重试一次（可用 `--no-self-heal` 关闭）。
- **全量同步误操作**：全量仅把旧页面移入回收站（不删除），用 `weread2notion restore <backups/日期.json>` 取消归档即可回滚。
- **`NOTION_TOKEN` 报格式错误**：须以 `ntn_` 或 `secret_` 开头；请检查 Integration 令牌。
- **限流 429 频繁**：增大 `NOTION_REQUEST_INTERVAL` 或降低 `CONCURRENCY`（默认 4）；代码已自动退避并尊重 `Retry-After`。
- **数据不一致**：先 `weread2notion status` 查看待修复项，再 `weread2notion repair --apply` 修复。
- **日志位置**：运行日志写入 `logs/weread2notion.log`（含脱敏），`--verbose` 同时在控制台打印调试信息。

## 安全说明

不要把 API Key、Notion Token 或 `.env` 提交到 Git。全量同步的 JSON 备份可能包含你的书名、划线和笔记，也应作为私密数据保存。

## AI 生成声明

本项目的代码、文档以及 Notion 模板适配工作完全由 OpenAI ChatGPT（Codex，GPT-5 系列模型）生成。

## License

MIT
