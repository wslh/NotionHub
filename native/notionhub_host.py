#!/usr/bin/env python
"""Native Messaging host for the NotionHub browser extension.

The browser extension cannot touch the filesystem, so this small host is the
bridge that lets the control panel read/write the project `.env` and launch the
`notionhub` CLI.

Protocol: Chrome Native Messaging - 4 byte little endian length prefix + JSON.

Supported messages::

    {"type": "ping"}                       -> {"ok": true, ...}
    {"type": "env_read"}                   -> {"ok": true, "values": {...}}
    {"type": "env_write", "values": {...}} -> {"ok": true, "path": "..."}
    {"type": "sync_start", "args": [...]}  -> {"ok": true, "started": true, "log": "..."}
    {"type": "sync_log", "lines": 200}     -> {"ok": true, "log": "..."}
    {"type": "worker_start", "args": {"interval": 300, "services": "", "mastodon": false}}
                                          -> {"ok": true, "started": true, "pid": ..., "log": "..."}
    {"type": "worker_stop"}                -> {"ok": true, "stopped": true}
    {"type": "worker_status"}              -> {"ok": true, "running": bool, "state": {...}}

Only the keys listed in :data:`ALLOWED_KEYS` may be written, and the target file
is fixed at launch time (``--env-file`` or ``NOTIONHUB_ENV_FILE``), so a
malicious page can never redirect the write to another location.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import struct
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HOST_NAME = "com.notionhub.host"

ALLOWED_KEYS = {
    "WEREAD_API_KEY",
    "NOTION_TOKEN",
    "NOTION_PAGE",
    "START_YEAR",
    "BACKUP_DIR",
    "NOTION_VERSION",
    "NOTION_REQUEST_INTERVAL",
    "CONCURRENCY",
    "MAX_RETRIES",
    "CHECKPOINT_FILE",
    "WEREAD_SKILL_VERSION",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_MODEL",
    "WEREAD2NOTION_TELEMETRY",
    "MASTODON_INSTANCE",
    "MASTODON_ACCESS_TOKEN",
}

# Sync is only ever started with these flags; arbitrary args are rejected.
ALLOWED_SYNC_ARGS = {
    "",
    "--quiet",
    "--full",
    "--dry-run",
    "--verbose",
    "--no-self-heal",
}

ENV_FILE: Path | None = None
CLI_COMMAND: list[str] = []


def resolve_env_file() -> Path:
    if ENV_FILE is not None:
        return ENV_FILE
    return Path(__file__).resolve().parent.parent / ".env"


def host_log(message: str) -> None:
    """Append a diagnostic line.

    This is the decisive probe: if Chrome ever launches us, logs/host.log gets a
    line. No line at all means the failure is upstream (registry / manifest /
    extension id), not in this script.
    """
    stamp = datetime.now().isoformat(timespec="seconds")
    line = f"[{stamp}] pid={os.getpid()} {message}\n"
    targets = []
    try:
        targets.append(resolve_env_file().resolve().parent / "logs" / "host.log")
    except Exception:
        pass
    targets.append(Path(os.environ.get("TEMP", ".")) / "notionhub_host.log")
    for target in targets:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "a", encoding="utf-8") as fh:
                fh.write(line)
            return
        except Exception:
            continue


def read_message():
    raw = sys.stdin.buffer.read(4)
    if len(raw) < 4:
        return None
    (length,) = struct.unpack("<I", raw)
    if length <= 0 or length > 1024 * 1024:
        return None
    payload = sys.stdin.buffer.read(length)
    if not payload:
        return None
    try:
        return json.loads(payload.decode("utf-8"))
    except Exception:
        return None


def send_message(obj) -> None:
    data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    try:
        sys.stdout.buffer.write(struct.pack("<I", len(data)))
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()
    except Exception:
        pass


def log_path() -> Path:
    return resolve_env_file().resolve().parent / "logs" / "native-sync.log"


def parse_env(text: str) -> dict:
    values = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        if key in ALLOWED_KEYS:
            values[key] = value.strip().strip('"').strip("'")
    return values


def handle_env_read() -> dict:
    path = resolve_env_file()
    if not path.exists():
        return {"ok": True, "values": {}, "path": str(path), "exists": False}
    try:
        values = parse_env(path.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"read_failed: {exc}"}
    return {"ok": True, "values": values, "path": str(path), "exists": True}


def handle_env_write(values: dict) -> dict:
    clean = {}
    for key, value in (values or {}).items():
        key = str(key).strip()
        if key not in ALLOWED_KEYS:
            return {"ok": False, "error": f"key_not_allowed: {key}"}
        clean[key] = str(value)
    if not clean:
        return {"ok": False, "error": "no_values"}

    path = resolve_env_file()
    try:
        existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"read_failed: {exc}"}

    out = []
    seen = set()
    for line in existing:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            out.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in clean:
            out.append(f"{key}={clean[key]}")
            seen.add(key)
        else:
            out.append(line)
    for key, value in clean.items():
        if key not in seen:
            out.append(f"{key}={value}")

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"write_failed: {exc}"}
    return {"ok": True, "path": str(path), "written": sorted(clean)}


def handle_sync_start(args) -> dict:
    raw_args = [str(a) for a in (args or [])]
    if any(a not in ALLOWED_SYNC_ARGS for a in raw_args):
        return {"ok": False, "error": "arg_not_allowed"}
    if "sync" not in raw_args:
        raw_args = ["sync"] + raw_args

    path = log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = list(CLI_COMMAND) + raw_args
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(
                "\n" + "=" * 60 + "\n"
                f"[{datetime.now().isoformat(timespec='seconds')}] $ "
                + " ".join(cmd) + "\n"
            )
            fh.flush()
            creation = 0
            if os.name == "nt":
                creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            proc = subprocess.Popen(
                cmd,
                cwd=str(resolve_env_file().resolve().parent),
                stdout=fh,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                creationflags=creation,
            )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"start_failed: {exc}"}
    return {"ok": True, "started": True, "pid": proc.pid, "log": str(path)}


def handle_sync_log(lines: int = 200) -> dict:
    path = log_path()
    if not path.exists():
        return {"ok": True, "log": "", "path": str(path)}
    try:
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"read_failed: {exc}"}
    tail = content[-max(1, min(int(lines or 200), 2000)):]
    return {"ok": True, "log": "\n".join(tail), "path": str(path)}


# --------------------------------------------------------------------------- #
# 自有 Worker（长毛象）：常驻同步触发器
# --------------------------------------------------------------------------- #
def worker_state_path() -> Path:
    return resolve_env_file().resolve().parent / "logs" / "worker-state.json"


def _read_worker_state() -> dict | None:
    try:
        p = worker_state_path()
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8", errors="replace"))
    except Exception:  # noqa: BLE001
        return None


def _pid_alive(pid) -> bool:
    if not pid:
        return False
    pid = int(pid)
    if os.name == "nt":
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"],
            capture_output=True,
            text=True,
        )
        return str(pid) in out.stdout
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def handle_worker_start(args) -> dict:
    args = args or {}
    try:
        interval = int(args.get("interval", 300))
    except (TypeError, ValueError):
        interval = 300
    services = (args.get("services") or "").strip()
    use_mastodon = bool(args.get("mastodon", False))

    state = _read_worker_state()
    if state and state.get("running") and _pid_alive(state.get("pid")):
        return {"ok": True, "already_running": True, "pid": state.get("pid")}

    cmd = list(CLI_COMMAND) + ["worker", "--interval", str(interval)]
    if services:
        cmd += ["--services", services]
    if use_mastodon:
        cmd += ["--mastodon"]

    try:
        logp = resolve_env_file().resolve().parent / "logs" / "worker.log"
        logp.parent.mkdir(parents=True, exist_ok=True)
        creation = 0
        if os.name == "nt":
            creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        with open(logp, "a", encoding="utf-8") as fh:
            fh.write(
                "\n" + "=" * 60 + "\n"
                f"[{datetime.now().isoformat(timespec='seconds')}] $ "
                + " ".join(cmd) + "\n"
            )
            fh.flush()
            env = dict(os.environ)
            env["NOTIONHUB_WORKER_STATE"] = str(worker_state_path())
            proc = subprocess.Popen(
                cmd,
                cwd=str(resolve_env_file().resolve().parent),
                stdout=fh,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                creationflags=creation,
                env=env,
            )
        return {
            "ok": True,
            "started": True,
            "pid": proc.pid,
            "interval": interval,
            "services": services or "all",
            "mastodon": use_mastodon,
            "log": str(logp),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"start_failed: {exc}"}


def handle_worker_stop() -> dict:
    state = _read_worker_state()
    if not state or not state.get("running"):
        return {"ok": True, "stopped": False, "message": "Worker 未运行"}
    pid = state.get("pid")
    if pid and _pid_alive(pid):
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    capture_output=True,
                )
            else:
                os.kill(int(pid), signal.SIGTERM)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"stop_failed: {exc}"}
    return {"ok": True, "stopped": True}


def handle_worker_status() -> dict:
    state = _read_worker_state()
    if not state:
        return {"ok": True, "running": False, "state": None}
    alive = bool(state.get("running")) and _pid_alive(state.get("pid"))
    return {"ok": True, "running": alive, "state": state}


def handle(msg) -> dict:
    mtype = (msg or {}).get("type")
    if mtype == "ping":
        return {
            "ok": True,
            "host": HOST_NAME,
            "env_file": str(resolve_env_file()),
            "cli": " ".join(CLI_COMMAND),
            "python": sys.executable,
        }
    if mtype == "env_read":
        return handle_env_read()
    if mtype == "env_write":
        return handle_env_write((msg or {}).get("values") or {})
    if mtype == "sync_start":
        return handle_sync_start((msg or {}).get("args") or [])
    if mtype == "sync_log":
        return handle_sync_log((msg or {}).get("lines") or 200)
    if mtype == "worker_start":
        return handle_worker_start((msg or {}).get("args") or {})
    if mtype == "worker_stop":
        return handle_worker_stop()
    if mtype == "worker_status":
        return handle_worker_status()
    return {"ok": False, "error": f"unknown_type: {mtype}"}


def main() -> int:
    global ENV_FILE, CLI_COMMAND

    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", help="absolute path of the .env to manage")
    parser.add_argument(
        "--cli",
        default="notionhub",
        help="CLI used to run the sync (default: notionhub)",
    )
    args, _ = parser.parse_known_args()
    if args.env_file:
        ENV_FILE = Path(args.env_file).expanduser()
    cli = args.cli.strip()
    CLI_COMMAND = cli.split() if cli else ["notionhub"]

    host_log(f"start argv={sys.argv} cwd={os.getcwd()} py={sys.version.split()[0]}")

    # Windows: keep stdin/stdout strictly binary so the length prefix survives.
    if os.name == "nt":  # pragma: no cover - platform specific
        try:
            import msvcrt

            msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
            msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
        except Exception:
            pass

    while True:
        msg = read_message()
        if msg is None:
            host_log("stdin closed, exiting")
            return 0
        try:
            reply = handle(msg)
        except Exception as exc:  # noqa: BLE001 - never crash the host
            host_log(f"handler raised: {exc!r}")
            reply = {"ok": False, "error": f"internal_error: {exc}"}
        host_log(f"recv={msg.get('type')!r} reply_ok={reply.get('ok')}")
        send_message(reply)


if __name__ == "__main__":
    sys.exit(main())
