from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from .analytics import reading_insights
from .config import ConfigError, Settings
from .export import export_books, export_snapshots
from .logging_utils import setup_logging
from .notion import NotionWorkspace
from .plugin import PluginContext
from .registry import build_default_registry
from .repair import Repair
from .runner import run_plugin
from .sources import build_source
from .status import workspace_status
from .sync import SYNC_VERSION, Synchronizer
from .telemetry import send
from .weread import WeReadClient

log = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="weread2notion")
    sub = parser.add_subparsers(dest="command")
    sync = sub.add_parser("sync", help="同步微信读书数据，保留 Notion 页面结构")
    sync.add_argument("--full", action="store_true", help="备份并重建全部数据库行")
    sync.add_argument(
        "--dry-run", action="store_true", help="只读取微信数据并显示同步计划"
    )
    sync.add_argument(
        "--quiet", action="store_true", help="不打印阶段进度，仅输出最终结果"
    )
    sync.add_argument(
        "--verbose", action="store_true", help="打印调试日志到控制台与 logs/"
    )
    sync.add_argument(
        "--book", action="append", metavar="BOOK_ID", help="只同步指定书籍（可多次）"
    )
    sync.add_argument(
        "--tag", action="append", metavar="TAG", help="只同步带指定标签的书（可多次）"
    )
    sync.add_argument(
        "--no-self-heal",
        action="store_true",
        help="关闭失败自愈（默认失败会自动 repair --apply 后重试一次）",
    )
    sync.add_argument(
        "--source",
        default="weread",
        help="数据源：weread（默认）、local:/目录、kindle:/MyClippings.txt、apple:/export.csv",
    )
    sub.add_parser("check", help="检查模板数据库与属性")
    repair = sub.add_parser(
        "repair", help="检测并修复数据不一致（默认仅检测，加 --apply 执行修复）"
    )
    repair.add_argument(
        "--apply", action="store_true", help="执行修复而非仅报告问题"
    )
    restore = sub.add_parser("restore", help="从全量备份 JSON 恢复已归档的页面")
    restore.add_argument("backup", help="backups/*.json 备份文件路径")
    status_cmd = sub.add_parser("status", help="显示工作区健康状态与待修复项")
    export = sub.add_parser("export", help="导出书架/阅读快照为 CSV 或 Markdown")
    export.add_argument(
        "--target", choices=["books", "snapshots"], default="books", help="导出对象"
    )
    export.add_argument("--format", choices=["csv", "md"], default="csv", help="导出格式")
    export.add_argument("--out", help="输出文件路径")
    sub.add_parser("insights", help="汇总阅读洞察（总时长/连续天数/Top 书目）")
    creds = sub.add_parser("credentials", help="列出各数据源插件所需凭证 / 校验已填凭证")
    csub = creds.add_subparsers(dest="credentials_command")
    csub.add_parser("list", help="列出每个插件的授权方式与 .env 键名")
    cv = csub.add_parser("verify", help="校验当前 .env 中已填写的凭证")
    cv.add_argument("plugin_id", nargs="?", help="指定插件 id，省略则校验全部")
    plugins = sub.add_parser("plugins", help="list or run NotionHub data-source plugins")
    psub = plugins.add_subparsers(dest="plugins_command")
    psub.add_parser("list", help="list every registered plugin")
    pi = psub.add_parser("info", help="show a plugin details and docs link")
    pi.add_argument("plugin_id", help="plugin id, e.g. weread/flomo/github/rss/douban")
    ps = psub.add_parser("sync", help="run a plugin (or every configured plugin with --all)")
    ps.add_argument("plugin_id", nargs="?", help="plugin id")
    ps.add_argument("--all", action="store_true", help="run every configured plugin")
    ps.add_argument(
        "--exclude", action="append", metavar="PLUGIN_ID",
        help="skip these plugin ids (only meaningful with --all)",
    )

    worker = sub.add_parser("worker", help="常驻 Worker（长毛象）：按间隔自动同步并播报至 Mastodon")
    worker.add_argument("--interval", type=int, default=300, help="同步间隔秒数（默认 300 = 5 分钟）")
    worker.add_argument("--services", help="逗号分隔的数据源 id；省略则同步全部已配置")
    worker.add_argument("--mastodon", action="store_true", help="把同步结果以嘟文发布到 Mastodon（长毛象）")
    worker.add_argument("--once", action="store_true", help="只跑一轮然后退出（用于测试）")
    worker.add_argument("--max-failures", type=int, default=5, help="连续失败达到该次数后自动停止（默认 5）")
    return parser


