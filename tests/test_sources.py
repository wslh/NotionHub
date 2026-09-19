import json
import tempfile
from pathlib import Path

import pytest

from weread2notion.sources import (
    AppleBooksSource,
    BookSource,
    KindleSource,
    LocalBookSource,
    WeReadBookSource,
    build_source,
)


def _write_local(tmp: Path) -> None:
    (tmp / "shelf.json").write_text(
        json.dumps({"books": [{"bookId": "b1", "title": "书一"}]}), encoding="utf-8"
    )
    (tmp / "b1.json").write_text(
        json.dumps(
            {
                "info": {"title": "书一"},
                "chapters": [],
                "highlights": [{"chapterUid": 1, "markText": "划线一"}],
                "reviews": [],
                "progress": {"readingTime": 600},
            }
        ),
        encoding="utf-8",
    )
    (tmp / "reading_days.json").write_text(
        json.dumps(
            [
                {"timestamp": 1700000000, "duration": 300},
                {"timestamp": 1600000000, "duration": 100},  # 早于 2023，应被过滤
            ]
        ),
        encoding="utf-8",
    )


def test_local_book_source_reads_exports():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _write_local(tmp)
        source = LocalBookSource(str(tmp))
        shelf = source.shelf()
        assert shelf["books"][0]["bookId"] == "b1"
        bundle = source.book_bundle("b1")
        assert bundle["info"]["title"] == "书一"
        assert bundle["highlights"][0]["markText"] == "划线一"
        days, summary = source.reading_days(2023)
        assert len(days) == 1
        assert days[0]["duration"] == 300
        assert summary == {}


def test_local_book_source_missing_bundle_returns_empty():
    with tempfile.TemporaryDirectory() as d:
        source = LocalBookSource(d)
        assert source.book_bundle("nope") == {}
        assert source.notebooks() == ([], {"books": 0, "notes": 0})


def test_build_source_parses_weread_and_local():
    class FakeClient:
        pass

    assert isinstance(build_source("weread", FakeClient()), WeReadBookSource)
    assert isinstance(build_source("", FakeClient()), WeReadBookSource)
    with tempfile.TemporaryDirectory() as d:
        src = build_source(f"local:{d}", FakeClient())
        assert isinstance(src, LocalBookSource)
        assert src.root == Path(d)


def test_build_source_rejects_unknown():
    with pytest.raises(ValueError):
        build_source("kindle", None)


def test_weread_book_source_delegates():
    class FakeClient:
        def shelf(self):
            return {"books": []}

        def notebooks(self):
            return [], {}

        def book_bundle(self, book_id):
            return {"info": {}}

        def reading_days(self, start_year):
            return [], {}

    src = WeReadBookSource(FakeClient())
    assert src.shelf() == {"books": []}
    assert src.notebooks() == ([], {})
    assert src.book_bundle("x") == {"info": {}}
    assert src.reading_days(2023) == ([], {})


def test_book_source_is_abstract():
    with pytest.raises(NotImplementedError):
        BookSource().shelf()


_KINDLE_CLIPPINGS = """\
==========
The Pragmatic Programmer (Hunt, Thomas)
- Your Highlight on Location 123-124 | Added on 1/1/24, 10:00:00 AM

Don't repeat yourself.
==========
The Pragmatic Programmer (Hunt, Thomas)
- Your Note on Location 200 | Added on 1/2/24, 11:30:00 AM

Good advice.
==========
Refactoring (Fowler)
- Your Highlight on Location 10-11 | Added on 2/1/24, 9:00:00 AM

Make small steps.
==========
"""


