from __future__ import annotationsimport jsonimport loggingimport osfrom collections import defaultdictfrom dataclasses import dataclass, fieldfrom datetime import date, datetime, timedeltafrom pathlib import Pathfrom typing import Anyfrom .blocks import get_callout, get_heading, get_table_of_contentsfrom .normalize import (    SHANGHAI,    iso_date,    period_keys,    progress_status,    shelf_entries,)from .template import PERIOD_DATABASES, READING_RECORD_DATABASESlog = logging.getLogger(__name__)

BOOK_ICON = "https://www.notion.so/icons/book_gray.svg"
USER_ICON = "https://www.notion.so/icons/user-circle-filled_gray.svg"
TAG_ICON = "https://www.notion.so/icons/tag_gray.svg"
TARGET_ICON = "https://www.notion.so/icons/target_red.svg"
SNAPSHOT_ICON = "https://www.notion.so/icons/clock_gray.svg"
SYNC_VERSION = 8

# 全量重建（备份 + 校验）涉及的数据数据库。run() 与 validate_full_rebuild()
# 都用到同一份清单，集中在此避免两处写出后漂移。
DATA_DATABASES = (
    "书架",
    "笔记",
    "划线",
    "日",
    "周",
    "月",
    "年",
    "分类",
    "作者",
    "阅读记录",
    "阅读记录1",
    "阅读记录2",
)


@dataclass
class _WorkSet:
    """run() 各流水线阶段之间传递状态的可变容器。

    重活（各库的 upsert）仍由公开 sync_* 方法承担；这里只承载 run() 编排时
    需要在线程阶段之间流动的中间状态，避免把所有局部变量塞进一个巨型方法。
    """

    entry_by_id: dict[str, Any]
    previous_books: dict[str, Any]
    existing: dict[str, Any]
    removed_ids: set[str]
    changed_ids: set[str]
    selected_book_ids: set[str]
    selection_active: bool
    done: set[str]
    full: bool
    days: list[Any] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)
    related_timestamps: list[int] = field(default_factory=list)
    work_entries: dict[str, Any] = field(default_factory=dict)
    periods: dict[str, dict[str, str]] = field(default_factory=dict)


