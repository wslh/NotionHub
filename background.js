"use strict";
/* NotionHub service worker: handles toolbar click, keyboard shortcuts, context menu, and OAuth launch.
 * 自托管改造：不再 importScripts("tweetnacl.js")——原先仅用于向 notionhub-runner 加密写入
 * secrets；该云端链路已移除，扩展现在只向本仓库发送 workflow_dispatch 触发信号。 */
chrome.runtime.onInstalled.addListener(() => {
  try {
    chrome.contextMenus.create({
      id: "notionhub-copy-sync-cmd",
      title: "Copy 'notionhub sync --quiet'",
      contexts: ["all"],
    });
  } catch (e) {
    /* Context menus may already exist on extension reload; ignore. */
  }
});
function openPanel() {
  const url = chrome.runtime.getURL("panel.html");
  chrome.tabs.create({ url: url });
}
// Toolbar click: opens the control panel in a new tab.
chrome.action.onClicked.addListener(() => {
  openPanel();
});
chrome.commands.onCommand.addListener(async (command) => {
  if (command === "notionhub-copy-sync-cmd") {
    try { await chrome.clipboard?.writeText?.("notionhub sync --quiet"); } catch (e) { /* noop */ }
    return;
  }
  if (command === "notionhub-open-panel") {
    openPanel();
  }
});
chrome.contextMenus?.onClicked.addListener((info) => {
  if (info.menuItemId === "notionhub-copy-sync-cmd") {
    try { chrome.clipboard?.writeText?.("notionhub sync --quiet"); } catch (e) { /* noop */ }
  }
});
/* Native messaging --------------------------------------------------------- */
const NATIVE_HOST = "com.notionhub.host";
const ALLOWED_ENV_KEYS = [
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
  // Resource storage (S3-compatible)
  "STORAGE_PROVIDER",
  "STORAGE_ENDPOINT",
  "STORAGE_REGION",
  "STORAGE_BUCKET",
  "STORAGE_ACCESS_KEY",
  "STORAGE_SECRET_KEY",
  "STORAGE_PREFIX",
  "STORAGE_CDN_DOMAIN",
  "STORAGE_YOUTUBE",
  "STORAGE_XIAOHONGSHU",
  "STORAGE_DOUYIN",
];
/* 独立发布版 OAuth 配置（wslh/NotionHub）。
 * 上游项目的 Notion / GitHub OAuth 客户端凭据默认值已全部清空：本仓库
 * 不再内置任何上游公共 OAuth 应用，也不再依赖上游托管的 token-exchange
 * 代理（notion-auth.notionhub.app）。请改用你在面板「账号」标签页高级设置
 * 里填写的 Client ID / Client Secret。
 *
 * Client ID 解析顺序：
 *   1. 用户在面板高级设置中保存的值（chrome.storage.local
 *      "notion_oauth_client_id" / "notion_oauth_client_secret"）。这是独立
 *      发布版唯一推荐的配置方式：凭据 100% 由你掌控，token 交换直连
 *      api.notion.com，不经过任何第三方代理。
 *   2. 下方 NOTIONHUB_DEFAULT_CLIENT_ID —— 本独立版刻意留空，提醒用户必须
 *      自建 OAuth 应用。若未填写，点击「登录账号」会提示 "missing_client_id"。
 *
 * Token exchange：只要用户在面板里提供了 client_secret，扩展就直连
 * api.notion.com/v1/oauth/token 交换；否则走 NOTIONHUB_TOKEN_EXCHANGE_URL
 * （本版为空，直接返回未配置错误，而非悄悄调用上游代理）。 */
const NOTIONHUB_DEFAULT_CLIENT_ID = "";
const NOTIONHUB_DEFAULT_CLIENT_SECRET = "";
const NOTIONHUB_TOKEN_EXCHANGE_URL = "";
/* GitHub OAuth：同 Notion，独立发布版默认留空，需用户自建 GitHub OAuth App。
 * 这些凭据与固定的扩展 ID（manifest key）绑定。 */
