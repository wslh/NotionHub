"""NotionHub 官方模板的结构清单（单一事实来源）。

把所有硬编码的库名、属性 schema、候选顺序集中到本模块，其余模块（notion.py /
sync.py / 插件）从这里派生，避免「库名硬编码、改名即断」：未来调整模板结构
只需改这一处，而非在十几个文件里逐行搜索替换。

注意：标题属性（title）并非硬编码——``NotionWorkspace.discover`` 会在运行时根据
各库 schema 中 ``type == "title"`` 的属性动态推断，因此本清单只描述库名与属性 schema。
"""
from typing import Any

# 周期统计库：维度 -> 库名（标题属性就是维度名，如「日」库的标题属性是「日」）。
PERIOD_DATABASES: dict[str, str] = {
    "day": "日",
    "week": "周",
    "month": "月",
    "year": "年",
}

# 阅读记录库候选顺序（按模板版本从高到低，取第一个存在的）。
READING_RECORD_DATABASES = ("阅读记录2", "阅读记录", "阅读记录1")

# 设置库。
SETTINGS_DATABASE = "设置"
SETTINGS_TITLE = "同步设置"

# 阅读快照库。
SNAPSHOTS_DATABASE = "阅读快照"

# discover() 校验缺库用的必需核心库（不含按需创建的 设置 / 阅读快照）。
REQUIRED_DATABASES = (
    "书架",
    "日",
    "周",
    "月",
    "年",
    "分类",
    "作者",
)

# 阅读快照库属性 schema（建库 / 校验用）。
SNAPSHOTS_PROPERTIES: dict[str, Any] = {
    "SnapshotKey": {"rich_text": {}},
    "BookId": {"rich_text": {}},
    "书名": {"rich_text": {}},
    "日期": {"date": {}},
    "累计阅读时长": {"number": {"format": "number"}},
    "累计阅读时长（分钟）": {"number": {"format": "number"}},
    "当日新增阅读时长": {"number": {"format": "number"}},
    "当日新增阅读时长（分钟）": {"number": {"format": "number"}},
    "阅读进度": {"number": {"format": "percent"}},
    "阅读状态": {"select": {}},
    "当前章节": {"rich_text": {}},
    "最后阅读时间": {"date": {}},
    "内容类型": {"select": {}},
}
