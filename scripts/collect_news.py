import json
import os
import re
import time
import hashlib
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.request import Request, urlopen
from urllib.parse import urljoin, urlparse
from urllib.error import URLError, HTTPError

SOURCES = [
    {
        "name": "山口県公式サイト",
        "url": "https://www.pref.yamaguchi.lg.jp/",
        "domain": "www.pref.yamaguchi.lg.jp",
    },
    {
        "name": "山口市公式サイト",
        "url": "https://www.city.yamaguchi.lg.jp/",
        "domain": "www.city.yamaguchi.lg.jp",
    },
]

MAX_PAGES_PER_SOURCE = 30
MAX_BODY_CHARS = 5000

KEYWORD_GROUPS = {
    "新店・開店": [
        "新店", "新規開店", "新規オープン",
        "オープン", "開店", "出店", "開業",
    ],
    "閉店": [
        "閉店", "営業終了", "閉業",
    ],
    "移転": [
        "移転", "店舗移転",
    ],
    "リニューアル": [
        "リニューアル", "改装オープン",
        "リニューアルオープン",
    ],
    "求人": [
        "オープニングスタッフ", "新店舗スタッフ",
        "求人", "スタッフ募集",
    ],
}

PRIORITY_WORDS = [
    "news", "notice", "topics", "release",
    "oshirase", "koho", "お知らせ", "新着",
    "報道", "press",
]

DATE_PATTERNS = [
    r"20\d{2}[年./-]\d{1,2}[月./-]\d{1,2}日?",
    r"令和\s*\d+\s*年\s*\d+\s*月\s*\d+\s*日",
]

class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.current_href = None
        self.current_text = []
        self.text_parts = []
        self.title_parts = []
        self.in_title = False
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag in ("script", "style", "noscript", "svg"):
            self.skip_depth += 1
            return

        if self.skip_depth:
            return

        if tag == "title":
            self.in_title = True

        if tag == "a":
            self.current_href = attrs.get("href")
            self.current_text = []

        if tag == "meta":
            name = (
                attrs.get("name", "")
                or attrs.get("property", "")
            ).lower()
            content = attrs.get("content", "")

            if content and (
                "published_time" in name
                or "article:published_time" in name
                or name in ("date", "datepublished")
            ):
                self.text_parts.append(
                    "公開日メタ情報:" + content
                )

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg"):
            if self.skip_depth:
                self.skip_depth -= 1
            return

        if self.skip_depth:
            return

        if tag == "title":
            self.in_title = False

        if tag == "a" and self.current_href:
            title = re.sub(
                r"\s+", " ", " ".join(self.current_text)
            ).strip()

            if title:
                self.links.append({
                    "title": title,
                    "url": self.current_href,
                })

            self.current_href = None
            self.current_text = []

    def handle_data(self, data):
        if self.skip_depth:
            return

        text = re.sub(r"\s+", " ", data).strip()
        if not text:
            return

        self.text_parts.append(text)

        if self.in_title:
            self.title_parts.append(text)

        if self.current_href:
            self.current_text.append(text)

def fetch_page(url):
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "(compatible; YamaguchiLocalUpdate/1.0)"
            )
        },
    )

    with urlopen(request, timeout=20) as response:
        content_type = response.headers.get(
            "Content-Type", ""
        )

        if "html" not in content_type.lower():
            return ""

        return response.read(2_000_000).decode(
            "utf-8", errors="replace"
        )

def normalize_url(base, href):
    if not href:
        return ""

    url = urljoin(base, href)
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        return ""

    if parsed.path.lower().endswith((
        ".pdf", ".jpg", ".jpeg", ".png",
        ".zip", ".xlsx", ".docx",
    )):
        return ""

    return url.split("#")[0]

def classify_text(text):
    categories = []

    for category, keywords in KEYWORD_GROUPS.items():
        if any(keyword in text for keyword in keywords):
            categories.append(category)

    return categories

def extract_date(text):
    for pattern in DATE_PATTERNS:
        match = re.search(pattern, text)
        if match:
            return match.group(0)

    return ""

def is_same_domain(url, domain):
    return urlparse(url).netloc.lower() == domain.lower()

