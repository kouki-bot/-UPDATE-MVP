import json
import os
import re
import time
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

KEYWORDS = [
    "開店", "オープン", "新店舗", "出店",
    "閉店", "移転", "リニューアル", "開業",
    "オープニングスタッフ", "商業施設",
    "新設", "営業終了", "募集開始",
]

# 1つの公式サイトで調べるページ数の上限
MAX_PAGES_PER_SOURCE = 30

class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.current_href = None
        self.current_text = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            attrs = dict(attrs)
            self.current_href = attrs.get("href")
            self.current_text = []

    def handle_data(self, data):
        if self.current_href:
            text = data.strip()
            if text:
                self.current_text.append(text)

    def handle_endtag(self, tag):
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

def fetch_page(url):
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; YamaguchiLocalUpdate/1.0)"
        },
    )

    with urlopen(request, timeout=20) as response:
        content_type = response.headers.get("Content-Type", "")

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

    if parsed.path.lower().endswith(
        (".pdf", ".jpg", ".jpeg", ".png", ".zip", ".xlsx", ".docx")
    ):
        return ""

    return url.split("#")[0]

def is_same_domain(url, domain):
    return urlparse(url).netloc.lower() == domain.lower()

def main():
    os.makedirs("data", exist_ok=True)

    checked_at = datetime.now(timezone.utc).isoformat()
    source_checks = []
    candidates = []
    scanned_pages = []

    for source in SOURCES:
        print(f"調査開始: {source['name']}")

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

        try:
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
                except (URLError, HTTPError, TimeoutError, ValueError) as error:
                    print(f"取得失敗: {current_url}: {error}")
                    continue

                if not html:
                    continue

                parser = LinkParser()
                parser.feed(html)

                scanned_pages.append({
                    "source_name": source["name"],
                    "url": current_url,
                    "checked_at": checked_at,
                })

                for link in parser.links:
                    title = re.sub(
                        r"\s+", " ", link["title"]
                    ).strip()

                    target_url = normalize_url(
                        current_url, link["url"]
                    )

                    if not title or not target_url:
                        continue

                    if not is_same_domain(
                        target_url, source["domain"]
                    ):
                        continue

                    matched = [
                        keyword for keyword in KEYWORDS
                        if keyword in title
                    ]

                    if matched:
                        candidates.append({
                            "title": title,
                            "url": target_url,
                            "source_name": source["name"],
                            "source_page": current_url,
                            "matched_keywords": matched,
                            "checked_at": checked_at,
                            "status": "要確認",
                        })

                    # お知らせ・報道発表などのページを優先して調べる
                    path = urlparse(target_url).path.lower()
                    priority_words = [
                        "news", "notice", "topics",
                        "release", "oshirase", "koho",
                        "お知らせ", "新着", "報道",
                    ]

                    if (
                        any(word in path for word in priority_words)
                        and target_url not in visited
                        and target_url not in queue
                    ):
                        queue.append(target_url)

                time.sleep(0.3)

            result["status"] = "reachable"
            result["pages_scanned"] = len(visited)
            result["note"] = "同一ドメイン内のページを上限付きで調査"

        except Exception as error:
            result["note"] = str(error)[:200]
            result["pages_scanned"] = len(visited)

        source_checks.append(result)

    unique = {}
    for item in candidates:
        unique[item["url"]] = item

    output = {
        "generated_at": checked_at,
        "area": "山口市・山口県",
        "purpose": "公式サイト内のページとリンクから記事候補を抽出",
        "note": (
            "初期版の自動収集結果です。すべての新店・閉店情報を網羅するものではありません。"
            "公開前にリンク先、発生日、営業状況を確認してください。"
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

    print(f"確認した情報源: {len(source_checks)}")
    print(f"調査したページ: {len(scanned_pages)}")
    print(f"記事候補: {len(unique)}")

    for item in unique.values():
        print(f"- {item['title']}: {item['url']}")

if __name__ == "__main__":
    main()