import os, time, struct, subprocess

here = os.path.dirname(os.path.abspath(__file__))
exe = os.path.join(here, "NotionHubBridge.exe")
repo = os.path.dirname(here)
env = os.path.join(repo, ".env")

# Realistic browser-like PATH: keep system dirs (Winsock works), but remove the
# Python Scripts dir so the bridge must resolve/absolute-path the cli itself.
real_path = os.environ.get("PATH", "")
browser_path = ";".join(d for d in real_path.split(";") if "Python314" not in d)
print("Python Scripts removed from PATH:", not any("Python314" in d for d in browser_path.split(";")))

def frame(o):
    b = o.encode("utf-8")
    return struct.pack("<I", len(b)) + b

def trial(label, cli_arg):
    print("\n=== %s (cli=%s) ===" % (label, cli_arg))
    p = subprocess.Popen(
        [exe, "--env-file", env, "--cli", cli_arg],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        env={"PATH": browser_path, "SystemRoot": os.environ.get("SystemRoot", "C:\\Windows")},
    )
    p.stdin.write(frame('{"type":"sync_start","args":["--dry-run"]}'))
    p.stdin.flush()
    time.sleep(3.0)
    hdr = p.stdout.read(4)
    if len(hdr) < 4:
        print("  -> NO HEADER"); p.terminate(); return
    n = struct.unpack("<I", hdr)[0]
    print("  ->", p.stdout.read(n).decode("utf-8", "replace"))
    try: p.stdin.close()
    except Exception: pass
    try: p.wait(timeout=5)
    except Exception: p.kill()

trial("A: bare cli, browser-like PATH (tests ResolveCli)", "weread2notion")
trial("B: absolute cli, browser-like PATH (matches new manifest)", r"C:\Python314\Scripts\weread2notion.exe")
print("\nDONE")
