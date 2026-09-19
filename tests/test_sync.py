from datetime import date

from weread2notion.notion import NotionWorkspace
from weread2notion.sync import Synchronizer


class Notion:
    titles = {
        "书架": "书名",
        "日": "标题",
        "周": "标题",
        "月": "标题",
        "年": "标题",
    }

    def __init__(self):
        self.rows = []
        self.upserts = []
        self.requests = []
        self.archived = []
        self.indexes = {}
        self.query_rows = {}
        self.sources = {}
        self.schemas = {
            name: {"时长": "number", "时长（分钟）": "number"}
            for name in ("日", "周", "月", "年", "阅读记录")
        }

    def upsert(
        self,
        database,
        key_name,
        key_value,
        raw,
        icon,
        cover=None,
        existing_id=None,
        existing_properties=None,
    ):
        self.upserts.append(
            {
                "database": database,
                "key_name": key_name,
                "key_value": key_value,
                "raw": raw,
                "existing_id": existing_id,
                "existing_properties": existing_properties,
            }
        )
        self.rows.append((database, raw))
        return existing_id or f"{database}:{key_value}"

    def request(self, *args, **kwargs):
        self.requests.append((args, kwargs))
        return {}

    def properties(self, database, raw):
        return raw

    # 本 Fake 的 properties() 不做类型转换，返回的是原始 Python 值，
    # 因此这里不能直接用 NotionWorkspace.changed_properties（它期望写模型）。
    # 语义保持一致：逐字段比对，只返回真正变化的属性。
    def changed_properties(self, database, existing, desired):
        if not existing:
            return desired
        schema = self.schemas.get(database) or {}
        changed = {}
        for name, value in desired.items():
            # rollup / formula 等由 Notion 计算，永远不写（与真实实现一致）。
            if schema.get(name) in NotionWorkspace.READ_ONLY_KINDS:
                continue
            current = existing.get(name)
            if current is None:
                changed[name] = value
                continue
            have = self.plain_property(current)
            if isinstance(have, dict) and "start" in have and isinstance(value, str):
                # date 读模型 vs 原始日期字符串
                same = (have.get("start") or None) == value
            elif isinstance(have, dict) and isinstance(value, dict):
                same = (have.get("start") or None) == (value.get("start") or None) and (
                    have.get("end") or None
                ) == (value.get("end") or None)
            elif isinstance(have, float) or isinstance(value, float):
                try:
                    same = abs(float(have) - float(value)) < 1e-9
                except (TypeError, ValueError):
                    same = have == value
            else:
                same = have == value
            if not same:
                changed[name] = value
        return changed

    def row_index(self, database, key_name):
        return self.indexes.get(database, {})

    def query_all(self, database, filter_=None):
        return self.query_rows.get(database, [])

    @staticmethod
    def plain_property(prop):
        if not prop:
            return None
        kind = prop.get("type")
        value = prop.get(kind)
        if kind in {"title", "rich_text"}:
            return "".join(item.get("plain_text", "") for item in (value or []))
        return value

    def archive_rows(self, *args, **kwargs):
        self.archived.append((args, kwargs))
        return 1

    def create(self, database, raw, icon):
        self.rows.append((database, raw))
        return f"{database}:created"

    def replace_generated_book_content(self, page_id, blocks):
        self.rows.append(("正文", {"page_id": page_id, "blocks": blocks}))


def test_period_rows_have_valid_date_ranges():
    notion = Notion()
    sync = Synchronizer(None, notion)
    sync.sync_periods([{"timestamp": 1691251200, "duration": 600}])
    ranges = {database: raw["日期"] for database, raw in notion.rows}
    assert ranges["日"] == {"start": "2023-08-06", "end": None}
    assert ranges["周"] == {"start": "2023-07-31", "end": "2023-08-06"}
    assert ranges["月"] == {"start": "2023-08-01", "end": "2023-08-31"}
    assert ranges["年"] == {"start": "2023-01-01", "end": "2023-12-31"}
    day = next(raw for database, raw in notion.rows if database == "日")
    assert day["时长（分钟）"] == 10


def test_book_sync_uses_accumulated_reading_time():
    notion = Notion()
    sync = Synchronizer(None, notion)
    sync.sync_books(
        {"book-1": {"title": "测试书籍"}},
        {
            "book-1": {
                "info": {"title": "测试书籍"},
                "progress": {
                    "progress": 50,
                    "readingTime": 3206,
                    "recordReadingTime": 0,
                },
            }
        },
        {},
        {},
        {"day": {}, "week": {}, "month": {}, "year": {}},
        {"book-1"},
        {},
    )
    book = next(raw for database, raw in notion.rows if database == "书架")
    assert book["阅读时长"] == 3206
    assert book["阅读时长（分钟）"] == 3206 / 60
    assert "同步版本" not in book


