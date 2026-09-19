# NotionHub Architecture

NotionHub is a plugin hub: one small protocol, many data sources. WeRead, Flomo, GitHub and future sources are all plugins. The core engine handles Notion I/O, retries, logging and discovery. Add a source by dropping a file into src/weread2notion/plugins/.

## Layers

  CLI (weread2notion / notionhub)
   -> Plugin Registry + Runner
   -> Plugins (one file per source)
   -> Core engine (NotionWorkspace, Synchronizer, analytics, sources)

## Three tiers (end to end)

The Python package is only the middle tier. A full sync spans three tiers:

1. **Browser extension (configure + trigger)** — `manifest.json` / `background.js` /
   `panel.js` at the repo root. It does *not* sync data. It authorizes Notion and
   GitHub (OAuth), captures the WeRead API key (`weread_key_capture.js`), verifies
   the Notion template (`verifyNotionTemplate`, 7 required databases), stores config,
   and triggers a sync. Triggers: local CLI via Native Messaging, `workflow_dispatch`
   on GitHub Actions, or the resident Worker.
2. **Runner (execute)** — either GitHub Actions using THIS repository's own workflows
   (`weread.yml` for WeRead, `sync.yml` for every other configured data source, both
   wrapping the repo-root `action.yml`; no external `notionhub-runner` needed) or a
   self-hosted Worker (`notionhub worker`, `src/weread2notion/worker.py`, polls every
   300s and can broadcast results to Mastodon). Both run the same CLI underneath.
3. **Notion workspace (store)** — the duplicated template. Database names, property
   names/types, relations and the dedupe IDs are hardcoded in the sync code
   (`REQUIRED_TEMPLATE_DBS`, `notion.py` schemas); renaming them breaks sync.

`runner.py` is deliberately thin: it only builds a `PluginContext`, checks
`is_configured()`, calls `setup()` then `sync()`. Scheduling, retries and
aggregation are the caller's job (CLI / cron / GitHub Actions / Worker).

## The Plugin contract

Implement meta + is_configured + setup + discover + sync + health.
PluginContext injects notion, settings, and a logger.

| Method         | Purpose                                                  |
|----------------|----------------------------------------------------------|
| is_configured  | False => sync safely skips, logs docs URL               |
| setup          | Run once (e.g. ensure_database)                          |
| discover       | Optional preview of items                                |
| sync           | Do the work, return SyncResult(synced, skipped, errors) |
| health         | Dict for the control panel                               |

## Categories

Category mirrors the control panel: reading / podcast / media / notes / todo / learning / exercise / productivity / diet / other.

## Adding a plugin

1. Copy src/weread2notion/plugins/template.py to a new file.
2. Inherit BasePlugin; declare DB_NAME/TITLE_PROP/KEY_PROP/SCHEMA, implement is_configured and _items(ctx) -> Iterable[(key, raw)]. setup/sync/discover/health are provided by the base class.
3. Register the class in src/weread2notion/plugins/__init__.py (_instances builder).
4. Add tests under tests/ using a FakeNotion (see test_plugin_framework.py).
5. Reuse shared helpers from weread2notion.utils instead of re-implementing text/date parsing: `strip_html` (strip tags + unescape), `parse_date_to_timestamp` (date string -> Unix timestamp), `parse_date_to_iso` (date string -> ISO 8601), `parse_kindle_clipping_date` (Kindle locale metadata line). See src/weread2notion/plugins/template.py for a worked example.

## Backwards compatibility

The CLI binary keeps the weread2notion entry point so existing forks and GitHub Actions continue to work. The Python package is still weread2notion; notionhub is a brand + new entry point only.
