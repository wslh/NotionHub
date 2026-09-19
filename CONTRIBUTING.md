# 贡献指南

感谢参与 WeRead2Notion AI 的改进。

## 开发环境

```bash
pip install -e '.[test]'
pytest
```

环境变量（可放入 `.env`，已自动加载）：

- `WEREAD_API_KEY`、`NOTION_TOKEN`(须以 `ntn_` 或 `secret_` 开头)、`NOTION_PAGE`
- 可选：`CONCURRENCY`(并发数)、`NOTION_REQUEST_INTERVAL`、`WEREAD2NOTION_TELEMETRY`(遥测)、`OPENAI_API_KEY`(AI 摘要)

## 代码约定

- 模块职责清晰：`weread.py`(数据源)、`notion.py`(目标)、`sync.py`(编排)、`repair.py`(修复)、`cli.py`(入口)。新增能力优先放入对应模块，跨模块入口统一在 `cli.py`。
- 涉及外部凭证的能力（AI 摘要、遥测）**必须默认关闭、优雅降级**，缺失凭证时返回 `None` 或跳过，绝不阻断主流程。
- 日志使用 `logging` 模块；敏感信息经 `logging_utils.redact` 脱敏，禁止在日志打印密钥。
- 破坏性操作（归档/删除）前必须有校验或备份；所有 WeRead 请求应在任何 Notion 写入之前完成。

## 提交前检查

```bash
pytest
python -m weread2notion check   # 本地校验模板
```

## 测试

- 新增功能请补充 `tests/` 用例，覆盖正常路径与降级路径。
- 涉及网络/Notion 的部分使用 Fake 客户端，不依赖真实凭证。

## 问题反馈

请附上 `logs/weread2notion.log` 中相关片段（已脱敏），以及 `weread2notion status` 输出。
