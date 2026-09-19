"""Plugin development template.

复制本文件为新插件命名（如 ``myapp.py``），按约定填充类属性与两个方法即可。
新建插件后，在 ``src/weread2notion/plugins/__init__.py`` 的 ``_instances`` 中注册，
并在 ``tests/`` 下用 ``FakeNotion`` 补测试（参考 ``test_plugin_framework.py``）。

约定优于配置
------------
继承 ``BasePlugin`` 后，**只需**声明库结构（类属性）+ 实现 ``is_configured`` 与
``_items``。``setup``（建库）、``discover``（预演）、``sync``（upsert 循环）、
``health``（健康探测）全部由基类提供，无需重写。

复用共享工具
------------
文本/日期解析请直接用 ``..utils`` 里的现成函数，不要在每个插件里重复实现：

- ``strip_html(value)`` —— 去 HTML 标签、反转义实体、折叠空白。
- ``parse_date_to_timestamp(value)`` —— 常见日期字符串 → 整型 Unix 时间戳（秒），
  解析失败返回 ``None``（适合直接喂给 Notion 的 ``date`` 属性）。
- ``parse_date_to_iso(value)`` —— 同上，但返回 ISO 8601 字符串。
- ``parse_kindle_clipping_date(meta)`` —— 解析 Kindle 标注元数据行（兼容中英文界面）。
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from ..plugin import Category, PluginMeta
from ..utils import parse_date_to_timestamp, strip_html
from .base import BasePlugin


class TemplatePlugin(BasePlugin):
    """模板插件：演示最小可用的 BasePlugin 实现。

    每个数据源只需把「原始数据」转成 ``(key, raw)`` 交给基类同步即可。
    """

    # —— 1. 库结构（建库用，setup 自动调用 ensure_database）——
    DB_NAME = "模板数据库"
    TITLE_PROP = "标题"
    KEY_PROP = "ID"  # upsert 用的唯一键列（必须是 title/rich_text/number/url 之一）
    SCHEMA = {
        "标题": {"title": {}},
        "ID": {"rich_text": {}},
        "内容": {"rich_text": {}},
        "时间": {"date": {}},
    }

    # —— 2. 元数据（在 credentials.py 声明同名凭证；env_key 必须与代码读取的环境变量一致）——
    meta = PluginMeta(
        id="template",
        name="模板",
        category=Category.OTHER,
        description="复制本模板实现新插件。",
        docs_url="https://github.com/wslh/NotionHub/blob/main/src/weread2notion/plugins/template.py",
        icon="🧩",
    )

    # —— 3. 是否已配置（缺凭证时 runner 会安全跳过本插件）——
    def is_configured(self) -> bool:
        return bool(os.getenv("TEMPLATE_EXPORT"))

    # —— 4. 把每条原始数据转成 (key, raw) 交给基类同步 ——
    # key 即 KEY_PROP 列的值（唯一键）；raw 是 Notion properties 字典。
    def _items(self, ctx):
        path = Path(os.environ.get("TEMPLATE_EXPORT", ""))
        if not path.exists():
            return
        for entry in _load_entries(path):
            # 演示复用共享工具（来自 ..utils）：
            # 1) strip_html：清洗富文本里的 HTML 标签/实体
            content = strip_html(entry.get("content") or "")[:1900]
            # 2) parse_date_to_timestamp：把原始日期字符串解析为整型时间戳
            ts = parse_date_to_timestamp(entry.get("created_at") or "")

            raw = {
                "ID": entry["id"],
                "内容": content,
            }
            if ts is not None:
                # 下游 Notion date 属性需要 ISO 字符串，由时间戳转换
                raw["时间"] = {"date": {"start": datetime.fromtimestamp(ts).isoformat()}}
            yield entry["id"], raw


def _load_entries(path: Path) -> list[dict]:
    """读取并解析导出文件，返回原始条目列表。按真实数据源替换此函数。"""
    # 示例：实际插件里这里可能是 json.loads / csv.DictReader / 解析 API 响应。
    # 解析出的字符串字段用 strip_html 清洗，日期字段用 parse_date_to_timestamp 归一化。
    raise NotImplementedError("请实现 _load_entries 以解析你的数据源")
