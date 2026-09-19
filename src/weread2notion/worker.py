"""自有 Worker（长毛象）：脱离 GitHub Actions 的常驻同步触发器。

架构定位（触发器层）
--------------------
在「浏览器面板」与「GitHub Actions」之外，用户也可以在本机常驻一个 Worker
进程，按固定间隔触发「本机 CLI 同步」。每轮同步结束后，Worker 可把结果以
「嘟文」发布到 Mastodon（长毛象），既作为运行播报，也作为心跳。

运行状态写入 logs/worker-state.json，供浏览器面板经 Native Bridge 读取与启停。
Worker 通过 `notionhub worker` 启动；路径由环境变量 NOTIONHUB_WORKER_STATE
指定（Native Host 会以项目根目录下的 logs/worker-state.json 注入）。
"""
from __future__ import annotations

import json
import logging
import os
import signal
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import Settings
from .logging_utils import setup_logging
from .mastodon import MastodonClient, MastodonError
from .notion import NotionWorkspace
from .registry import build_default_registry
from .runner import run_plugin
from .sources import build_source
from .sync import Synchronizer
from .weread import WeReadClient

log = logging.getLogger(__name__)

STATE_FILE = Path(os.environ.get("NOTIONHUB_WORKER_STATE") or "logs") / "worker-state.json"


class Worker:
    def __init__(self, interval: int = 300, services=None, mastodon: bool = False, max_failures: int = 5):
        self.interval = int(interval)
        self.services = services  # list[str] 或 None（全部已配置）
        self.use_mastodon = bool(mastodon)
        self.max_failures = int(max_failures)
        self.failures = 0
        self._stop = False
        self.last_run = None
        self.last_result = None
        self.mastodon: Optional[MastodonClient] = None
        if self.use_mastodon:
            try:
                self.mastodon = MastodonClient.from_env()
            except Exception as exc:  # noqa: BLE001
                log.warning("Mastodon 未就绪，将以静默模式运行：%s", exc)

    # ---- 状态持久化 ----------------------------------------------------------
    def _write_state(self, **extra) -> None:
        now = datetime.now()
        state = {
            "running": not self._stop,
            "pid": os.getpid(),
            "interval": self.interval,
            "services": self.services,
            "mastodon": bool(self.mastodon),
            "last_run": self.last_run,
            "next_run": (now.timestamp() + self.interval) if not self._stop else None,
            "last_result": self.last_result,
            "consecutive_failures": self.failures,
            "updated_at": now.isoformat(timespec="seconds"),
        }
        state.update(extra)
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            STATE_FILE.write_text(
                json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("写入 Worker 状态失败：%s", exc)

    def _include(self, plugin_id: str) -> bool:
        if not self.services:
            return True
        return plugin_id in self.services

    # ---- 单轮同步 ------------------------------------------------------------
    def run_cycle(self) -> list:
        settings = Settings.from_env()
        weread = WeReadClient(settings.weread_api_key, settings.skill_version)
        source = build_source("weread", weread)
        notion = NotionWorkspace(
            settings.notion_token,
            settings.notion_page_id,
            settings.notion_version,
            settings.request_interval,
        ).discover()
        preferences = notion.ensure_sync_settings(settings.start_year)
        notion.ensure_reading_snapshots()

        results: list = []

        # 核心：微信读书全量同步
        if self._include("weread"):
            try:
                res = Synchronizer(
                    source,
                    notion,
                    settings.start_year,
                    preferences=preferences,
                    concurrency=settings.concurrency,
                    checkpoint_file=settings.checkpoint_file,
                ).run(full=False, backup_dir=settings.backup_dir)
                results.append(
                    {
                        "service": "weread",
                        "ok": True,
                        "changed_books": res.get("changed_books", 0),
                    }
                )
            except Exception as exc:  # noqa: BLE001
                results.append({"service": "weread", "ok": False, "error": str(exc)})

        # 插件同步（weread 作为核心已单独处理）
        registry = build_default_registry()
        for plugin in registry:
            pid = plugin.meta.id
            if pid == "weread":
                continue
            if not self._include(pid):
                continue
            try:
                r = run_plugin(plugin, notion, settings).to_dict()
                r["service"] = pid
                results.append(r)
            except Exception as exc:  # noqa: BLE001
                results.append({"service": pid, "ok": False, "error": str(exc)})

        return results


def _toot(client: Optional[MastodonClient], text: str) -> None:
    if not client:
        return
    try:
        client.post(text)
    except MastodonError as exc:
        log.warning("Mastodon 发布失败：%s", exc)
    except Exception as exc:  # noqa: BLE001
        log.warning("Mastodon 发布异常：%s", exc)


def _summarize(results) -> str:
    lines = []
    for r in results or []:
        svc = r.get("service", "?")
        if r.get("ok"):
            lines.append(f"· {svc}: ✅")
        else:
            err = str(r.get("error", ""))[:80]
            lines.append(f"· {svc}: ❌ {err}")
    return "\n".join(lines) or "（无数据源）"


def run_worker(
    interval: int = 300,
    services=None,
    mastodon: bool = False,
    once: bool = False,
    max_failures: int = 5,
) -> None:
    """常驻运行 Worker 主循环。"""
    setup_logging(verbose=False, quiet=False)
    worker = Worker(
        interval=interval, services=services, mastodon=mastodon, max_failures=max_failures
    )

    def _request_stop(signum, _frame):
        worker._stop = True
        worker._write_state()
        log.info("收到停止信号，Worker 将在本轮结束后退出")

    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)

    log.info(
        "Worker 启动：间隔 %ss，服务=%s，Mastodon=%s",
        interval,
        services or "全部已配置",
        worker.mastodon is not None,
    )
    worker._write_state()
    _toot(worker.mastodon, f"🐘 NotionHub Worker 已启动：每 {interval}s 同步一次。")

    while not worker._stop:
        worker.last_run = datetime.now().isoformat(timespec="seconds")
        worker._write_state()
        try:
            results = worker.run_cycle()
            worker.last_result = results
            worker.failures = 0
            ok = [r for r in results if r.get("ok")]
            failed = [r for r in results if not r.get("ok")]
            summary = _summarize(results)
            log.info("同步周期完成：成功 %d / 失败 %d\n%s", len(ok), len(failed), summary)
            _toot(
                worker.mastodon,
                f"🐘 同步完成（{len(ok)}✅/{len(failed)}❌）\n{summary}",
            )
        except Exception as exc:  # noqa: BLE001
            worker.failures += 1
            log.error("同步周期失败（%d/%d）：%s", worker.failures, max_failures, exc)
            _toot(
                worker.mastodon,
                f"🐘 同步异常（{worker.failures}/{max_failures}）：{exc}",
            )

        worker._write_state()

        if worker.failures >= max_failures:
            log.error("连续失败达到上限 %d，Worker 自动退出", max_failures)
            _toot(
                worker.mastodon,
                f"🐘 Worker 因连续失败达上限（{max_failures}）而停止。",
            )
            break

        if once:
            break

        # 分段睡眠，保证停止信号能及时打断
        slept = 0
        while slept < worker.interval and not worker._stop:
            step = min(5, worker.interval - slept)
            time.sleep(step)
            slept += step

    log.info("Worker 已停止")
    worker._write_state(running=False)
