"use strict";
/* NotionHub control panel (wide window). 5 tabs: Sync / Account / Notify / Storage / About. */
const NOTION_API = "https://api.notion.com/v1";
const NOTION_VERSION = "2022-06-28";

function escapeHtml(value) {
  return String(value || "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

function toast(message, type = "info") {
  const el = document.createElement("div");
  el.className = "toast " + type;
  el.textContent = String(message || "");
  document.body.appendChild(el);
  requestAnimationFrame(() => el.classList.add("show"));
  setTimeout(() => {
    el.classList.add("hide");
    el.addEventListener("transitionend", () => el.remove(), { once: true });
    setTimeout(() => el.remove(), 300);
  }, 3000);
}

function renderGrid() {
  const q = (els.search.value || "").trim().toLowerCase();
  const cat = els.filterCategory.value || "";
  const filtered = PLUGINS.filter((p) => {
    if (cat && p.category !== cat) return false;
    if (q && !p.name.toLowerCase().includes(q) && !p.desc.toLowerCase().includes(q)) return false;
    return true;
  });
  els.grid.innerHTML = "";
  for (const p of filtered) {
    const card = document.createElement("div");
    card.className = "plugin-card";
    card.dataset.pluginId = p.id;
    card.setAttribute("role", "button");
    card.tabIndex = 0;
    const configured = pluginConfigured[p.id] === true;
    card.innerHTML =
      '<div class="icon">' + escapeHtml(p.icon) + '</div>' +
      '<div class="body">' +
      '<div class="head">' +
      '<span class="name">' + escapeHtml(p.name) + '</span>' +
      '<span class="category">' + escapeHtml(p.category) + '</span>' +
      '<span class="state' + (configured ? " ok" : "") + '">' +
      (configured ? "\u5df2\u914d\u7f6e" : "\u672a\u914d\u7f6e") + '</span>' +
      '</div>' +
      '<div class="desc">' + escapeHtml(p.desc) + '</div>' +
      '</div>' +
      '<div class="actions">' +
      '<a class="docs" href="' + escapeHtml(p.docs) + '" target="_blank" rel="noopener">' +
      '\u4f7f\u7528\u6587\u6863 \u29c9</a>' +
      '<a class="arrow" href="' + escapeHtml(p.docs) + '" target="_blank" rel="noopener" title="Open docs">&rarr;</a>' +
      '</div>';
    card.addEventListener("click", (e) => {
      if (e.target.closest("a")) return;
      openDrawer(p);
    });
    card.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        openDrawer(p);
      }
    });
    els.grid.appendChild(card);
  }
  if (filtered.length === 0) {
    const empty = document.createElement("div");
    empty.className = "footer-hint";
    empty.style.gridColumn = "1 / -1";
    empty.textContent = "\u6ca1\u6709\u5339\u914d\u7684\u63d2\u4ef6\u3002";
    els.grid.appendChild(empty);
  }
}

/* ---------- Plugin config drawer ---------------------------------------- */

