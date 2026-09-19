"""Douban book plugin for NotionHub.

Reads public Douban book pages from URLs in DOUBAN_BOOK_URLS
(comma-separated, https://book.douban.com/subject/XXXX/) and writes
each book to the Notion "豆瓣书单" database. No login required.
"""
from __future__ import annotationsimport osimport reimport requestsfrom ..plugin import Category, PluginMetafrom ..utils import strip_htmlfrom .base import BasePlugin_TITLE_RE = re.compile(r'<title>([^<]+)</title>')
_AUTHOR_BLOCK_RE = re.compile(r'<span class="pl">作者:</span>(.*?)(?:<br|</div)', re.DOTALL)
_AUTHOR_LINK_RE = re.compile(r'<a[^>]*>([^<]+)</a>')
_RATING_RE = re.compile(r'<strong class="(?:ll )?rating_num">([\d.]+)</strong>')
_PUB_RE = re.compile(r'<span class="pl">出版年:</span>\s*([^<]+?)(?:<br|$)', re.MULTILINE)
_PRESS_RE = re.compile(r'<span class="pl">出版社:</span>\s*([^<]+?)(?:<br|$)', re.MULTILINE)
_ISBN_RE = re.compile(r'<span class="pl">ISBN:</span>\s*([^<]+?)(?:<br|$)', re.MULTILINE)
_PAGES_RE = re.compile(r'<span class="pl">页数:</span>\s*([^<]+?)(?:<br|$)', re.MULTILINE)
_PRICE_RE = re.compile(r'<span class="pl">定价:</span>\s*([^<]+?)(?:<br|$)', re.MULTILINE)
_INTRO_RE = re.compile(r'<div class="intro">\s*<p>(.*?)</p>', re.DOTALL)
_TAG_RE = re.compile(r'<a[^>]+href="/tag/[^"]+"[^>]*>([^<]+)</a>')


import logginglog = logging.getLogger(__name__)
def _extract_subject_id(url):
    m = re.search(r"/subject/(\d+)", url)
    return m.group(1) if m else url


def _parse_book(html, url):
    title_match = _TITLE_RE.search(html)
    title = ''
    if title_match:
        title = title_match.group(1).strip()
        if title.endswith("(豆瓣)"):
            title = title[:-4].strip()
    author_match = _AUTHOR_BLOCK_RE.search(html)
    if author_match:
        block = author_match.group(1)
        links = _AUTHOR_LINK_RE.findall(block)
        if links:
            author = ' / '.join(strip_html(n) for n in links if strip_html(n))
        else:
            author = strip_html(block)
    else:
        author = ''
    rating_match = _RATING_RE.search(html)
    rating = float(rating_match.group(1)) if rating_match else 0.0
    pub_match = _PUB_RE.search(html)
    pub_date = strip_html(pub_match.group(1)) if pub_match else ''
    press_match = _PRESS_RE.search(html)
    press = strip_html(press_match.group(1)) if press_match else ''
    isbn_match = _ISBN_RE.search(html)
    isbn = strip_html(isbn_match.group(1)) if isbn_match else ''
    pages_match = _PAGES_RE.search(html)
    pages = strip_html(pages_match.group(1)) if pages_match else ''
    price_match = _PRICE_RE.search(html)
    price = strip_html(price_match.group(1)) if price_match else ''
    intro_match = _INTRO_RE.search(html)
    summary = strip_html(intro_match.group(1))[:1900] if intro_match else ''
    tags = [t.strip() for t in _TAG_RE.findall(html) if t.strip()]
    subject_id = _extract_subject_id(url)
    return {
        "subject_id": subject_id,
        "title": title or subject_id,
        "author": author,
        "rating": rating,
        "pub_date": pub_date,
        "press": press,
        "isbn": isbn,
        "pages": pages,
        "price": price,
        "summary": summary,
        "tags": tags,
        "url": url,
    }


def _fetch_book(url, timeout=20):
    resp = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0 NotionHub/1.0"})
    resp.raise_for_status()
    resp.encoding = 'utf-8'
    return _parse_book(resp.text, url)


class DoubanPlugin(BasePlugin):
    """豆瓣书单同步：抓取每本书的公开页面，解析后 upsert 到 Notion。"""

    DB_NAME = "豆瓣书单"
    TITLE_PROP = "书名"
    KEY_PROP = "SubjectId"
    SCHEMA = {
        "书名": {"title": {}},
        "作者": {"rich_text": {}},
        "评分": {"number": {"format": "number"}},
        "出版社": {"rich_text": {}},
        "出版年": {"rich_text": {}},
        "ISBN": {"rich_text": {}},
        "页数": {"rich_text": {}},
        "定价": {"rich_text": {}},
        "标签": {"multi_select": {"options": []}},
        "简介": {"rich_text": {}},
        "链接": {"url": {}},
        "SubjectId": {"rich_text": {}},
    }

    meta = PluginMeta(
        id="douban",
        name="Douban Books",
        category=Category.READING,
        description="Parse Douban public book pages into Notion. Set DOUBAN_BOOK_URLS to a comma-separated list of book subject URLs.",
        docs_url="https://github.com/wslh/NotionHub#douban",
        icon="📖",
    )

    def is_configured(self):
        return bool(os.getenv("DOUBAN_BOOK_URLS"))

    def _urls(self):
        return [u.strip() for u in os.environ.get("DOUBAN_BOOK_URLS", "").split(",") if u.strip()]

    def _items(self, ctx):
        for url in self._urls():
            try:
                book = _fetch_book(url)
            except Exception as exc:  # noqa: BLE001
                log.warning("error in %s: %s", __name__, exc)
                continue
            subject_id = book["subject_id"]
            raw = {
                "书名": book["title"],
                "作者": book["author"][:1900],
                "评分": book["rating"],
                "出版社": book["press"][:1900],
                "出版年": book["pub_date"][:1900],
                "ISBN": book["isbn"][:1900],
                "页数": book["pages"][:1900],
                "定价": book["price"][:1900],
                "简介": book["summary"][:1900],
                "链接": book["url"],
                "SubjectId": subject_id,
            }
            tags = book.get('tags') or []
            if tags:
                raw["标签"] = {"multi_select": [{"name": t[:80]} for t in tags[:20]]}
            yield subject_id, raw

    def _health_extra(self, ctx):
        return {"books": len(self._urls())}
