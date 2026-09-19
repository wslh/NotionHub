from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from notion_client import Client

from .blocks import get_callout
from .config import ConfigError
from .notion_diff import (
    READ_ONLY_KINDS,
    compute_changed_properties,
    plain_property_value,
    same_value,
)
from .notion_http import list_children_blocks, request_with_retry
from .notion_text import chunks, text_value
from .template import (
    REQUIRED_DATABASES,
    SETTINGS_DATABASE,
    SETTINGS_TITLE,
    SNAPSHOTS_DATABASE,
    SNAPSHOTS_PROPERTIES,
)


# 模块级工具函数：从 notion_text 重新导出，保持 ``from weread2notion.notion
# import text_value`` 之类的旧导入路径仍然可用。
__all__ = ["NotionWorkspace", "chunks", "text_value", "READ_ONLY_KINDS"]

SETTINGS_ICON = "https://www.notion.so/icons/settings_gray.svg"
SNAPSHOTS_ICON = "https://www.notion.so/icons/clock_gray.svg"


class NotionWorkspace:
    """Operate on database rows only; never replace the dashboard page content."""

    READ_ONLY_KINDS = READ_ONLY_KINDS

    def __init__(
        self,
        token: str,
        page_id: str,
        notion_version: str,
        interval: float = 0.34,
        client=None,
    ):
        self.client = client or Client(auth=token, notion_version=notion_version)
        self.page_id = page_id
        self.interval = interval
        self.databases: dict[str, str] = {}
        self.sources: dict[str, str] = {}
        self.schemas: dict[str, dict[str, str]] = {}
        self.titles: dict[str, str] = {}

    def request(self, path: str, method: str = "GET", body: dict | None = None) -> dict:
        return request_with_retry(self.client, path, method, body, self.interval)

    def list_children(self, block_id: str) -> list[dict[str, Any]]:
        return list_children_blocks(self.client, block_id)

    def discover(self) -> "NotionWorkspace":
        def walk(block_id: str) -> None:
            for block in self.list_children(block_id):
                if block.get("type") == "child_database":
                    title = (block.get("child_database") or {}).get("title") or ""
                    self.databases.setdefault(title, block["id"])
                if block.get("has_children") and block.get("type") != "child_database":
                    walk(block["id"])

        walk(self.page_id)
        missing = [name for name in REQUIRED_DATABASES if name not in self.databases]
        if missing:
            raise ConfigError(
                "模板页缺少必需的数据库：" + "、".join(missing) + "\n\n"
                "请按以下步骤修复：\n"
                "  1. 打开官方模板 https://app.notion.com/p/wph/"
                "Template-3a329affe5af800b8581f98b71e948fb\n"
                "  2. 点右上角 Duplicate，复制到你自己的 Notion 工作区\n"
                "  3. 打开复制出的新页面，右上角 ••• → Connections，添加你的 integration\n"
                "  4. 把新页面 URL 填入 .env 的 NOTION_PAGE\n\n"
                "注意：NotionHub OAuth 登录后自动复制出来的页面不是本项目标准模板，"
                "不能用作同步目标。"
            )
        for name, database_id in self.databases.items():
            database = self.request(f"databases/{database_id}")
            sources = database.get("data_sources") or []
            source_id = sources[0]["id"] if sources else database_id
            self.sources[name] = source_id
            data_source = self.request(f"data_sources/{source_id}")
            properties = data_source.get("properties") or {}
            self.schemas[name] = {
                prop_name: (definition or {}).get("type")
                for prop_name, definition in properties.items()
            }
            self.titles[name] = next(
                (prop for prop, kind in self.schemas[name].items() if kind == "title"),
                "Name",
            )
        return self

    def ensure_sync_settings(self, default_start_year: int = 2023) -> dict[str, Any]:
        """Read user preferences, creating the settings database when absent."""
        if SETTINGS_DATABASE not in self.sources:
            database = self.request(
                "databases",
                "POST",
                {
                    "parent": {"type": "page_id", "page_id": self.page_id},
                    "title": text_value(SETTINGS_DATABASE),
                    "is_inline": True,
                    "icon": {"type": "external", "external": {"url": SETTINGS_ICON}},
                    "initial_data_source": {
                        "properties": {
                            "配置": {"title": {}},
                            "阅读完成进度强制改为100%": {"checkbox": {}},
                            "只同步我的书架书籍": {"checkbox": {}},
                            "同步划线和笔记": {"checkbox": {}},
                            "同步快照": {"checkbox": {}},
                            "同步阅读记录": {"checkbox": {}},
                            "同步人物卡片": {"checkbox": {}},
                            "生成 AI 导读": {"checkbox": {}},
                            "阅读统计起始年份": {
                                "number": {"format": "number"}
                            },
                            "同步配置版本（不可删除）": {
                                "number": {"format": "number"}
                            },
                        }
                    },
                },
            )
            database_id = database["id"]
            sources = database.get("data_sources") or []
            source_id = sources[0]["id"] if sources else database_id
            self.databases[SETTINGS_DATABASE] = database_id
            self.sources[SETTINGS_DATABASE] = source_id
            self.schemas[SETTINGS_DATABASE] = {
                "配置": "title",
                "阅读完成进度强制改为100%": "checkbox",
                "只同步我的书架书籍": "checkbox",
                "同步划线和笔记": "checkbox",
                "同步快照": "checkbox",
                "同步阅读记录": "checkbox",
                "同步人物卡片": "checkbox",
                "生成 AI 导读": "checkbox",
                "阅读统计起始年份": "number",
                "同步配置版本（不可删除）": "number",
            }
            self.titles[SETTINGS_DATABASE] = "配置"

        # 迁移：为已存在的工作区补齐新增的范围开关列（同步快照/记录/人物/AI 导读）。
        _needed_settings = {
            "同步快照": {"checkbox": {}},
            "同步阅读记录": {"checkbox": {}},
            "同步人物卡片": {"checkbox": {}},
            "生成 AI 导读": {"checkbox": {}},
        }
        _missing_settings = {
            name: definition
            for name, definition in _needed_settings.items()
            if name not in self.schemas.get(SETTINGS_DATABASE, {})
        }
        if _missing_settings:
            self.request(
                f"data_sources/{self.sources[SETTINGS_DATABASE]}",
                "PATCH",
                {"properties": _missing_settings},
            )
            self.schemas[SETTINGS_DATABASE].update(
                {name: "checkbox" for name in _missing_settings}
            )

        rows = self.query_all(SETTINGS_DATABASE)
        if not rows:
            page_id = self.create(
                SETTINGS_DATABASE,
                {
                    "配置": SETTINGS_TITLE,
                    "阅读完成进度强制改为100%": False,
                    "只同步我的书架书籍": True,
                    "同步划线和笔记": True,
                    "同步快照": True,
                    "同步阅读记录": True,
                    "同步人物卡片": True,
                    "生成 AI 导读": False,
                    "阅读统计起始年份": default_start_year,
                    "同步配置版本（不可删除）": 0,
                },
                SETTINGS_ICON,
            )
            self.request(
                f"blocks/{page_id}/children",
                "PATCH",
                {
                    "children": [
                        {
                            "object": "block",
                            "type": "callout",
                            "callout": {
                                "icon": {"type": "emoji", "emoji": "⚙️"},
                                "rich_text": text_value(
                                    "NotionHub 每次同步前都会读取本页属性。"
                                    "删除本数据库或缺少字段时，将自动使用系统默认值。"
                                ),
                            },
                        },
                        {
                            "object": "block",
                            "type": "bulleted_list_item",
                            "bulleted_list_item": {
                                "rich_text": text_value(
                                    "阅读完成进度强制改为100%：只改变 Notion 展示，不修改微信读书真实进度。"
                                )
                            },
                        },
                        {
                            "object": "block",
                            "type": "bulleted_list_item",
                            "bulleted_list_item": {
                                "rich_text": text_value(
                                    "阅读统计起始年份：使用数字填写，例如 2023。"
                                )
                            },
                        },
                        {
                            "object": "block",
                            "type": "bulleted_list_item",
                            "bulleted_list_item": {
                                "rich_text": text_value(
                                    "同步配置版本（不可删除）：由系统维护，请勿手动修改。"
                                )
                            },
                        },
                        {
                            "object": "block",
                            "type": "bulleted_list_item",
                            "bulleted_list_item": {
                                "rich_text": text_value(
                                    "只同步我的书架书籍：移除不在当前书架中的书籍及自动同步内容。"
                                )
                            },
                        },
                        {
                            "object": "block",
                            "type": "bulleted_list_item",
                            "bulleted_list_item": {
                                "rich_text": text_value(
                                    "同步划线和笔记：关闭后不再更新书籍正文中的自动同步内容。"
                                )
                            },
                        },
                        {
                            "object": "block",
                            "type": "bulleted_list_item",
                            "bulleted_list_item": {
                                "rich_text": text_value(
                                    "同步快照：是否生成每日/周期阅读快照；关闭可节省 Notion 配额。"
                                )
                            },
                        },
                        {
                            "object": "block",
                            "type": "bulleted_list_item",
                            "bulleted_list_item": {
                                "rich_text": text_value(
                                    "同步阅读记录：是否同步划线/笔记到书籍正文；关闭则仅保留书籍元信息。"
                                )
                            },
                        },
                        {
                            "object": "block",
                            "type": "bulleted_list_item",
                            "bulleted_list_item": {
                                "rich_text": text_value(
                                    "同步人物卡片：是否生成书中人物卡片；大书目可关闭以加速同步。"
                                )
                            },
                        },
                        {
                            "object": "block",
                            "type": "bulleted_list_item",
                            "bulleted_list_item": {
                                "rich_text": text_value(
                                    "生成 AI 导读：需配置 OPENAI_API_KEY；开启后为每本书写入一段 AI 导读（可选）。"
                                )
                            },
                        },
                    ]
                },
            )
            rows = self.query_all(SETTINGS_DATABASE)

        properties = (rows[0].get("properties") or {}) if rows else {}

        def value(name: str, default: Any) -> Any:
            parsed = self.plain_property(properties.get(name))
            return default if parsed is None else parsed

        def compatible_value(name: str, old_name: str, default: Any) -> Any:
            if name in properties:
                return value(name, default)
            return value(old_name, default)

        settings = {
            "completed_progress_100": bool(
                compatible_value(
                    "阅读完成进度强制改为100%", "已读进度显示为100%", False
                )
            ),
            "delete_removed": bool(
                compatible_value("只同步我的书架书籍", "移出书架时删除", True)
            ),
            "sync_notes": bool(value("同步划线和笔记", True)),
            "sync_snapshots": bool(value("同步快照", True)),
            "sync_records": bool(value("同步阅读记录", True)),
            "sync_people": bool(value("同步人物卡片", True)),
            "ai_intro": bool(value("生成 AI 导读", False)),
            "start_year": int(value("阅读统计起始年份", default_start_year)),
        }
        config_code = (
            1_000_000
            + settings["start_year"] * 8
            + int(settings["completed_progress_100"])
            + int(settings["delete_removed"]) * 2
            + int(settings["sync_notes"]) * 4
            + int(settings["sync_snapshots"]) * 8
            + int(settings["sync_records"]) * 16
            + int(settings["sync_people"]) * 32
            + int(settings["ai_intro"]) * 64
        )
        config_property = (
            "同步配置版本（不可删除）"
            if "同步配置版本（不可删除）" in properties
            else "已应用配置码"
        )
        settings["settings_changed"] = value(config_property, 0) != config_code
        settings["_config_code"] = config_code
        settings["_config_property"] = config_property
        settings["_page_id"] = rows[0].get("id") if rows else None
        return settings

    def ensure_reading_snapshots(self) -> None:
        """Create or migrate the append-only daily per-book snapshot database."""
        if SNAPSHOTS_DATABASE not in self.sources:
            database = self.request(
                "databases",
                "POST",
                {
                    "parent": {"type": "page_id", "page_id": self.page_id},
                    "title": text_value(SNAPSHOTS_DATABASE),
                    "is_inline": True,
                    "icon": {
                        "type": "external",
                        "external": {"url": SNAPSHOTS_ICON},
                    },
                    "initial_data_source": {
                        "properties": {
                            "快照": {"title": {}},
                            **SNAPSHOTS_PROPERTIES,
                        }
                    },
                },
            )
            database_id = database["id"]
            sources = database.get("data_sources") or []
            source_id = sources[0]["id"] if sources else database_id
            self.databases[SNAPSHOTS_DATABASE] = database_id
            self.sources[SNAPSHOTS_DATABASE] = source_id
            self.schemas[SNAPSHOTS_DATABASE] = {
                "快照": "title",
                **{
                    name: next(iter(definition))
                    for name, definition in SNAPSHOTS_PROPERTIES.items()
                },
            }
            self.titles[SNAPSHOTS_DATABASE] = "快照"
            return

        missing = {
            name: definition
            for name, definition in SNAPSHOTS_PROPERTIES.items()
            if name not in self.schemas.get(SNAPSHOTS_DATABASE, {})
        }
        if not missing:
            return
        self.request(
            f"data_sources/{self.sources[SNAPSHOTS_DATABASE]}",
            "PATCH",
            {"properties": missing},
        )
        self.schemas[SNAPSHOTS_DATABASE].update(
            {name: next(iter(definition)) for name, definition in missing.items()}
        )

    def mark_sync_settings_applied(
        self,
        page_id: str | None,
        config_code: int,
        config_property: str = "同步配置版本（不可删除）",
    ) -> None:
        if not page_id:
            return
        self.request(
            f"pages/{page_id}",
            "PATCH",
            {
                "properties": self.properties(
                    SETTINGS_DATABASE, {config_property: config_code}
                )
            },
        )

    def write_ai_intro(self, page_id: str, summary: str) -> None:
        """在书籍页面追加（并替换上一次的）AI 导读 callout 块。

        通过固定前缀 ``AI 导读`` 识别由本工具写入的 callout，重复同步时先删除旧块再追加。
        """
        marker = "AI 导读"
        for block in self.list_children(page_id):
            if block.get("type") != "callout":
                continue
            callout = block.get("callout") or {}
            text = "".join(
                item.get("plain_text", "")
                for item in (callout.get("rich_text") or [])
            )
            if text.startswith(marker):
                self.request(f"blocks/{block['id']}", "DELETE")
        self.request(
            f"blocks/{page_id}/children",
            "PATCH",
            {"children": [get_callout(f"{marker}\n\n{summary}", icon="\U0001F916")]},
        )

    def ensure_database(
        self,
        name: str,
        title_prop: str,
        properties: dict[str, dict],
        icon: dict | None = None,
    ) -> str:
        """为插件创建（若已存在则复用）一个 Notion 数据库。

        ``properties`` 是数据库的列定义，键为属性名，值为 Notion 属性类型定义
        （如 ``{"rich_text": {}}``、``{"number": {"format": "number"}}``）。
        ``title_prop`` 是作为标题的列名。返回数据源 ID。
        """
        if name in self.sources:
            return self.sources[name]
        schema = dict(properties)
        schema.setdefault(title_prop, {"title": {}})
        body: dict[str, Any] = {
            "parent": {"type": "page_id", "page_id": self.page_id},
            "title": [{"type": "text", "text": {"content": name}}],
            "properties": schema,
        }
        if icon:
            body["icon"] = icon
        db = self.request("databases", "POST", body)
        if not db or "id" not in db:
            raise RuntimeError(f"创建数据库失败：{name}")
        source_id = db.get("data_sources", [{}])[0].get("id") or db.get("id")
        self.sources[name] = source_id
        self.schemas[name] = {
            prop: (definition or {}).get("type", "rich_text")
            for prop, definition in schema.items()
        }
        self.titles[name] = title_prop
        return source_id

    def query_all(self, database_name: str, filter_: dict | None = None) -> list[dict]:
        rows, cursor = [], None
        while True:
            body: dict[str, Any] = {"page_size": 100}
            if cursor:
                body["start_cursor"] = cursor
            if filter_:
                body["filter"] = filter_
            response = self.request(
                f"data_sources/{self.sources[database_name]}/query", "POST", body
            )
            rows.extend(response.get("results") or [])
            if not response.get("has_more"):
                return rows
            cursor = response.get("next_cursor")

    def property(self, database: str, name: str, value: Any) -> dict | None:
        kind = self.schemas[database].get(name)
        if not kind or value is None:
            return None
        if kind == "title":
            return {"title": text_value(value)}
        if kind == "rich_text":
            return {"rich_text": text_value(value)}
        if kind == "number":
            return {"number": float(value) if value != "" else None}
        if kind == "url":
            return {"url": str(value) or None}
        if kind == "date":
            if not value:
                return {"date": None}
            if isinstance(value, dict):
                return {"date": value}
            return {"date": {"start": value}}
        if kind == "relation":
            return {"relation": [{"id": item} for item in (value or [])]}
        if kind in {"select", "status"}:
            return {kind: {"name": str(value)}} if value else {kind: None}
        if kind == "multi_select":
            values = value if isinstance(value, (list, tuple, set)) else [value]
            return {"multi_select": [{"name": str(item)} for item in values if item]}
        if kind == "checkbox":
            return {"checkbox": bool(value)}
        return None

    def properties(self, database: str, raw: dict[str, Any]) -> dict[str, Any]:
        result = {}
        for name, value in raw.items():
            prop = self.property(database, name, value)
            if prop is not None:
                result[name] = prop
        return result

    @classmethod
    def _same_value(cls, kind: str, current: dict, desired: dict) -> bool:
        """见 :func:`weread2notion.notion_diff.same_value`（纯函数版）。"""
        return same_value(kind, current, desired)

    def changed_properties(
        self, database: str, existing: dict | None, desired: dict
    ) -> dict:
        """返回 desired 中与 Notion 现有值不同的字段子集。

        existing 为空（新记录）时返回全部字段；无法逐字段比较时也返回全部字段。
        """
        return compute_changed_properties(
            self.schemas.get(database) or {}, existing, desired
        )

    def find(self, database: str, property_name: str, value: Any) -> dict | None:
        kind = self.schemas[database].get(property_name)
        if kind not in {"title", "rich_text", "number", "url"}:
            return None
        query_kind = "rich_text" if kind == "url" else kind
        rows = self.query_all(
            database,
            {"property": property_name, query_kind: {"equals": value}},
        )
        return rows[0] if rows else None

    def upsert(
        self,
        database: str,
        key_name: str,
        key_value: Any,
        raw: dict[str, Any],
        icon: str | None = None,
        cover: str | None = None,
        existing_id: str | None = None,
        existing_properties: dict | None = None,
    ) -> str:
        properties = self.properties(database, raw)
        existing = (
            {"id": existing_id}
            if existing_id
            else self.find(database, key_name, key_value)
        )
        if existing:
            # 只有拿到现有属性才能做字段级 diff。调用方传了 existing_properties
            # 或 find() 自带 properties 时走增量更新；否则退回全量覆盖，
            # 绝不为了 diff 额外发一次 GET（那会抵消掉省下的写入）。
            current_props = existing_properties
            if current_props is None:
                current_props = existing.get("properties")
            if current_props:
                properties = self.changed_properties(
                    database, current_props, properties
                )
                # 没有任何字段变化：连 icon/cover 都不必重写，直接跳过 PATCH。
                if not properties and not (icon or cover):
                    return existing["id"]
            body: dict[str, Any] = {"properties": properties}
            if icon:
                body["icon"] = {"type": "external", "external": {"url": icon}}
            if cover:
                body["cover"] = {"type": "external", "external": {"url": cover}}
            self.request(f"pages/{existing['id']}", "PATCH", body)
            return existing["id"]
        body = {
            "parent": {
                "type": "data_source_id",
                "data_source_id": self.sources[database],
            },
            "properties": properties,
        }
        if icon:
            body["icon"] = {"type": "external", "external": {"url": icon}}
        if cover:
            body["cover"] = {"type": "external", "external": {"url": cover}}
        return self.request("pages", "POST", body)["id"]

    def row_index(self, database: str, key_name: str) -> dict[str, dict[str, Any]]:
        """Load a database once and index rows by a stable property value."""
        result = {}
        for row in self.query_all(database):
            properties = row.get("properties") or {}
            key = self.plain_property(properties.get(key_name))
            if key is None or key == "":
                continue
            if isinstance(key, float) and key.is_integer():
                key = int(key)
            result[str(key)] = {
                "page_id": row["id"],
                "properties": properties,
            }
        return result

    def create(
        self,
        database: str,
        raw: dict[str, Any],
        icon: str | None = None,
        cover: str | None = None,
    ) -> str:
        body: dict[str, Any] = {
            "parent": {
                "type": "data_source_id",
                "data_source_id": self.sources[database],
            },
            "properties": self.properties(database, raw),
        }
        if icon:
            body["icon"] = {"type": "external", "external": {"url": icon}}
        if cover:
            body["cover"] = {"type": "external", "external": {"url": cover}}
        return self.request("pages", "POST", body)["id"]

    def archive_rows(
        self, database: str, relation: tuple[str, str] | None = None
    ) -> int:
        filter_ = None
        if relation:
            filter_ = {"property": relation[0], "relation": {"contains": relation[1]}}
        rows = self.query_all(database, filter_)
        for row in rows:
            self.request(f"pages/{row['id']}", "PATCH", {"in_trash": True})
        return len(rows)

    def replace_generated_book_content(
        self, page_id: str, children: list[dict[str, Any]]
    ) -> None:
        """Replace only the generated synced block, preserving user blocks."""
        marker = "由 NotionHub 自动同步"
        for block in self.list_children(page_id):
            if block.get("type") != "synced_block" or not block.get("has_children"):
                continue
            nested = self.list_children(block["id"])
            if not nested or nested[0].get("type") != "paragraph":
                continue
            rich_text = (nested[0].get("paragraph") or {}).get("rich_text") or []
            text = "".join(item.get("plain_text", "") for item in rich_text)
            if text == marker:
                self.request(f"blocks/{block['id']}", "DELETE")

        if not children:
            return
        response = self.request(
            f"blocks/{page_id}/children",
            "PATCH",
            {
                "children": [
                    {
                        "object": "block",
                        "type": "synced_block",
                        "synced_block": {"synced_from": None},
                    }
                ]
            },
        )
        container_id = response["results"][0]["id"]
        marker_block = {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {"content": marker},
                        "annotations": {"color": "gray"},
                    }
                ]
            },
        }
        for batch in chunks([marker_block, *children], 100):
            self.request(
                f"blocks/{container_id}/children",
                "PATCH",
                {"children": batch},
            )

    @staticmethod
    def plain_property(prop: dict | None) -> Any:
        """从 Notion 读模型里取出属性的「业务值」（剥离类型外壳）。"""
        return plain_property_value(prop)

    def book_index(self) -> dict[str, dict[str, Any]]:
        result = {}
        for row in self.query_all("书架"):
            properties = row.get("properties") or {}
            book_id = self.plain_property(properties.get("BookId"))
            if book_id:
                last_read = self.plain_property(properties.get("最后阅读时间"))
                if isinstance(last_read, dict):
                    last_read = last_read.get("start")
                result[str(book_id)] = {
                    "page_id": row["id"],
                    # 保留原始 properties 供 upsert 做字段级 diff，避免为比对
                    # 现有值再发一次 GET 请求。
                    "properties": properties,
                    "sort": self.plain_property(properties.get("Sort")) or 0,
                    "sync_version": self.plain_property(properties.get("同步版本"))
                    or 0,
                    "title": self.plain_property(
                        properties.get(self.titles["书架"])
                    )
                    or "",
                    "reading_seconds": self.plain_property(
                        properties.get("阅读时长")
                    )
                    or 0,
                    "progress": self.plain_property(properties.get("阅读进度")) or 0,
                    "status": self.plain_property(properties.get("阅读状态")) or "",
                    "current_chapter": self.plain_property(
                        properties.get("当前章节")
                    )
                    or "",
                    "last_read": last_read,
                    "content_type": self.plain_property(properties.get("内容类型"))
                    or "",
                }
        return result

    def backup_and_archive(self, backup_dir: Path, databases: Iterable[str]) -> Path:
        backup_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "created_at": datetime.now().astimezone().isoformat(),
            "notion_page_id": self.page_id,
            "databases": {},
        }
        rows_by_database = {}
        for name in databases:
            rows = self.query_all(name)
            rows_by_database[name] = rows
            payload["databases"][name] = rows
        target = backup_dir / f"weread2notion-{datetime.now():%Y%m%d-%H%M%S}.json"
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        for rows in rows_by_database.values():
            for row in rows:
                self.request(f"pages/{row['id']}", "PATCH", {"in_trash": True})
        return target

    def restore_from_backup(self, path: Path) -> int:
        """从全量备份 JSON 恢复页面（取消归档 in_trash）。

        全量同步仅将旧页面移入回收站（不删除），因此恢复等价于取消归档。
        """
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        restored = 0
        for rows in (payload.get("databases") or {}).values():
            for row in rows:
                page_id = row.get("id")
                if not page_id:
                    continue
                self.request(f"pages/{page_id}", "PATCH", {"in_trash": False})
                restored += 1
        return restored