def main():
    os.makedirs("data", exist_ok=True)

    checked_at = datetime.now(timezone.utc).isoformat()
    source_checks = []
    candidates = []
    scanned_pages = []
    visited_candidate_urls = set()

    for source in SOURCES:
        print("調査開始:", source["name"])

        result = {
            "name": source["name"],
            "url": source["url"],
            "checked_at": checked_at,
            "status": "check_needed",
            "pages_scanned": 0,
            "note": "",
        }

        queue = [source["url"]]
        visited = set()

        while queue and len(visited) < MAX_PAGES_PER_SOURCE:
            current_url = queue.pop(0)

            if current_url in visited:
                continue

            if not is_same_domain(
                current_url, source["domain"]
            ):
                continue

            visited.add(current_url)

            try:
                html = fetch_page(current_url)
                if not html:
                    continue

                parser = PageParser()
                parser.feed(html)

                page_text = " ".join(parser.text_parts)
                page_title = " ".join(parser.title_parts).strip()
                page_text = page_text[:MAX_BODY_CHARS]

                scanned_pages.append({
                    "source_name": source["name"],
                    "url": current_url,
                    "checked_at": checked_at,
                })

                for link in parser.links:
                    title = link["title"]
                    target_url = normalize_url(
                        current_url, link["url"]
                    )

                    if not title or not target_url:
                        continue

                    if not is_same_domain(
                        target_url, source["domain"]
                    ):
                        continue

                    path = urlparse(target_url).path.lower()

                    if (
                        any(word in path for word in PRIORITY_WORDS)
                        and target_url not in visited
                        and target_url not in queue
                    ):
                        queue.append(target_url)

                    categories = classify_text(title)

                    if not categories:
                        continue

                    if target_url in visited_candidate_urls:
                        continue

                    visited_candidate_urls.add(target_url)

                    # 候補ページの本文を取得
                    body = ""
                    article_title = title
                    published_date = ""
                    article_status = "要確認"

                    try:
                        article_html = fetch_page(target_url)
                        article_parser = PageParser()
                        article_parser.feed(article_html)

                        article_title = (
                            " ".join(
                                article_parser.title_parts
                            ).strip()
                            or title
                        )

                        body = " ".join(
                            article_parser.text_parts
                        )[:MAX_BODY_CHARS]

                        published_date = extract_date(body)

                        # タイトルと本文を合わせて分類
                        categories = classify_text(
                            article_title + " " + body
                        )

                        if not categories:
                            article_status = "関連性要確認"

                    except (
                        URLError, HTTPError,
                        TimeoutError, ValueError,
                    ) as error:
                        body = ""
                        article_status = (
                            "本文取得失敗: "
                            + str(error)[:100]
                        )

                    item_id = hashlib.sha256(
                        target_url.encode("utf-8")
                    ).hexdigest()[:16]

                    candidates.append({
                        "id": item_id,
                        "title": article_title,
                        "url": target_url,
                        "source_name": source["name"],
                        "source_page": current_url,
                        "category": categories,
                        "published_date": published_date,
                        "body_excerpt": body[:1000],
                        "checked_at": checked_at,
                        "status": article_status,
                    })

                    time.sleep(0.3)

                time.sleep(0.3)

            except (
                URLError, HTTPError,
                TimeoutError, ValueError,
            ) as error:
                print("取得失敗:", current_url, str(error)[:150])

        result["pages_scanned"] = len(visited)
        result["status"] = (
            "reachable" if visited else "check_needed"
        )
        result["note"] = (
            "ページ本文・リンク・候補ページを確認"
        )
        source_checks.append(result)

    # URL単位で重複を除外
    unique = {}
    for item in candidates:
        unique[item["url"]] = item

    output = {
        "generated_at": checked_at,
        "area": "山口市・山口県",
        "purpose": (
            "公式サイトから記事候補を抽出し、"
            "本文・公開日候補・分類を記録"
        ),
        "note": (
            "公開日が取得できない場合は空欄です。"
            "本文内の日付が必ずしも公開日とは限りません。"
            "公開前に出典と情報の正確性を確認してください。"
        ),
        "sources": source_checks,
        "scanned_pages": scanned_pages,
        "candidates": list(unique.values()),
    }

    with open(
        "data/source_checks.json",
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            output, file, ensure_ascii=False, indent=2
        )

    print("確認した情報源:", len(source_checks))
    print("調査したページ:", len(scanned_pages))
    print("記事候補:", len(unique))

    for item in unique.values():
        print(
            "-", item["category"],
            item["title"],
            item["url"],
        )

if __name__ == "__main__":
    main()