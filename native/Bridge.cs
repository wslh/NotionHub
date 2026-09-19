using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Text;

// NotionHub native messaging host (self-contained, no Python required).
//
// WHY THIS EXISTS
// ---------------
// Chrome passes the host three pipes on stdin/stdout and speaks a framing
// protocol: [4 byte little endian length][UTF-8 JSON].
//
// Hosting this directly in Python is unreliable on Windows:
//   * python.exe  is a CONSOLE subsystem binary - Windows allocates a new
//     console for it, so the pipes Chrome handed over are not used and the
//     browser reports "Error when communicating with the native messaging
//     host."
//   * pythonw.exe is a WINDOWS subsystem binary - it does not allocate a
//     console, but its stdin never yields the bytes Chrome wrote, so the host
//     silently exits with no response.
//
// Compiling this as a WINDOWS subsystem (/target:winexe) gives us the correct
// behaviour: no console is allocated, so stdin/stdout ARE Chrome's pipes, and
// we implement the protocol here. No child process, no handle juggling.
//
// PROTOCOL (all frames are length-prefixed JSON)
//   -> {"type":"ping"}
//   <- {"ok":true,"host":"...","env_file":"...","cli":"...","python":"(self-contained)"}
//   -> {"type":"env_read"}
//   -> {"type":"env_write","values":{...}}   keys restricted to ALLOWED_KEYS
//   -> {"type":"sync_start","args":[...]}    args restricted to ALLOWED_ARGS
//   -> {"type":"sync_log","lines":N}
//   -> {"type":"worker_start","args":{"interval":300,"services":"","mastodon":false}}
//   -> {"type":"worker_stop"}
//   -> {"type":"worker_status"}
//
// USAGE (supplied by the manifest install script)
//   NotionHubBridge.exe --env-file <abs path> [--cli <command>]

internal static class Bridge
{
    // Only these keys may ever be written to the .env.
    private static readonly HashSet<string> AllowedKeys = new HashSet<string>(StringComparer.Ordinal)
    {
        "WEREAD_API_KEY", "NOTION_TOKEN", "NOTION_PAGE", "START_YEAR",
        "BACKUP_DIR", "NOTION_VERSION", "NOTION_REQUEST_INTERVAL",
        "CONCURRENCY", "MAX_RETRIES", "CHECKPOINT_FILE",
        "WEREAD_SKILL_VERSION", "OPENAI_API_KEY", "OPENAI_BASE_URL",
        "OPENAI_MODEL", "WEREAD2NOTION_TELEMETRY",
        // Resource storage (S3-compatible)
        "STORAGE_PROVIDER", "STORAGE_ENDPOINT", "STORAGE_REGION",
        "STORAGE_BUCKET", "STORAGE_ACCESS_KEY", "STORAGE_SECRET_KEY",
        "STORAGE_PREFIX", "STORAGE_CDN_DOMAIN",
        "STORAGE_YOUTUBE", "STORAGE_XIAOHONGSHU", "STORAGE_DOUYIN",
    };

    // Only these sync flags may be passed to the CLI.
    private static readonly HashSet<string> AllowedArgs = new HashSet<string>(StringComparer.Ordinal)
    {
        "sync", "--quiet", "--full", "--dry-run", "--verbose", "--no-self-heal",
    };

    private const int MaxFrame = 1024 * 1024; // 1 MiB

    private static string _envFile = null;
    private static string _cli = "weread2notion";

    private static int Main(string[] argv)
    {
        for (int i = 0; i < argv.Length; i++)
        {
            if (argv[i] == "--env-file" && i + 1 < argv.Length) _envFile = argv[++i];
            else if (argv[i] == "--cli" && i + 1 < argv.Length) _cli = argv[++i];
        }

        using (var stdin = Console.OpenStandardInput())
        using (var stdout = Console.OpenStandardOutput())
        {
            try
            {
                while (true)
                {
                    byte[] request = ReadFrame(stdin);
                    if (request == null) break; // stdin closed -> normal shutdown
                    string reply = Dispatch(request);
                    WriteFrame(stdout, reply);
                }
            }
            catch (Exception ex)
            {
                try { WriteFrame(stdout, Json.Err("internal_error: " + ex.Message)); }
                catch { /* nothing we can do */ }
                Log("fatal: " + ex);
                return 1;
            }
        }
        return 0;
    }

    // ---------------- framing ----------------