def test_book_period_relations_use_finish_time_not_last_read_time():
    notion = Notion()
    sync = Synchronizer(None, notion)
    finish_time = 1704067200  # 2024-01-01 Asia/Shanghai
    last_read_time = 1735689600  # 2025-01-01 Asia/Shanghai
    periods = {
        "day": {"2024-01-01": "day-2024"},
        "week": {"2024-01-01": "week-2024"},
        "month": {"2024-01": "month-2024"},
        "year": {"2024": "year-2024", "2025": "year-2025"},
    }
    sync.sync_books(
        {"book-1": {"title": "测试书籍", "finishReading": 1}},
        {
            "book-1": {
                "info": {"title": "测试书籍"},
                "progress": {
                    "progress": 100,
                    "finishTime": finish_time,
                    "updateTime": last_read_time,
                },
            }
        },
        {},
        {},
        periods,
        {"book-1"},
        {},
    )
    book = next(raw for database, raw in notion.rows if database == "书架")
    assert book["阅读完成时间"] == "2024-01-01"
    assert book["最后阅读时间"] == "2025-01-01"
    assert book["年"] == ["year-2024"]


def test_book_status_uses_explicit_shelf_finish_marker():
    notion = Notion()
    sync = Synchronizer(None, notion)
    sync.sync_books(
        {"book-1": {"title": "生死疲劳", "finishReading": 1}},
        {
            "book-1": {
                "info": {"title": "生死疲劳"},
                "progress": {"progress": 12, "readingTime": 600},
            }
        },
        {},
        {},
        {"day": {}, "week": {}, "month": {}, "year": {}},
        {"book-1"},
        {},
    )
    book = next(raw for database, raw in notion.rows if database == "书架")
    assert book["阅读状态"] == "已读"


def test_completed_progress_can_be_displayed_as_100_percent():
    notion = Notion()
    sync = Synchronizer(
        None, notion, preferences={"completed_progress_100": True}
    )
    sync.sync_books(
        {"book-1": {"title": "测试书籍", "finishReading": 1}},
        {
            "book-1": {
                "info": {"title": "测试书籍"},
                "progress": {"progress": 40},
            }
        },
        {},
        {},
        {"day": {}, "week": {}, "month": {}, "year": {}},
        {"book-1"},
        {},
    )
    book = next(raw for database, raw in notion.rows if database == "书架")
    assert book["阅读进度"] == 1


def test_sync_version_is_marked_only_after_book_content():
    notion = Notion()
    sync = Synchronizer(None, notion)
    sync.sync_book_content(
        {
            "book-1": {
                "chapters": [],
                "highlights": [],
                "reviews": [],
            }
        },
        {"book-1": "page-1"},
        {"day": {}, "week": {}, "month": {}, "year": {}},
    )
    assert notion.rows[-1] == ("正文", {"page_id": "page-1", "blocks": []})
    assert notion.requests[-1][0] == (
        "pages/page-1",
        "PATCH",
        {"properties": {"同步版本": 8}},
    )


def test_periods_include_zero_duration_book_dates():
    notion = Notion()
    sync = Synchronizer(None, notion)
    maps = sync.sync_periods([], [1784563200])
    assert "2026" in maps["year"]
    assert "2026-07" in maps["month"]


def test_unchanged_periods_do_not_write_pages():
    notion = Notion()
    timestamp = 1691251200
    # 真实 Notion 会返回该行的全部属性，这里也补全标题 / 日期 / 时间戳，
    # 否则 diff 会把它们当成「模板新增字段」而误判为需要写入。
    def period_props(key, start, end, with_timestamp=False):
        props = {
            "标题": {"type": "title", "title": [{"plain_text": key}]},
            "日期": {"type": "date", "date": {"start": start, "end": end}},
            "时长": {"type": "number", "number": 600},
            "时长（分钟）": {"type": "number", "number": 10},
        }
        if with_timestamp:
            props["时间戳"] = {"type": "number", "number": timestamp}
        return props

    notion.indexes = {
        "日": {
            "2023-08-06": {
                "page_id": "day-page",
                "properties": period_props(
                    "2023-08-06", "2023-08-06", None, with_timestamp=True
                ),
            }
        },
        "周": {
            "2023-07-31": {
                "page_id": "week-page",
                "properties": period_props("2023-07-31", "2023-07-31", "2023-08-06"),
            }
        },
        "月": {
            "2023-08": {
                "page_id": "month-page",
                "properties": period_props("2023-08", "2023-08-01", "2023-08-31"),
            }
        },
        "年": {
            "2023": {
                "page_id": "year-page",
                "properties": period_props("2023", "2023-01-01", "2023-12-31"),
            }
        },
    }
    sync = Synchronizer(None, notion)
    maps = sync.sync_periods([{"timestamp": timestamp, "duration": 600}])
    assert maps["day"]["2023-08-06"] == "day-page"
    assert notion.rows == []
    assert notion.requests == []


