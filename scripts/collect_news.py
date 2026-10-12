import json
import re
import os
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.request import Request, urlopen
from urllib.parse import urljoin
from urllib.error import URLError, HTTPError

SOURCES = [
    {
        "name": "山口県公式サイト",
        "url": "https://www.pref.yamaguchi.lg.jp/",
    },
    {
        "name": "山口市公式サイト",
        "url": "https://www.city.yamaguchi.lg.jp/",
    },
]

KEYWORDS = [
    "開店", "オープン", "新店舗", "出店",
    "閉店", "移転", "リニューアル", "開業",
    "オープニングスタッフ", "商業施設",
    "新設", "開業予定", "営業終了",
]

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
            "User-Agent": "Mozilla/5.0 YamaguchiLocalUpdate/1.0"
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

def main():
    os.makedirs("data", exist_ok=True)

    checked_at = datetime.now(timezone.utc).isoformat()
    source_checks = []
    candidates = []

    for source in SOURCES:
        result = {
            "name": source["name"],
            "url": source["url"],
            "checked_at": checked_at,
            "status": "check_needed",
            "note": "",
        }

        try:
            html = fetch_page(source["url"])
            parser = LinkParser()
            parser.feed(html)

            result["status"] = "reachable"
            result["note"] = "トップページのリンクを確認"

            for link in parser.links:
                title = link["title"]

                matched = [
                    keyword
                    for keyword in KEYWORDS
                    if keyword in title
                ]

                if not matched:
                    continue

                candidates.append({
                    "title": title,
                    "url": urljoin(
                        source["url"], link["url"]
                    ),
                    "source_name": source["name"],
                    "source_url": source["url"],
                    "matched_keywords": matched,
                    "checked_at": checked_at,
                    "status": "要確認",
                })

        except (URLError, HTTPError, TimeoutError, ValueError) as error:
            result["note"] = str(error)[:200]

        source_checks.append(result)

    unique = {}
    for item in candidates:
        unique[item["url"]] = item

    output = {
        "generated_at": checked_at,
        "area": "山口市・山口県",
        "purpose": "公式サイトのリンクから記事候補を抽出",
        "note": (
            "トップページのリンク名を対象とした初期版です。"
            "すべての新店・閉店情報を網羅するものではありません。"
            "公開前にリンク先と情報の正確性を確認してください。"
        ),
        "sources": source_checks,
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
    print(f"記事候補: {len(unique)}")

    for item in unique.values():
        print(f"- {item['title']}: {item['url']}")

if __name__ == "__main__":
    main()