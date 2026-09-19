from weread2notion.notion import NotionWorkspace
from weread2notion.sync import Synchronizer


class Client:
    def __init__(self):
        self.calls = 0

    def request(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            raise type("Transient", (RuntimeError,), {"status": 520})("transient")
        return {}


class FakeNotionAI:
    sources = {}

    def __init__(self, children):
        self.children = children
        self.requests = []
        self.schemas = {}

    def list_children(self, page_id):
        return self.children

    def write_ai_intro(self, page_id, summary):
        self.requests.append(("write_ai_intro", page_id, summary))

    def request(self, path, method="GET", body=None):
        self.requests.append((path, method, body))
        return {}

    @staticmethod
    def plain_property(prop):
        return NotionWorkspace.plain_property(prop)


def test_write_ai_intro_replaces_old_marker(monkeypatch):
    monkeypatch.setattr("weread2notion.notion_http.time.sleep", lambda _: None)
    notion = NotionWorkspace("token", "page", "v", client=Client())
    children = [
        {"id": "old-1", "type": "callout", "callout": {"rich_text": [{"plain_text": "AI 导读\n旧内容"}]}},
        {"id": "keep-1", "type": "paragraph", "paragraph": {"rich_text": []}},
        {"id": "old-2", "type": "callout", "callout": {"rich_text": [{"plain_text": "AI 导读\n另一段"}]}},
    ]
    monkeypatch.setattr(notion, "list_children", lambda page_id: children)
    calls = []
    monkeypatch.setattr(
        notion,
        "request",
        lambda path, method="GET", body=None: calls.append((path, method, body)) or {},
    )
    notion.write_ai_intro("page-1", "新导读")
    deletes = [c for c in calls if c[1] == "DELETE"]
    assert {d[0] for d in deletes} == {"blocks/old-1", "blocks/old-2"}
    patch = [c for c in calls if c[0] == "blocks/page-1/children" and c[1] == "PATCH"]
    assert patch, "应追加一段新的 AI 导读 callout"
    callout = patch[0][2]["children"][0]
    assert callout["type"] == "callout"
    text = callout["callout"]["rich_text"][0]["text"]["content"]
    assert text.startswith("AI 导读")
    assert "新导读" in text


def test_sync_ai_intros_writes_summary(monkeypatch):
    notion = FakeNotionAI([])
    sync = Synchronizer(None, notion, preferences={"ai_intro": True})
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(
        "weread2notion.ai_summary.summarize_book",
        lambda title, highlights: f"导读：{title}",
    )
    bundles = {"b1": {"info": {"title": "测试书"}, "highlights": [{"markText": "划线"}]}}
    sync.sync_ai_intros({}, bundles, {"b1": "page-b1"})
    assert sync.counts["ai_intro"] == 1
    assert notion.requests[-1] == ("write_ai_intro", "page-b1", "导读：测试书")


def test_sync_ai_intros_skips_without_key(monkeypatch):
    notion = FakeNotionAI([])
    sync = Synchronizer(None, notion, preferences={"ai_intro": True})
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        "weread2notion.ai_summary.summarize_book", lambda title, highlights: "x"
    )
    sync.sync_ai_intros({}, {"b1": {"info": {}, "highlights": []}}, {"b1": "p"})
    assert sync.counts["ai_intro"] == 0
    assert notion.requests == []


def test_sync_ai_intros_handles_summary_failure(monkeypatch):
    notion = FakeNotionAI([])
    sync = Synchronizer(None, notion, preferences={"ai_intro": True})
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    def _boom(title, highlights):
        raise RuntimeError("boom")

    monkeypatch.setattr("weread2notion.ai_summary.summarize_book", _boom)
    sync.sync_ai_intros({}, {"b1": {"info": {"title": "x"}, "highlights": []}}, {"b1": "p"})
    assert sync.counts["ai_intro"] == 0
    assert sync.counts["ai_intro_errors"] == 1
    assert notion.requests == []
