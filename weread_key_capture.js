/* WeRead Skill API Key capture.
 *
 * 官方 skills 页（https://weread.qq.com/r/weread-skills）在用户登录后会展示
 * API Key。腾讯并未公开“扫码取 key”的调用接口，因此这里不伪造任何协议，
 * 而是：用户在官方页正常扫码登录 → 本脚本在页面 DOM 里发现 wrk- 开头的
 * key → 回传给扩展自动填入配置。
 *
 * 之所以用 MutationObserver 轮询 DOM，是因为 key 的展示形态
 * （纯文本 / 需点击“复制” / 弹层）可能随官方改版变化，
 * 扫描整棵树的文本能同时兼容这几种情况。
 */
(function () {
  if (window.__wereadKeyCaptureInstalled) return;
  window.__wereadKeyCaptureInstalled = true;

  const KEY_RE = /wrk-[A-Za-z0-9_\-]{16,}/g;

  function notify(key) {
    try {
      chrome.runtime.sendMessage({ type: "weread_key_captured", key: key });
    } catch (e) {
      /* 扩展上下文失效时忽略 */
    }
  }

  // 扫描可见文本（跳过 script/style，避免误报）
  function scanTree() {
    const walker = document.createTreeWalker(
      document.body || document.documentElement,
      NodeFilter.SHOW_TEXT,
      {
        acceptNode(node) {
          const p = node.parentElement;
          if (!p) return NodeFilter.FILTER_REJECT;
          const tag = p.tagName;
          if (tag === "SCRIPT" || tag === "STYLE" || tag === "NOSCRIPT") {
            return NodeFilter.FILTER_REJECT;
          }
          return NodeFilter.FILTER_ACCEPT;
        },
      },
    );
    while (walker.nextNode()) {
      const txt = walker.currentNode.nodeValue || "";
      KEY_RE.lastIndex = 0;
      let m;
      while ((m = KEY_RE.exec(txt)) !== null) {
        notify(m[0]);
      }
    }
    // 也可能出现在 input/textarea 的 value 里
    document.querySelectorAll("input, textarea").forEach((el) => {
      const v = (el.value || "") + " " + (el.getAttribute("data-clipboard-text") || "");
      KEY_RE.lastIndex = 0;
      const m = v.match(KEY_RE);
      if (m) notify(m[0]);
    });
  }

  function start() {
    scanTree();
    const obs = new MutationObserver(() => scanTree());
    obs.observe(document.documentElement, {
      childList: true,
      subtree: true,
      characterData: true,
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
