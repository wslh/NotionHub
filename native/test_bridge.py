import os, sys, time, struct, subprocess

here = os.path.dirname(os.path.abspath(__file__))
exe = os.path.join(here, "NotionHubBridge.exe")
repo = os.path.dirname(here)
env = os.path.join(repo, ".env")
print("EXE =", exe)
print("ENV =", env)

def frame(obj):
    b = obj.encode("utf-8")
    return struct.pack("<I", len(b)) + b

def run(msg):
    p = subprocess.Popen(
        [exe, "--env-file", env, "--cli", "weread2notion"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
    )
    p.stdin.write(frame(msg))
    p.stdin.flush()
    time.sleep(0.3)
    hdr = p.stdout.read(4)
    if len(hdr) < 4:
        print("  -> NO HEADER:", hdr)
        p.terminate()
        return
    n = struct.unpack("<I", hdr)[0]
    body = p.stdout.read(n) if n > 0 else b""
    print("  ->", body.decode("utf-8", "replace"))
    try:
        p.stdin.close()
    except Exception:
        pass
    try:
        p.wait(timeout=3)
    except Exception:
        p.kill()

print("=== ping ===")
run('{"type":"ping"}')
print("=== env_read ===")
run('{"type":"env_read"}')
print("=== sync_log ===")
run('{"type":"sync_log","lines":20}')
print("DONE")