    private static byte[] ReadFrame(Stream stdin)
    {
        byte[] header = ReadExactly(stdin, 4);
        if (header == null || header.Length < 4) return null;
        uint len = (uint)(header[0] | (header[1] << 8) | (header[2] << 16) | (header[3] << 24));
        if (len == 0) return new byte[0];
        if (len > MaxFrame) throw new IOException("frame too large: " + len);
        return ReadExactly(stdin, (int)len);
    }

    private static byte[] ReadExactly(Stream stream, int count)
    {
        var buffer = new byte[count];
        int offset = 0;
        while (offset < count)
        {
            int read = stream.Read(buffer, offset, count - offset);
            if (read <= 0)
            {
                if (offset == 0) return null; // clean EOF
                Array.Resize(ref buffer, offset);
                return buffer;
            }
            offset += read;
        }
        return buffer;
    }

    private static void WriteFrame(Stream stdout, string json)
    {
        byte[] payload = Encoding.UTF8.GetBytes(json);
        byte[] header = new byte[4];
        header[0] = (byte)(payload.Length & 0xFF);
        header[1] = (byte)((payload.Length >> 8) & 0xFF);
        header[2] = (byte)((payload.Length >> 16) & 0xFF);
        header[3] = (byte)((payload.Length >> 24) & 0xFF);
        stdout.Write(header, 0, 4);
        stdout.Write(payload, 0, payload.Length);
        stdout.Flush();
    }

    // ---------------- dispatch ----------------

    private static string Dispatch(byte[] raw)
    {
        string text = Encoding.UTF8.GetString(raw);
        var msg = Json.Parse(text);
        string type = msg.ContainsKey("type") ? (msg["type"] as string ?? "") : "";
        Log("recv type=" + type);

        switch (type)
        {
            case "ping":
                return Json.Obj(
                    "ok", true,
                    "host", "com.notionhub.host",
                    "env_file", EnvPath(),
                    "cli", _cli,
                    "python", "(self-contained)");

            case "env_read":
                return HandleEnvRead();

            case "env_write":
                return HandleEnvWrite(msg);

            case "sync_start":
                return HandleSyncStart(msg);

            case "sync_log":
                return HandleSyncLog(msg);

            case "worker_start":
                return HandleWorkerStart(msg);

            case "worker_stop":
                return HandleWorkerStop();

            case "worker_status":
                return HandleWorkerStatus();

            default:
                return Json.Err("unknown_type: " + type);
        }
    }