const GITHUBHUB_DEFAULT_CLIENT_ID = "";
const GITHUBHUB_DEFAULT_CLIENT_SECRET = "";
function sendNative(msg) {
  return new Promise((resolve) => {
    if (!chrome.runtime?.sendNativeMessage) {
      resolve({ ok: false, error: "native_messaging_unavailable" });
      return;
    }
    try {
      chrome.runtime.sendNativeMessage(NATIVE_HOST, msg, (response) => {
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
function sanitizeEnvValues(values) {
  const clean = {};
  for (const key of ALLOWED_ENV_KEYS) {
    if (Object.prototype.hasOwnProperty.call(values || {}, key)) {
      clean[key] = String(values[key] ?? "");
    }
  }
  return clean;
}
/* OAuth helpers ------------------------------------------------------------ */
function isPlaceholderClient(id) {
  // In the independent release NOTIONHUB_DEFAULT_CLIENT_ID is empty by default,
  // so the only valid case is a user-supplied client id; any blank value is
  // treated as "missing".
  return !id || !id.trim();
}
async function getNotionOAuthConfig() {
  const data = await new Promise((resolve) => {
    chrome.storage.local.get(["notion_oauth_client_id", "notion_oauth_client_secret"], resolve);
  });
  const clientId = (data.notion_oauth_client_id || "").trim() || NOTIONHUB_DEFAULT_CLIENT_ID || "";
  const clientSecret = (data.notion_oauth_client_secret || "").trim() || NOTIONHUB_DEFAULT_CLIENT_SECRET || "";
  return {
    clientId,
    clientSecret,
    hasSecret: !!(clientId && clientSecret),
  };
}
async function launchNotionOAuth() {
  const cfg = await getNotionOAuthConfig();
  if (isPlaceholderClient(cfg.clientId)) {
    return { ok: false, reason: "missing_client_id" };
  }
  const redirectUrl = chrome.identity.getRedirectURL();
  const authUrl = new URL("https://api.notion.com/v1/oauth/authorize");
  authUrl.searchParams.set("client_id", cfg.clientId);
  authUrl.searchParams.set("response_type", "code");
  authUrl.searchParams.set("owner", "user");
  authUrl.searchParams.set("redirect_uri", redirectUrl);
  try {
    const responseUrl = await new Promise((resolve, reject) => {
      chrome.identity.launchWebAuthFlow(
        { url: authUrl.toString(), interactive: true },
        (resp) => {
          if (chrome.runtime.lastError || !resp) {
            reject(chrome.runtime.lastError || new Error("no response"));
          } else {
            resolve(resp);
          }
        },
      );
    });
    const url = new URL(responseUrl);
    const code = url.searchParams.get("code");
    const error = url.searchParams.get("error");
    if (error) {
      return { ok: false, reason: "oauth_" + error };
    }
    if (!code) {
      return { ok: false, reason: "no_code" };
    }
    return { ok: true, code, redirectUri: redirectUrl };
  } catch (err) {
    return { ok: false, reason: "launch_failed", detail: String(err) };
  }
}
/* Build the URL the panel can show for debugging or manual auth. */
async function buildAuthUrl() {
  const cfg = await getNotionOAuthConfig();
  const redirectUrl = chrome.identity.getRedirectURL();
  if (isPlaceholderClient(cfg.clientId)) {
    return { url: null, redirectUrl };
  }
  const authUrl = new URL("https://api.notion.com/v1/oauth/authorize");
  authUrl.searchParams.set("client_id", cfg.clientId);
  authUrl.searchParams.set("response_type", "code");
  authUrl.searchParams.set("owner", "user");
  authUrl.searchParams.set("redirect_uri", redirectUrl);
  return { url: authUrl.toString(), redirectUrl };
}
if (typeof chrome !== "undefined" && chrome.runtime?.onMessage?.hasListener === undefined) {
  /* placeholder */
}
async function exchangeCodeForToken(code, redirectUri) {
  const cfg = await getNotionOAuthConfig();
  if (cfg.hasSecret) {
    return exchangeCodeDirectly(code, redirectUri, cfg.clientId, cfg.clientSecret);
  }
  return exchangeCodeViaNotionHub(code, redirectUri, cfg.clientId);
}
async function exchangeCodeDirectly(code, redirectUri, clientId, clientSecret) {
  const body = new URLSearchParams();
  body.set("grant_type", "authorization_code");
  body.set("code", code);
  body.set("redirect_uri", redirectUri);
  const auth = btoa(clientId + ":" + clientSecret);
  try {
    const resp = await fetch("https://api.notion.com/v1/oauth/token", {
      method: "POST",
      headers: {
        Authorization: "Basic " + auth,
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: body.toString(),
    });
    const text = await resp.text();
    let data;
    try { data = JSON.parse(text); } catch { data = { raw: text }; }
    if (!resp.ok) {
      return { ok: false, status: resp.status, data };
    }
    return { ok: true, data };
  } catch (err) {
    return { ok: false, reason: "exchange_failed", detail: String(err) };
  }
}
/* Token 交换（兜底路径）：仅当用户在面板填写了 client_id 但未提供
 * client_secret 时才会走这里——此时本独立版已无内置代理，故
 * NOTIONHUB_TOKEN_EXCHANGE_URL 为空，直接返回 "exchange_url_not_configured"。
 * 推荐做法是在面板「账号」高级设置里同时填写你自己的 Client ID + Secret，
 * 让 exchangeCodeDirectly 直连 api.notion.com 完成交换。 */
async function exchangeCodeViaNotionHub(code, redirectUri, clientId) {
  if (!NOTIONHUB_TOKEN_EXCHANGE_URL) {
    return { ok: false, reason: "exchange_url_not_configured" };
  }
  try {
    const resp = await fetch(NOTIONHUB_TOKEN_EXCHANGE_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        code,
        redirect_uri: redirectUri,
        grant_type: "authorization_code",
        client_id: clientId || "",
      }),
    });
    const text = await resp.text();
    let data;
    try { data = JSON.parse(text); } catch { data = { raw: text }; }
    if (!resp.ok) {
      return { ok: false, status: resp.status, data };
    }
    if (!data.access_token) {
      return { ok: false, reason: "no_access_token", data };
    }
    return { ok: true, data };
  } catch (err) {
    return { ok: false, reason: "exchange_failed", detail: String(err) };
  }
}
async function fetchBotInfo(token) {
  try {
    const resp = await fetch("https://api.notion.com/v1/users/me", {
      headers: {
        Authorization: "Bearer " + token,
        "Notion-Version": "2022-06-28",
      },
    });
    const data = await resp.json();
    return { ok: resp.ok, data };
  } catch (err) {
    return { ok: false, detail: String(err) };
  }
}
/* GitHub OAuth (reuses the same chrome.identity web-auth flow as Notion) ------ */
async function getGithubOAuthConfig() {
  const data = await new Promise((resolve) => {
    chrome.storage.local.get(["github_oauth_client_id", "github_oauth_client_secret"], resolve);
  });
  return {
    clientId: data.github_oauth_client_id || GITHUBHUB_DEFAULT_CLIENT_ID || "",
    clientSecret: data.github_oauth_client_secret || GITHUBHUB_DEFAULT_CLIENT_SECRET || "",
  };
}
async function buildGithubAuthUrl() {
  const cfg = await getGithubOAuthConfig();
  if (!cfg.clientId) return null;
  const redirectUrl = chrome.identity.getRedirectURL();
  const authUrl = new URL("https://github.com/login/oauth/authorize");
  authUrl.searchParams.set("client_id", cfg.clientId);
  authUrl.searchParams.set("redirect_uri", redirectUrl);
  authUrl.searchParams.set("scope", "repo read:user");
  authUrl.searchParams.set("state", "notionhub-github");
  authUrl.searchParams.set("allow_signup", "false");
  return { url: authUrl.toString(), redirectUrl };
}
async function launchGithubOAuth() {
  const cfg = await getGithubOAuthConfig();
  if (!cfg.clientId) return { ok: false, reason: "missing_client_id" };
  const built = await buildGithubAuthUrl();
  if (!built) return { ok: false, reason: "missing_client_id" };
  try {
    const responseUrl = await new Promise((resolve, reject) => {
      chrome.identity.launchWebAuthFlow(
        { url: built.url, interactive: true },
        (resp) => {
          if (chrome.runtime.lastError || !resp) reject(chrome.runtime.lastError || new Error("no response"));
          else resolve(resp);
        },
      );
    });
    const url = new URL(responseUrl);
    const code = url.searchParams.get("code");
    const error = url.searchParams.get("error");
    if (error) return { ok: false, reason: "oauth_" + error };
    if (!code) return { ok: false, reason: "no_code" };
    return { ok: true, code, redirectUri: built.redirectUrl };
  } catch (err) {
    return { ok: false, reason: "launch_failed", detail: String(err) };
  }
}
async function exchangeGithubCode(code) {
  const cfg = await getGithubOAuthConfig();
  if (!cfg.clientId || !cfg.clientSecret) return { ok: false, reason: "missing_credentials" };
  const body = new URLSearchParams();
  body.set("client_id", cfg.clientId);
  body.set("client_secret", cfg.clientSecret);
  body.set("code", code);
  try {
    const resp = await fetch("https://github.com/login/oauth/access_token", {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/x-www-form-urlencoded" },
      body: body.toString(),
    });
    const data = await resp.json();
    if (!resp.ok || !data.access_token) return { ok: false, status: resp.status, data };
    return { ok: true, token: data.access_token };
  } catch (err) {
    return { ok: false, reason: "exchange_failed", detail: String(err) };
  }
}
async function fetchGithubUser(token) {
  try {
    const resp = await fetch("https://api.github.com/user", {
      headers: { Authorization: "Bearer " + token, Accept: "application/vnd.github+json" },
    });
    const data = await resp.json();
    return { ok: resp.ok, data };
  } catch (err) {
    return { ok: false, detail: String(err) };
  }
}
/*
 * 自托管 GitHub 同步：绑定 GitHub 后，向「本仓库」(默认 wslh/NotionHub，
 * 可在设置里改成你自己的 fork) 的 sync.yml 发送 workflow_dispatch，触发
 * weread2notion 的 plugins sync。不再依赖 notionhub-runner 云端仓库，
 * 也不再推送 workflow / 写 secret —— 仓库里的工作流文件已就绪。
 *
 * 目标仓库需在 GitHub 上对该 token 有 actions:write 权限（即你自己的 fork，
 * 或你拥有写入权限的仓库）。
 */
async function githubApi(token, path, method = "GET", body = null) {
  const resp = await fetch("https://api.github.com" + path, {
    method,
    headers: {
      Authorization: "Bearer " + token,
      Accept: "application/vnd.github+json",
      "Content-Type": "application/json",
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await resp.text();
  let data;
  try { data = text ? JSON.parse(text) : null; } catch { data = { raw: text }; }
  return { ok: resp.ok, status: resp.status, data };
}
// 自托管目标仓库：优先用设置里的 sync_repo，默认本仓库。
const SELF_HOSTED_REPO_DEFAULT = "wslh/NotionHub";
// 读取用户设置的同步目标仓库（"owner/repo"）；为空或格式非法则回退默认本仓库。
async function getSyncRepo() {
  const d = await new Promise((resolve) =>
    chrome.storage.local.get(["sync_repo"], (v) => resolve(v || {})));
  const repo = (d && d.sync_repo || "").trim();
  return /^[^\/\s]+\/[^\/\s]+$/.test(repo) ? repo : SELF_HOSTED_REPO_DEFAULT;
}
// 数据源 → 自托管工作流映射：
//   weread → weread.yml（专用链路，接 full / retries / verbose / concurrency 输入）
//   其它   → sync.yml  （通用链路，接 plugin 输入）
function workflowForService(service) {
  return service === "weread" ? "weread.yml" : "sync.yml";
}
// 向「本仓库」的 weread.yml / sync.yml 发送 workflow_dispatch，触发同步。
// 这是“触发同步”职责的真实落地：扩展把运行信号发给本仓库的 GitHub Actions。
// 不再需要 notionhub-runner 云端仓库，也不再推送 workflow / 写 secret。
async function githubTriggerWorkflow(token, login, service, inputs) {
  const svc = service || "weread";
  const repoFull = await getSyncRepo();
  const parts = repoFull.split("/");
  const owner = parts[0];
  const repo = parts[1];
  const wf = workflowForService(svc);
  // 默认分支不固定为 main（取决于用户仓库设置），动态读取以免 dispatch 404
  let ref = "main";
  const info = await githubApi(token, `/repos/${owner}/${repo}`);
  if (info.ok && info.data && info.data.default_branch) ref = info.data.default_branch;
  else return { ok: false, reason: "repo_unreachable", status: info.status, data: info.data, repo: repoFull };
  // weread.yml 直接接收同步参数；sync.yml 需要 plugin_id 指定数据源。
  // 注意：输入名必须与 sync.yml 的 workflow_dispatch.inputs 完全一致（plugin_id），
  // 否则 GitHub 会忽略该输入，inputs.plugin_id 为空 → sync.yml 兜底成 weread，
  // 导致「同步 douban」实际跑成了微信读书。
  const payloadInputs = svc === "weread"
    ? Object.assign({ reason: "manual" }, inputs || {})
    : Object.assign({ plugin_id: svc, reason: "manual" }, inputs || {});
  // 记录基准 run id，用于识别本次 dispatch 创建的新 run
  const before = await githubApi(token, `/repos/${owner}/${repo}/actions/runs?per_page=1`);
  const baseline = (before.data && before.data.workflow_runs && before.data.workflow_runs[0] || {}).id || null;
  const url = `/repos/${owner}/${repo}/actions/workflows/${wf}/dispatches`;
  const res = await githubApi(token, url, "POST", { ref, inputs: payloadInputs });
  if (!res.ok) {
    // 404 说明目标仓库里没有这个工作流文件（仓库不对，或不是本项目的 fork）。
    if (res.status === 404) {
      return {
        ok: false, status: res.status, data: res.data, repo: repoFull,
        reason: "workflow_missing",
        hint: `${repoFull} 缺少 .github/workflows/${wf}，请把同步目标设为本项目仓库或含该工作流的 fork`,
      };
    }
    if (res.status === 401 || res.status === 403) {
      return {
        ok: false, status: res.status, data: res.data, repo: repoFull,
        reason: "no_permission",
        hint: `当前 GitHub 授权对 ${repoFull} 无 actions:write 权限，请改用你自己的 fork`,
      };
    }
    return { ok: false, status: res.status, data: res.data, repo: repoFull, reason: "dispatch_failed" };
  }
  // GitHub 对新建 run 有索引延迟，轮询直到出现不同于基准的新 run
  for (let i = 0; i < 8; i++) {
    await new Promise((r) => setTimeout(r, 1200));
    const runs = await githubApi(token, `/repos/${owner}/${repo}/actions/runs?per_page=5`);
    const list = (runs.data && runs.data.workflow_runs) || [];
    const fresh = list.find((r) => r.id !== baseline);
    if (fresh) return { ok: true, run_id: fresh.id, html_url: fresh.html_url, ref, repo: repoFull, workflow: wf };
  }
  return { ok: true, run_id: null, html_url: null, ref, repo: repoFull, workflow: wf, note: "run_pending" };
}
// 轮询 GitHub Actions 运行状态，供面板展示进度。
async function githubGetRun(token, login, runId) {
  const repoFull = await getSyncRepo();
  const parts = repoFull.split("/");
  const res = await githubApi(token, `/repos/${parts[0]}/${parts[1]}/actions/runs/${runId}`);
  if (!res.ok) return { ok: false, status: res.status };
  const r = res.data;
  return { ok: true, status: r.status, conclusion: r.conclusion, html_url: r.html_url };
}
// 校验自托管同步目标：仓库是否可达、所需工作流文件是否存在。
// 绑定 GitHub 后由面板调用，取代原先「创建 notionhub-runner + 推送 workflow + 写 secret」的三步流程。
async function verifySyncTarget(token) {
  const repoFull = await getSyncRepo();
  const parts = repoFull.split("/");
  const info = await githubApi(token, `/repos/${parts[0]}/${parts[1]}`);
  if (!info.ok) return { ok: false, repo: repoFull, reason: "repo_unreachable", status: info.status, data: info.data };
  const dir = await githubApi(token, `/repos/${parts[0]}/${parts[1]}/contents/.github/workflows`);
  const names = Array.isArray(dir.data) ? dir.data.map((f) => f.name) : [];
  const missing = ["weread.yml", "sync.yml"].filter((n) => !names.includes(n));
  return {
    ok: true,
    repo: repoFull,
    default_branch: (info.data && info.data.default_branch) || "main",
    workflows: names.filter((n) => /\.ya?ml$/.test(n)),
    missing,
  };
}
/* 自托管改造：以下云端逻辑已全部移除
 *   - githubEncryptSecret / githubSetSecret：向 notionhub-runner 写入加密 secret
 *   - fetchNotionHubConfigs：从 NotionHub 云端拉取 *_CONFIG 与 workflow 明文
 *   - githubPushWorkflowFile / githubPushAllWorkflows：向 runner 仓库推送 nh-*.yml
 *   - githubPushAllSecrets / WORKFLOW_DIR / libsodium 与 base64 辅助函数
 * 现在凭证由用户在「仓库 Settings → Secrets → Actions」自行配置，
 * 扩展只发送 workflow_dispatch 触发信号，不再接触 secret 写入与 workflow 推送。
 */
/* 自托管改造：fetchNotionHubConfigs / githubPushAllSecrets 已移除。
 * 云端不再参与任何凭证分发——各插件的 secret 由用户在本仓库
 * Settings → Secrets and variables → Actions 中自行填写。 */
/* 自托管改造：workflow 文件推送（Contents API）已移除。
 * 原先需要先向 notionhub-runner 推送 .github/workflows/nh-{service}.yml，
 * 否则 workflow_dispatch 会 404。现在工作流文件随本仓库（或你的 fork）
 * 一起存在于 git 中——weread.yml（微信读书）与 sync.yml（其它数据源），
 * 扩展无需、也不再具备推送能力。 */
// 登录成功后：把用户在面板里手动配置好的标准模板页 / ntn_ token 同步回 .env，
// 以防此前 OAuth 自动填充误把“非标准模板页”和 OAuth access_token 写进了 .env，
// 从而破坏 weread2notion CLI 同步。
//
// 重要：NotionHub OAuth 返回的 access_token 与 weread2notion CLI 使用的
// ntn_ Internal Token 是两套体系；且 OAuth 复制出的页面（duplicated_template_id）
// 只有“模板”一个数据库，并不是 weread2notion 标准模板（缺少书架/日/周/月/年/
// 分类/作者）。因此这里**绝不**用 OAuth 数据去覆盖 weread 配置或 .env，
// 而是用浏览器存储中用户手动配置的正确值去修复 .env。
async function provisionNotionOAuthTarget(tokenData) {
  const existing = await new Promise((resolve) =>
    chrome.storage.local.get(
      ["weread_notion_token", "weread_notion_page", "notion_page"],
      resolve,
    ),
  );
  if (!(existing.weread_notion_token || existing.weread_notion_page)) return;
  try {
    const read = await sendNative({ type: "env_read" });
    const cur = (read && read.ok && read.values) || {};
    const tok = existing.weread_notion_token || "";
    const safeTok = tok.startsWith("ntn_") || tok.startsWith("secret_")
      ? tok
      : (cur.NOTION_TOKEN || "");
    const page = existing.weread_notion_page || existing.notion_page || "";
    if (!safeTok || !page) return;
    const values = {
      NOTION_TOKEN: safeTok,
      NOTION_PAGE: page,
      WEREAD_API_KEY: cur.WEREAD_API_KEY || "",
      START_YEAR: cur.START_YEAR || "2023",
    };
    await sendNative({ type: "env_write", values: sanitizeEnvValues(values) });
  } catch (e) {
    /* 桥未安装：浏览器存储已保存，可稍后在面板中保存 */
  }
}
// 校验用户填的 Notion 页面是否为 weread2notion 标准模板（含 7 个必需数据库）。
// 这是“模板复制与识别”的第一层职责：在配置阶段就拦截错误页面，避免同步时才失败。
const REQUIRED_TEMPLATE_DBS = ["书架", "日", "周", "月", "年", "分类", "作者"];
async function verifyNotionTemplate(pageUrl, token) {
  const m = (pageUrl || "").match(/([a-f0-9]{32})/i) ||
    (pageUrl || "").match(/([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/i);
  if (!m) return { ok: false, reason: "invalid_url" };
  const pageId = m[1].replace(/-/g, "");
  const tok = token || (await new Promise((r) =>
    chrome.storage.local.get(["weread_notion_token"], (d) => r(d.weread_notion_token || ""))));
  if (!tok) return { ok: false, reason: "no_token" };
  const headers = { Authorization: "Bearer " + tok, "Notion-Version": "2022-06-28" };
  const found = [];
  let cursor = undefined;
  try {
    do {
      const u = "https://api.notion.com/v1/blocks/" + pageId + "/children?page_size=100" +
        (cursor ? "&start_cursor=" + encodeURIComponent(cursor) : "");
      const resp = await fetch(u, { headers });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        // Notion 对“页面未共享给该集成”会返回 404 + object_not_found，
        // 与真正的页面不存在表现一致，统一标记为 not_shared 便于前端给出指引。
        const isNotFound = resp.status === 404 || err.code === "object_not_found" ||
          /not\s+find|shared\s+with\s+your\s+integration/i.test(err.message || "");
        return {
          ok: false,
          reason: isNotFound ? "not_shared" : "notion_error",
          status: resp.status,
          message: err.message || resp.statusText,
        };
      }
      const data = await resp.json();
      for (const b of data.results || []) {
        if (b.type === "child_database") found.push(b.child_database.title);
      }
      cursor = data.has_more ? data.next_cursor : undefined;
    } while (cursor);
  } catch (e) {
    return { ok: false, reason: "fetch_failed", message: String((e && e.message) || e) };
  }
  const missing = REQUIRED_TEMPLATE_DBS.filter((r) => !found.includes(r));
  return { ok: true, valid: missing.length === 0, found, missing };
}
// 微信读书扫码登录后，content script 捕获到 API Key 时触发：
// 存入 chrome.storage 并经 native 桥写入 .env，省去手动复制粘贴。
async function handleWereadKeyCaptured(key) {
  if (!key) return;
  // API Key 属于凭据，只写 local：chrome.storage.sync 会随浏览器账号跨设备同步。
  await new Promise((resolve) =>
    chrome.storage.local.set({ weread_api_key: key }, resolve));
  try {
    const read = await sendNative({ type: "env_read" });
    const cur = (read && read.ok && read.values) || {};
    await sendNative({
      type: "env_write",
      values: sanitizeEnvValues({ WEREAD_API_KEY: key, NOTION_TOKEN: cur.NOTION_TOKEN || "",
        NOTION_PAGE: cur.NOTION_PAGE || "", START_YEAR: cur.START_YEAR || "2023" }),
    });
  } catch (e) { /* 桥未安装 */ }
  // 通知面板刷新 UI（面板可能正打开着配置抽屉）
  try {
    chrome.runtime.sendMessage({ type: "weread_key_filled", key: key }, () => {
      void chrome.runtime.lastError; // 面板未打开时忽略
    });
  } catch (e) { /* ignore */ }
}
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  (async () => {
    if (msg && msg.type === "weread_key_captured") {
      await handleWereadKeyCaptured(msg.key);
      sendResponse({ ok: true });
      return;
    }
    if (msg && msg.type === "notionhub_open_weread_login") {
      // 打开官方 skills 页，用户扫码登录后 content script 会自动捕获 key
      const url = "https://weread.qq.com/r/weread-skills";
      try {
        await chrome.tabs.create({ url, active: true });
        sendResponse({ ok: true, url });
      } catch (e) {
        sendResponse({ ok: false, error: String((e && e.message) || e) });
      }
      return;
    }
    if (msg && msg.type === "notionhub_verify_template") {
      sendResponse(await verifyNotionTemplate(msg.pageUrl, msg.token));
      return;
    }
    if (msg && msg.type === "notionhub_oauth_get_auth_url") {
      const data = await buildAuthUrl();
      sendResponse({ ok: !!data, url: data ? data.url : "", redirectUrl: data ? data.redirectUrl : "" });
      return;
    }
    if (msg && msg.type === "notionhub_oauth_login") {
      const launch = await launchNotionOAuth();
      if (!launch.ok) {
        sendResponse({ ok: false, reason: launch.reason, detail: launch.detail });
        return;
      }
      const exchange = await exchangeCodeForToken(launch.code, launch.redirectUri);
      if (!exchange.ok) {
        sendResponse({ ok: false, reason: exchange.reason, status: exchange.status, data: exchange.data });
        return;
      }
      const tokenData = exchange.data;
      const bot = await fetchBotInfo(tokenData.access_token);
      const botInfo = bot.ok ? bot.data : null;
      const owner = (tokenData.owner && (tokenData.owner.user || tokenData.owner)) || {};
      const workspaceName =
        (botInfo && (botInfo.bot && botInfo.bot.workspace_name)) ||
        owner.user?.name ||
        owner.workspace_name ||
        "Notion Workspace";
      const workspaceId =
        (botInfo && botInfo.id) ||
        owner.user?.id ||
        tokenData.workspace_id ||
        "";
      await new Promise((resolve) => {
        chrome.storage.local.set(
          {
            notion_token: tokenData.access_token,
            notion_bot_id: botInfo && botInfo.id ? botInfo.id : "",
            notion_workspace_id: workspaceId,
            notion_workspace_name: workspaceName,
            notion_oauth_workspace_name: workspaceName,
            notion_duplicated_template_id: tokenData.duplicated_template_id || "",
            notion_oauth_login_at: new Date().toISOString(),
          },
          resolve,
        );
      });
      // 自动把 token / 复制出的模板页 同步到 weread 配置与 .env
      await provisionNotionOAuthTarget(tokenData);
      sendResponse({
        ok: true,
        workspaceName,
        workspaceId,
        botId: botInfo && botInfo.id ? botInfo.id : "",
        duplicatedTemplateId: tokenData.duplicated_template_id || "",
      });
      return;
    }
    if (msg && msg.type === "notionhub_oauth_logout") {
      await new Promise((resolve) => {
        chrome.storage.local.remove(
          [
            "notion_token",
            "notion_bot_id",
            "notion_workspace_id",
            "notion_workspace_name",
            "notion_oauth_workspace_name",
            "notion_oauth_login_at",
            "notion_duplicated_template_id",
          ],
          resolve,
        );
      });
      sendResponse({ ok: true });
      return;
    }
    if (msg && msg.type === "notionhub_native_ping") {
      sendResponse(await sendNative({ type: "ping" }));
      return;
    }
    if (msg && msg.type === "notionhub_env_read") {
      sendResponse(await sendNative({ type: "env_read" }));
      return;
    }
    if (msg && msg.type === "notionhub_env_write") {
      sendResponse(await sendNative({ type: "env_write", values: sanitizeEnvValues(msg.values) }));
      return;
    }
    if (msg && msg.type === "notionhub_sync_start") {
      sendResponse(await sendNative({ type: "sync_start", args: msg.args || ["--quiet"] }));
      return;
    }
    if (msg && msg.type === "notionhub_sync_log") {
      sendResponse(await sendNative({ type: "sync_log", lines: msg.lines || 200 }));
      return;
    }
    if (msg && msg.type === "notionhub_worker_start") {
      sendResponse(
        await sendNative({ type: "worker_start", args: msg.args || { interval: 300 } }),
      );
      return;
    }
    if (msg && msg.type === "notionhub_worker_stop") {
      sendResponse(await sendNative({ type: "worker_stop" }));
      return;
    }
    if (msg && msg.type === "notionhub_worker_status") {
      sendResponse(await sendNative({ type: "worker_status" }));
      return;
    }
    if (msg && msg.type === "notionhub_save_oauth_credentials") {
      await new Promise((resolve) => {
        chrome.storage.local.set(
          {
            notion_oauth_client_id: msg.clientId || "",
            notion_oauth_client_secret: msg.clientSecret || "",
          },
          resolve,
        );
      });
      sendResponse({ ok: true });
      return;
    }
    if (msg && msg.type === "github_oauth_get_auth_url") {
      const data = await buildGithubAuthUrl();
      sendResponse({ ok: !!data, url: data ? data.url : "", redirectUrl: data ? data.redirectUrl : "" });
      return;
    }
    if (msg && msg.type === "github_oauth_login") {
      const launch = await launchGithubOAuth();
      if (!launch.ok) { sendResponse({ ok: false, reason: launch.reason, detail: launch.detail }); return; }
      const exchange = await exchangeGithubCode(launch.code);
      if (!exchange.ok) { sendResponse({ ok: false, reason: exchange.reason, status: exchange.status, data: exchange.data }); return; }
      const user = await fetchGithubUser(exchange.token);
      const login = user.ok ? user.data.login : "";
      await new Promise((resolve) => {
        chrome.storage.local.set(
          {
            github_token: exchange.token,
            github_login: login,
            github_oauth_login_at: new Date().toISOString(),
          },
          resolve,
        );
      });
      sendResponse({ ok: true, login });
      return;
    }
    if (msg && msg.type === "github_oauth_logout") {
      await new Promise((resolve) => {
        chrome.storage.local.remove(["github_token", "github_login", "github_oauth_login_at"], resolve);
      });
      sendResponse({ ok: true });
      return;
    }
    if (msg && msg.type === "github_save_oauth_credentials") {
      await new Promise((resolve) => {
        chrome.storage.local.set(
          {
            github_oauth_client_id: msg.clientId || "",
            github_oauth_client_secret: msg.clientSecret || "",
          },
          resolve,
        );
      });
      sendResponse({ ok: true });
      return;
    }
    // 自托管改造：绑定 GitHub 后只校验目标仓库与工作流文件是否就绪，
    // 不再创建 notionhub-runner、不再推送 workflow、不再写入 secret。
    if (msg && msg.type === "github_verify_target") {
      const store = await new Promise((resolve) =>
        chrome.storage.local.get(["github_token", "github_login"], (d) => resolve(d)));
      if (!store.github_token) { sendResponse({ ok: false, reason: "not_bound" }); return; }
      sendResponse(await verifySyncTarget(store.github_token));
      return;
    }
    // 保存用户自定义的同步目标仓库（"owner/repo"）；留空表示使用默认本仓库。
    if (msg && msg.type === "github_save_sync_repo") {
      await new Promise((resolve) =>
        chrome.storage.local.set({ sync_repo: (msg.repo || "").trim() }, resolve));
      sendResponse({ ok: true });
      return;
    }
    if (msg && msg.type === "github_trigger_sync") {
      const store = await new Promise((resolve) =>
        chrome.storage.local.get(["github_token", "github_login"], (d) => resolve(d)));
      if (!store.github_token) { sendResponse({ ok: false, reason: "not_bound" }); return; }
      const service = msg.service || "weread";
      const r = await githubTriggerWorkflow(store.github_token, store.github_login, service, msg.inputs || {});
      sendResponse(r);
      return;
    }
    if (msg && msg.type === "github_get_run") {
      const store = await new Promise((resolve) =>
        chrome.storage.local.get(["github_token", "github_login"], (d) => resolve(d)));
      if (!store.github_token) { sendResponse({ ok: false, reason: "not_bound" }); return; }
      sendResponse(await githubGetRun(store.github_token, store.github_login, msg.runId));
      return;
    }
    sendResponse({ ok: false, reason: "unknown_type" });
  })();
  return true;
});