def _self_heal(weread, notion, start_year: int) -> None:
    """同步失败后的自愈：自动检测并修复，再尝试一次。"""
    try:
        Repair(weread, notion, start_year, apply=True).fix()
        log.warning("自愈：已执行 repair --apply，将重试同步")
    except Exception as exc:  # noqa: BLE001 - 自愈失败不应掩盖原始错误
        log.warning("自愈失败：%s", exc)


def _connect_notion(settings: Settings):
    """建立并发现 Notion 工作区，返回 ``(notion, preferences)``。"""
    notion = NotionWorkspace(
        settings.notion_token,
        settings.notion_page_id,
        settings.notion_version,
        settings.request_interval,
    ).discover()
    preferences = notion.ensure_sync_settings(settings.start_year)
    notion.ensure_reading_snapshots()
    return notion, preferences


# --------------------------------------------------------------------------- #
# 子命令 handler：每个命令一个函数，main 通过 _DISPATCH 查表分发。
# 签名统一为 (args, settings, weread, source)。
# --------------------------------------------------------------------------- #


def cmd_credentials(args, settings, weread, source) -> None:
    sub_cmd = getattr(args, "credentials_command", None) or "list"
    from .credentials import all_credentials, credentials_for, verify_credential

    load_dotenv()
    all_specs = all_credentials()
    if sub_cmd == "list":
        rows = []
        for pid, specs in sorted(all_specs.items()):
            rows.append({
                "id": pid,
                "credentials": [
                    {**s, "filled": bool(os.getenv(s["env_key"], "").strip())}
                    for s in specs
                ],
            })
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    if sub_cmd == "verify":
        target = getattr(args, "plugin_id", None)
        registry_ids = [p.meta.id for p in build_default_registry()]
        ids = [target] if target else registry_ids
        report = {}
        for pid in ids:
            for s in all_specs.get(pid, []) or [
                x.to_dict() for x in credentials_for(pid)
            ]:
                if not s.get("required", True):
                    continue
                val = (os.getenv(s["env_key"], "") or "").strip()
                if not val:
                    report.setdefault(pid, []).append({
                        "env_key": s["env_key"], "ok": False,
                        "message": "未填写", "required": True})
                else:
                    r = verify_credential(s["cred_type"], val)
                    report.setdefault(pid, []).append({
                        "env_key": s["env_key"], "ok": r["ok"],
                        "message": r["message"],
                        "required": s.get("required", True)})
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return


def cmd_worker(args, settings, weread, source) -> None:
    from .worker import run_worker

    svcs = [
        s.strip()
        for s in (getattr(args, "services", "") or "").split(",")
        if s.strip()
    ] or None
    run_worker(
        interval=getattr(args, "interval", 300),
        services=svcs,
        mastodon=getattr(args, "mastodon", False),
        once=getattr(args, "once", False),
        max_failures=getattr(args, "max_failures", 5),
    )