def test_rollup_period_metrics_are_not_patched():
    notion = Notion()
    notion.schemas["月"] = {"时长": "rollup"}
    notion.indexes = {
        "月": {
            "2023-08": {
                "page_id": "month-page",
                "properties": {
                    "标题": {"type": "title", "title": [{"plain_text": "2023-08"}]},
                    "日期": {
                        "type": "date",
                        "date": {"start": "2023-08-01", "end": "2023-08-31"},
                    },
                    # rollup 由 Notion 计算，必须在 diff 中被跳过
                    "时长": {"type": "rollup", "rollup": {}},
                    "时长（分钟）": {"type": "number", "number": 10},
                },
            }
        }
    }
    sync = Synchronizer(None, notion)
    sync.sync_periods([{"timestamp": 1691251200, "duration": 600}], full=False)
    month_updates = [
        request for request in notion.requests if request[0][0] == "pages/month-page"
    ]
    assert month_updates == []


def test_existing_people_and_categories_are_reused_without_writes():
    notion = Notion()
    notion.titles.update({"作者": "姓名", "分类": "名称"})
    notion.indexes = {
        "作者": {"作者甲": {"page_id": "author-page", "properties": {}}},
        "分类": {"分类甲": {"page_id": "category-page", "properties": {}}},
    }
    sync = Synchronizer(None, notion)
    authors, categories = sync.sync_people_and_categories(
        [{"author": "作者甲", "category": "分类甲"}], {}
    )
    assert authors == {"作者甲": "author-page"}
    assert categories == {"分类甲": "category-page"}
    assert notion.rows == []


def test_new_people_and_categories_are_created_with_icons():
    notion = Notion()
    notion.titles.update({"作者": "姓名", "分类": "名称"})
    created = []

    def create(database, raw, icon):
        created.append((database, raw, icon))
        return f"{database}:created"

    notion.create = create
    sync = Synchronizer(None, notion)

    authors, categories = sync.sync_people_and_categories(
        [{"author": "作者甲", "category": "分类甲"}], {}
    )

    assert authors == {"作者甲": "作者:created"}
    assert categories == {"分类甲": "分类:created"}
    assert created == [
        (
            "作者",
            {"姓名": "作者甲"},
            "https://www.notion.so/icons/user-circle-filled_gray.svg",
        ),
        (
            "分类",
            {"名称": "分类甲"},
            "https://www.notion.so/icons/tag_gray.svg",
        ),
    ]


def test_unchanged_reading_records_do_not_write_pages():
    notion = Notion()
    notion.titles["阅读记录"] = "标题"
    notion.sources = {"阅读记录": "source"}
    notion.indexes = {
        "阅读记录": {
            "1691251200": {
                "page_id": "record-page",
                "properties": {
                    "标题": {"type": "title", "title": [{"plain_text": "2023-08-06"}]},
                    "日期": {
                        "type": "date",
                        "date": {"start": "2023-08-06", "end": None},
                    },
                    "Date": {
                        "type": "date",
                        "date": {"start": "2023-08-06", "end": None},
                    },
                    "时长": {"type": "number", "number": 600},
                    "时长（分钟）": {"type": "number", "number": 10},
                    "时间戳": {"type": "number", "number": 1691251200},
                },
            }
        }
    }
    sync = Synchronizer(None, notion)
    sync.sync_reading_records(
        [{"timestamp": 1691251200, "duration": 600}],
        {"day": {}, "week": {}, "month": {}, "year": {}},
    )
    assert notion.rows == []
    assert notion.requests == []