const STORAGE_KEYS = ["weread_api_key", "weread_notion_page", "weread_notion_token", "weread_start_year"];
const PAGE_ID_RE = /([a-f0-9]{32}|[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/i;

let currentPluginId = null;

/* Native bridge state: null = not probed yet, object = host info, false = unavailable. */
let nativeInfo = null;
let logTimer = null;

/* The panel is an extension page, so it can talk to the host directly - this
   bypasses the service worker and surfaces Chrome's real error text. */
function callNativeDirect(msg) {
  return new Promise((resolve) => {
    if (!chrome.runtime?.sendNativeMessage) {
      resolve(null);
      return;
    }
    try {
      chrome.runtime.sendNativeMessage("com.notionhub.host", msg, (response) => {
        const err = chrome.runtime.lastError;
        if (err) {
          resolve({ ok: false, error: String(err.message || err) });
        } else {
          resolve(response || { ok: false, error: "no_response" });
        }
      });
    } catch (err) {
      resolve({ ok: false, error: String(err) });
    }
  });
}

function nativeCall(msg) {
  return new Promise((resolve) => {
    try {
      chrome.runtime.sendMessage(msg, (r) => resolve(r || { ok: false, error: "no_response" }));
    } catch (err) {
      resolve({ ok: false, error: String(err) });
    }
  });
}

/* Host protocol and background-relay protocol use different type names but the
   same payload keys, so the relay message is derived from the host message. */
async function nativeRequest(hostMsg, bgType) {
  const direct = await callNativeDirect(hostMsg);
  if (direct && direct.ok) return direct;
  const bgMsg = Object.assign({}, hostMsg, { type: bgType });
  const relayed = await nativeCall(bgMsg);
  if (relayed && relayed.ok) return relayed;
  return direct || relayed || { ok: false, error: "no_response" };
}

function setNativeStatus(text, kind, title) {
  els.cfgNativeStatus.textContent = text;
  els.cfgNativeStatus.className = "status-pill" + (kind ? " " + kind : "");
  if (title) els.cfgNativeStatus.title = title;
}

async function probeNative() {
  const reply = await nativeRequest({ type: "ping" }, "notionhub_native_ping");
  if (reply && reply.ok) {
    nativeInfo = reply;
    setNativeStatus("本机桥接：已连接", "ok", reply.env_file || "");
    els.cfgNativeRaw.hidden = true;
    els.cfgEnvPath.textContent = reply.env_file ? reply.env_file : "";
    els.cfgWriteEnv.disabled = false;
    els.cfgRunSync.disabled = false;
    return true;
  }
  nativeInfo = false;
  const reason = (reply && reply.error) || "unknown";
  let hint;
  if (reason === "no_response") {
    hint = "本机桥接未安装或扩展 ID 不匹配，请重跑 native\\install.ps1";
  } else if (/not found/i.test(reason)) {
    hint = "找不到宿主，请重跑 native\\install.ps1（注册表未生效）";
  } else if (/forbidden|not allowed/i.test(reason)) {
    hint = "扩展 ID 未被授权，请重跑 native\\install.ps1 更新 allowed_origins";
  } else if (/access is denied/i.test(reason)) {
    hint = "Edge 拒绝启动宿主（access denied）。确认 native\\NotionHubBridge.exe 存在且未被杀软拦截，并重跑 native\\install.ps1";
  } else {
    hint = "桥接不可用：" + reason;
  }
  setNativeStatus(hint, "warn", hint + "\n\n[raw] " + reason);
  els.cfgNativeRaw.hidden = false;
  els.cfgNativeRaw.textContent = "[raw] " + reason;
  els.cfgEnvPath.textContent = "";
  els.cfgWriteEnv.disabled = true;
  els.cfgRunSync.disabled = true;
  return false;
}

async function writeEnvFile() {
  const error = validateWereadConfig();
  if (error) {
    setCfgStatus(error, "err");
    return false;
  }
  setCfgStatus("正在写入 .env…", null);
  const reply = await nativeRequest({
    type: "env_write",
    values: {
      WEREAD_API_KEY: (els.cfgWereadKey.value || "").trim(),
      NOTION_TOKEN: (els.cfgNotionToken.value || "").trim(),
      NOTION_PAGE: (els.cfgNotionPage.value || "").trim(),
      START_YEAR: (els.cfgStartYear.value || "2023").trim(),
    },
  }, "notionhub_env_write");
  if (!reply || !reply.ok) {
    setCfgStatus("写入失败：" + ((reply && reply.error) || "unknown"), "err");
    return false;
  }
  setCfgStatus("已写入 " + reply.path, "ok");
  return true;
}

async function refreshSyncLog() {
  const reply = await nativeRequest({ type: "sync_log", lines: 200 }, "notionhub_sync_log");
  if (reply && reply.ok) {
    els.cfgSyncLog.textContent = reply.log || "（日志为空）";
  }
}

async function startNativeSync() {
  setCfgStatus("正在启动同步…", null);
  const reply = await nativeRequest({ type: "sync_start", args: ["--quiet"] }, "notionhub_sync_start");
  if (!reply || !reply.ok) {
    setCfgStatus("启动失败：" + ((reply && reply.error) || "unknown"), "err");
    return;
  }
  setCfgStatus("同步已启动（PID " + reply.pid + "）", "ok");
  await refreshSyncLog();
  if (logTimer) clearInterval(logTimer);
  logTimer = setInterval(refreshSyncLog, 3000);
}

// 向本仓库的 GitHub Actions 发送 workflow_dispatch 触发信号（自托管同步）。
// weread 走 weread.yml，其余数据源走 sync.yml —— 与仓库 action.yml 一一对应。
async function startCloudSync(service) {
  service = service || "weread";
  setCfgStatus("正在向 GitHub Actions 发送触发信号…", null);
  const reply = await new Promise((res) => chrome.runtime.sendMessage(
    { type: "github_trigger_sync", service, inputs: { reason: "manual", sync_mode: "incremental" } }, res));
  if (!reply || !reply.ok) {
    const hint = reply && reply.hint ? "（" + reply.hint + "）" : "";
    const detail = (reply && reply.data && JSON.stringify(reply.data)) || (reply && reply.reason) || "unknown";
    setCfgStatus("触发失败：" + detail + hint, "err");
    return;
  }
  const runId = reply.run_id;
  const wfName = reply.workflow || "sync.yml";
  setCfgStatus("已触发 " + wfName + " 运行 #" + runId + "，等待结果…", "ok");
  if (els.cfgSyncLog) els.cfgSyncLog.textContent = "GitHub Actions 运行：" + (reply.html_url || "（无链接）");
  // 轮询运行状态
  const timer = setInterval(async () => {
    const st = await new Promise((res) => chrome.runtime.sendMessage(
      { type: "github_get_run", runId }, res));
    if (!st || !st.ok) { clearInterval(timer); setCfgStatus("状态查询失败", "err"); return; }
    if (st.status === "completed") {
      clearInterval(timer);
      const ok = st.conclusion === "success";
      setCfgStatus(ok ? "✅ 自托管同步完成" : "❌ 自托管同步失败（" + st.conclusion + "）", ok ? "ok" : "err");
      if (els.cfgSyncLog) els.cfgSyncLog.textContent += "\n结论：" + st.conclusion;
    } else {
      setCfgStatus("GitHub Actions 运行中（" + st.status + "）…", null);
    }
  }, 4000);
}

function stopLogPolling() {
  if (logTimer) {
    clearInterval(logTimer);
    logTimer = null;
  }
}

function maskSecret(value) {
  const v = value || "";
  if (v.length <= 8) return v ? "****" : "";
  return v.slice(0, 4) + "****" + v.slice(-4);
}

function buildEnvText() {
  const lines = [
    "WEREAD_API_KEY=" + (els.cfgWereadKey.value || "").trim(),
    "NOTION_TOKEN=" + (els.cfgNotionToken.value || "").trim(),
    "NOTION_PAGE=" + (els.cfgNotionPage.value || "").trim(),
    "START_YEAR=" + (els.cfgStartYear.value || "2023").trim(),
  ];
  return lines.join("\n") + "\n";
}

function renderEnvPreview() {
  if (!els.cfgEnvPreview) return;
  const preview = [
    "WEREAD_API_KEY=" + (maskSecret(els.cfgWereadKey.value) || "<\u5f85\u586b\u5199>"),
    "NOTION_TOKEN=" + (maskSecret(els.cfgNotionToken.value) || "<\u5f85\u586b\u5199>"),
    "NOTION_PAGE=" + (els.cfgNotionPage.value.trim() || "<\u5f85\u586b\u5199>"),
    "START_YEAR=" + (els.cfgStartYear.value || "2023"),
  ];
  els.cfgEnvPreview.textContent = preview.join("\n");
}

function updateWereadState() {
  if (!els.cfgWereadState) return;
  const ok = !!(els.cfgWereadKey.value || "").trim();
  els.cfgWereadState.textContent = ok ? "\u5df2\u914d\u7f6e" : "\u5f85\u914d\u7f6e";
  els.cfgWereadState.className = "status-pill" + (ok ? " ok" : "");
}

function setCfgStatus(text, kind) {
  els.cfgStatus.textContent = text || "";
  els.cfgStatus.className = "status-pill" + (kind ? " " + kind : "");
}

function setTplStatus(text, kind) {
  if (!els.cfgTplStatus) return;
  els.cfgTplStatus.textContent = text || "";
  els.cfgTplStatus.className = "status-pill" + (kind ? " " + kind : "");
}

// 通过 background.js 调用 Notion API 校验页面是否为标准模板，并把结果显示在配置区。
async function verifyTemplateAndReport(page, token) {
  setTplStatus("校验中…", null);
  let reply;
  try {
    reply = await new Promise((res) => chrome.runtime.sendMessage(
      { type: "notionhub_verify_template", pageUrl: page, token }, res));
  } catch (e) {
    setTplStatus("校验调用失败：" + String(e.message || e), "err");
    return;
  }
  if (!reply || !reply.ok) {
    const msg = (reply && reply.message) || "";
    // Notion 的“未共享给集成”报错最常见，翻译成明确操作指引
    if ((reply && reply.reason === "not_shared") ||
        /shared\s+with\s+your\s+integration|object_not_found|restricted/i.test(msg)) {
      setTplStatus("❌ NotionHub 看不到这个页面。请在 Notion 里打开它 → 右上角 ••• → Connections → 添加 NotionHub 集成，再重新校验。", "err");
      return;
    }
    if (reply && reply.reason === "no_token") {
      setTplStatus("❌ 缺少 Notion Token，请先填好第 3 步的 Integration Token。", "err");
      return;
    }
    if (reply && reply.reason === "invalid_url") {
      setTplStatus("❌ 页面 URL 里没有有效的 32 位 Notion 页面 ID。", "err");
      return;
    }
    setTplStatus("校验失败：" + (msg || (reply && reply.reason) || "未知错误"), "err");
    return;
  }
  if (reply.valid) {
    setTplStatus("✅ 这是标准模板，含全部 7 个必需数据库", "ok");
  } else {
    setTplStatus("❌ 不是标准模板，缺少：" + reply.missing.join("、") + "。请重新 Duplicate 官方模板 3a329aff", "err");
  }
}

/* ---------- 通用第三方平台授权 -------------------------------------- */

function escapeHtml(s) {
  return String(s || "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

function setCredStatus(text, kind) {
  if (!els.credStatus) return;
  els.credStatus.textContent = text || "";
  els.credStatus.className = "status-pill" + (kind ? " " + kind : "");
}

// 依据插件声明的 credentials 自动生成授权表单
function renderCredForm(pluginId) {
  if (!els.credForm) return;
  const specs = PLUGIN_CREDENTIALS[pluginId] || [];
  if (!specs.length) { els.credForm.innerHTML = ""; return; }
  els.credForm.innerHTML = specs
    .map((s) => {
      const inputType = s.secret === false && s.cred_type !== "file" ? "text" : "password";
      const ph = s.cred_type === "file"
        ? "例如 C:\\exports\\data.json"
        : s.cred_type === "urls"
          ? "https://a.com/feed.xml,https://b.com/rss"
          : "在此粘贴" + (CRED_TYPE_LABEL[s.cred_type] || "内容");
      return (
        '<div class="cred-field">' +
        '<label for="cred-' + escapeHtml(s.env_key) + '">' +
        escapeHtml(s.label) +
        ' <span class="cred-type">' + escapeHtml(CRED_TYPE_LABEL[s.cred_type] || s.cred_type) + "</span>" +
        (s.required === false ? ' <span class="cred-opt">可选</span>' : "") +
        "</label>" +
        '<input id="cred-' + escapeHtml(s.env_key) + '" data-env="' + escapeHtml(s.env_key) +
        '" type="' + inputType + '" placeholder="' + escapeHtml(ph) +
        '" autocomplete="off" spellcheck="false">' +
        (s.hint ? '<p class="hint">' + escapeHtml(s.hint) + "</p>" : "") +
        "</div>"
      );
    })
    .join("");
}

// 把 .env 中已有值回填到表单，避免每次重填
async function loadCredValues(specs) {
  if (!nativeInfo || !specs.length) return;
  const reply = await nativeRequest({ type: "env_read" }, "notionhub_env_read");
  if (!reply || !reply.ok || !reply.values) return;
  for (const s of specs) {
    const el = document.getElementById("cred-" + s.env_key);
    if (el) el.value = reply.values[s.env_key] || "";
  }
}

// 保存：写入 chrome.storage + .env，并逐个做本地校验
async function saveCreds(pluginId) {
  const specs = PLUGIN_CREDENTIALS[pluginId] || [];
  if (!specs.length) return;
  const payload = {};
  for (const s of specs) {
    const el = document.getElementById("cred-" + s.env_key);
    if (el) payload[s.env_key] = (el.value || "").trim();
  }
  await storageSet({ ["creds_" + pluginId]: payload });

  if (!nativeInfo) {
    setCredStatus("已存到浏览器（未安装桥接，无法写入 .env）", "warn");
    return;
  }
  const reply = await nativeRequest(
    { type: "env_write", values: payload }, "notionhub_env_write");
  if (!reply || !reply.ok) {
    setCredStatus("写入 .env 失败：" + ((reply && reply.error) || "unknown"), "err");
    return;
  }

  // 本地校验：文件路径是否存在、URL 格式、Cookie 形态
  const bad = [];
  for (const s of specs) {
    const v = payload[s.env_key] || "";
    if (!v) {
      if (s.required !== false) bad.push(s.label + "（未填写）");
      continue;
    }
    let ok = true;
    if (s.cred_type === "file") ok = true; // 路径存在性由 CLI/面板无法判定（本机 vs runner）
    else if (s.cred_type === "urls") {
      const items = v.split(",").map((x) => x.trim()).filter(Boolean);
      ok = items.length > 0 && items.every((u) => u.startsWith("http"));
    } else if (s.cred_type === "cookie" || s.cred_type === "qrcode") {
      ok = v.includes("=") && v.length >= 16;
    } else ok = v.length >= 8;
    if (!ok) bad.push(s.label);
  }
  if (bad.length) setCredStatus("已写入，但需检查：" + bad.join("、"), "warn");
  else setCredStatus("✅ 已写入 " + reply.path, "ok");
  renderGrid();
}

/* 监听后台转发来的「扫码登录已捕获 API Key」，自动回填并写盘。
 * 桥接写入发生在 background 侧，这里只负责把 UI 同步到最新值。 */
function registerWereadKeyListener() {
  if (!chrome.runtime || !chrome.runtime.onMessage) return;
  chrome.runtime.onMessage.addListener((msg) => {
    if (!msg || msg.type !== "weread_key_filled") return;
    const key = msg.key || "";
    if (els.cfgWereadKey) {
      els.cfgWereadKey.value = key;
      updateWereadState();
      renderEnvPreview();
    }
    pluginConfigured.weread = !!(
      key && els.cfgNotionToken.value.trim() && els.cfgNotionPage.value.trim()
    );
    renderGrid();
    setCfgStatus("已自动填入微信读书 API Key 并写入 .env", "ok");
  });
}

function openDrawer(plugin) {
  currentPluginId = plugin.id;
  els.drawerIcon.textContent = plugin.icon;
  els.drawerTitle.textContent = plugin.name;
  els.drawerDesc.textContent = plugin.desc;
  els.drawerDocs.href = plugin.docs;
  const supported = plugin.id === "weread";
  els.drawerBody.classList.toggle("unsupported", !supported);
  els.drawerNotice.hidden = supported;
  if (!supported) {
    els.drawerNotice.textContent =
      "\u8be5\u63d2\u4ef6\u7684\u540c\u6b65\u903b\u8f91\u5c1a\u672a\u5728\u672c\u673a\u5b9e\u73b0\uff0c" +
      "\u53ef\u5148\u5b8c\u6210\u4e0b\u65b9\u300c\u7b2c\u4e09\u65b9\u5e73\u53f0\u6388\u6743\u300d\uff0c" +
      "\u51ed\u8bc1\u4f1a\u5199\u5165 .env \u4f9b\u4e91\u7aef / \u540e\u7eed\u540c\u6b65\u4f7f\u7528\u3002";
  }
  // 通用授权表单：weread 走专用四步配置，其余插件用凭据表单
  const specs = PLUGIN_CREDENTIALS[plugin.id] || [];
  const showCreds = !supported && specs.length > 0;
  if (els.credPanel) els.credPanel.hidden = !showCreds;
  if (showCreds) {
    renderCredForm(plugin.id);
    setCredStatus("", null);
    loadCredValues(specs);
  }
  setCfgStatus("", null);
  updateWereadState();
  renderEnvPreview();
  if (supported && nativeInfo) refreshSyncLog();
  els.drawerOverlay.hidden = false;
}

function closeDrawer() {
  els.drawerOverlay.hidden = true;
  currentPluginId = null;
  stopLogPolling();
}

async function loadWereadConfig() {
  const data = await storageGet(STORAGE_KEYS);
  let key = data.weread_api_key || "";
  let page = data.weread_notion_page || "";
  let token = data.weread_notion_token || "";
  let year = data.weread_start_year || "2023";

  // The .env is what the CLI actually reads, so prefer it when the panel is empty.
  if (nativeInfo) {
    const reply = await nativeRequest({ type: "env_read" }, "notionhub_env_read");
    if (reply && reply.ok && reply.values) {
      key = key || reply.values.WEREAD_API_KEY || "";
      page = page || reply.values.NOTION_PAGE || "";
      token = token || reply.values.NOTION_TOKEN || "";
      year = (data.weread_start_year || reply.values.START_YEAR || "2023");
    }
  }

  els.cfgWereadKey.value = key;
  els.cfgNotionPage.value = page;
  els.cfgNotionToken.value = token;
  els.cfgStartYear.value = year;
  pluginConfigured.weread = !!(key && token && page);
  updateWereadState();
  renderEnvPreview();
}

function validateWereadConfig() {
  const page = (els.cfgNotionPage.value || "").trim();
  const token = (els.cfgNotionToken.value || "").trim();
  if (page && !PAGE_ID_RE.test(page)) {
    return "NOTION_PAGE \u5fc5\u987b\u662f Notion \u9875\u9762\u94fe\u63a5\u6216\u9875\u9762 ID";
  }
  if (token && token.length < 20 && !(token.startsWith("ntn_") || token.startsWith("secret_"))) {
    return "NOTION_TOKEN \u5e94\u4ee5 ntn_ \u6216 secret_ \u5f00\u5934";
  }
  return null;
}

async function saveWereadConfig() {
  const error = validateWereadConfig();
  if (error) {
    setCfgStatus(error, "err");
    return false;
  }
  const payload = {
    weread_api_key: (els.cfgWereadKey.value || "").trim(),
    weread_notion_page: (els.cfgNotionPage.value || "").trim(),
    weread_notion_token: (els.cfgNotionToken.value || "").trim(),
    weread_start_year: (els.cfgStartYear.value || "2023").trim(),
  };
  await storageSet(payload);
  pluginConfigured.weread = !!(
    payload.weread_api_key && payload.weread_notion_token && payload.weread_notion_page
  );
  updateWereadState();
  renderEnvPreview();
  renderGrid();
  // When the bridge is installed, keep the .env in sync automatically.
  if (nativeInfo) {
    const reply = await nativeRequest({
      type: "env_write",
      values: {
        WEREAD_API_KEY: payload.weread_api_key,
        NOTION_TOKEN: payload.weread_notion_token,
        NOTION_PAGE: payload.weread_notion_page,
        START_YEAR: payload.weread_start_year,
      },
    }, "notionhub_env_write");
    if (!reply || !reply.ok) {
      setCfgStatus("\u5df2\u4fdd\u5b58\u5230\u6d4f\u89c8\u5668\uff0c.env \u5199\u5165\u5931\u8d25\uff1a" + ((reply && reply.error) || "unknown"), "warn");
      return true;
    }
    setCfgStatus("\u5df2\u4fdd\u5b58\u5e76\u5199\u5165 " + reply.path, "ok");
    return true;
  }
  setCfgStatus("\u5df2\u4fdd\u5b58\u5230\u6d4f\u89c8\u5668\uff08\u672a\u5b89\u88c5\u6865\u63a5\uff09", "warn");
  // 保存后立即 best-effort 校验模板页结构，避免填错页而同步时才发现
  if (payload.weread_notion_page) {
    verifyTemplateAndReport(payload.weread_notion_page, payload.weread_notion_token);
  }
  return true;
}

function switchTab(tab) {
  els.tabs.forEach((t) => {
    t.classList.toggle("active", t.dataset.tab === tab);
  });
  els.panes.forEach((p) => {
    p.classList.toggle("active", p.id === "tab-" + tab);
  });
  const meta = TAB_META[tab];
  els.tabTitle.textContent = meta.title;
  els.tabSubtitle.textContent = meta.subtitle;
  if (location.hash !== "#" + tab) {
    history.replaceState(null, "", "#" + tab);
  }
  if (tab === "storage") renderStorageGate();
  if (tab === "worker") refreshWorkerStatus();
}

async function copy(text) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch (e) {
    /* fall through */
  }
  const ta = document.createElement("textarea");
  ta.value = text;
  document.body.appendChild(ta);
  ta.select();
  document.execCommand("copy");
  document.body.removeChild(ta);
  return true;
}


/* 第三方平台授权方式。与 src/weread2notion/credentials.py 的 PLUGIN_CREDENTIALS
 * 保持一致：env_key 决定写入 .env 的键名，cred_type 决定输入框类型与提示。 */
const CRED_TYPE_LABEL = {
  api_key: "API Key / Token",
  cookie: "Cookie",
  oauth: "OAuth Token",
  qrcode: "扫码凭证 / Cookie",
  file: "本地导出文件",
  urls: "URL 列表",
};

const PLUGIN_CREDENTIALS = {
  weread: [{ env_key: "WEREAD_API_KEY", label: "微信读书 Gateway API Key", cred_type: "api_key", hint: "以 wrk- 开头（连字符），从微信读书 Gateway 获取。" }],
  toggl: [{ env_key: "TOGGL_API_TOKEN", label: "Toggl API Token", cred_type: "api_key", hint: "Toggl 网页版 → 个人设置 → API Token。" }],
  trakt: [
    { env_key: "TRAKT_CLIENT_ID", label: "Trakt Client ID", cred_type: "api_key", hint: "Trakt 应用设置里的 Client ID。" },
    { env_key: "TRAKT_TOKEN", label: "Trakt Access Token", cred_type: "oauth", hint: "OAuth 授权后获得的 access token。" },
  ],
  github: [{ env_key: "GH_TOKEN", label: "GitHub Token", cred_type: "oauth", hint: "Personal Access Token（需 repo / read:user），或在「账号」页绑定 GitHub。" }],
  bilibili: [{ env_key: "BILIBILI_COOKIE", label: "B 站 Cookie", cred_type: "cookie", hint: "登录 bilibili 后，从 DevTools → Application → Cookies 复制整条 Cookie。" }],
  douban: [{ env_key: "DOUBAN_COOKIE", label: "豆瓣 Cookie", cred_type: "cookie", hint: "登录 douban.com 后复制整条 Cookie（含 dbcl2）。" }],
  douyin: [
    { env_key: "DOUYIN_COOKIE", label: "抖音 Cookie / 扫码凭证", cred_type: "qrcode", hint: "手机抖音扫码登录后导出，或手动复制 Cookie。" },
    { env_key: "DOUYIN_EXPORT", label: "抖音导出文件路径", cred_type: "file", hint: "导出 JSON 的绝对路径。", required: false, secret: false },
  ],
  youtube: [
    { env_key: "YOUTUBE_EXPORT", label: "YouTube 导出文件路径", cred_type: "file", hint: "Google Takeout / yt-dlp 导出的 JSON 路径。", required: false, secret: false },
    { env_key: "YOUTUBE_API_KEY", label: "YouTube Data API Key", cred_type: "api_key", hint: "在线拉取时需填 Google Cloud API Key。", required: false },
  ],
  flomo: [{ env_key: "FLOMO_EXPORT", label: "Flomo 导出文件路径", cred_type: "file", hint: "Flomo 网页端导出的 JSON 路径。", secret: false }],
  telegram: [{ env_key: "TELEGRAM_EXPORT", label: "Telegram 导出 result.json 路径", cred_type: "file", hint: "Telegram Desktop 导出后的 result.json。", secret: false }],
  keep: [{ env_key: "KEEP_EXPORT", label: "Keep 导出文件路径", cred_type: "file", hint: "Google Takeout 中 Keep 的 JSON 路径。", secret: false }],
  forest: [{ env_key: "FOREST_EXPORT", label: "Forest 导出文件路径", cred_type: "file", hint: "Forest 导出的 CSV / JSON 路径。", secret: false }],
  ticktick: [{ env_key: "TICKTICK_EXPORT", label: "滴答清单导出文件路径", cred_type: "file", hint: "滴答清单导出的 CSV 路径。", secret: false }],
  duolingo: [{ env_key: "DUOLINGO_EXPORT", label: "多邻国导出文件路径", cred_type: "file", hint: "多邻国数据导出的 JSON 路径。", secret: false }],
  dayone: [{ env_key: "DAYONE_EXPORT", label: "Day One 导出文件路径", cred_type: "file", hint: "Day One 导出的 JSON 路径。", secret: false }],
  gutu: [{ env_key: "GUTU_EXPORT", label: "古文岛导出文件路径", cred_type: "file", hint: "古文岛导出的 JSON 路径。", secret: false }],
  netease: [{ env_key: "NETEASE_PLAYLIST", label: "网易云歌单 JSON 路径", cred_type: "file", hint: "网易云音乐歌单导出的 JSON 路径。", secret: false }],
  applemusic: [{ env_key: "APPLEMUSIC_EXPORT", label: "Apple Music 导出文件路径", cred_type: "file", hint: "Apple Music 资料库导出的 JSON 路径。", secret: false }],
  beidanci: [{ env_key: "BEIDANCI_EXPORT", label: "百词斩导出文件路径", cred_type: "file", hint: "百词斩导出的 JSON 路径。", secret: false }],
  rss: [{ env_key: "RSS_FEEDS", label: "RSS 订阅地址", cred_type: "urls", hint: "多个 feed 用英文逗号分隔。", secret: false }],
  xiaoyuzhou: [{ env_key: "XIAOYUZHOU_FEEDS", label: "小宇宙播客 feed 地址", cred_type: "urls", hint: "多个播客 RSS 用英文逗号分隔。", secret: false }],
};

const PLUGINS = [
  {
    id: "weread",
    name: "WeRead",
    icon: "\uD83D\uDCD6",
    category: "\u9605\u8bfb",
    desc: "微信读书笔记、划线、章节感想自动同步到 Notion，自动清理移出书架的书。",
    docs: "https://github.com/wslh/NotionHub#weread",
  },
  {
    id: "flomo",
    name: "Flomo",
    icon: "\uD83D\uDCA1",
    category: "\u7b14\u8bb0",
    desc: "Flomo 笔记自动同步到 Notion，支持 JSON 导出。",
    docs: "https://github.com/wslh/NotionHub#flomo",
  },
  {
    id: "github",
    name: "GitHub Stars",
    icon: "\u2B50",
    category: "\u6548\u7387",
    desc: "GitHub Star 仓库、作者和 Lists 分类自动同步到 Notion。",
    docs: "https://github.com/wslh/NotionHub#github",
  },
  {
    id: "rss",
    name: "RSS Feeds",
    icon: "\uD83D\uDCE1",
    category: "\u5176\u4ed6",
    desc: "任意 RSS/Atom 订阅源自动同步到 Notion，按 GUID 去重。",
    docs: "https://github.com/wslh/NotionHub#rss",
  },
  {
    id: "douban",
    name: "Douban",
    icon: "\uD83D\uDCD6",
    category: "\u9605\u8bfb",
    desc: "豆瓣公开书单（无需登录）自动同步到 Notion，含评分/标签/简介。",
    docs: "https://github.com/wslh/NotionHub#douban",
  },
  {
    id: "telegram",
    name: "Telegram Saved",
    icon: "\uD83D\uDCAC",
    category: "\u7b14\u8bb0",
    desc: "Telegram Saved Messages 导出 JSON 自动同步到 Notion。",
    docs: "https://github.com/wslh/NotionHub#telegram",
  },
  {
    id: "netease",
    name: "NetEase Playlist",
    icon: "\uD83C\uDFB5",
    category: "\u5f71\u97f3",
    desc: "网易云音乐歌单（JSON 导出）自动同步到 Notion。",
    docs: "https://github.com/wslh/NotionHub#netease",
  },
  {
    id: "xiaoyuzhou",
    name: "小宇宙",
    icon: "\u{1F680}",
    category: "播客",
    desc: "小宇宙播客收记、收听时长自动同步到 Notion，自动生成 AI 语音文本、生成脑图、并自动同步",
    docs: "https://github.com/wslh/NotionHub#xiaoyuzhou",
  },

  {
    id: "keep",
    name: "Keep",
    icon: "\u{1F3C3}",
    category: "运动",
    desc: "Keep 运动记录、前深体重、身体数据、历史记录自动同步到 Notion。",
    docs: "https://github.com/wslh/NotionHub#keep",
  },

  {
    id: "toggl",
    name: "Toggl",
    icon: "\u{1F3AF}",
    category: "效率",
    desc: "Toggl 时间追踪记录自动同步到 Notion。",
    docs: "https://github.com/wslh/NotionHub#toggl",
  },

  {
    id: "forest",
    name: "Forest",
    icon: "\u{1F333}",
    category: "效率",
    desc: "Forest 专注时间、种植记录自动同步到 Notion。",
    docs: "https://github.com/wslh/NotionHub#forest",
  },

  {
    id: "applemusic",
    name: "Apple Music",
    icon: "\u{1F3B5}",
    category: "影音",
    desc: "Apple Music 听歌记录自动同步到 Notion。",
    docs: "https://github.com/wslh/NotionHub#applemusic",
  },

  {
    id: "douyin",
    name: "抖音",
    icon: "\u{1F4AC}",
    category: "影音",
    desc: "抖音发布、收藏、点赞视频和图集自动同步到 Notion，可按需开启大文件上传。",
    docs: "https://github.com/wslh/NotionHub#douyin",
  },

  {
    id: "youtube",
    name: "YouTube",
    icon: "\u{1F525}",
    category: "影音",
    desc: "YouTube 频道、播放列表、赞过的视频自动同步到 Notion。",
    docs: "https://github.com/wslh/NotionHub#youtube",
  },

  {
    id: "gutu",
    name: "古文岛",
    icon: "\u{1F4DD}",
    category: "学习",
    desc: "古文岛诗文、作者、收藏、诗单、标注和背诵记录自动同步到 Notion。",
    docs: "https://github.com/wslh/NotionHub#gutu",
  },

  {
    id: "trakt",
    name: "Trakt",
    icon: "\u{2728}",
    category: "影音",
    desc: "自动将 Trakt 的电影、剧集、单集观看历史同步到 Notion。",
    docs: "https://github.com/wslh/NotionHub#trakt",
  },

  {
    id: "dayone",
    name: "生成日记",
    icon: "\u{1F4D4}",
    category: "效率",
    desc: "汇总当天的阅读、笔记、任务、运动、影音和时间记录，自动生成 Notion 日记。",
    docs: "https://github.com/wslh/NotionHub#dayone",
  },

  {
    id: "ticktick",
    name: "滴答清单",
    icon: "\u{2705}",
    category: "待办",
    desc: "滴答清单任务、习惯自动同步到 Notion。",
    docs: "https://github.com/wslh/NotionHub#ticktick",
  },

  {
    id: "duolingo",
    name: "多邻国",
    icon: "\u{1F426}",
    category: "学习",
    desc: "多邻国学习记录自动同步到 Notion。",
    docs: "https://github.com/wslh/NotionHub#duolingo",
  },

  {
    id: "bilibili",
    name: "B站",
    icon: "\u{1F4FA}",
    category: "影音",
    desc: "哔哩哔哩体验账号、后台追随、历史记录自动同步到 Notion。",
    docs: "https://github.com/wslh/NotionHub#bilibili",
  },

  {
    id: "beidanci",
    name: "不背单词",
    icon: "\u{1F4DA}",
    category: "学习",
    desc: "不背单词每日学习、授课、新学和复习记录自动同步到 Notion。",
    docs: "https://github.com/wslh/NotionHub#beidanci",
  },
];

/* plugin id -> boolean, filled from chrome.storage.local before first render. */
const pluginConfigured = {};

const els = {
  tabTitle: document.getElementById("tab-title"),
  tabSubtitle: document.getElementById("tab-subtitle"),
  search: document.getElementById("search"),
  filterCategory: document.getElementById("filter-category"),
  grid: document.getElementById("plugin-grid"),
  copySync: document.getElementById("copy-sync"),
  // Account tab
  notionAccountMeta: document.getElementById("notion-account-meta"),
  notionAccountHint: document.getElementById("notion-account-hint"),
  notionLoginBtn: document.getElementById("notion-login-btn"),
  notionAccountActions: document.getElementById("notion-account-actions"),
  githubAccountMeta: document.getElementById("github-account-meta"),
  githubAccountActions: document.getElementById("github-account-actions"),
  oauthClientId: document.getElementById("oauth-client-id"),
  oauthClientSecret: document.getElementById("oauth-client-secret"),
  oauthSave: document.getElementById("oauth-save"),
  oauthStatus: document.getElementById("oauth-status"),
  oauthRedirectUri: document.getElementById("oauth-redirect-uri"),
  // Notify tab
  notifyChannels: document.querySelectorAll(".notify-channel"),
  notifyBotToken: document.getElementById("bot-token"),
  notifyChatId: document.getElementById("chat-id"),
  notifySave: document.getElementById("notify-save"),
  notifyClear: document.getElementById("notify-clear"),
  notifyStatus: document.getElementById("notify-status"),
  copyBtns: document.querySelectorAll(".copy-btn"),
  // Storage tab
  storageGate: document.getElementById("storage-gate"),
  storageBody: document.getElementById("storage-body"),
  storageProviders: document.querySelectorAll(".storage-provider"),
  storageEndpoint: document.getElementById("storage-endpoint"),
  storageRegion: document.getElementById("storage-region"),
  storageBucket: document.getElementById("storage-bucket"),
  storageAccessKey: document.getElementById("storage-access-key"),
  storageSecretKey: document.getElementById("storage-secret-key"),
  storagePrefix: document.getElementById("storage-prefix"),
  storageCdnDomain: document.getElementById("storage-cdn-domain"),
  storageYoutube: document.getElementById("storage-youtube"),
  storageXiaohongshu: document.getElementById("storage-xiaohongshu"),
  storageDouyin: document.getElementById("storage-douyin"),
  storageSave: document.getElementById("storage-save"),
  storageClear: document.getElementById("storage-clear"),
  storageStatus: document.getElementById("storage-status"),
  // Misc
  openPopup: document.getElementById("open-popup"),
  tabs: document.querySelectorAll(".nav-item"),
  panes: document.querySelectorAll(".tab-pane"),
  // Plugin config drawer
  drawerOverlay: document.getElementById("drawer-overlay"),
  drawer: document.querySelector(".drawer"),
  drawerIcon: document.getElementById("drawer-icon"),
  drawerTitle: document.getElementById("drawer-title"),
  drawerDesc: document.getElementById("drawer-desc"),
  drawerDocs: document.getElementById("drawer-docs"),
  drawerClose: document.getElementById("drawer-close"),
  drawerBody: document.getElementById("drawer-body"),
  credPanel: document.getElementById("cred-panel"),
  credForm: document.getElementById("cred-form"),
  credSave: document.getElementById("cred-save"),
  credStatus: document.getElementById("cred-status"),
  drawerNotice: document.getElementById("drawer-notice"),
  cfgNotionPage: document.getElementById("cfg-notion-page"),
  cfgVerifyTpl: document.getElementById("cfg-verify-tpl"),
  cfgTplStatus: document.getElementById("cfg-tpl-status"),
  cfgWereadKey: document.getElementById("cfg-weread-key"),
  wereadScanLogin: document.getElementById("weread-scan-login"),
  cfgWereadState: document.getElementById("cfg-weread-state"),
  cfgNotionToken: document.getElementById("cfg-notion-token"),
  cfgStartYear: document.getElementById("cfg-start-year"),
  cfgEnvPreview: document.getElementById("cfg-env-preview"),
  cfgCopyEnv: document.getElementById("cfg-copy-env"),
  cfgWriteEnv: document.getElementById("cfg-write-env"),
  cfgNativeStatus: document.getElementById("cfg-native-status"),
  cfgNativeRaw: document.getElementById("cfg-native-raw"),
  cfgReprobe: document.getElementById("cfg-reprobe"),
  cfgEnvPath: document.getElementById("cfg-env-path"),
  cfgRunSync: document.getElementById("cfg-run-sync"),
  cfgRefreshLog: document.getElementById("cfg-refresh-log"),
  cfgSyncLog: document.getElementById("cfg-sync-log"),
  cfgStatus: document.getElementById("cfg-status"),
  cfgSave: document.getElementById("cfg-save"),
  cfgSync: document.getElementById("cfg-sync"),
  cfgActionsSync: document.getElementById("cfg-actions-sync"),
  githubSyncRepo: document.getElementById("github-sync-repo"),
  // Worker（长毛象）tab
  workerInterval: document.getElementById("worker-interval"),
  workerServices: document.getElementById("worker-services"),
  workerMastodon: document.getElementById("worker-mastodon"),
  workerMastodonInstance: document.getElementById("worker-mastodon-instance"),
  workerMastodonToken: document.getElementById("worker-mastodon-token"),
  workerMastodonSave: document.getElementById("worker-mastodon-save"),
  workerMastodonStatus: document.getElementById("worker-mastodon-status"),
  workerStart: document.getElementById("worker-start"),
  workerStop: document.getElementById("worker-stop"),
  workerRefresh: document.getElementById("worker-refresh"),
  workerStatusPill: document.getElementById("worker-status-pill"),
  workerDetail: document.getElementById("worker-detail"),
  eyeToggles: document.querySelectorAll(".eye-toggle"),
};;

const TAB_META = {
  sync: {
    title: "\u540c\u6b65\u670d\u52a1",
    subtitle: "\u9009\u62e9\u5df2\u914d\u7f6e\u7684\u6570\u636e\u6e90\uff0c\u70b9\u51fb\u300c\u4f7f\u7528\u6587\u6863\u300d\u67e5\u770b\u63a5\u5165\u6b65\u9aa4\u3002",
  },
  account: {
    title: "\u8d26\u53f7",
    subtitle: "\u4ee5 Notion OAuth \u767b\u5f55\u540e\u4f1a\u81ea\u52a8\u521b\u5efa\u4e2a\u4eba\u96c6\u6210\u5e76\u590d\u5236\u6a21\u677f\u5230\u4f60\u7684\u5de5\u4f5c\u7a7a\u95f4\u3002",
  },
  notify: {
    title: "\u901a\u77e5",
    subtitle: "\u9009\u62e9\u4e00\u4e2a\u540c\u6b65\u5b8c\u6210 / \u51fa\u9519\u540e\u63a5\u6536\u63d0\u9192\u7684\u5e73\u53f0\u3002",
  },
  storage: {
    title: "\u8d44\u6e90\u5b58\u50a8",
    subtitle: "\u914d\u7f6e\u81ea\u6709\u5bf9\u8c61\u5b58\u50a8\uff0c\u7528\u4e8e\u4e0a\u4f20 YouTube\u3001\u5c0f\u7ea2\u4e66\u7b49\u5a92\u4f53\u6587\u4ef6\u3002",
  },
  about: {
    title: "\u5173\u4e8e",
    subtitle: "NotionHub \u63d2\u4ef6\u4e0e Python CLI \u4fe1\u606f\u3002",
  },
  worker: {
    title: "Worker（长毛象）",
    subtitle: "本机常驻同步触发器，可把每轮结果播报到 Mastodon（长毛象）。",
  },
};

function setOauthStatus(text, kind) {
  els.accountStatus.textContent = text || "";
  els.accountStatus.className = "status-pill" + (kind ? " " + kind : "");
}

/* 凭据类配置只存本机：chrome.storage.sync 会随浏览器账号跨设备同步，
 * 把 Integration Token / API Key 扩散出去不符合最小权限原则。
 * 这些 key 无论谁调用 storageSet 都强制落到 local。 */
const SENSITIVE_KEYS = new Set([
  "weread_api_key",
  "weread_notion_token",
  "notion_token",
  "github_token",
  "github_oauth_client_id",
  "github_oauth_client_secret",
  "oauth_client_id",
  "oauth_client_secret",
]);

function splitBySensitivity(obj) {
  const local = {};
  const sync = {};
  for (const [k, v] of Object.entries(obj)) {
    if (SENSITIVE_KEYS.has(k)) local[k] = v;
    else sync[k] = v;
  }
  return { local, sync };
}

// 惰性迁移：早期版本把凭据也写进了 sync，这里搬到 local 并清掉 sync 中的副本。
async function migrateSensitiveFromSync(keys, fromSync) {
  const stale = keys.filter((k) => SENSITIVE_KEYS.has(k) && fromSync && fromSync[k] !== undefined);
  if (!stale.length) return;
  const patch = {};
  for (const k of stale) patch[k] = fromSync[k];
  await new Promise((resolve) => chrome.storage.local.set(patch, resolve));
  await new Promise((resolve) => chrome.storage.sync.remove(stale, resolve));
}

// 普通配置跨设备同步（sync），凭据只在本机（local）；读取时两侧合并，local 优先。
async function storageGet(keys) {
  const [fromSync, fromLocal] = await Promise.all([
    new Promise((resolve) => chrome.storage.sync.get(keys, resolve)),
    new Promise((resolve) => chrome.storage.local.get(keys, resolve)),
  ]);
  await migrateSensitiveFromSync(keys, fromSync);
  const merged = { ...(fromSync || {}) };
  for (const k of keys) {
    if (fromLocal && fromLocal[k] !== undefined) merged[k] = fromLocal[k];
  }
  return merged;
}

async function storageSet(obj) {
  const { local, sync } = splitBySensitivity(obj);
  if (Object.keys(local).length) {
    await new Promise((resolve) => chrome.storage.local.set(local, resolve));
  }
  if (!Object.keys(sync).length) return;
  try {
    return await new Promise((resolve, reject) => {
      chrome.storage.sync.set(sync, () => {
        if (chrome.runtime.lastError) reject(chrome.runtime.lastError);
        else resolve();
      });
    });
  } catch (e) {
    // sync 写入失败（配额/未登录同步）时回退 local，保证配置不丢失。
    return new Promise((resolve) => chrome.storage.local.set(sync, resolve));
  }
}

async function loadAccountFromStorage() {
  const data = await storageGet([
    "notion_token", "notion_oauth_workspace_name", "notion_workspace_name", "notion_oauth_login_at",
  ]);
  const renderNotion = (loggedIn) => {
    if (loggedIn) {
      const name = data.notion_oauth_workspace_name || data.notion_workspace_name || "Notion";
      const at = data.notion_oauth_login_at
        ? new Date(data.notion_oauth_login_at).toLocaleString()
        : "";
      const tmpl = data.notion_duplicated_template_id || "";
      els.notionAccountMeta.innerHTML =
        (at ? "<span class=\"muted-inline\">" + escapeHtml(at) + "</span><br>" : "") +
        "<b>" + escapeHtml(name) + "</b>" +
        (tmpl ? "<br><span class=\"muted-inline\">\u5df2\u590d\u5236\u6a21\u677f</span>" : "");
      if (els.notionAccountHint) els.notionAccountHint.hidden = true;
      els.notionAccountActions.innerHTML =
        '<a class="link-btn" href="https://www.notion.so/" target="_blank" rel="noopener" title="\u6253\u5f00\u4ed6\u4eec">\u2197</a>' +
        '<button id="notion-logout-btn" class="btn-secondary">\u9000\u51fa</button>';
      const btn = document.getElementById("notion-logout-btn");
      if (btn) btn.addEventListener("click", notionLogout);
    } else {
      els.notionAccountMeta.textContent = "\u672a\u767b\u5f55";
      if (els.notionAccountHint) els.notionAccountHint.hidden = false;
      els.notionAccountActions.innerHTML =
        '<button id="notion-login-btn" class="btn-primary">\u767b\u5f55\u8d26\u53f7</button>';
      const btn = document.getElementById("notion-login-btn");
      if (btn) btn.addEventListener("click", notionLogin);
    }
  };
  renderNotion(!!data.notion_token);
  const notionLoggedIn = !!data.notion_token;
  if (data.github_login) {
    els.githubAccountMeta.textContent = "\u5df2\u7ed1\u5b9a @" + data.github_login;
    els.githubAccountActions.innerHTML =
      '<a class="link-btn" href="https://github.com/" target="_blank" rel="noopener" title="\u6253\u5f00\u5916\u90e8\u94fe\u63a5">\u{1F517}</a>' +
      '<button id="github-logout-btn" class="btn-secondary">\u89e3\u7ed1</button>';
    const gh = document.getElementById("github-logout-btn");
    if (gh) gh.addEventListener("click", githubLogout);
  } else if (!notionLoggedIn) {
    els.githubAccountMeta.textContent = "\u8bf7\u5148\u767b\u5f55 Notion";
    els.githubAccountActions.innerHTML =
      '<button id="github-login-btn" class="btn-secondary" disabled>\u8fde\u63a5 GitHub</button>';
  } else {
    els.githubAccountMeta.textContent = "\u672a\u7ed1\u5b9a";
    els.githubAccountActions.innerHTML =
      '<a class="link-btn" href="https://github.com/" target="_blank" rel="noopener" title="\u6253\u5f00\u5916\u90e8\u94fe\u63a5">\u{1F517}</a>' +
      '<button id="github-login-btn" class="btn-secondary">\u8fde\u63a5 GitHub</button>';
    const gh = document.getElementById("github-login-btn");
    if (gh) gh.addEventListener("click", githubLogin);
  }
}

async function githubLogin() {
  const btn = document.getElementById("github-login-btn");
  if (btn) btn.disabled = true;
  els.githubAccountMeta.textContent = "\u6b63\u5728\u8df3\u8f6c GitHub OAuth...";
  try {
    const resp = await new Promise((resolve) => chrome.runtime.sendMessage(
      { type: "github_oauth_login" },
      (r) => resolve(r || { ok: false, reason: "no_response" }),
    ));
    if (!resp || !resp.ok) {
      const reason = (resp && resp.reason) || "unknown";
      const hint = reason === "missing_client_id"
        ? "\u8bf7\u5148\u5728\u4e0b\u65b9\u586b\u5165 GitHub OAuth App \u7684 Client ID / Secret"
        : reason === "launch_failed"
          ? "GitHub OAuth \u8df3\u8f6c\u88ab\u53d6\u6d88\u3002\u5982\u88ab\u62d25\uff0c\u8bf7\u68c0\u67e5\u6d4f\u89c8\u5668\u63d0\u793a\u3002"
          : "\u7ed1\u5b9a\u5931\u8d25: " + reason;
      els.githubAccountMeta.textContent = hint;
      return;
    }
    await verifySelfHostedTarget();
  } finally {
    const b = document.getElementById("github-login-btn");
    if (b) b.disabled = false;
  }
}

// 绑定 GitHub 后校验「自托管同步目标仓库」：仓库可达 + weread.yml / sync.yml 存在。
// 取代原先的 provisionRunner（创建 notionhub-runner、推送 workflows、写入 secrets）。
async function verifySelfHostedTarget() {
  const login = await getGithubLogin();
  const repoInput = els.githubSyncRepo ? els.githubSyncRepo.value.trim() : "";
  // 先落盘用户填写的目标仓库（留空则回退默认本仓库）
  await new Promise((resolve) => chrome.runtime.sendMessage(
    { type: "github_save_sync_repo", repo: repoInput }, () => resolve()),
  );
  els.githubAccountMeta.textContent = "@" + login + "：正在校验同步目标仓库…";
  const resp = await new Promise((resolve) => chrome.runtime.sendMessage(
    { type: "github_verify_target" },
    (r) => resolve(r || { ok: false, reason: "no_response" }),
  ));
  if (!resp || !resp.ok) {
    els.githubAccountMeta.textContent =
      "@" + login + "：目标仓库不可达（" + ((resp && resp.reason) || "unknown") +
      "）。请确认仓库名正确、且该授权对它可见。";
    return;
  }
  if (resp.missing && resp.missing.length) {
    els.githubAccountMeta.textContent =
      "@" + login + "：已绑定 " + resp.repo + "，但缺少 " + resp.missing.join("、") +
      "，请把目标设为本项目仓库（或含这些工作流的 fork）。";
    return;
  }
  els.githubAccountMeta.textContent =
    "@" + login + "：已绑定自托管同步目标 " + resp.repo + "（" + (resp.default_branch || "main") + "）";
}

async function getGithubLogin() {
  const d = await storageGet(["github_login"]);
  return d.github_login || "";
}

async function githubLogout() {
  await new Promise((resolve) => chrome.runtime.sendMessage(
    { type: "github_oauth_logout" },
    () => resolve(),
  ));
  await loadAccountFromStorage();
}

async function notionLogin() {
  const btn = document.getElementById("notion-login-btn");
  if (btn) btn.disabled = true;
  els.notionAccountMeta.textContent = "\u6b63\u5728\u8df3\u8f6c Notion OAuth...";
  try {
    const resp = await new Promise((resolve) => chrome.runtime.sendMessage(
      { type: "notionhub_oauth_login" },
      (r) => resolve(r || { ok: false, reason: "no_response" }),
    ));
    if (!resp || !resp.ok) {
      const reason = (resp && resp.reason) || "unknown";
      const hint = reason === "missing_client_id"
        ? "\u8bf7\u5148\u5728\u4e0b\u65b9\u9ad8\u7ea7\u8bbe\u7f6e\u4e2d\u586b\u5165\u4f60\u81ea\u5df1\u7684 Notion Client ID\uff08\u4ec5\u9700 Client ID\uff0c\u65e0\u9700 Secret \u5373\u53ef\u81ea\u52a8\u6388\u6743\uff09"
        : reason === "launch_failed"
          ? "OAuth \u8df3\u8f6c\u88ab\u53d6\u6d88\u3002\u5982\u679c\u4f60\u7684\u8b66\u793a\u88ab\u62d2\u7edd\uff0c\u8bf7\u68c0\u67e5\u6d4f\u89c8\u5668\u63d0\u793a\u3002"
          : "\u767b\u5f55\u5931\u8d25: " + reason;
      els.notionAccountMeta.textContent = hint;
      return;
    }
    await loadAccountFromStorage();
    await loadWereadConfig();
    renderGrid();
  } finally {
    const b = document.getElementById("notion-login-btn");
    if (b) b.disabled = false;
  }
}

async function notionLogout() {
  await new Promise((resolve) => chrome.runtime.sendMessage(
    { type: "notionhub_oauth_logout" },
    () => resolve(),
  ));
  await loadAccountFromStorage();
}

async function loadOauthCredentials() {
  const data = await new Promise((resolve) => chrome.storage.local.get(
    ["notion_oauth_client_id", "notion_oauth_client_secret"],
    resolve,
  ));
  els.oauthClientId.value = data.notion_oauth_client_id || "";
  els.oauthClientSecret.value = data.notion_oauth_client_secret || "";
  const reply = await new Promise((resolve) => chrome.runtime.sendMessage(
    { type: "notionhub_oauth_get_auth_url" },
    (r) => resolve(r || { ok: false }),
  ));
  if (reply && reply.ok && reply.redirectUrl) {
    els.oauthRedirectUri.value = reply.redirectUrl;
  } else {
    els.oauthRedirectUri.value = "(reload extension to compute)";
  }
}

function setOauthStatus(text, kind) {
  els.oauthStatus.textContent = text || "";
  els.oauthStatus.className = "status-pill" + (kind ? " " + kind : "");
}

async function loadNotifyConfig() {
  const data = await storageGet(["notify_channel", "notify_bot_token", "notify_chat_id"]);
  const channel = data.notify_channel || "telegram";
  els.notifyChannels.forEach((card) => {
    card.classList.toggle("selected", card.dataset.channel === channel);
  });
  els.notifyBotToken.value = data.notify_bot_token || "";
  els.notifyChatId.value = data.notify_chat_id || "";
  const has = !!(data.notify_bot_token || data.notify_chat_id);
  els.notifyStatus.textContent = has ? "\u5df2\u4fdd\u5b58" : "\u672a\u4fdd\u5b58";
  els.notifyStatus.className = "status-pill" + (has ? " ok" : "");
}

function setNotifyStatus(text, kind) {
  els.notifyStatus.textContent = text || "";
  els.notifyStatus.className = "status-pill" + (kind ? " " + kind : "");
}

/* ---------- Storage config tab -------------------------------------------- */

function setStorageStatus(text, kind) {
  if (!els.storageStatus) return;
  els.storageStatus.textContent = text || "";
  els.storageStatus.className = "status-pill" + (kind ? " " + kind : "");
}

async function renderStorageGate() {
  const data = await storageGet(["notion_token"]);
  const loggedIn = !!data.notion_token;
  if (els.storageGate) els.storageGate.hidden = loggedIn;
  if (els.storageBody) els.storageBody.hidden = !loggedIn;
  return loggedIn;
}

async function loadStorageConfig() {
  const loggedIn = await renderStorageGate();
  if (!loggedIn) return;
  const data = await storageGet([
    "storage_provider",
    "storage_endpoint",
    "storage_region",
    "storage_bucket",
    "storage_access_key",
    "storage_secret_key",
    "storage_prefix",
    "storage_cdn_domain",
    "storage_youtube",
    "storage_xiaohongshu",
    "storage_douyin",
  ]);
  const provider = data.storage_provider || "r2";
  els.storageProviders.forEach((card) => {
    card.classList.toggle("selected", card.dataset.provider === provider);
  });
  els.storageEndpoint.value = data.storage_endpoint || "";
  els.storageRegion.value = data.storage_region || "";
  els.storageBucket.value = data.storage_bucket || "";
  els.storageAccessKey.value = data.storage_access_key || "";
  els.storageSecretKey.value = data.storage_secret_key || "";
  els.storagePrefix.value = data.storage_prefix || "notionhub-media/";
  els.storageCdnDomain.value = data.storage_cdn_domain || "";
  els.storageYoutube.checked = !!data.storage_youtube;
  els.storageXiaohongshu.checked = !!data.storage_xiaohongshu;
  els.storageDouyin.checked = !!data.storage_douyin;
  const has = !!(data.storage_endpoint && data.storage_bucket && data.storage_access_key && data.storage_secret_key);
  setStorageStatus(has ? "\u5df2\u4fdd\u5b58" : "\u672a\u4fdd\u5b58", has ? "ok" : "");
}

async function saveStorageConfig() {
  const selected = Array.from(els.storageProviders).find((c) => c.classList.contains("selected"));
  const provider = selected?.dataset.provider || "r2";
  const endpoint = (els.storageEndpoint.value || "").trim();
  const bucket = (els.storageBucket.value || "").trim();
  const accessKey = (els.storageAccessKey.value || "").trim();
  const secretKey = (els.storageSecretKey.value || "").trim();
  if (!endpoint || !bucket || !accessKey || !secretKey) {
    setStorageStatus("Endpoint\u3001Bucket\u3001Access Key\u3001Secret Key \u4e0d\u80fd\u4e3a\u7a7a", "err");
    return false;
  }
  if (!endpoint.startsWith("http://") && !endpoint.startsWith("https://")) {
    setStorageStatus("Endpoint \u5fc5\u987b\u4ee5 http:// \u6216 https:// \u5f00\u5934", "err");
    return false;
  }
  const payload = {
    storage_provider: provider,
    storage_endpoint: endpoint,
    storage_region: (els.storageRegion.value || "").trim(),
    storage_bucket: bucket,
    storage_access_key: accessKey,
    storage_secret_key: secretKey,
    storage_prefix: (els.storagePrefix.value || "").trim(),
    storage_cdn_domain: (els.storageCdnDomain.value || "").trim(),
    storage_youtube: els.storageYoutube.checked,
    storage_xiaohongshu: els.storageXiaohongshu.checked,
    storage_douyin: els.storageDouyin.checked,
  };
  await storageSet(payload);
  setStorageStatus("\u5df2\u4fdd\u5b58", "ok");
  if (nativeInfo) {
    const envValues = {
      STORAGE_PROVIDER: payload.storage_provider,
      STORAGE_ENDPOINT: payload.storage_endpoint,
      STORAGE_REGION: payload.storage_region,
      STORAGE_BUCKET: payload.storage_bucket,
      STORAGE_ACCESS_KEY: payload.storage_access_key,
      STORAGE_SECRET_KEY: payload.storage_secret_key,
      STORAGE_PREFIX: payload.storage_prefix,
      STORAGE_CDN_DOMAIN: payload.storage_cdn_domain,
      STORAGE_YOUTUBE: payload.storage_youtube ? "1" : "0",
      STORAGE_XIAOHONGSHU: payload.storage_xiaohongshu ? "1" : "0",
      STORAGE_DOUYIN: payload.storage_douyin ? "1" : "0",
    };
    const reply = await nativeRequest({ type: "env_write", values: envValues }, "notionhub_env_write");
    if (!reply || !reply.ok) {
      setStorageStatus("\u5df2\u4fdd\u5b58\u5230\u6d4f\u89c8\u5668\uff0c.env \u5199\u5165\u5931\u8d25\uff1a" + ((reply && reply.error) || "unknown"), "warn");
      return true;
    }
    setStorageStatus("\u5df2\u4fdd\u5b58\u5e76\u5199\u5165 " + reply.path, "ok");
  }
  return true;
}

async function clearStorageConfig() {
  await storageSet({
    storage_provider: "",
    storage_endpoint: "",
    storage_region: "",
    storage_bucket: "",
    storage_access_key: "",
    storage_secret_key: "",
    storage_prefix: "notionhub-media/",
    storage_cdn_domain: "",
    storage_youtube: false,
    storage_xiaohongshu: false,
    storage_douyin: false,
  });
  await loadStorageConfig();
  setStorageStatus("\u5df2\u5220\u9664", "warn");
}

// 把 manifest 里的版本号填进 UI。面板不再硬编码版本，避免与 manifest 漂移。
function renderVersion() {
  const version = (chrome.runtime.getManifest() || {}).version || "—";
  const brand = document.getElementById("brand-version");
  if (brand) brand.textContent = "v" + version;
  document.querySelectorAll(".app-version").forEach((el) => {
    el.textContent = "v" + version;
  });
}

async function init() {
  renderVersion();
  await probeNative();
  registerWereadKeyListener();
  await loadWereadConfig();
  renderGrid();
  await loadAccountFromStorage();
  await loadOauthCredentials();
  await loadNotifyConfig();
  await loadStorageConfig();
  await initWorkerCard();

  const initialTab = (location.hash || "#sync").slice(1);
  switchTab(TAB_META[initialTab] ? initialTab : "sync");

  els.tabs.forEach((t) => {
    t.addEventListener("click", (e) => {
      e.preventDefault();
      switchTab(t.dataset.tab);
    });
  });
  els.search.addEventListener("input", renderGrid);
  els.filterCategory.addEventListener("change", renderGrid);

  els.copySync.addEventListener("click", async () => {
    await copy("notionhub sync --quiet");
    const orig = els.copySync.textContent;
    els.copySync.textContent = "\u5df2\u590d\u5236";
    setTimeout(() => { els.copySync.textContent = orig; }, 900);
  });

  els.oauthSave.addEventListener("click", async () => {
    const clientId = els.oauthClientId.value.trim();
    const clientSecret = els.oauthClientSecret.value.trim();
    if (!clientId) {
      setOauthStatus("Client ID \u4e0d\u80fd\u4e3a\u7a7a", "err");
      return;
    }
    await new Promise((resolve) => chrome.runtime.sendMessage(
      { type: "notionhub_save_oauth_credentials", clientId, clientSecret },
      () => resolve(),
    ));
    await new Promise((resolve) => chrome.runtime.sendMessage(
      { type: "github_save_oauth_credentials", clientId, clientSecret },
      () => resolve(),
    ));
    setOauthStatus("\u5df2\u4fdd\u5b58\uff08Notion + GitHub \u5171\u7528\uff09", "ok");
  });

  els.notifyChannels.forEach((card) => {
    card.addEventListener("click", async () => {
      const channel = card.dataset.channel;
      await storageSet({ notify_channel: channel });
      els.notifyChannels.forEach((c) => c.classList.toggle("selected", c.dataset.channel === channel));
    });
  });

  els.notifySave.addEventListener("click", async () => {
    await storageSet({
      notify_bot_token: els.notifyBotToken.value.trim(),
      notify_chat_id: els.notifyChatId.value.trim(),
    });
    setNotifyStatus("\u5df2\u4fdd\u5b58", "ok");
  });

  els.notifyClear.addEventListener("click", async () => {
    await storageSet({ notify_bot_token: "", notify_chat_id: "" });
    els.notifyBotToken.value = "";
    els.notifyChatId.value = "";
    setNotifyStatus("\u5df2\u5220\u9664", "warn");
  });

  els.storageProviders.forEach((card) => {
    card.addEventListener("click", () => {
      const provider = card.dataset.provider;
      els.storageProviders.forEach((c) => c.classList.toggle("selected", c.dataset.provider === provider));
    });
  });
  els.storageSave.addEventListener("click", () => { saveStorageConfig(); });
  els.storageClear.addEventListener("click", () => { clearStorageConfig(); });

  els.eyeToggles.forEach((btn) => {
    btn.addEventListener("click", () => {
      const target = document.getElementById(btn.dataset.target);
      if (!target) return;
      if (target.type === "password") {
        target.type = "text";
        btn.textContent = "\u{1F576}";
      } else {
        target.type = "password";
        btn.textContent = "\u{1F441}";
      }
    });
  });

  els.copyBtns.forEach((btn) => {
    btn.addEventListener("click", async () => {
      const target = document.getElementById(btn.dataset.target);
      if (!target) return;
      await copy(target.value);
      const orig = btn.textContent;
      btn.textContent = "\u5df2\u590d\u5236";
      setTimeout(() => { btn.textContent = orig; }, 900);
    });
  });

  // Plugin config drawer
  els.drawerClose.addEventListener("click", closeDrawer);
  els.drawerOverlay.addEventListener("click", (e) => {
    if (e.target === els.drawerOverlay) closeDrawer();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !els.drawerOverlay.hidden) closeDrawer();
  });
  [els.cfgWereadKey, els.cfgNotionToken, els.cfgNotionPage, els.cfgStartYear].forEach((input) => {
    input.addEventListener("input", () => {
      updateWereadState();
      renderEnvPreview();
    });
  });
  els.cfgSave.addEventListener("click", () => { saveWereadConfig(); });
  els.credSave.addEventListener("click", () => {
    if (!currentPluginId) return;
    saveCreds(currentPluginId);
  });
  els.wereadScanLogin.addEventListener("click", async () => {
    setCfgStatus("正在打开微信读书官方登录页，请扫码…", null);
    const reply = await new Promise((res) => chrome.runtime.sendMessage(
      { type: "notionhub_open_weread_login" }, res));
    if (!reply || !reply.ok) {
      setCfgStatus("打开失败，可直接点「获取 API Key」链接", "err");
    }
  });
  els.cfgVerifyTpl.addEventListener("click", () => {
    const page = els.cfgNotionPage.value.trim();
    if (!page) { setTplStatus("请先填写 Duplicate 后的页面 URL", "err"); return; }
    verifyTemplateAndReport(page, els.cfgNotionToken.value.trim());
  });
  els.cfgCopyEnv.addEventListener("click", async () => {
    await copy(buildEnvText());
    const orig = els.cfgCopyEnv.textContent;
    els.cfgCopyEnv.textContent = "\u5df2\u590d\u5236";
    setTimeout(() => { els.cfgCopyEnv.textContent = orig; }, 900);
  });
  els.cfgWriteEnv.addEventListener("click", () => { writeEnvFile(); });
  els.cfgRunSync.addEventListener("click", () => { startNativeSync(); });
  els.cfgActionsSync.addEventListener("click", async () => {
    const saved = await saveWereadConfig();
    if (!saved) return;
    const ghLogin = await getGithubLogin();
    if (!ghLogin) { setCfgStatus("请先绑定 GitHub 账号", "err"); return; }
    startCloudSync("weread");
  });
  // 同步目标仓库输入框：回填已保存值；修改后落盘并重新校验。
  if (els.githubSyncRepo) {
    chrome.storage.local.get(["sync_repo"], (d) => {
      if (d && d.sync_repo) els.githubSyncRepo.value = d.sync_repo;
    });
    els.githubSyncRepo.addEventListener("change", async () => {
      await new Promise((resolve) => chrome.runtime.sendMessage(
        { type: "github_save_sync_repo", repo: els.githubSyncRepo.value.trim() }, () => resolve()));
      if (await getGithubLogin()) verifySelfHostedTarget();
    });
  }
  els.cfgReprobe.addEventListener("click", async () => {
    setNativeStatus("检测中…", null);
    els.cfgNativeRaw.hidden = true;
    const ok = await probeNative();
    if (ok) await loadWereadConfig();
  });
  els.cfgRefreshLog.addEventListener("click", () => { refreshSyncLog(); });
  els.cfgSync.addEventListener("click", async () => {
    const saved = await saveWereadConfig();
    if (!saved) return;
    if (nativeInfo) {
      await startNativeSync();
      return;
    }
    await copy("notionhub sync --quiet");
    setCfgStatus("\u5df2\u590d\u5236\u540c\u6b65\u547d\u4ee4\uff0c\u8bf7\u5728\u7ec8\u7aef\u7c98\u8d34\u8fd0\u884c", "ok");
  });

  els.openPopup.addEventListener("click", (e) => {
    e.preventDefault();
    try { window.close(); } catch (err) { /* ignore */ }
    setTimeout(() => {
      try { chrome.tabs?.getCurrent?.()?.then?.((t) => t && chrome.tabs.remove(t.id)); } catch (err) { /* ignore */ }
    }, 50);
  });
}

// ---- 自有 Worker（长毛象）------------------------------------------------
async function initWorkerCard() {
  const cfg = await storageGet(["worker_interval", "worker_services"]);
  if (cfg.worker_interval) els.workerInterval.value = cfg.worker_interval;
  if (cfg.worker_services != null) els.workerServices.value = cfg.worker_services;

  const env = await nativeRequest({ type: "env_read" }, "notionhub_env_read");
  if (env && env.ok && env.values) {
    if (env.values.MASTODON_INSTANCE) els.workerMastodonInstance.value = env.values.MASTODON_INSTANCE;
    const ok = !!env.values.MASTODON_ACCESS_TOKEN;
    els.workerMastodonStatus.textContent = ok ? "已配置" : "未配置";
    els.workerMastodonStatus.className = "status-pill" + (ok ? " ok" : "");
  }

  els.workerStart.addEventListener("click", startWorker);
  els.workerStop.addEventListener("click", stopWorker);
  els.workerRefresh.addEventListener("click", refreshWorkerStatus);
  els.workerMastodonSave.addEventListener("click", saveWorkerMastodon);

  await refreshWorkerStatus();
}

async function startWorker() {
  const intervalMin = Math.max(1, parseInt(els.workerInterval.value || "5", 10) || 5);
  const services = els.workerServices.value.trim();
  await storageSet({ worker_interval: intervalMin, worker_services: services });
  const args = {
    interval: intervalMin * 60,
    services,
    mastodon: !!els.workerMastodon.checked,
  };
  const reply = await nativeRequest({ type: "worker_start", args }, "notionhub_worker_start");
  if (reply && reply.ok) {
    toast(reply.already_running ? "Worker 已在运行" : "Worker 已启动（PID " + (reply.pid || "?") + "）");
  } else {
    toast("启动失败：" + ((reply && reply.error) || "未知错误"));
  }
  await refreshWorkerStatus();
}

async function stopWorker() {
  const reply = await nativeRequest({ type: "worker_stop" }, "notionhub_worker_stop");
  if (reply && reply.ok) {
    toast(reply.stopped ? "Worker 已停止" : (reply.message || "Worker 未运行"));
  } else {
    toast("停止失败：" + ((reply && reply.error) || "未知错误"));
  }
  await refreshWorkerStatus();
}

async function refreshWorkerStatus() {
  const pill = els.workerStatusPill;
  if (!pill) return;
  const reply = await nativeRequest({ type: "worker_status" }, "notionhub_worker_status");
  if (!reply || !reply.ok || !reply.running) {
    pill.textContent = "未运行";
    pill.className = "status-pill";
    els.workerDetail.textContent = (reply && reply.state)
      ? JSON.stringify(reply.state, null, 2)
      : "尚未启动。";
    return;
  }
  const s = reply.state || {};
  pill.textContent = "运行中";
  pill.className = "status-pill ok";
  const next = s.next_run ? new Date(s.next_run * 1000).toLocaleTimeString() : "-";
  const last = s.last_run || "-";
  let detail = "状态：运行中（PID " + (s.pid || "?") + "）\n"
    + "间隔：" + (s.interval || "-") + "s\n"
    + "下一轮：" + next + "\n"
    + "上一轮：" + last + "\n"
    + "长毛象：" + (s.mastodon ? "已启用" : "未启用") + "\n"
    + "连续失败：" + (s.consecutive_failures || 0);
  if (Array.isArray(s.last_result)) {
    detail += "\n最近结果：\n" + s.last_result
      .map((r) => "  · " + r.service + ": " + (r.ok ? "✅" : "❌ " + (r.error || "")))
      .join("\n");
  }
  els.workerDetail.textContent = detail;
}

async function saveWorkerMastodon() {
  const instance = els.workerMastodonInstance.value.trim();
  const token = els.workerMastodonToken.value.trim();
  const values = { MASTODON_INSTANCE: instance };
  if (token) values.MASTODON_ACCESS_TOKEN = token;
  const reply = await nativeRequest({ type: "env_write", values }, "notionhub_env_write");
  if (reply && reply.ok) {
    els.workerMastodonStatus.textContent = "已保存";
    els.workerMastodonStatus.className = "status-pill ok";
    els.workerMastodonToken.value = "";
    toast("已保存 Mastodon 凭据到 .env");
  } else {
    toast("保存失败：" + ((reply && reply.error) || "未知错误"));
  }
}

init().catch((err) => {
  setOauthStatus("\u9519\u8bef: " + (err.message || err), "err");
});