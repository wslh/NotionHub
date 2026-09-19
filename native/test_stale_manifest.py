import os, time, struct, subprocess

here = os.path.dirname(os.path.abspath(__file__))
exe = os.path.join(here, "NotionHubBridge.exe")
repo = os.path.dirname(here)
env = os.path.join(repo, ".env")

# Simulate a STALE cached manifest: no --cli passed at all. The browser may keep
# using an old host config that never set --cli. Bridge must self-heal to weread2notion.
real_path = os.environ.get("PATH", "")
browser_path = ";".join(d for d in real_path.split(";") if "Python314" not in d)

def frame(o):
    b = o.encode("utf-8")
    return struct.pack("<I", len(b)) + b

print("=== sync_start with NO --cli (stale manifest sim, browser-like PATH) ===")
p = subprocess.Popen(
    [exe, "--env-file", env],  # <-- no --cli at all
    stdin=subprocess.PIPE, stdout=subprocess.PIPE,
    env={"PATH": browser_path, "SystemRoot": os.environ.get("SystemRoot", "C:\\Windows")},
)
p.stdin.write(frame('{"type":"sync_start","args":["--dry-run"]}'))
p.stdin.flush()
time.sleep(3.0)
hdr = p.stdout.read(4)
if len(hdr) < 4:
    print("  -> NO HEADER"); p.terminate()
else:
    n = struct.unpack("<I", hdr)[0]
    print("  ->", p.stdout.read(n).decode("utf-8", "replace"))
try: p.stdin.close()
except Exception: pass
try: p.wait(timeout=5)
except Exception: p.kill()
print("\nDONE")