def test_changed_reading_records_patch_only_changed_field():
    """时长变化后，只把变化的时长字段发过去，标题/日期/时间戳不应重发。"""
    notion = Notion()
    notion.titles["阅读记录"] = "标题"
    notion.sources = {"阅读记录": "source"}
    notion.indexes = {
        "阅读记录": {
            "1691251200": {
                "page_id": "record-page",
                "properties": {
                    "标题": {"type": "title", "title": [{"plain_text": "2023-08-06"}]},
                    "日期": {
                        "type": "date",
                        "date": {"start": "2023-08-06", "end": None},
                    },
                    "Date": {
                        "type": "date",
                        "date": {"start": "2023-08-06", "end": None},
                    },
                    "时长": {"type": "number", "number": 600},
                    "时长（分钟）": {"type": "number", "number": 10},
                    "时间戳": {"type": "number", "number": 1691251200},
                },
            }
        }
    }
    sync = Synchronizer(None, notion)
    sync.sync_reading_records(
        [{"timestamp": 1691251200, "duration": 900}],
        {"day": {}, "week": {}, "month": {}, "year": {}},
    )
    # 只关心时长更新这一次请求，确认它没有顺带重发未变化的字段。
    updates = [r for r in notion.requests if "时长" in r[0][2]["properties"]]
    assert len(updates) == 1
    assert updates[0][0][0] == "pages/record-page"
    assert set(updates[0][0][2]["properties"]) == {"时长", "时长（分钟）"}


def test_changed_periods_patch_only_changed_metrics():
    notion = Notion()
    timestamp = 1691251200
    notion.indexes = {
        "日": {
            "2023-08-06": {
                "page_id": "day-page",
                "properties": {
                    "标题": {"type": "title", "title": [{"plain_text": "2023-08-06"}]},
                    "日期": {
                        "type": "date",
                        "date": {"start": "2023-08-06", "end": None},
                    },
                    "时长": {"type": "number", "number": 600},
                    "时长（分钟）": {"type": "number", "number": 10},
                    "时间戳": {"type": "number", "number": timestamp},
                },
            }
        },
        "周": {},
        "月": {},
        "年": {},
    }
    sync = Synchronizer(None, notion)
    sync.sync_periods([{"timestamp": timestamp, "duration": 900}])
    # 后续还有一次写入 relation 的 PATCH，这里只断言时长更新本身。
    duration_updates = [
        r
        for r in notion.requests
        if r[0][0] == "pages/day-page" and "时长" in r[0][2]["properties"]
    ]
    assert len(duration_updates) == 1
    assert set(duration_updates[0][0][2]["properties"]) == {"时长", "时长（分钟）"}


def test_rollup_period_metrics_are_not_patched():
    blocks = Synchronizer.book_content_blocks(
        {
            "chapters": [{"chapterUid": 1, "chapterIdx": 1, "title": "第一章"}],
            "highlights": [{"chapterUid": 1, "markText": "一条划线"}],
            "reviews": [],
        }
    )
    assert blocks[0]["type"] == "table_of_contents"
    assert blocks[1]["heading_2"]["rich_text"][0]["text"]["content"] == "第一章"
    assert blocks[2]["callout"]["rich_text"][0]["text"]["content"] == "一条划线"


def test_daily_snapshot_uses_previous_book_state_for_delta():
    notion = Notion()
    notion.sources["阅读快照"] = "snapshots-source"
    notion.titles["阅读快照"] = "快照"
    sync = Synchronizer(None, notion)

    sync.sync_daily_snapshots(
        {
            "book-1": {
                "bookId": "book-1",
                "title": "测试书籍",
                "kind": "book",
                "readUpdateTime": 1691251200,
            }
        },
        {
            "book-1": {
                "info": {"title": "测试书籍"},
                "progress": {
                    "progress": 50,
                    "readingTime": 900,
                    "updateTime": 1691251200,
                },
                "chapters": [],
            }
        },
        {
            "book-1": {
                "reading_seconds": 600,
                "progress": 0.4,
                "status": "在读",
            }
        },
        snapshot_date=date(2026, 7, 31),
    )

    snapshot = notion.upserts[-1]
    assert snapshot["key_value"] == "2026-07-31:book-1"
    assert snapshot["raw"]["累计阅读时长"] == 900
    assert snapshot["raw"]["当日新增阅读时长"] == 300
    assert snapshot["raw"]["当日新增阅读时长（分钟）"] == 5
    assert snapshot["raw"]["阅读进度"] == 0.5


