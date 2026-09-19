"""数据源插件抽象层。

让同步核心不再局限于微信读书，任何实现了 :class:`BookSource` 接口的来源
（本地导出、Apple Books、Kindle 等）都可以接入 :class:`~weread2notion.sync.Synchronizer`。

已实现的具体来源：

- :class:`WeReadBookSource`：适配现有 ``WeReadClient``，保持向后兼容。
- :class:`LocalBookSource`：从本地目录读取书籍导出，便于离线测试与二次开发。
- :class:`KindleSource`：解析 Kindle ``My Clippings.txt``。
- :class:`AppleBooksSource`：解析 Apple Books 高亮 CSV 导出。

``--source`` 取值：``weread``（默认）、``local:/路径``、``kindle:/路径/MyClippings.txt``、
``apple:/路径/export.csv``。新增来源只需继承 :class:`BookSource` 并在 :func:`build_source`
中登记即可，无需改动同步核心。

多数「解析型」来源（Kindle / Apple Books）都遵循同一套路：先把原始标注聚合成
``{book_id: {title, author, highlights, notes}}``，再统一实现四个接口方法。这类来源应
继承 :class:`AggregatedBookSource`，只需实现 :meth:`~AggregatedBookSource._aggregate`
与 :meth:`~AggregatedBookSource._day_timestamps`，避免各来源重复书写接口样板。
"""

from __future__ import annotations

import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .utils import parse_date_to_timestamp, parse_kindle_clipping_date


def _book_id(title: str) -> str:
    """把书名映射为稳定的内部 ID（同时用作 Notion 的 BookId 文本）。"""
    return re.sub(r"\s+", " ", title).strip()


def _build_bundle(
    book_id: str,
    title: str,
    author: str,
    highlights: list[dict[str, Any]],
    notes: list[dict[str, Any]],
) -> dict[str, Any]:
    """根据解析出的划线/笔记，组装与微信读书 bundle 兼容的结构。"""
    return {
        "info": {"title": title, "author": author, "cover": "", "bookId": book_id},
        "chapters": [{"chapterUid": 1, "chapterIdx": 1, "title": "高亮"}],
        "highlights": [
            {
                "chapterUid": 1,
                "markText": h["text"],
                "createTime": h.get("timestamp") or 0,
                "range": h.get("range") or "",
            }
            for h in highlights
        ],
        "reviews": [
            {
                "chapterUid": 1,
                "abstract": n["text"],
                "content": n["text"],
                "createTime": n.get("timestamp") or 0,
            }
            for n in notes
        ],
        "progress": {"readingTime": 0},
    }