def test_kindle_source_parses_clippings(tmp_path):
    clip = tmp_path / "My Clippings.txt"
    clip.write_text(_KINDLE_CLIPPINGS, encoding="utf-8")
    source = KindleSource(str(clip))
    books = source.shelf()["books"]
    assert {b["title"] for b in books} == {"The Pragmatic Programmer", "Refactoring"}

    bundle = source.book_bundle("The Pragmatic Programmer")
    assert bundle["info"]["author"] == "Hunt, Thomas"
    assert len(bundle["highlights"]) == 1
    assert bundle["highlights"][0]["markText"] == "Don't repeat yourself."
    assert len(bundle["reviews"]) == 1
    assert bundle["reviews"][0]["content"] == "Good advice."
    # 中文界面时间无法解析时仍保留内容
    assert bundle["chapters"][0]["title"] == "高亮"

    days, _ = source.reading_days(2024)
    assert len(days) == 3
    assert all(d["duration"] == 0 for d in days)

    notebooks, summary = source.notebooks()
    assert summary["books"] == 2
    assert summary["notes"] == 1


def test_kindle_source_chinese_locale_dates(tmp_path):
    text = (
        "书名一（作者甲）\n"
        "- 您的标注 位于 12-13 | 添加于 2024年3月5日 星期二 上午8:00:00\n\n"
        "中文划线内容\n"
        "==========\n"
    )
    clip = tmp_path / "clippings.txt"
    clip.write_text(text, encoding="utf-8")
    source = KindleSource(str(clip))
    days, _ = source.reading_days(2024)
    assert len(days) == 1
    from datetime import datetime

    assert datetime.fromtimestamp(days[0]["timestamp"]).year == 2024


_APPLE_CSV = """\
Title,Author,Location,Highlight,Note
Clean Code,Robert C. Martin,100,"Functions should be small",""
Clean Code,Robert C. Martin,101,,"Avoid comments"
"""


def test_apple_books_source_parses_csv(tmp_path):
    csv_path = tmp_path / "export.csv"
    csv_path.write_text(_APPLE_CSV, encoding="utf-8")
    source = AppleBooksSource(str(csv_path))
    books = source.shelf()["books"]
    assert len(books) == 1
    assert books[0]["title"] == "Clean Code"

    bundle = source.book_bundle("Clean Code")
    assert len(bundle["highlights"]) == 1
    assert bundle["highlights"][0]["markText"] == "Functions should be small"
    assert len(bundle["reviews"]) == 1
    assert bundle["reviews"][0]["content"] == "Avoid comments"


def test_local_book_source_reads_notebooks(tmp_path):
    (tmp_path / "notebooks.json").write_text(
        json.dumps([{"bookId": "b1", "title": "书一"}]), encoding="utf-8"
    )
    items, summary = LocalBookSource(str(tmp_path)).notebooks()
    assert items == [{"bookId": "b1", "title": "书一"}]
    assert summary == {"books": 1, "notes": 0}


def test_build_source_parses_kindle_and_apple(tmp_path):
    class FakeClient:
        pass

    clip = tmp_path / "c.txt"
    clip.write_text(_KINDLE_CLIPPINGS, encoding="utf-8")
    assert isinstance(build_source(f"kindle:{clip}", FakeClient()), KindleSource)

    csv_path = tmp_path / "e.csv"
    csv_path.write_text(_APPLE_CSV, encoding="utf-8")
    assert isinstance(build_source(f"apple:{csv_path}", FakeClient()), AppleBooksSource)


def test_parsed_bundle_is_compatible_with_sync_blocks():
    from weread2notion.sync import Synchronizer

    source = KindleSource.__new__(KindleSource)
    source._clippings = [
        {
            "title": "Demo",
            "author": "A",
            "note": False,
            "meta": "loc",
            "body": "划线内容",
            "timestamp": 1700000000,
        },
        {
            "title": "Demo",
            "author": "A",
            "note": True,
            "meta": "loc",
            "body": "笔记内容",
            "timestamp": 1700000001,
        },
    ]
    bundle = source.book_bundle("Demo")
    blocks = Synchronizer.book_content_blocks(bundle)
    types = {b["type"] for b in blocks}
    assert "table_of_contents" in types
    assert any(b.get("type") == "heading_2" and "高亮" in _heading_text(b) for b in blocks)


def _heading_text(block):
    rich = block.get("heading_2", {}).get("rich_text", [])
    return "".join(item.get("text", {}).get("content", "") for item in rich)