    private static string EnvPath()
    {
        if (!string.IsNullOrEmpty(_envFile)) return Path.GetFullPath(_envFile);
        // Default to <repo>\.env - repo is one level above native\
        // AppContext.BaseDirectory works for both single-file and framework-dependent builds
        // (Assembly.Location is empty inside a single-file app).
        string nativeDir = AppContext.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar);
        string repo = Directory.GetParent(nativeDir).FullName;
        return Path.Combine(repo, ".env");
    }

    private static string HandleEnvRead()
    {
        string path = EnvPath();
        try
        {
            if (!File.Exists(path))
                return Json.Obj("ok", true, "values", new Dictionary<string, string>(),
                                "path", path, "exists", false);

            var values = new Dictionary<string, string>();
            foreach (string line in File.ReadAllLines(path))
            {
                string trimmed = line.Trim();
                if (trimmed.Length == 0 || trimmed.StartsWith("#")) continue;
                int eq = trimmed.IndexOf('=');
                if (eq <= 0) continue;
                string key = trimmed.Substring(0, eq).Trim();
                if (!AllowedKeys.Contains(key)) continue;
                string val = trimmed.Substring(eq + 1).Trim().Trim('"').Trim('\'');
                values[key] = val;
            }
            return Json.Obj("ok", true, "values", values, "path", path, "exists", true);
        }
        catch (Exception ex)
        {
            return Json.Err("read_failed: " + ex.Message);
        }
    }

    private static string HandleEnvWrite(Dictionary<string, object> msg)
    {
        object rawValues;
        if (!msg.TryGetValue("values", out rawValues) || rawValues == null)
            return Json.Err("no_values");

        var incoming = rawValues as Dictionary<string, object>;
        if (incoming == null) return Json.Err("bad_values");

        var clean = new Dictionary<string, string>();
        foreach (var kv in incoming)
        {
            // Reject the whole write if a single key is not whitelisted.
            if (!AllowedKeys.Contains(kv.Key))
                return Json.Err("key_not_allowed: " + kv.Key);
            clean[kv.Key] = kv.Value == null ? "" : kv.Value.ToString();
        }
        if (clean.Count == 0) return Json.Err("no_values");

        string path = EnvPath();
        try
        {
            var lines = new List<string>();
            if (File.Exists(path)) lines.AddRange(File.ReadAllLines(path));

            var seen = new HashSet<string>(StringComparer.Ordinal);
            for (int i = 0; i < lines.Count; i++)
            {
                string line = lines[i];
                int eq = line.IndexOf('=');
                if (eq <= 0) continue;
                string key = line.Substring(0, eq).Trim();
                if (clean.ContainsKey(key))
                {
                    lines[i] = key + "=" + clean[key];
                    seen.Add(key);
                }
            }
            foreach (var kv in clean)
                if (!seen.Contains(kv.Key)) lines.Add(kv.Key + "=" + kv.Value);

            Directory.CreateDirectory(Path.GetDirectoryName(path));
            File.WriteAllText(path, string.Join("\n", lines.ToArray()) + "\n", new UTF8Encoding(false));

            var written = new List<string>(clean.Keys);
            written.Sort();
            return Json.Obj("ok", true, "path", path, "written", written);
        }
        catch (Exception ex)
        {
            return Json.Err("write_failed: " + ex.Message);
        }
    }

    // Resolve the CLI to an absolute path. The browser launches this host with
    // its own (often reduced) PATH, so a bare "weread2notion" may not be found
    // even though it works in an interactive shell. Search PATH and the usual
    // Python Scripts directories before giving up.
    //
    // Robustness: if the configured name is missing, also try its sibling
    // ("notionhub" <-> "weread2notion") so a stale manifest that never set --cli
    // still self-heals instead of failing with "file not found".
    private static string ResolveCli(string cli)
    {
        if (string.IsNullOrEmpty(cli)) cli = "weread2notion";
        string[] candidates = new[] { cli, (cli == "notionhub" ? "weread2notion" : "notionhub") };

        foreach (string name in candidates)
        {
            if (Path.IsPathRooted(name))
            {
                if (File.Exists(name)) return name;
                continue; // rooted but missing: try next candidate
            }

            string pathEnv = Environment.GetEnvironmentVariable("PATH") ?? "";
            foreach (string dir in pathEnv.Split(';'))
            {
                if (string.IsNullOrWhiteSpace(dir)) continue;
                foreach (string ext in new[] { ".exe", ".cmd", ".bat", "" })
                {
                    try
                    {
                        string cand = Path.Combine(dir.Trim(), name + ext);
                        if (File.Exists(cand)) return cand;
                    }
                    catch { /* ignore */ }
                }
            }

            string[] roots = new[]
            {
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
            };
            foreach (string root in roots)
            {
                if (string.IsNullOrEmpty(root)) continue;
                string pyStore = Path.Combine(root, "Programs", "Python");
                if (Directory.Exists(pyStore))
                {
                    foreach (string pyDir in Directory.GetDirectories(pyStore))
                    {
                        string cand = Path.Combine(pyDir, "Scripts", name + ".exe");
                        if (File.Exists(cand)) return cand;
                    }
                }
                string cand2 = Path.Combine(root, "Python", "Scripts", name + ".exe");
                if (File.Exists(cand2)) return cand2;
            }
            foreach (string drive in new[] { "C:\\", "D:\\" })
            {
                if (!Directory.Exists(drive)) continue;
                foreach (string d in Directory.GetDirectories(drive, "Python3*"))
                {
                    string cand = Path.Combine(d, "Scripts", name + ".exe");
                    if (File.Exists(cand)) return cand;
                }
            }
        }
        return cli; // unresolved: let Process.Start report the error
    }

    private static string HandleSyncStart(Dictionary<string, object> msg)
    {
        var args = new List<string> { "sync" };
        object rawArgs;
        if (msg.TryGetValue("args", out rawArgs) && rawArgs is System.Collections.IList)
        {
            var list = (System.Collections.IList)rawArgs;
            foreach (object item in list)
            {
                string flag = item == null ? "" : item.ToString();
                if (!AllowedArgs.Contains(flag)) return Json.Err("arg_not_allowed: " + flag);
                if (flag != "sync") args.Add(flag);
            }
        }

        string repo = Path.GetDirectoryName(EnvPath());
        string logFile = Path.Combine(repo, "logs", "native-sync.log");
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(logFile));

            var psi = new ProcessStartInfo
            {
                FileName = ResolveCli(_cli),
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                WorkingDirectory = repo,
            };
            foreach (var a in args) psi.Arguments += (psi.Arguments.Length > 0 ? " " : "") + a;

            // Append a command banner then stream the run into the log.
            File.AppendAllText(logFile,
                "\n" + new string('=', 60) + "\n[" +
                DateTime.Now.ToString("yyyy-MM-ddTHH:mm:ss", CultureInfo.InvariantCulture) +
                "] $ " + _cli + " " + psi.Arguments + "\n", new UTF8Encoding(false));

            using (var proc = Process.Start(psi))
            {
                if (proc == null) return Json.Err("start_failed: null process");
                string outText = proc.StandardOutput.ReadToEnd();
                string errText = proc.StandardError.ReadToEnd();
                proc.WaitForExit();
                File.AppendAllText(logFile, outText + errText, new UTF8Encoding(false));
                return Json.Obj("ok", true, "started", true, "pid", proc.Id,
                                "exit_code", proc.ExitCode, "log", logFile);
            }
        }
        catch (Exception ex)
        {
            return Json.Err("start_failed: " + ex.Message);
        }
    }

    private static string HandleSyncLog(Dictionary<string, object> msg)
    {
        int lines = 200;
        object rawLines;
        if (msg.TryGetValue("lines", out rawLines) && rawLines != null)
        {
            int parsed;
            if (int.TryParse(rawLines.ToString(), out parsed))
                lines = Math.Max(1, Math.Min(parsed, 2000));
        }
        string repo = Path.GetDirectoryName(EnvPath());
        string logFile = Path.Combine(repo, "logs", "native-sync.log");
        try
        {
            if (!File.Exists(logFile)) return Json.Obj("ok", true, "log", "", "path", logFile);
            string[] all = File.ReadAllLines(logFile);
            int take = Math.Min(lines, all.Length);
            var tail = new string[take];
            Array.Copy(all, all.Length - take, tail, 0, take);
            return Json.Obj("ok", true, "log", string.Join("\n", tail), "path", logFile);
        }
        catch (Exception ex)
        {
            return Json.Err("read_failed: " + ex.Message);
        }
    }

    // ---------------- worker (long-running sync trigger) ----------------
    //
    // The worker is `notionhub worker`: a resident process that triggers a
    // local CLI sync on a fixed interval (default 300s) instead of relying on
    // GitHub Actions. It reports its state to <repo>/logs/worker-state.json,
    // which is what worker_status reads back.

    // Keep a strong reference: async output handlers stop firing once the
    // Process object gets collected.
    private static readonly List<Process> Workers = new List<Process>();
    private static readonly object WorkerLogLock = new object();

    private static string WorkerStatePath()
    {
        return Path.Combine(Path.GetDirectoryName(EnvPath()), "logs", "worker-state.json");
    }

    private static string WorkerLogPath()
    {
        return Path.Combine(Path.GetDirectoryName(EnvPath()), "logs", "worker.log");
    }

    private static Dictionary<string, object> ReadWorkerState()
    {
        try
        {
            string path = WorkerStatePath();
            if (!File.Exists(path)) return null;
            return Json.Parse(File.ReadAllText(path));
        }
        catch (Exception ex)
        {
            Log("read worker state failed: " + ex.Message);
            return null;
        }
    }

    private static int StatePid(Dictionary<string, object> state)
    {
        if (state == null) return 0;
        object raw;
        if (!state.TryGetValue("pid", out raw) || raw == null) return 0;
        try { return Convert.ToInt32(raw, CultureInfo.InvariantCulture); }
        catch { return 0; }
    }

    private static bool PidAlive(int pid)
    {
        if (pid <= 0) return false;
        try
        {
            using (Process p = Process.GetProcessById(pid)) return !p.HasExited;
        }
        catch { return false; }
    }

    private static bool DictFlag(IDictionary dict, string key, bool fallback)
    {
        if (dict == null || !dict.Contains(key)) return fallback;
        object value = dict[key];
        if (value == null) return fallback;
        if (value is bool) return (bool)value;
        string text = Convert.ToString(value, CultureInfo.InvariantCulture);
        return text == "True" || text == "true" || text == "1";
    }

    private static void AppendWorkerLog(string logFile, string line)
    {
        try
        {
            lock (WorkerLogLock)
                File.AppendAllText(logFile, line + "\n", new UTF8Encoding(false));
        }
        catch { /* logging must never kill the host */ }
    }

    private static string HandleWorkerStart(Dictionary<string, object> msg)
    {
        int interval = 300;
        string services = "";
        bool mastodon = false;

        object rawArgs;
        IDictionary args = null;
        if (msg.TryGetValue("args", out rawArgs)) args = rawArgs as IDictionary;
        if (args != null)
        {
            if (args.Contains("interval"))
            {
                int parsed;
                if (int.TryParse(Convert.ToString(args["interval"], CultureInfo.InvariantCulture), out parsed)
                    && parsed > 0)
                    interval = parsed;
            }
            if (args.Contains("services") && args["services"] != null)
                services = Convert.ToString(args["services"], CultureInfo.InvariantCulture).Trim();
            mastodon = DictFlag(args, "mastodon", false);
        }

        // Never run two loops: reuse the live one if the state file still points at it.
        Dictionary<string, object> state = ReadWorkerState();
        int existingPid = StatePid(state);
        if (state != null && PidAlive(existingPid) && DictFlag(state, "running", false))
            return Json.Obj("ok", true, "already_running", true, "pid", existingPid);

        string repo = Path.GetDirectoryName(EnvPath());
        string logFile = WorkerLogPath();
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(logFile));
            string cmd = "worker --interval " + interval.ToString(CultureInfo.InvariantCulture);
            if (services.Length > 0) cmd += " --services " + services;
            if (mastodon) cmd += " --mastodon";

            File.AppendAllText(logFile,
                "\n" + new string('=', 60) + "\n[" +
                DateTime.Now.ToString("yyyy-MM-ddTHH:mm:ss", CultureInfo.InvariantCulture) +
                "] $ " + _cli + " " + cmd + "\n", new UTF8Encoding(false));

            var psi = new ProcessStartInfo
            {
                FileName = ResolveCli(_cli),
                Arguments = cmd,
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                WorkingDirectory = repo,
            };
            // Tell the worker where to write its state file, so the panel can
            // read it back regardless of the process CWD.
            psi.EnvironmentVariables["NOTIONHUB_WORKER_STATE"] = WorkerStatePath();

            var proc = new Process { StartInfo = psi, EnableRaisingEvents = true };
            // Stream to the log file: a long-running worker would otherwise
            // block forever once its redirected pipe filled up.
            proc.OutputDataReceived += (s, e) => { if (e.Data != null) AppendWorkerLog(logFile, e.Data); };
            proc.ErrorDataReceived += (s, e) => { if (e.Data != null) AppendWorkerLog(logFile, e.Data); };
            proc.Start();
            proc.BeginOutputReadLine();
            proc.BeginErrorReadLine();
            lock (Workers) Workers.Add(proc);

            return Json.Obj("ok", true, "started", true, "pid", proc.Id,
                            "interval", interval,
                            "services", services.Length > 0 ? services : "all",
                            "mastodon", mastodon, "log", logFile);
        }
        catch (Exception ex)
        {
            Log("worker start failed: " + ex);
            return Json.Err("start_failed: " + ex.Message);
        }
    }

    private static string HandleWorkerStop()
    {
        Dictionary<string, object> state = ReadWorkerState();
        int pid = StatePid(state);
        if (state == null || pid == 0 || !PidAlive(pid))
            return Json.Obj("ok", true, "stopped", false, "message", "Worker 未运行");

        try
        {
            // /T kills the whole tree: the CLI wrapper spawns python.exe.
            var psi = new ProcessStartInfo
            {
                FileName = "taskkill",
                Arguments = "/PID " + pid.ToString(CultureInfo.InvariantCulture) + " /T /F",
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
            };
            using (Process p = Process.Start(psi))
            {
                if (p != null) p.WaitForExit(5000);
            }
        }
        catch (Exception ex)
        {
            Log("worker stop failed: " + ex.Message);
            return Json.Err("stop_failed: " + ex.Message);
        }

        lock (Workers)
        {
            for (int i = Workers.Count - 1; i >= 0; i--)
            {
                if (Workers[i].Id != pid) continue;
                try { Workers[i].Close(); } catch { /* already gone */ }
                Workers.RemoveAt(i);
            }
        }
        return Json.Obj("ok", true, "stopped", true);
    }

    private static string HandleWorkerStatus()
    {
        Dictionary<string, object> state = ReadWorkerState();
        if (state == null) return Json.Obj("ok", true, "running", false, "state", null);
        bool alive = PidAlive(StatePid(state)) && DictFlag(state, "running", false);
        return Json.Obj("ok", true, "running", alive, "state", state);
    }

    // ---------------- helpers ----------------

    private static void Log(string message)
    {
        try
        {
            string repo = Path.GetDirectoryName(EnvPath());
            string logFile = Path.Combine(repo, "logs", "host.log");
            Directory.CreateDirectory(Path.GetDirectoryName(logFile));
            File.AppendAllText(logFile,
                "[" + DateTime.Now.ToString("yyyy-MM-ddTHH:mm:ss", CultureInfo.InvariantCulture) +
                "] pid=" + Process.GetCurrentProcess().Id + " " + message + "\n");
        }
        catch { /* diagnostics must never break the host */ }
    }
}