class BookSource:
    """同步核心依赖的最小数据源接口。

    所有方法返回的结构需与微信读书 Gateway 兼容，使下游 ``Synchronizer``
    无需关心数据来自哪里。
    """

    def shelf(self) -> dict[str, Any]:
        """返回书架列表，形如 ``{"books": [{...}]}``。"""
        raise NotImplementedError

    def notebooks(self) -> tuple[list[dict[str, Any]], dict[str, int]]:
        """返回 (笔记列表, 计数汇总)。"""
        raise NotImplementedError

    def book_bundle(self, book_id: str) -> dict[str, Any]:
        """返回单本书的完整 bundle（info/chapters/highlights/reviews/progress）。"""
        raise NotImplementedError

    def reading_days(self, start_year: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """返回 (阅读时长列表, 汇总)。列表元素形如 ``{"timestamp": int, "duration": int}``。"""
        raise NotImplementedError


class AggregatedBookSource(BookSource):
    """解析型来源的基类：子类把原始标注聚合成 books 字典，本类统一实现接口。

    子类只需实现两个钩子：

    - :meth:`_aggregate`：返回 ``{book_id: {"title", "author", "highlights", "notes"}}``。
    - :meth:`_day_timestamps`：产出用于「阅读天数」统计的时间戳（秒）。

    ``shelf`` / ``notebooks`` / ``book_bundle`` / ``reading_days`` 由此统一实现，
    避免每个解析型来源重复书写同一套接口样板。
    """

    def _aggregate(self) -> dict[str, dict[str, Any]]:
        raise NotImplementedError

    def _day_timestamps(self) -> Iterable[int | None]:
        raise NotImplementedError

    def shelf(self) -> dict[str, Any]:
        return {
            "books": [
                {"bookId": bid, "title": b["title"], "author": b["author"], "cover": ""}
                for bid, b in self._aggregate().items()
            ]
        }

    def notebooks(self) -> tuple[list[dict[str, Any]], dict[str, int]]:
        books = self._aggregate()
        items = [
            {
                "bookId": bid,
                "title": b["title"],
                "highlights": len(b["highlights"]),
                "notes": len(b["notes"]),
            }
            for bid, b in books.items()
        ]
        return items, {
            "books": len(items),
            "notes": sum(i["notes"] for i in items),
            "highlights": sum(i["highlights"] for i in items),
        }

    def book_bundle(self, book_id: str) -> dict[str, Any]:
        book = self._aggregate().get(book_id)
        if not book:
            return {}
        return _build_bundle(
            book_id, book["title"], book["author"], book["highlights"], book["notes"]
        )

    def reading_days(self, start_year: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        days: list[dict[str, Any]] = []
        for ts in self._day_timestamps():
            if ts and datetime.fromtimestamp(ts).year >= start_year:
                days.append({"timestamp": ts, "duration": 0})
        return days, {}


class WeReadBookSource(BookSource):
    """适配现有 ``WeReadClient``，方法调用原样转发。"""

    def __init__(self, client):
        self.client = client

    def shelf(self) -> dict[str, Any]:
        return self.client.shelf()

    def notebooks(self) -> tuple[list[dict[str, Any]], dict[str, int]]:
        return self.client.notebooks()

    def book_bundle(self, book_id: str) -> dict[str, Any]:
        return self.client.book_bundle(book_id)

    def reading_days(self, start_year: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        return self.client.reading_days(start_year)


class LocalBookSource(BookSource):
    """从本地目录读取书籍导出（离线 / 测试用途）。

    目录结构约定：

    - ``shelf.json``：书架列表，形如 ``{"books": [{...}]}`` 或直接是列表。
    - ``<book_id>.json``：单本书的 bundle（info/chapters/highlights/reviews/progress）。
    - ``reading_days.json``：阅读时长列表，形如 ``[{"timestamp": int, "duration": int}]``。
    - ``notebooks.json``（可选）：笔记列表，形如 ``[{"bookId": ..., "title": ...}]``。

    新增来源（例如 Apple Books / Kindle 导出解析器）只需继承 :class:`BookSource`
    并实现四个方法即可，无需改动同步核心。
    """

    def __init__(self, path: str):
        self.root = Path(path)

    def shelf(self) -> dict[str, Any]:
        data = json.loads((self.root / "shelf.json").read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"books": data}

    def notebooks(self) -> tuple[list[dict[str, Any]], dict[str, int]]:
        path = self.root / "notebooks.json"
        if not path.exists():
            return [], {"books": 0, "notes": 0}
        items = json.loads(path.read_text(encoding="utf-8")) or []
        return items, {"books": len(items), "notes": 0}

    def book_bundle(self, book_id: str) -> dict[str, Any]:
        path = self.root / f"{book_id}.json"
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def reading_days(self, start_year: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        path = self.root / "reading_days.json"
        if not path.exists():
            return [], {}
        days = json.loads(path.read_text(encoding="utf-8")) or []
        keep = [
            d
            for d in days
            if d.get("duration") and int(d["timestamp"]) >= _year_start(start_year)
        ]
        return keep, {}


class KindleSource(AggregatedBookSource):
    """解析 Kindle ``My Clippings.txt``。

    文件按 ``==========`` 分块，每块含：书名（可能带 ``(作者)``）、以 ``- `` 开头的
    元数据行（标注 Highlight / Note 及时间）、以及高亮/笔记正文。本解析器对英文与
    中文界面的时间格式均做了兼容，无法解析时间时仍保留内容（仅阅读统计缺失日期）。
    """

    def __init__(self, path: str):
        self.path = Path(path)
        self._clippings = _parse_clippings(
            self.path.read_text(encoding="utf-8-sig")
        )

    def _aggregate(self) -> dict[str, dict[str, Any]]:
        books: dict[str, dict[str, Any]] = {}
        for clip in self._clippings:
            bid = _book_id(clip["title"])
            book = books.setdefault(
                bid, {"title": clip["title"], "author": clip["author"], "highlights": [], "notes": []}
            )
            entry = {"text": clip["body"], "timestamp": clip["timestamp"], "range": clip["meta"]}
            if clip["note"]:
                book["notes"].append(entry)
            else:
                book["highlights"].append(entry)
        return books

    def _day_timestamps(self) -> Iterable[int | None]:
        for clip in self._clippings:
            yield clip["timestamp"]


class AppleBooksSource(AggregatedBookSource):
    """解析 Apple Books 高亮导出 CSV。

    对列名做了别名兼容（如 ``Title``/``书名``、``Highlight``/``划线``、``Note``/``笔记``、
    ``Location``/``位置``）。划线写入正文，笔记写入「想法」区块；源格式不含阅读时长，
    故阅读统计时长为 0（best-effort）。
    """

    _ALIASES = {
        "title": ["title", "书名", "book", "book title"],
        "author": ["author", "作者"],
        "highlight": ["highlight", "划线", "highlighted text", "text"],
        "note": ["note", "笔记", "comment"],
        "location": ["location", "page", "位置", "loc"],
        "date": ["date", "时间", "added", "添加时间"],
    }

    def __init__(self, path: str):
        self.path = Path(path)
        self._rows = self._read_csv(self.path)

    @staticmethod
    def _read_csv(path: Path) -> list[dict[str, str]]:
        with path.open(encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            return [{(k or "").strip().lower(): (v or "").strip() for k, v in row.items()} for row in reader]

    def _pick(self, row: dict[str, str], kind: str) -> str:
        for alias in self._ALIASES.get(kind, []):
            for key, value in row.items():
                if key == alias:
                    return value
        return ""

    def _aggregate(self) -> dict[str, dict[str, Any]]:
        books: dict[str, dict[str, Any]] = {}
        for raw in self._rows:
            title = self._pick(raw, "title")
            if not title:
                continue
            bid = _book_id(title)
            book = books.setdefault(
                bid, {"title": title, "author": self._pick(raw, "author"), "highlights": [], "notes": []}
            )
            highlight = self._pick(raw, "highlight")
            note = self._pick(raw, "note")
            ts = parse_date_to_timestamp(self._pick(raw, "date")) if self._pick(raw, "date") else None
            location = self._pick(raw, "location")
            if highlight:
                book["highlights"].append({"text": highlight, "timestamp": ts, "range": location})
            if note:
                book["notes"].append({"text": note, "timestamp": ts, "range": location})
        return books

    def _day_timestamps(self) -> Iterable[int | None]:
        for book in self._aggregate().values():
            for entry in book["highlights"] + book["notes"]:
                yield entry.get("timestamp")


def _year_start(start_year: int) -> int:
    return int(datetime(start_year, 1, 1).timestamp())


def _parse_clippings(text: str) -> list[dict[str, Any]]:
    """解析 Kindle ``My Clippings.txt`` 为结构化列表。"""
    clippings: list[dict[str, Any]] = []
    for raw in re.split(r"^={10}\s*$", text, flags=re.MULTILINE):
        lines = [ln.rstrip() for ln in raw.splitlines() if ln.strip() != ""]
        if len(lines) < 2:
            continue
        title_line = lines[0]
        meta_line = lines[1]
        body = "\n".join(lines[2:]).strip()
        if not body:
            continue
        m = re.match(r"^(.*?)\s*\(([^()]*)\)\s*$", title_line)
        title, author = (m.group(1).strip(), m.group(2).strip()) if m else (title_line.strip(), "")
        is_note = "note" in meta_line.lower() or "笔记" in meta_line
        clippings.append(
            {
                "title": title,
                "author": author,
                "note": is_note,
                "meta": meta_line,
                "body": body,
                "timestamp": parse_kindle_clipping_date(meta_line),
            }
        )
    return clippings






def build_source(spec: str, weread_client) -> BookSource:
    """根据 CLI 的 ``--source`` 参数构造数据源。

    - ``weread``（默认）：使用微信读书客户端。
    - ``local:/abs/path``：使用本地目录数据源。
    - ``kindle:/abs/path/MyClippings.txt``：解析 Kindle 标注文件。
    - ``apple:/abs/path/export.csv``：解析 Apple Books 高亮导出。
    """
    if not spec or spec == "weread":
        return WeReadBookSource(weread_client)
    if spec.startswith("local:"):
        return LocalBookSource(spec[len("local:"):])
    if spec.startswith("kindle:"):
        return KindleSource(spec[len("kindle:"):])
    if spec.startswith("apple:"):
        return AppleBooksSource(spec[len("apple:"):])
    raise ValueError(f"未知数据源：{spec}")
