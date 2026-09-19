import os, time, struct, subprocess, shutil, json

here = os.path.dirname(os.path.abspath(__file__))
exe = os.path.join(here, "NotionHubBridge.exe")
repo = os.path.dirname(here)
env = os.path.join(repo, ".env")
backup = env + ".simbak"
print("EXE =", exe)
print("ENV =", env)

def frame(obj):
    b = obj.encode("utf-8")
    return struct.pack("<I", len(b)) + b

def call(msg, wait=0.4):
    p = subprocess.Popen(
        [exe, "--env-file", env, "--cli", "weread2notion"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
    )
    p.stdin.write(frame(msg)); p.stdin.flush()
    time.sleep(wait)
    hdr = p.stdout.read(4)
    if len(hdr) < 4:
        print("  -> NO HEADER"); p.terminate(); return None
    n = struct.unpack("<I", hdr)[0]
    body = p.stdout.read(n).decode("utf-8", "replace") if n else ""
    try: p.stdin.close()
    except Exception: pass
    try: p.wait(timeout=3)
    except Exception: p.kill()
    return body

# 0) backup
shutil.copyfile(env, backup)
print("BACKUP ->", backup)

print("\n=== 1) ping ===")
print(call('{"type":"ping"}'))

print("\n=== 2) env_read (before) ===")
before = call('{"type":"env_read"}')
print(before)

print("\n=== 3) env_write (temporarily set START_YEAR=2000) ===")
print(call('{"type":"env_write","values":{"START_YEAR":"2000"}}', wait=0.5))

print("\n=== 4) env_read (after write, expect START_YEAR=2000) ===")
after = call('{"type":"env_read"}')
print(after)
try:
    v = json.loads(after).get("values", {}).get("START_YEAR")
    print("  >> START_YEAR now:", v, "  (write persist OK)" if v == "2000" else "  (FAILED)")
except Exception as e:
    print("  >> parse error", e)

print("\n=== 5) sync_start (dry-run, read-only, no Notion writes) ===")
r = call('{"type":"sync_start","args":["--dry-run"]}', wait=3.0)
print(r)

print("\n=== 6) sync_log (tail) ===")
print(call('{"type":"sync_log","lines":40}'))

# 7) restore
shutil.move(backup, env)
print("\nRESTORED", env)
print("\n=== 7) env_read (after restore, expect START_YEAR back to 2023) ===")
print(call('{"type":"env_read"}'))
print("\nALL STEPS DONE")
