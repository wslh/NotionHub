import subprocess, struct, json, sys, os

exe = os.path.join(os.path.dirname(__file__), "NotionHubBridge.exe")

def frame(obj):
    body = json.dumps(obj).encode("utf-8")
    return struct.pack("<I", len(body)) + body

def send_recv(exe, msg, env_file=None, cli=None):
    args = [exe, "--env-file", env_file or os.path.join(os.path.dirname(exe), "..", ".env")]
    if cli:
        args += ["--cli", cli]
    p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, creationflags=0)
    p.stdin.write(frame(msg))
    p.stdin.flush()
    p.stdin.close()
    hdr = p.stdout.read(4)
    if len(hdr) < 4:
        print("NO REPLY. stderr:", p.stderr.read().decode("utf-8", "replace"))
        return None
    n = struct.unpack("<I", hdr)[0]
    body = p.stdout.read(n)
    return json.loads(body.decode("utf-8"))

print("== ping ==")
print(send_recv(exe, {"type": "ping"}))

print("== env_write ==")
print(send_recv(exe, {"type": "env_write", "values": {"NOTION_TOKEN": "secret123", "START_YEAR": "2021"}}))

print("== env_read ==")
print(send_recv(exe, {"type": "env_read"}))

print("== sync_log ==")
print(send_recv(exe, {"type": "sync_log", "lines": 20}))