def test_snapshot_passes_existing_properties_for_diff():
    """同一天重复同步时，必须把已有行的属性交给 upsert 做字段级 diff。"""
    notion = Notion()
    notion.sources["阅读快照"] = "snapshots-source"
    notion.titles["阅读快照"] = "快照"
    notion.query_rows["阅读快照"] = [
        {
            "id": "snapshot-page",
            "properties": {
                "BookId": {
                    "type": "rich_text",
                    "rich_text": [{"plain_text": "book-1"}],
                },
                "累计阅读时长": {"type": "number", "number": 900},
                "当日新增阅读时长": {"type": "number", "number": 300},
            },
        }
    ]
    sync = Synchronizer(None, notion)
    sync.sync_daily_snapshots(
        {
            "book-1": {
                "bookId": "book-1",
                "title": "测试书籍",
                "kind": "book",
                "readUpdateTime": 1691251200,
            }
        },
        {
            "book-1": {
                "info": {"title": "测试书籍"},
                "progress": {
                    "progress": 50,
                    "readingTime": 900,
                    "updateTime": 1691251200,
                },
                "chapters": [],
            }
        },
        {"book-1": {"reading_seconds": 600, "progress": 0.4, "status": "在读"}},
        snapshot_date=date(2026, 7, 31),
    )

    snapshot = notion.upserts[-1]
    # 复用已有页（同一天同一本书只保留一条）
    assert snapshot["existing_id"] == "snapshot-page"
    # 传入了现有属性，upsert 才能做 diff 而不是整页覆盖
    assert snapshot["existing_properties"]["累计阅读时长"] == {
        "type": "number",
        "number": 900,
    }


def test_daily_snapshot_reuses_same_day_row_and_accumulates_delta():
    notion = Notion()
    notion.sources["阅读快照"] = "snapshots-source"
    notion.titles["阅读快照"] = "快照"
    notion.query_rows["阅读快照"] = [
        {
            "id": "snapshot-page",
            "properties": {
                "BookId": {"type": "rich_text", "rich_text": [{"plain_text": "book-1"}]},
                "累计阅读时长": {"type": "number", "number": 900},
                "当日新增阅读时长": {"type": "number", "number": 300},
            },
        }
    ]
    sync = Synchronizer(None, notion)

    sync.sync_daily_snapshots(
        {"book-1": {"bookId": "book-1", "title": "测试书籍", "kind": "book"}},
        {
            "book-1": {
                "info": {"title": "测试书籍"},
                "progress": {"progress": 55, "readingTime": 1020},
                "chapters": [],
            }
        },
        {"book-1": {"reading_seconds": 600}},
        snapshot_date=date(2026, 7, 31),
    )

    snapshot = notion.upserts[-1]
    assert snapshot["existing_id"] == "snapshot-page"
    assert snapshot["raw"]["当日新增阅读时长"] == 420


def test_new_book_lifetime_time_is_not_counted_as_today():
    notion = Notion()
    notion.sources["阅读快照"] = "snapshots-source"
    notion.titles["阅读快照"] = "快照"
    sync = Synchronizer(None, notion)

    sync.sync_daily_snapshots(
        {"book-1": {"bookId": "book-1", "title": "新书", "kind": "book"}},
        {
            "book-1": {
                "info": {"title": "新书"},
                "progress": {"progress": 70, "readingTime": 7200},
                "chapters": [],
            }
        },
        {},
        snapshot_date=date(2026, 7, 31),
    )

    assert notion.upserts[-1]["raw"]["当日新增阅读时长"] == 0


def test_plan_uses_shelf_as_authoritative_source():
    class Weread:
        def shelf(self):
            return {"books": [{"bookId": "on-shelf", "title": "书架中的书"}]}

        def notebooks(self):
            return (
                [
                    {"bookId": "on-shelf", "sort": 2},
                    {"bookId": "removed", "sort": 3},
                ],
                {"books": 2, "notes": 1},
            )

    plan = Synchronizer(Weread(), Notion()).plan()
    assert plan["book_ids"] == ["on-shelf"]
    assert [entry["bookId"] for entry in plan["entries"]] == ["on-shelf"]


def test_removed_book_and_related_rows_are_moved_to_trash():
    notion = Notion()
    notion.sources = {"笔记": "notes", "划线": "marks"}
    notion.schemas.update(
        {
            "笔记": {"书籍": "relation"},
            "划线": {"书籍": "relation"},
        }
    )
    sync = Synchronizer(None, notion)
    sync.delete_removed_books(
        {"removed"}, {"removed": {"page_id": "book-page"}}
    )

    assert [call[0] for call in notion.archived] == [
        ("笔记", ("书籍", "book-page")),
        ("划线", ("书籍", "book-page")),
    ]
    assert notion.requests[-1][0] == (
        "pages/book-page",
        "PATCH",
        {"in_trash": True},
    )
    assert sync.counts["删除书架"] == 1
