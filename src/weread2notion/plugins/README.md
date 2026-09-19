# Built-in plugins

NotionHub 把每个数据源都当成一个**插件**。所有插件遵循同一个 `Plugin` 协议（`meta` + `is_configured` + `setup` + `discover` + `sync` + `health`），通过 `PluginRegistry` 注册，由 `run_plugin` 执行。

当前内置 **33 个插件**（与 `README.md` 插件表、浏览器控制面板、VS Code 扩展 `List Plugins` 命令保持一致）：

| id | name | category | env / credential |
|----|------|----------|------------------|
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
| douyin | 抖音 | 影音 | `DOUYIN_EXPORT` / `DOUYIN_COOKIE` |
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
| fix | 修复工具 | 效率 | —（仅需 `NOTION_TOKEN`；重跑各库 `ensure_database` 修复结构） |

> 后 12 个（spotify 起）原先是 NotionHub 云端集成（拉外部仓库在云端运行），现已改为本仓库自托管插件，由 `.github/workflows/sync.yml` 统一调度。凭证在仓库 `Settings → Secrets and variables → Actions` 中配置，未配置的插件会被 `run_plugin` 安全跳过。

## 新增数据源

复制 `src/weread2notion/plugins/template.py` 到新文件，**继承 `BasePlugin`**，只需实现 `is_configured` 与 `_items`（`setup`/`discover`/`sync`/`health` 由基类提供）；在 `src/weread2notion/plugins/__init__.py` 的 `_instances` 里注册；并在 `tests/` 下用 `FakeNotion` 补测试（参考 `test_plugin_framework.py`）。

**复用共享工具**：文本/日期解析不要每个插件各写一份，直接用 `src/weread2notion/utils.py` 的现成函数：

```python
from ..utils import strip_html, parse_date_to_timestamp

# 清洗富文本里的 HTML 标签/实体
content = strip_html(entry.get("content") or "")[:1900]

# 把原始日期字符串解析为整型 Unix 时间戳（解析失败返回 None）
ts = parse_date_to_timestamp(entry.get("created_at") or "")
if ts is not None:
    raw["时间"] = {"date": {"start": datetime.fromtimestamp(ts).isoformat()}}
```

`utils` 还提供 `parse_date_to_iso`（返回 ISO 字符串）与 `parse_kindle_clipping_date`（解析 Kindle 中文/英文标注时间），详见 `utils.py` 文档字符串。

若新插件继承 `BasePlugin`，只需实现 `is_configured` 与 `_items`；`discover` 由基类提供（**注意**：`discover` 是 `Plugin` 协议的必需成员，缺失会让注册表的 `isinstance` 校验失败）。同时记得在 `src/weread2notion/credentials.py` 声明凭证——**env_key 必须与插件代码实际读取的环境变量完全一致**，否则面板会收集到插件永远不会读的值。

详见 [`docs/ARCHITECTURE.md`](../../docs/ARCHITECTURE.md) 与根目录 `README.md`。
