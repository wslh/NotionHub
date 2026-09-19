from weread2notion.analytics import reading_insights, snapshot_diff
from weread2notion.notion import NotionWorkspace


class FakeNotion:
    sources = {"阅读快照": "snap-source"}

    def __init__(self, rows):
        self._rows = rows

    def query_all(self, database):
        return self._rows.get(database, [])

    def find(self, database, key, value):
        for row in self._rows.get(database, []):
            props = row.get("properties") or {}
            if NotionWorkspace.plain_property(props.get(key)) == value:
                return row
        return None

    @staticmethod
    def plain_property(prop):
        return NotionWorkspace.plain_property(prop)


def _snapshot(book_id, day, minutes):
    return {
        "properties": {
            "日期": {"type": "date", "date": {"start": day}},
            "BookId": {"type": "rich_text", "rich_text": [{"plain_text": book_id}]},
            "SnapshotKey": {
                "type": "rich_text",
                "rich_text": [{"plain_text": f"{book_id}-{day}"}],
            },
            "累计阅读时长（分钟）": {"type": "number", "number": minutes},
        }
    }


def test_reading_insights_aggregates():
    rows = {
        "阅读快照": [
            _snapshot("b1", "2026-07-30", 30),
            _snapshot("b1", "2026-07-31", 60),
            _snapshot("b2", "2026-07-31", 30),  # 同日，与 b1 的 60 合计 90
        ]
    }
    insights = reading_insights(FakeNotion(rows))
    assert insights["total_minutes"] == 120
    assert insights["total_hours"] == 2.0
    assert insights["active_days"] == 2
    assert insights["daily_average_minutes"] == 60
    assert insights["top_books_minutes"][0][0] == "b1"
    assert insights["longest_streak_days"] == 2
    assert insights["current_streak_days"] == 0  # 今天不在阅读集合内


def test_reading_insights_empty():
    insights = reading_insights(FakeNotion({}))
    assert insights["total_minutes"] == 0
    assert insights["active_days"] == 0
    assert insights["top_books_minutes"] == []


def test_snapshot_diff_computes_delta():
    rows = {
        "阅读快照": [
            _snapshot("b1", "2026-07-30", 10),
            _snapshot("b1", "2026-07-31", 40),
        ]
    }
    diff = snapshot_diff(FakeNotion(rows), "b1", "2026-07-30", "2026-07-31")
    assert diff["minutes_a"] == 10
    assert diff["minutes_b"] == 40
    assert diff["delta_minutes"] == 30


def test_snapshot_diff_missing_rows():
    diff = snapshot_diff(FakeNotion({}), "b1", "2026-07-30", "2026-07-31")
    assert diff["minutes_a"] == 0
    assert diff["minutes_b"] == 0
    assert diff["delta_minutes"] == 0