class Synchronizer:
    def __init__(
        self,
        weread,
        notion,
        start_year: int = 2023,
        dry_run: bool = False,
        preferences: dict[str, Any] | None = None,
        quiet: bool = False,
        concurrency: int = 4,
        checkpoint_file: Path | None = None,
        only_books: set[str] | None = None,
        only_tags: set[str] | None = None,
    ):
        self.weread = weread
        self.notion = notion
        self.preferences = {
            "completed_progress_100": False,
            "delete_removed": True,
            "sync_notes": True,
            "sync_snapshots": True,
            "sync_records": True,
            "sync_people": True,
            "start_year": start_year,
            **(preferences or {}),
        }
        self.start_year = int(self.preferences["start_year"])
        self.dry_run = dry_run
        self.quiet = quiet
        self.concurrency = max(1, int(concurrency))
        self.checkpoint_file = checkpoint_file
        self.only_books = set(only_books or set())
        self.only_tags = set(only_tags or set())
        self.counts = defaultdict(int)
        self._checkpoint_done: set[str] = set()

    def _log(self, message: str) -> None:
        if self.quiet:
            log.debug(message)
        else:
            log.info(message)

    # ---- 选择性同步 ----
    def _select_entries(self, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if self.only_books:
            return [e for e in entries if e.get("bookId") in self.only_books]
        if self.only_tags:
            return [
                e
                for e in entries
                if self.only_tags & set(e.get("labels") or e.get("tags") or [])
            ]
        return entries

    # ---- 检查点续传 ----
    def _load_checkpoint(self) -> set[str]:
        if not self.checkpoint_file or not Path(self.checkpoint_file).exists():
            return set()
        try:
            data = json.loads(Path(self.checkpoint_file).read_text(encoding="utf-8"))
            return set(data.get("done", []))
        except Exception as exc:  # noqa: BLE001
            log.warning("检查点读取失败，将从头全量同步：%s", exc)
            return set()

    def _save_checkpoint(self) -> None:
        if not self.checkpoint_file:
            return
        Path(self.checkpoint_file).parent.mkdir(parents=True, exist_ok=True)
        Path(self.checkpoint_file).write_text(
            json.dumps({"done": sorted(self._checkpoint_done)}, ensure_ascii=False),
            encoding="utf-8",
        )

    def _mark_done(self, book_id: str) -> None:
        self._checkpoint_done.add(book_id)
        self._save_checkpoint()

    def clear_checkpoint(self) -> None:
        if self.checkpoint_file and Path(self.checkpoint_file).exists():
            Path(self.checkpoint_file).unlink()

    def plan(self) -> dict[str, Any]:
        shelf = self.weread.shelf()
        notebooks, totals = self.weread.notebooks()
        entries = shelf_entries(shelf)
        # /shelf/sync is the authoritative source for current membership.
        # /user/notebooks also returns historical books that have been removed
        # from the shelf, so notebook IDs must never expand the sync set.
        ids = {item.get("bookId") for item in entries if item.get("kind") == "book"}
        return {
            "shelf": shelf,
            "notebooks": notebooks,
            "entries": entries,
            "book_ids": sorted(item for item in ids if item),
            "note_totals": totals,
        }

    def run(self, full: bool = False, backup_dir=None) -> dict[str, Any]:
        """执行一次完整同步：按阶段流水线推进，返回统计计数。

        编排逻辑拆成若干私有 stage 方法，每个只负责一个明确步骤；线上共享状态
        通过 :class:`_WorkSet` 在阶段间传递。各 sync_* 公开方法仍承载单库写入。
        """
        plan = self.plan()
        if self.dry_run:
            return {
                "mode": "dry-run",
                "shelf_entries": len(plan["entries"]),
                "related_books": len(plan["book_ids"]),
                "notebook_totals": plan["note_totals"],
            }
        ws = self._stage_compute_work_set(plan, full)
        self._stage_prefetch_reading_days(ws)
        bundles = self._stage_fetch_bundles(ws)
        self._stage_remove_deleted_books(ws, full)
        self._stage_full_rebuild(ws, full, backup_dir)

        # 关联时间戳：把阅读统计 / 记录链接到正确的日 / 周 / 月 / 年周期。
        ws.related_timestamps = self._stage_collect_related_timestamps(ws, bundles)
        # 选择性同步时，同步范围收窄到筛选出的书目。
        ws.work_entries = (
            {bid: ws.entry_by_id[bid] for bid in ws.selected_book_ids}
            if ws.selection_active
            else ws.entry_by_id
        )

        self._log("阶段 1/7 同步阅读统计（日/周/月/年）")
        ws.periods = self.sync_periods(ws.days, ws.related_timestamps, full=full)

        if self.preferences.get("sync_people"):
            self._log("阶段 2/7 同步作者与分类")
            authors, categories = self.sync_people_and_categories(
                ws.work_entries.values(), bundles, full=full
            )
        else:
            authors, categories = {}, {}
            self._log("阶段 2/7 跳过作者与分类（设置关闭）")

        self._log("阶段 3/7 同步书架记录")
        books = self.sync_books(
            ws.work_entries,
            bundles,
            authors,
            categories,
            ws.periods,
            ws.changed_ids,
            ws.existing,
        )

        if self.preferences.get("sync_snapshots"):
            self._log("阶段 4/7 同步每日阅读快照")
            self.sync_daily_snapshots(ws.work_entries, bundles, ws.previous_books)
        else:
            self._log("阶段 4/7 跳过每日阅读快照（设置关闭）")

        self._log("阶段 5/7 写入书籍正文划线与笔记")
        self.sync_book_content(bundles, books, ws.periods)

        if self.preferences.get("sync_records"):
            self._log("阶段 6/7 同步阅读记录")
            self.sync_reading_records(ws.days, ws.periods, full=full)
        else:
            self._log("阶段 6/7 跳过阅读记录（设置关闭）")

        if self.preferences.get("ai_intro"):
            self._log("阶段 7/7 生成 AI 导读")
            self.sync_ai_intros(ws.work_entries, bundles, books)
        else:
            self._log("阶段 7/7 跳过 AI 导读（设置未开启）")

        self.counts["reading_seconds"] = int(
            (ws.stats.get("overall") or {}).get("totalReadTime") or 0
        )
        self.clear_checkpoint()
        self._log(f"同步完成：{dict(self.counts)}")
        return dict(self.counts)

    # ---- 流水线阶段：变更检测 / 拉取 / 删除 / 全量重建 ----

    def _stage_compute_work_set(self, plan, full: bool) -> _WorkSet:
        entry_by_id = {entry["bookId"]: entry for entry in plan["entries"]}
        for notebook in plan["notebooks"]:
            book = notebook.get("book") or notebook
            book_id = notebook.get("bookId") or book.get("bookId")
            if book_id in entry_by_id:
                entry_by_id[book_id]["sort"] = max(
                    int(entry_by_id[book_id].get("sort") or 0),
                    int(notebook.get("sort") or 0),
                )

        previous_books = self.notion.book_index()
        existing = {} if full else previous_books
        removed_ids = set(existing) - set(entry_by_id)
        changed_ids = {
            book_id
            for book_id, entry in entry_by_id.items()
            if full
            or book_id not in existing
            or (
                entry.get("kind") == "book"
                and int(existing[book_id].get("sync_version") or 0) < SYNC_VERSION
            )
            or int(entry.get("sort") or entry.get("readUpdateTime") or 0)
            > int(existing[book_id].get("sort") or 0)
        }
        if self.preferences.get("settings_changed"):
            changed_ids.update(entry_by_id)

        # 选择性同步：--book / --tag 仅处理指定书目。
        selection_active = bool(self.only_books or self.only_tags)
        selected_entries = self._select_entries(plan["entries"])
        selected_book_ids = {
            e["bookId"] for e in selected_entries if e.get("kind") == "book"
        }
        if selection_active:
            changed_ids &= selected_book_ids
            removed_ids = set()  # 选择性同步不删除其它书

        # 检查点续传：已完成的书跳过内容同步，避免重复拉取/写入。
        done = self._load_checkpoint()
        if done:
            skipped = len(done & changed_ids)
            if skipped:
                log.info("检查点恢复：跳过 %d 本已同步书籍", skipped)

        self._log(
            f"变更检测完成：{len(changed_ids)} 本需更新，"
            f"{len(entry_by_id) - len(changed_ids)} 本无变化"
        )
        self.counts["changed_books"] = len(changed_ids)
        self.counts["skipped_books"] = len(entry_by_id) - len(changed_ids)

        return _WorkSet(
            entry_by_id=entry_by_id,
            previous_books=previous_books,
            existing=existing,
            removed_ids=removed_ids,
            changed_ids=changed_ids,
            selected_book_ids=selected_book_ids,
            selection_active=selection_active,
            done=done,
            full=full,
        )

    def _stage_prefetch_reading_days(self, ws: _WorkSet) -> None:
        # 阅读时长统计走 /readdata/detail，该接口在网关侧偶发 499/限流，
        # 且属于非关键数据。失败时仅跳过统计，不阻断书架/笔记主同步。
        try:
            days, stats = self.weread.reading_days(self.start_year)
        except Exception as exc:
            log.warning("阅读时长统计获取失败，已跳过（不影响书/笔记同步）：%s", exc)
            days, stats = [], {}
        ws.days = days
        ws.stats = stats

    def _stage_fetch_bundles(self, ws: _WorkSet) -> dict[str, Any]:
        # 并发拉取书籍 bundle，受并发数与请求间隔约束，缩短大书架同步耗时。
        from concurrent.futures import ThreadPoolExecutor, as_completed

        bundles: dict[str, Any] = {}
        electronic_ids = [
            book_id
            for book_id in sorted(ws.changed_ids)
            if ws.entry_by_id[book_id].get("kind") == "book" and book_id not in ws.done
        ]
        total = len(electronic_ids)
        with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
            futures = {
                pool.submit(self.weread.book_bundle, bid): bid for bid in electronic_ids
            }
            finished = 0
            for future in as_completed(futures):
                bid = futures[future]
                bundle = future.result()
                bundles[bid] = bundle
                finished += 1
                self.counts["highlights"] += len(bundle.get("highlights") or [])
                self.counts["reviews"] += len(bundle.get("reviews") or [])
                if not (bundle.get("info") or {}).get("cover"):
                    self.counts["missing_cover"] += 1
                self._log(f"读取书籍 {finished}/{total}: {bid}")
        return bundles

    def _stage_remove_deleted_books(self, ws: _WorkSet, full: bool) -> None:
        # Only start destructive work after every WeRead request has succeeded.
        # A transient upstream failure must never make the current shelf appear
        # empty and remove valid Notion pages.
        if not full and self.preferences["delete_removed"]:
            self.delete_removed_books(ws.removed_ids, ws.existing)
            for book_id in ws.removed_ids:
                ws.existing.pop(book_id, None)

    def _stage_full_rebuild(self, ws: _WorkSet, full: bool, backup_dir) -> None:
        if not full:
            return
        self.validate_full_rebuild()
        data_databases = [
            name for name in DATA_DATABASES if name in self.notion.sources
        ]
        old_count = sum(len(self.notion.query_all(name)) for name in data_databases)
        self.counts["backup"] = str(
            self.notion.backup_and_archive(backup_dir, data_databases)
        )
        self.counts["archived"] = old_count
        self._log(f"已生成备份：{self.counts['backup']}（含 {old_count} 条记录）")
        ws.existing = {}

    @staticmethod
    def _stage_collect_related_timestamps(
        ws: _WorkSet, bundles: dict[str, Any]
    ) -> list[int]:
        related_timestamps: list[int] = []
        for book_id, entry in ws.entry_by_id.items():
            bundle = bundles.get(book_id, {})
            progress = bundle.get("progress") or {}
            timestamp = (
                progress.get("updateTime")
                or entry.get("readUpdateTime")
                or entry.get("sort")
            )
            if timestamp:
                related_timestamps.append(int(timestamp))
            for item in [
                *(bundle.get("highlights") or []),
                *(bundle.get("reviews") or []),
            ]:
                if item.get("createTime"):
                    related_timestamps.append(int(item["createTime"]))
        return related_timestamps

    def sync_daily_snapshots(
        self,
        entries: dict[str, dict[str, Any]],
        bundles: dict[str, dict[str, Any]],
        previous_books: dict[str, dict[str, Any]],
        snapshot_date: date | None = None,
    ) -> None:
        """Upsert one cumulative progress snapshot per current shelf item and day."""
        if "阅读快照" not in self.notion.sources:
            return
        snapshot_day = snapshot_date or datetime.now(SHANGHAI).date()
        day_text = snapshot_day.isoformat()
        today_rows = self.notion.query_all(
            "阅读快照",
            {"property": "日期", "date": {"equals": day_text}},
        )
        today_by_book: dict[str, dict[str, Any]] = {}
        for row in today_rows:
            properties = row.get("properties") or {}
            book_id = self.notion.plain_property(properties.get("BookId"))
            if book_id:
                today_by_book[str(book_id)] = {
                    "page_id": row["id"],
                    "cumulative": self.notion.plain_property(
                        properties.get("累计阅读时长")
                    )
                    or 0,
                    "delta": self.notion.plain_property(
                        properties.get("当日新增阅读时长")
                    )
                    or 0,
                    # 保留原始属性，供 upsert 做字段级 diff（避免额外 GET）。
                    "properties": properties,
                }

        for book_id, entry in sorted(entries.items()):
            bundle = bundles.get(book_id) or {}
            info = bundle.get("info") or {}
            progress = bundle.get("progress") or {}
            previous = previous_books.get(book_id) or {}
            current_seconds = int(
                progress.get("readingTime")
                or progress.get("recordReadingTime")
                or previous.get("reading_seconds")
                or 0
            )
            today = today_by_book.get(book_id)
            if today:
                delta_seconds = int(today["delta"]) + max(
                    current_seconds - int(today["cumulative"]), 0
                )
            elif previous:
                delta_seconds = max(
                    current_seconds - int(previous.get("reading_seconds") or 0), 0
                )
            else:
                # A newly discovered book may already contain lifetime reading
                # time. Do not mislabel that entire history as today's reading.
                delta_seconds = 0

            chapter_uid = str(progress.get("chapterUid") or "")
            current_chapter = next(
                (
                    chapter.get("title")
                    for chapter in (bundle.get("chapters") or [])
                    if str(chapter.get("chapterUid") or "") == chapter_uid
                ),
                previous.get("current_chapter") or "",
            )
            finish_reading = bool(entry.get("finishReading"))
            if progress:
                progress_value = int(progress.get("progress") or 0) / 100
                if finish_reading and self.preferences["completed_progress_100"]:
                    progress_value = 1
                status = progress_status(progress, finish_reading)
            else:
                progress_value = float(previous.get("progress") or 0)
                status = "已读" if finish_reading else previous.get("status") or "想读"
            last_read = iso_date(
                progress.get("updateTime")
                or entry.get("readUpdateTime")
                or entry.get("sort")
            ) or previous.get("last_read")
            content_type = {
                "book": "电子书",
                "album": "有声书",
                "mp": "文章收藏",
            }.get(entry.get("kind"), previous.get("content_type") or "电子书")
            title = (
                info.get("title")
                or entry.get("title")
                or previous.get("title")
                or book_id
            )
            snapshot_key = f"{day_text}:{book_id}"
            raw = {
                self.notion.titles["阅读快照"]: f"{day_text} · {title}",
                "SnapshotKey": snapshot_key,
                "BookId": book_id,
                "书名": title,
                "日期": day_text,
                "累计阅读时长": current_seconds,
                "累计阅读时长（分钟）": current_seconds / 60,
                "当日新增阅读时长": delta_seconds,
                "当日新增阅读时长（分钟）": delta_seconds / 60,
                "阅读进度": progress_value,
                "阅读状态": status,
                "当前章节": current_chapter,
                "最后阅读时间": last_read,
                "内容类型": content_type,
            }
            self.notion.upsert(
                "阅读快照",
                "SnapshotKey",
                snapshot_key,
                raw,
                SNAPSHOT_ICON,
                existing_id=(today or {}).get("page_id"),
                existing_properties=(today or {}).get("properties"),
            )
            self.counts["阅读快照"] += 1

    def delete_removed_books(self, removed_ids, existing) -> None:
        """Move books absent from /shelf/sync and their generated data to trash."""
        for book_id in sorted(removed_ids):
            page_id = existing[book_id]["page_id"]
            for database in ("笔记", "划线"):
                if database not in self.notion.sources:
                    continue
                # Current and legacy templates relate these rows to 书架 through
                # a property named 书籍. Skip unknown schemas instead of risking
                # an unfiltered archive of an entire database.
                if self.notion.schemas.get(database, {}).get("书籍") != "relation":
                    continue
                count = self.notion.archive_rows(database, ("书籍", page_id))
                self.counts[f"删除{database}"] += int(count or 0)
            # Highlights and reviews in current templates live inside the book
            # page's generated block, so trashing the page removes them too.
            self.notion.request(
                f"pages/{page_id}", "PATCH", {"in_trash": True}
            )
            self.counts["删除书架"] += 1

    def validate_full_rebuild(self) -> None:
        """全量重建前校验：确认将要归档的数据数据库均可查询，避免破坏性操作前才发现权限/结构问题。"""
        data_databases = [
            name
            for name in (
                "书架",
                "笔记",
                "划线",
                "日",
                "周",
                "月",
                "年",
                "分类",
                "作者",
                "阅读记录",
                "阅读记录1",
                "阅读记录2",
            )
            if name in self.notion.sources
        ]
        unreadable = []
        for name in data_databases:
            try:
                self.notion.query_all(name, {"page_size": 1})
            except Exception as exc:  # noqa: BLE001 - 校验需捕获全部查询异常
                unreadable.append(f"{name}（{exc}）")
        if unreadable:
            raise RuntimeError(
                "全量重建前校验失败，已中止以免误删数据："
                + "；".join(unreadable)
            )

    def sync_periods(
        self,
        days: list[dict[str, Any]],
        related_timestamps: list[int] | None = None,
        full: bool = False,
    ) -> dict[str, dict[str, str]]:
        maps = {"day": {}, "week": {}, "month": {}, "year": {}}
        durations = defaultdict(int)
        rows_by_timestamp = {
            int(row["timestamp"]): int(row.get("duration") or 0) for row in days
        }
        for timestamp in related_timestamps or []:
            rows_by_timestamp.setdefault(int(timestamp), 0)
        period_rows = [
            {"timestamp": timestamp, "duration": duration}
            for timestamp, duration in sorted(rows_by_timestamp.items())
        ]
        for row in period_rows:
            keys = period_keys(row["timestamp"])
            for kind in maps:
                durations[(kind, keys[kind])] += int(row["duration"])
        db_names = PERIOD_DATABASES
        existing = {
            kind: (
                {}
                if full
                else self.notion.row_index(database, self.notion.titles[database])
            )
            for kind, database in db_names.items()
        }
        changed_periods = {kind: set() for kind in maps}
        for (kind, key), duration in sorted(durations.items()):
            if kind == "year":
                start = date(int(key), 1, 1)
            elif kind == "month":
                year, month = map(int, key.split("-"))
                start = date(year, month, 1)
            else:
                start = date.fromisoformat(key)
            if kind == "week":
                end = start + timedelta(days=6)
            elif kind == "month":
                next_month = date(
                    start.year + (start.month == 12),
                    1 if start.month == 12 else start.month + 1,
                    1,
                )
                end = next_month - timedelta(days=1)
            elif kind == "year":
                end = date(start.year, 12, 31)
            else:
                end = start
            raw = {
                self.notion.titles[db_names[kind]]: key,
                "日期": {
                    "start": start.isoformat(),
                    "end": end.isoformat() if end != start else None,
                },
                "时长": duration,
                "时长（分钟）": duration / 60,
            }
            if kind == "day":
                timestamp = next(
                    row["timestamp"]
                    for row in period_rows
                    if period_keys(row["timestamp"])["day"] == key
                )
                raw["时间戳"] = timestamp
            database = db_names[kind]
            row = existing[kind].get(key)
            if row:
                page_id = row["page_id"]
                # 字段级 diff：比较该周期记录的全部属性，只把真正变化的发过去。
                # 时长未变时 changed 为空，既跳过请求也不标记为待重算。
                changed = self.notion.changed_properties(
                    database,
                    row["properties"],
                    self.notion.properties(database, raw),
                )
                if changed:
                    self.notion.request(
                        f"pages/{page_id}",
                        "PATCH",
                        {"properties": changed},
                    )
                    self.counts[database] += 1
                    if kind == "day":
                        changed_periods[kind].add(key)
            else:
                page_id = self.notion.create(database, raw, TARGET_ICON)
                self.counts[database] += 1
                changed_periods[kind].add(key)
            maps[kind][key] = page_id
        for row in period_rows:
            keys = period_keys(row["timestamp"])
            if not any(keys[kind] in changed_periods[kind] for kind in maps):
                continue
            day_id = maps["day"][keys["day"]]
            raw = {
                "年": [maps["year"][keys["year"]]],
                "月": [maps["month"][keys["month"]]],
                "周": [maps["week"][keys["week"]]],
            }
            self.notion.request(
                f"pages/{day_id}",
                "PATCH",
                {"properties": self.notion.properties("日", raw)},
            )
        return maps

    def sync_people_and_categories(self, entries, bundles, full: bool = False):
        author_names, category_names = set(), set()
        for entry in entries:
            author_names.update(filter(None, [str(entry.get("author") or "").strip()]))
            category_names.update(filter(None, [entry.get("category")]))
        for bundle in bundles.values():
            info = bundle["info"]
            author_names.update(filter(None, [str(info.get("author") or "").strip()]))
            categories = info.get("categories") or []
            category_names.update(
                (item.get("title") if isinstance(item, dict) else item)
                for item in categories
            )
            category_names.update(filter(None, [info.get("category")]))
        existing_authors = (
            {} if full else self.notion.row_index("作者", self.notion.titles["作者"])
        )
        existing_categories = (
            {} if full else self.notion.row_index("分类", self.notion.titles["分类"])
        )
        authors = {}
        for name in sorted(filter(None, author_names)):
            row = existing_authors.get(name)
            if row:
                authors[name] = row["page_id"]
            else:
                authors[name] = self.notion.create(
                    "作者", {self.notion.titles["作者"]: name}, USER_ICON
                )
                self.counts["作者"] += 1
        categories = {}
        for name in sorted(filter(None, category_names)):
            row = existing_categories.get(name)
            if row:
                categories[name] = row["page_id"]
            else:
                categories[name] = self.notion.create(
                    "分类", {self.notion.titles["分类"]: name}, TAG_ICON
                )
                self.counts["分类"] += 1
        return authors, categories

    def sync_books(
        self, entries, bundles, authors, categories, periods, changed_ids, existing
    ):
        result = {}
        for book_id, entry in entries.items():
            if book_id not in changed_ids and book_id in existing:
                result[book_id] = existing[book_id]["page_id"]
                continue
            bundle = bundles.get(book_id, {})
            info, progress = bundle.get("info", {}), bundle.get("progress", {})
            author = info.get("author") or entry.get("author") or ""
            cats = info.get("categories") or []
            cat_names = [(x.get("title") if isinstance(x, dict) else x) for x in cats]
            cat_names += [info.get("category") or entry.get("category")]
            timestamp = (
                progress.get("updateTime")
                or entry.get("readUpdateTime")
                or entry.get("sort")
            )
            finish_reading = bool(entry.get("finishReading"))
            finish_timestamp = (
                (
                    progress.get("finishTime")
                    or entry.get("readUpdateTime")
                    or progress.get("updateTime")
                )
                if finish_reading
                else None
            )
            # Book period relations represent when the book was completed.
            # The last-read timestamp can change after completion and must not
            # move a finished book into a different day/month/year.
            relations = period_keys(finish_timestamp) if finish_timestamp else {}
            chapter_uid = str(progress.get("chapterUid") or "")
            current_chapter = next(
                (
                    chapter.get("title")
                    for chapter in (bundle.get("chapters") or [])
                    if str(chapter.get("chapterUid") or "") == chapter_uid
                ),
                "",
            )
            content_type = {
                "book": "电子书",
                "album": "有声书",
                "mp": "文章收藏",
            }.get(entry.get("kind"), "电子书")
            publish_time = info.get("publishTime")
            publish_date = str(publish_time)[:10] if publish_time else None
            reading_time = (
                progress.get("readingTime") or progress.get("recordReadingTime") or 0
            )
            raw = {
                self.notion.titles["书架"]: info.get("title")
                or entry.get("title")
                or book_id,
                "BookId": book_id,
                "ISBN": info.get("isbn") or "",
                "Sort": entry.get("sort") or timestamp or 0,
                "评分": info.get("newRating") or 0,
                "评分人数": info.get("newRatingCount") or 0,
                "链接": info.get("deepLink") or entry.get("deepLink"),
                "简介": info.get("intro") or entry.get("intro") or "",
                "出版社": info.get("publisher") or "",
                "出版日期": publish_date,
                "字数": info.get("wordCount") or 0,
                "译者": info.get("translator") or "",
                "内容类型": content_type,
                "当前章节": current_chapter,
                "听书时长": progress.get("ttsTime") or 0,
                "私密阅读": bool(entry.get("secret")),
                "置顶": bool(entry.get("isTop")),
                "有声书集数": entry.get("trackCount") or 0,
                "完结状态": entry.get("finishStatus") or "",
                "作者": [authors[author]] if author in authors else [],
                "分类": [categories[name] for name in cat_names if name in categories],
                # Shelf/update timestamps only prove that an item was added or
                # changed. They do not prove that the user actually read it.
                # The explicit WeRead shelf marker has priority over progress.
                # A book is 已读 only when finishReading=1.
                "阅读状态": progress_status(progress, finish_reading),
                # /book/getprogress exposes the accumulated text-reading duration
                # as readingTime (seconds). recordReadingTime is a different metric
                # and is commonly zero even for books with substantial progress.
                "阅读时长": reading_time,
                "阅读时长（分钟）": reading_time / 60,
                "阅读进度": (
                    1
                    if finish_reading and self.preferences["completed_progress_100"]
                    else int(progress.get("progress") or 0) / 100
                ),
                "开始阅读时间": iso_date(
                    progress.get("startReadingTime") or progress.get("beginReadingDate")
                ),
                "最后阅读时间": iso_date(timestamp),
                "阅读完成时间": iso_date(finish_timestamp),
                "时间": iso_date(progress.get("finishTime") or timestamp),
            }
            for kind, prop in PERIOD_DATABASES.items():
                if relations.get(kind) in periods[kind]:
                    raw[prop] = [periods[kind][relations[kind]]]
            cover = info.get("cover") or entry.get("cover")
            result[book_id] = self.notion.upsert(
                "书架",
                "BookId",
                book_id,
                raw,
                cover or BOOK_ICON,
                cover,
                existing_id=(existing.get(book_id) or {}).get("page_id"),
                existing_properties=(existing.get(book_id) or {}).get("properties"),
            )
            self.counts["书架"] += 1
        return result

    def sync_book_content(self, bundles, books, periods):
        for book_id, bundle in bundles.items():
            page_id = books.get(book_id)
            if not page_id:
                continue
            if not self.preferences["sync_notes"]:
                self.notion.request(
                    f"pages/{page_id}",
                    "PATCH",
                    {
                        "properties": self.notion.properties(
                            "书架", {"同步版本": SYNC_VERSION}
                        )
                    },
                )
                continue
            # Highlights and reviews are rendered directly into the book body.
            # Do not create one Notion page/relation tag per item.
            self.counts["正文划线"] += len(bundle.get("highlights") or [])
            self.counts["正文笔记"] += len(bundle.get("reviews") or [])
            self.notion.replace_generated_book_content(
                page_id, self.book_content_blocks(bundle)
            )
            # Mark the book complete only after all related rows and generated
            # page content have been written. If a run is interrupted before
            # this point, the next incremental sync will retry the book.
            self.notion.request(
                f"pages/{page_id}",
                "PATCH",
                {
                    "properties": self.notion.properties(
                        "书架", {"同步版本": SYNC_VERSION}
                    )
                },
            )
            # 检查点：完成一本书即记录，支持断点续传。
            self._mark_done(book_id)

    def sync_ai_intros(
        self,
        entries: dict[str, dict[str, Any]],
        bundles: dict[str, dict[str, Any]],
        books: dict[str, str],
    ) -> None:
        """为每本书生成并写入 AI 导读（可选，需 OPENAI_API_KEY）。

        仅当设置开启且配置了 ``OPENAI_API_KEY`` 时执行；任何失败都只记录日志，
        不影响其余同步。调用 ``notion.write_ai_intro`` 保证页面上只保留最新一段。
        """
        if not os.getenv("OPENAI_API_KEY"):
            self._log("跳过 AI 导读（未设置 OPENAI_API_KEY）")
            return
        from .ai_summary import summarize_book

        for book_id, bundle in bundles.items():
            if book_id not in books:
                continue
            info = bundle.get("info") or {}
            title = info.get("title") or book_id
            highlights = [
                item.get("markText")
                for item in (bundle.get("highlights") or [])
                if item.get("markText")
            ]
            try:
                summary = summarize_book(title, highlights)
            except Exception as exc:  # noqa: BLE001 - AI 为可选增强，失败不阻断
                self._log(f"AI 导读生成失败（{title}）：{exc}")
                self.counts["ai_intro_errors"] += 1
                continue
            if not summary:
                continue
            try:
                self.notion.write_ai_intro(books[book_id], summary)
                self.counts["ai_intro"] += 1
                self._log(f"已写入 AI 导读：{title}")
            except Exception as exc:  # noqa: BLE001
                self._log(f"AI 导读写入失败（{title}）：{exc}")
                self.counts["ai_intro_errors"] += 1

    @staticmethod
    def book_content_blocks(bundle: dict[str, Any]) -> list[dict[str, Any]]:
        chapters = {
            str(chapter.get("chapterUid")): chapter
            for chapter in (bundle.get("chapters") or [])
        }
        grouped: dict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
        for mark in bundle.get("highlights") or []:
            grouped[str(mark.get("chapterUid") or "")].append((0, mark))
        for review in bundle.get("reviews") or []:
            grouped[str(review.get("chapterUid") or "")].append((1, review))
        if not grouped:
            return []

        def chapter_sort(uid: str) -> tuple[int, str]:
            chapter = chapters.get(uid) or {}
            return (int(chapter.get("chapterIdx") or 10**9), uid)

        blocks: list[dict[str, Any]] = [get_table_of_contents()]
        for uid in sorted(grouped, key=chapter_sort):
            chapter = chapters.get(uid) or {}
            title = chapter.get("title") or "其他笔记"
            blocks.append(get_heading(2, title))
            for kind, item in sorted(
                grouped[uid], key=lambda pair: int(pair[1].get("createTime") or 0)
            ):
                if kind == 0:
                    text = item.get("markText") or "划线"
                    blocks.append(get_callout(text, "〰️"))
                else:
                    abstract = item.get("abstract") or ""
                    content = item.get("content") or ""
                    text = (
                        "\n\n".join(part for part in (abstract, content) if part)
                        or "想法"
                    )
                    blocks.append(get_callout(text, "💭"))
        return blocks

    def sync_reading_records(self, days, periods, full: bool = False):
        database = next(
            (
                name
                for name in READING_RECORD_DATABASES
                if name in self.notion.sources
            ),
            None,
        )
        if not database:
            return
        existing = {} if full else self.notion.row_index(database, "时间戳")
        for row in days:
            keys = period_keys(row["timestamp"])
            raw = {
                self.notion.titles[database]: keys["day"],
                "日期": keys["day"],
                "Date": keys["day"],
                "时长": row["duration"],
                "时长（分钟）": row["duration"] / 60,
                "时间戳": row["timestamp"],
            }
            current = existing.get(str(row["timestamp"]))
            if current:
                # 与书架 / 统计库一致：全字段比较，只提交变化的属性。
                changed = self.notion.changed_properties(
                    database,
                    current["properties"],
                    self.notion.properties(database, raw),
                )
                if not changed:
                    continue
                self.notion.request(
                    f"pages/{current['page_id']}",
                    "PATCH",
                    {"properties": changed},
                )
            else:
                self.notion.create(database, raw, TARGET_ICON)
            self.counts[database] += 1
