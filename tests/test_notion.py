from weread2notion.notion import NotionWorkspace


class TransientError(RuntimeError):
    status = 520


class Client:
    def __init__(self):
        self.calls = 0

    def request(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            raise TransientError("temporary Notion failure")
        return {"ok": True}


def test_request_retries_transient_notion_errors(monkeypatch):
    monkeypatch.setattr("weread2notion.notion_http.time.sleep", lambda _: None)
    client = Client()
    notion = NotionWorkspace("token", "page", "version", client=client)
    assert notion.request("pages/page", "PATCH", {}) == {"ok": True}
    assert client.calls == 2


def test_upsert_refreshes_existing_page_icon(monkeypatch):
    notion = NotionWorkspace("token", "page", "version", client=Client())
    notion.schemas["year"] = {}
    monkeypatch.setattr(
        notion, "properties", lambda database, raw: {"Name": raw["Name"]}
    )
    monkeypatch.setattr(
        notion, "find", lambda database, key, value: {"id": "year-page"}
    )
    calls = []
    monkeypatch.setattr(
        notion, "request", lambda path, method, body: calls.append((path, method, body))
    )

    page_id = notion.upsert(
        "year",
        "Name",
        "2026",
        {"Name": "2026"},
        "https://www.notion.so/icons/target_red.svg",
    )

    assert page_id == "year-page"
    assert calls[0][2]["icon"] == {
        "type": "external",
        "external": {"url": "https://www.notion.so/icons/target_red.svg"},
    }


def test_upsert_reuses_known_page_without_query(monkeypatch):
    notion = NotionWorkspace("token", "page", "version", client=Client())
    notion.schemas["book"] = {}
    monkeypatch.setattr(notion, "properties", lambda database, raw: {"Name": "Book"})
    monkeypatch.setattr(
        notion,
        "find",
        lambda *args: (_ for _ in ()).throw(AssertionError("find should not run")),
    )
    calls = []
    monkeypatch.setattr(
        notion,
        "request",
        lambda path, method, body: calls.append((path, method, body)),
    )
    page_id = notion.upsert(
        "book", "BookId", "book-1", {"Name": "Book"}, existing_id="page-1"
    )
    assert page_id == "page-1"
    assert calls[0][0] == "pages/page-1"


def test_row_index_normalizes_integer_float_keys(monkeypatch):
    notion = NotionWorkspace("token", "page", "version", client=Client())
    monkeypatch.setattr(
        notion,
        "query_all",
        lambda database: [
            {
                "id": "record-page",
                "properties": {"时间戳": {"type": "number", "number": 1.0}},
            }
        ],
    )
    assert notion.row_index("阅读记录", "时间戳")["1"]["page_id"] == "record-page"


def test_existing_sync_settings_are_read_from_notion(monkeypatch):
    notion = NotionWorkspace("token", "page", "version", client=Client())
    notion.sources["设置"] = "settings-source"
    notion.schemas["设置"] = {
        "配置": "title",
        "阅读完成进度强制改为100%": "checkbox",
        "只同步我的书架书籍": "checkbox",
        "同步划线和笔记": "checkbox",
        "阅读统计起始年份": "number",
        "同步配置版本（不可删除）": "number",
    }
    monkeypatch.setattr(
        notion,
        "query_all",
        lambda database: [
            {
                "properties": {
                    "阅读完成进度强制改为100%": {
                        "type": "checkbox",
                        "checkbox": True,
                    },
                    "只同步我的书架书籍": {
                        "type": "checkbox",
                        "checkbox": False,
                    },
                    "同步划线和笔记": {
                        "type": "checkbox",
                        "checkbox": True,
                    },
                    "阅读统计起始年份": {"type": "number", "number": 2025},
                    "同步配置版本（不可删除）": {
                        "type": "number",
                        "number": 0,
                    },
                }
            }
        ],
    )
    settings = notion.ensure_sync_settings()
    assert {key: settings[key] for key in (
        "completed_progress_100",
        "delete_removed",
        "sync_notes",
        "start_year",
    )} == {
        "completed_progress_100": True,
        "delete_removed": False,
        "sync_notes": True,
        "start_year": 2025,
    }
    assert settings["settings_changed"] is True


def test_legacy_sync_setting_names_remain_compatible(monkeypatch):
    notion = NotionWorkspace("token", "page", "version", client=Client())
    notion.sources["设置"] = "settings-source"
    notion.schemas["设置"] = {
        "配置": "title",
        "已读进度显示为100%": "checkbox",
        "移出书架时删除": "checkbox",
        "同步划线和笔记": "checkbox",
        "阅读统计起始年份": "number",
        "已应用配置码": "number",
    }
    monkeypatch.setattr(
        notion,
        "query_all",
        lambda database: [
            {
                "id": "settings-page",
                "properties": {
                    "已读进度显示为100%": {
                        "type": "checkbox",
                        "checkbox": True,
                    },
                    "移出书架时删除": {
                        "type": "checkbox",
                        "checkbox": False,
                    },
                    "同步划线和笔记": {
                        "type": "checkbox",
                        "checkbox": True,
                    },
                    "阅读统计起始年份": {"type": "number", "number": 2024},
                    "已应用配置码": {"type": "number", "number": 0},
                },
            }
        ],
    )
    monkeypatch.setattr(notion, "request", lambda *args, **kwargs: {})
    settings = notion.ensure_sync_settings()
    assert settings["completed_progress_100"] is True
    assert settings["delete_removed"] is False
    assert settings["_config_property"] == "已应用配置码"


def test_missing_sync_settings_database_is_created(monkeypatch):
    notion = NotionWorkspace("token", "root-page", "version", client=Client())
    calls = []
    rows = []

    def request(path, method="GET", body=None):
        calls.append((path, method, body))
        if path == "databases":
            return {"id": "settings-db", "data_sources": [{"id": "settings-source"}]}
        return {}

    def query_all(database):
        if not rows:
            return []
        return rows

    def create(database, raw, icon=None, cover=None):
        rows.append(
            {
                "properties": {
                    "阅读完成进度强制改为100%": {
                        "type": "checkbox",
                        "checkbox": raw["阅读完成进度强制改为100%"],
                    },
                    "只同步我的书架书籍": {
                        "type": "checkbox",
                        "checkbox": raw["只同步我的书架书籍"],
                    },
                    "同步划线和笔记": {
                        "type": "checkbox",
                        "checkbox": raw["同步划线和笔记"],
                    },
                    "阅读统计起始年份": {
                        "type": "number",
                        "number": raw["阅读统计起始年份"],
                    },
                    "同步配置版本（不可删除）": {
                        "type": "number",
                        "number": raw["同步配置版本（不可删除）"],
                    },
                }
            }
        )
        return "settings-page"

    monkeypatch.setattr(notion, "request", request)
    monkeypatch.setattr(notion, "query_all", query_all)
    monkeypatch.setattr(notion, "create", create)

    settings = notion.ensure_sync_settings(2024)
    assert settings["start_year"] == 2024
    assert notion.sources["设置"] == "settings-source"
    assert calls[0][0:2] == ("databases", "POST")
    assert any(call[0] == "blocks/settings-page/children" for call in calls)


def test_missing_reading_snapshots_database_is_created(monkeypatch):
    notion = NotionWorkspace("token", "root-page", "version", client=Client())
    calls = []

    def request(path, method="GET", body=None):
        calls.append((path, method, body))
        return {
            "id": "snapshots-db",
            "data_sources": [{"id": "snapshots-source"}],
        }

    monkeypatch.setattr(notion, "request", request)
    notion.ensure_reading_snapshots()

    assert calls[0][0:2] == ("databases", "POST")
    properties = calls[0][2]["initial_data_source"]["properties"]
    assert properties["快照"] == {"title": {}}
    assert properties["SnapshotKey"] == {"rich_text": {}}
    assert properties["阅读进度"] == {"number": {"format": "percent"}}
    assert notion.sources["阅读快照"] == "snapshots-source"
    assert notion.titles["阅读快照"] == "快照"


def test_existing_reading_snapshots_database_gets_missing_properties(monkeypatch):
    notion = NotionWorkspace("token", "root-page", "version", client=Client())
    notion.sources["阅读快照"] = "snapshots-source"
    notion.schemas["阅读快照"] = {"快照": "title", "SnapshotKey": "rich_text"}
    notion.titles["阅读快照"] = "快照"
    calls = []
    monkeypatch.setattr(
        notion,
        "request",
        lambda path, method="GET", body=None: calls.append((path, method, body))
        or {},
    )

    notion.ensure_reading_snapshots()

    assert calls[0][0:2] == ("data_sources/snapshots-source", "PATCH")
    assert "日期" in calls[0][2]["properties"]
    assert "SnapshotKey" not in calls[0][2]["properties"]


# --- 字段级 diff（upsert 只写变化字段） --------------------------------------

def _diff_notion():
    notion = NotionWorkspace("token", "page", "version", client=Client())
    notion.schemas["book"] = {
        "Name": "title",
        "Desc": "rich_text",
        "Score": "number",
        "Done": "checkbox",
        "Status": "status",
        "Tags": "multi_select",
        "ReadAt": "date",
        "Period": "relation",
        "Link": "url",
    }
    notion.sources["book"] = "book-source"
    return notion


def _unchanged_existing():
    return {
        "Name": {"type": "title", "title": [{"plain_text": "三体"}]},
        "Desc": {"type": "rich_text", "rich_text": [{"plain_text": "科幻"}]},
        "Score": {"type": "number", "number": 9.0},
        "Done": {"type": "checkbox", "checkbox": True},
        "Status": {"type": "status", "status": {"name": "在读"}},
        "Tags": {
            "type": "multi_select",
            "multi_select": [{"name": "科幻"}, {"name": "长篇"}],
        },
        "ReadAt": {"type": "date", "date": {"start": "2026-01-01", "end": None}},
        "Period": {"type": "relation", "relation": [{"id": "p1"}]},
        "Link": {"type": "url", "url": "https://example.com"},
    }


def _unchanged_raw():
    return {
        "Name": "三体",
        "Desc": "科幻",
        "Score": 9.0,
        "Done": True,
        "Status": "在读",
        "Tags": ["长篇", "科幻"],  # 顺序与现有值不同，应视为未变
        "ReadAt": {"start": "2026-01-01"},
        "Period": ["p1"],
        "Link": "https://example.com",
    }


def test_changed_properties_returns_only_modified_fields():
    notion = _diff_notion()
    desired = notion.properties("book", _unchanged_raw())
    assert notion.changed_properties("book", _unchanged_existing(), desired) == {}


def test_changed_properties_detects_each_kind():
    notion = _diff_notion()
    cases = {
        "Name": "三体2",
        "Desc": "科幻小说",
        "Score": 8.5,
        "Done": False,
        "Status": "已读",
        "Tags": ["科幻"],
        "ReadAt": {"start": "2026-02-02"},
        "Period": ["p2"],
        "Link": "https://other.example.com",
    }
    for field, new_value in cases.items():
        raw = _unchanged_raw()
        raw[field] = new_value
        desired = notion.properties("book", raw)
        changed = notion.changed_properties("book", _unchanged_existing(), desired)
        assert list(changed) == [field], field


def test_changed_properties_keeps_fields_missing_in_notion():
    """模板新增字段时，现有记录没有该属性，必须写入。"""
    notion = _diff_notion()
    desired = notion.properties("book", {"Name": "三体", "Desc": "科幻"})
    existing = {"Name": {"type": "title", "title": [{"plain_text": "三体"}]}}
    assert list(notion.changed_properties("book", existing, desired)) == ["Desc"]


def test_changed_properties_ignores_read_only_kinds():
    notion = _diff_notion()
    notion.schemas["book"]["Rollup"] = "rollup"
    existing = _unchanged_existing()
    existing["Rollup"] = {"type": "rollup", "rollup": {"number": 3}}
    desired = dict(notion.properties("book", _unchanged_raw()))
    desired["Rollup"] = {"rollup": {"number": 3}}
    assert notion.changed_properties("book", existing, desired) == {}


def test_upsert_skips_request_when_nothing_changed(monkeypatch):
    notion = _diff_notion()
    calls = []
    monkeypatch.setattr(
        notion, "request", lambda path, method, body=None: calls.append((path, method))
    )
    page_id = notion.upsert(
        "book",
        "Name",
        "三体",
        _unchanged_raw(),
        existing_id="page-1",
        existing_properties=_unchanged_existing(),
    )
    assert page_id == "page-1"
    assert calls == []  # 无变化则完全不发请求


def test_upsert_patches_only_changed_field(monkeypatch):
    notion = _diff_notion()
    calls = []
    monkeypatch.setattr(
        notion,
        "request",
        lambda path, method, body=None: calls.append((path, method, body)) or {"id": "page-1"},
    )
    raw = _unchanged_raw()
    raw["Score"] = 8.5
    notion.upsert(
        "book",
        "Name",
        "三体",
        raw,
        existing_id="page-1",
        existing_properties=_unchanged_existing(),
    )
    assert calls[0][0] == "pages/page-1"
    assert list(calls[0][2]["properties"]) == ["Score"]


def test_upsert_falls_back_to_full_write_without_existing_properties(monkeypatch):
    """拿不到现有属性时不做 diff，退回全量覆盖（保守但安全）。"""
    notion = _diff_notion()
    calls = []
    monkeypatch.setattr(
        notion,
        "request",
        lambda path, method, body=None: calls.append((path, method, body)) or {"id": "page-1"},
    )
    notion.upsert("book", "Name", "三体", _unchanged_raw(), existing_id="page-1")
    assert set(calls[0][2]["properties"]) == set(_unchanged_raw())


def test_upsert_creates_page_when_not_found(monkeypatch):
    notion = _diff_notion()
    calls = []
    monkeypatch.setattr(notion, "find", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        notion,
        "request",
        lambda path, method, body=None: calls.append((path, method, body)) or {"id": "new-page"},
    )
    page_id = notion.upsert("book", "Name", "三体", _unchanged_raw())
    assert page_id == "new-page"
    assert calls[0][0] == "pages"
    assert set(calls[0][2]["properties"]) == set(_unchanged_raw())