def cmd_check(args, settings, weread, source) -> None:
    notion, preferences = _connect_notion(settings)
    print(
        json.dumps(
            {
                "databases": notion.databases,
                "schemas": notion.schemas,
                "settings": {
                    key: value
                    for key, value in preferences.items()
                    if not key.startswith("_")
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def cmd_repair(args, settings, weread, source) -> None:
    notion, _ = _connect_notion(settings)
    repair = Repair(source, notion, settings.start_year, apply=args.apply)
    result = repair.fix() if args.apply else repair.check()
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_restore(args, settings, weread, source) -> None:
    notion, _ = _connect_notion(settings)
    restored = notion.restore_from_backup(Path(args.backup))
    print(
        json.dumps(
            {"restored": restored, "backup": str(args.backup)},
            ensure_ascii=False,
            indent=2,
        )
    )


def cmd_status(args, settings, weread, source) -> None:
    notion, _ = _connect_notion(settings)
    result = workspace_status(source, notion, settings.start_year)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["healthy"] else 1)


def cmd_export(args, settings, weread, source) -> None:
    notion, _ = _connect_notion(settings)
    if args.target == "books":
        out = export_books(notion, args.format, Path(args.out) if args.out else None)
    else:
        out = export_snapshots(notion, args.format, Path(args.out) if args.out else None)
    print(json.dumps({"exported": str(out)}, ensure_ascii=False))


def cmd_plugins(args, settings, weread, source) -> None:
    registry = build_default_registry()
    sub_cmd = getattr(args, "plugins_command", None) or "list"
    # 插件命令复用独立的 notion 连接（无需 discover 后的模板自检）。
    plugin_notion = NotionWorkspace(
        settings.notion_token, settings.notion_page_id,
        settings.notion_version, settings.request_interval,
    )
    if sub_cmd == "list":
        print(json.dumps(registry.summary(), ensure_ascii=False, indent=2))
        return
    if sub_cmd == "info":
        try:
            plugin = registry.get(args.plugin_id)
        except KeyError as exc:
            sys.stderr.write(json.dumps({"error": str(exc), "available": [p.meta.id for p in registry]}, ensure_ascii=False) + chr(10))
            raise SystemExit(1)
        health = plugin.health(PluginContext(notion=plugin_notion, settings=settings))
        payload = {**plugin.meta.__dict__, "category": plugin.meta.category.value, "configured": plugin.is_configured(), "health": health}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if sub_cmd == "sync":
        plugin_notion.discover()
        if args.all:
            excluded = set(args.exclude or [])
            targets = [p for p in registry if p.meta.id not in excluded]
        else:
            try:
                targets = [registry.get(args.plugin_id)]
            except KeyError as exc:
                sys.stderr.write(json.dumps({"error": str(exc), "available": [p.meta.id for p in registry]}, ensure_ascii=False) + chr(10))
                raise SystemExit(1)
        results = [run_plugin(p, plugin_notion, settings).to_dict() for p in targets]
        print(json.dumps({"results": results}, ensure_ascii=False, indent=2))
        return


def cmd_insights(args, settings, weread, source) -> None:
    notion, _ = _connect_notion(settings)
    result = reading_insights(notion)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_sync(args, settings, weread, source) -> None:
    quiet = getattr(args, "quiet", False)
    # dry-run 不需要连接 Notion。
    if getattr(args, "dry_run", False):
        result = Synchronizer(source, None, settings.start_year, dry_run=True).run()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    notion, preferences = _connect_notion(settings)

    # 版本自检：提示模板与代码同步版本是否匹配。
    if int(preferences.get("sync_version", 0)) != SYNC_VERSION:
        log.warning(
            "代码同步版本 v%d 与设置库记录 v%s 不一致，建议运行 "
            "`weread2notion sync --full` 以应用模板变更",
            SYNC_VERSION,
            preferences.get("sync_version"),
        )

    only_books = set(args.book) if getattr(args, "book", None) else None
    only_tags = set(args.tag) if getattr(args, "tag", None) else None

    def run_sync() -> dict:
        return Synchronizer(
            source,
            notion,
            settings.start_year,
            dry_run=False,
            preferences=preferences,
            quiet=quiet,
            concurrency=settings.concurrency,
            checkpoint_file=settings.checkpoint_file,
            only_books=only_books,
            only_tags=only_tags,
        ).run(
            full=getattr(args, "full", False),
            backup_dir=settings.backup_dir,
        )

    try:
        result = run_sync()
    except Exception as exc:  # noqa: BLE001 - 触发自愈重试
        if getattr(args, "no_self_heal", False):
            raise
        log.error("同步失败：%s，尝试自愈后重试", exc)
        _self_heal(source, notion, settings.start_year)
        result = run_sync()

    notion.mark_sync_settings_applied(
        preferences.get("_page_id"),
        preferences.get("_config_code", 0),
        preferences.get("_config_property", "同步配置版本（不可删除）"),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if getattr(args, "full", False) and result.get("backup"):
        print(f"全量同步已完成。备份文件：{result['backup']}")
        print(f"如需回滚，可执行：weread2notion restore {result['backup']}")

    # 可选遥测（需 WEREAD2NOTION_TELEMETRY=1，失败不影响主流程）。
    send(
        "sync",
        {"books": result.get("changed_books", 0), "mode": "full" if args.full else "incr"},
    )


# 子命令 → handler 注册表。未知命令回退到 cmd_sync（与原「漏网即走同步」行为一致）。
_DISPATCH = {
    "sync": cmd_sync,
    "check": cmd_check,
    "repair": cmd_repair,
    "restore": cmd_restore,
    "status": cmd_status,
    "export": cmd_export,
    "plugins": cmd_plugins,
    "insights": cmd_insights,
    "credentials": cmd_credentials,
    "worker": cmd_worker,
}


def main(argv=None) -> None:
    args = build_parser().parse_args(argv)
    command = args.command or "sync"
    setup_logging(
        verbose=getattr(args, "verbose", False),
        quiet=getattr(args, "quiet", False),
    )
    try:
        settings = Settings.from_env()
        # 微信读书专属 sync 命令仍强制要求 WEREAD_API_KEY（多数据源自托管路径已放宽）。
        if command == "sync" and not settings.weread_api_key:
            raise ConfigError("缺少 WEREAD_API_KEY（微信读书同步必需）")
        weread = WeReadClient(settings.weread_api_key, settings.skill_version)
        source = build_source(getattr(args, "source", "weread") or "weread", weread)
        # 凭证清单 / 校验、worker 不需要连接 Notion，由对应 handler 自行决定是否建连。
        _DISPATCH.get(command, cmd_sync)(args, settings, weread, source)
    except ConfigError as exc:
        raise SystemExit(f"配置错误：{exc}") from exc


if __name__ == "__main__":
    main()
