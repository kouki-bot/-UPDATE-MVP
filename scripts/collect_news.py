import json
import os
import re
import time
import hashlib
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.request import Request, urlopen
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.error import URLError, HTTPError


# ==================================================
# 基本設定
# ==================================================

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
MAX_HTML_BYTES = 2_000_000
MAX_BODY_CHARS = 5000
REQUEST_DELAY = 0.3

OUTPUT_FILE = "data/source_checks.json"

JAPAN_AREAS = [
    "山口市",
    "下関市",
    "宇部市",
    "萩市",
    "防府市",
    "下松市",
    "岩国市",
    "光市",
    "長門市",
    "柳井市",
    "美祢市",
    "周南市",
    "山陽小野田市",
    "大島郡周防大島町",
    "周防大島町",
    "玖珂郡和木町",
    "和木町",
    "熊毛郡上関町",
    "上関町",
    "熊毛郡田布施町",
    "田布施町",
    "熊毛郡平生町",
    "平生町",
    "阿武郡阿武町",
    "阿武町",
]

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
    "イベント": [
        "イベント", "開催", "フェア",
        "祭り", "マルシェ", "講座",
        "体験会", "リユース会",
    ],
    "新施設・地域の動き": [
        "新施設", "供用開始", "開館",
        "開設", "完成", "地域交流",
    ],
}

# 探索対象にするリンクの目印
PRIORITY_WORDS = [
    "news", "notice", "topics", "release",
    "oshirase", "koho", "お知らせ", "新着",
    "報道", "press", "event", "event-info",
]

# 公開日として扱う可能性のあるメタ情報
PUBLISHED_META_NAMES = {
    "article:published_time",
    "datepublished",
    "publishdate",
    "pubdate",
    "date",
}

SKIP_TAGS = {
    "script",
    "style",
    "noscript",
    "svg",
    "nav",
    "header",
    "footer",
    "aside",
    "form",
}


# ==================================================
# HTML解析
# ==================================================

class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()

        self.links = []
        self.current_href = None
        self.current_text = []

        self.title_parts = []
        self.meta_dates = []

        self.text_parts = []
        self.article_parts = []

        self.tag_stack = []
        self.skip_depth = 0
        self.article_depth = 0
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag in SKIP_TAGS:
            self.skip_depth += 1
            self.tag_stack.append(tag)
            return

        if self.skip_depth:
            self.tag_stack.append(tag)
            return

        if tag == "title":
            self.in_title = True

        if tag == "a":
            self.current_href = attrs.get("href")
            self.current_text = []

        if tag == "meta":
            name = (
                attrs.get("property")
                or attrs.get("name")
                or ""
            ).strip().lower()

            content = (
                attrs.get("content") or ""
            ).strip()

            if content and name in PUBLISHED_META_NAMES:
                self.meta_dates.append({
                    "name": name,
                    "value": content,
                })

        if tag in ("main", "article"):
            self.article_depth += 1

        self.tag_stack.append(tag)

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS:
            # 入れ子のタグを考慮してスキップ階層を戻す
            for index in range(
                len(self.tag_stack) - 1,
                -1,
                -1,
            ):
                if self.tag_stack[index] == tag:
                    removed = self.tag_stack[index:]
                    self.tag_stack = self.tag_stack[:index]

                    self.skip_depth = max(
                        0,
                        self.skip_depth - removed.count(tag),
                    )
                    break

            return

        if self.skip_depth:
            if self.tag_stack:
                self.tag_stack.pop()
            return

        if tag == "title":
            self.in_title = False

        if tag in ("main", "article"):
            self.article_depth = max(
                0,
                self.article_depth - 1,
            )

        if tag == "a" and self.current_href:
            title = re.sub(
                r"\s+",
                " ",
                " ".join(self.current_text),
            ).strip()

            if title:
                self.links.append({
                    "title": title,
                    "url": self.current_href,
                })

            self.current_href = None
            self.current_text = []

        if self.tag_stack:
            self.tag_stack.pop()

    def handle_data(self, data):
        if self.skip_depth:
            return

        text = re.sub(
            r"\s+",
            " ",
            data,
        ).strip()

        if not text:
            return

        self.text_parts.append(text)

        if self.article_depth > 0:
            self.article_parts.append(text)

        if self.in_title:
            self.title_parts.append(text)

        if self.current_href:
            self.current_text.append(text)


# ==================================================
# 共通処理
# ==================================================

def clean_text(value):
    return re.sub(
        r"\s+",
        " ",
        str(value or ""),
    ).strip()


def normalize_url(base, href):
    if not href:
        return ""

    url = urljoin(base, href)
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        return ""

    if parsed.netloc.lower() != urlparse(base).netloc.lower():
        return ""

    if parsed.path.lower().endswith((
        ".pdf", ".jpg", ".jpeg", ".png",
        ".gif", ".zip", ".xlsx", ".xls",
        ".docx", ".doc", ".pptx", ".ppt",
    )):
        return ""

    # フラグメントを除去し、URL末尾の不要な差を抑える
    return urlunparse((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        parsed.path or "/",
        parsed.params,
        parsed.query,
        "",
    ))


def is_same_domain(url, domain):
    return urlparse(url).netloc.lower() == domain.lower()


def fetch_page(url):
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "(compatible; YamaguchiLocalUpdate/2.0)"
            )
        },
    )

    with urlopen(request, timeout=20) as response:
        content_type = response.headers.get(
            "Content-Type",
            "",
        )

        if "html" not in content_type.lower():
            return ""

        raw = response.read(MAX_HTML_BYTES)

        charset_match = re.search(
            r"charset=([^\s;]+)",
            content_type,
            flags=re.IGNORECASE,
        )

        charset = (
            charset_match.group(1).strip("\"'")
            if charset_match
            else "utf-8"
        )

        try:
            return raw.decode(
                charset,
                errors="replace",
            )
        except LookupError:
            return raw.decode(
                "utf-8",
                errors="replace",
            )


def extract_page_text(parser):
    """
    main/article が取得できた場合は優先する。
    見つからない場合は通常テキストを使用する。
    """

    article_text = clean_text(
        " ".join(parser.article_parts)
    )

    full_text = clean_text(
        " ".join(parser.text_parts)
    )

    if len(article_text) >= 100:
        return article_text[:MAX_BODY_CHARS]

    return full_text[:MAX_BODY_CHARS]


def classify_text(title, body=""):
    """
    タイトルの分類を優先し、本文は補助的に使う。
    """

    title = clean_text(title)
    body = clean_text(body)

    title_categories = []
    combined_categories = []

    for category, keywords in KEYWORD_GROUPS.items():
        if any(keyword in title for keyword in keywords):
            title_categories.append(category)

        if any(
            keyword in (title + " " + body)
            for keyword in keywords
        ):
            combined_categories.append(category)

    # タイトルで判断できた場合はタイトルを優先
    if title_categories:
        return title_categories, "タイトル"

    if combined_categories:
        return combined_categories, "概要・要確認"

    return [], "分類要確認"


def extract_published_date(parser, body):
    """
    公開日として明示されたメタ情報を優先。
    本文中で最初に見つかった日付は公開日と断定しない。
    """

    for item in parser.meta_dates:
        value = clean_text(item.get("value"))

        if value:
            return value, "メタ情報"

    # 本文の日付は公開日と断定できないため空欄にする
    return "", "日付確認が必要"


def extract_area(text):
    text = clean_text(text)

    found = []

    for area in JAPAN_AREAS:
        if area in text and area not in found:
            found.append(area)

    return found


def is_relevant_page(title, body):
    categories, basis = classify_text(
        title,
        body,
    )

    return categories, basis


# ==================================================
# 候補ページの取得
# ==================================================

def inspect_candidate(
    target_url,
    link_title,
    source_name,
    source_page,
):
    article_title = clean_text(link_title)
    body = ""
    published_date = ""
    date_basis = "日付確認が必要"
    status = "未確認・公開禁止"

    try:
        html = fetch_page(target_url)

        if not html:
            return None

        parser = PageParser()
        parser.feed(html)

        article_title = (
            clean_text(" ".join(parser.title_parts))
            or article_title
        )

        body = extract_page_text(parser)
        print("本文取得確認:", target_url, "文字数:", len(body), "本文:", body[-500:])
        published_date, date_basis = (
            extract_published_date(parser, body)
        )

        categories, category_basis = classify_text(
            article_title,
            body,
        )

        if not categories:
            return None

        area = extract_area(
            article_title + " " + body
        )

        item_id = hashlib.sha256(
            target_url.encode("utf-8")
        ).hexdigest()[:16]

        return {
            "id": item_id,
            "title": article_title,
            "url": target_url,
            "source_name": source_name,
            "source_page": source_page,
            "category": categories,
            "category_basis": category_basis,
            "published_date": published_date,
            "date_basis": date_basis,
            "area": area,
            "body_excerpt": body[:1000],
            "checked_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "status": status,
        }

    except (
        URLError,
        HTTPError,
        TimeoutError,
        ValueError,
        OSError,
    ) as error:
        print(
            "候補取得失敗:",
            target_url,
            str(error)[:120],
        )

        return None


# ==================================================
# メイン処理
# ==================================================

def main():
    os.makedirs("data", exist_ok=True)

    checked_at = datetime.now(
        timezone.utc
    ).isoformat()

    source_checks = []
    candidates = []
    scanned_pages = []

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
        queued = {source["url"]}

        while queue and len(visited) < MAX_PAGES_PER_SOURCE:
            current_url = queue.pop(0)
            queued.discard(current_url)

            if current_url in visited:
                continue

            if not is_same_domain(
                current_url,
                source["domain"],
            ):
                continue

            visited.add(current_url)

            try:
                html = fetch_page(current_url)

                if not html:
                    continue

                parser = PageParser()
                parser.feed(html)

                page_title = clean_text(
                    " ".join(parser.title_parts)
                )

                page_text = extract_page_text(parser)

                scanned_pages.append({
                    "source_name": source["name"],
                    "title": page_title,
                    "url": current_url,
                    "checked_at": checked_at,
                })

                for link in parser.links:
                    title = clean_text(link["title"])

                    target_url = normalize_url(
                        current_url,
                        link["url"],
                    )

                    if not title or not target_url:
                        continue

                    if not is_same_domain(
                        target_url,
                        source["domain"],
                    ):
                        continue

                    path = urlparse(
                        target_url
                    ).path.lower()

                    should_follow = any(
                        word in path
                        for word in PRIORITY_WORDS
                    )

                    if (
                        should_follow
                        and target_url not in visited
                        and target_url not in queued
                        and len(visited) + len(queue)
                        < MAX_PAGES_PER_SOURCE
                    ):
                        queue.append(target_url)
                        queued.add(target_url)

                    categories, basis = classify_text(
                        title,
                        "",
                    )

                    if not categories:
                        continue

                    candidate = inspect_candidate(
                        target_url=target_url,
                        link_title=title,
                        source_name=source["name"],
                        source_page=current_url,
                    )

                    if candidate:
                        candidates.append(candidate)

                    time.sleep(REQUEST_DELAY)

                time.sleep(REQUEST_DELAY)

            except (
                URLError,
                HTTPError,
                TimeoutError,
                ValueError,
                OSError,
            ) as error:
                print(
                    "取得失敗:",
                    current_url,
                    str(error)[:150],
                )

        result["pages_scanned"] = len(visited)

        result["status"] = (
            "reachable"
            if visited
            else "check_needed"
        )

        result["note"] = (
            "ページ本文・リンク・候補ページを確認。"
            "公開日は明示的なメタ情報を優先。"
            "公開前に元記事を確認してください。"
        )

        source_checks.append(result)

    # URL単位で重複を整理
    unique = {}

    for item in candidates:
        url = item["url"]

        if url not in unique:
            unique[url] = item
            continue

        existing = unique[url]

        if (
            len(item.get("body_excerpt", ""))
            > len(existing.get("body_excerpt", ""))
        ):
            unique[url] = item

    output = {
        "generated_at": checked_at,
        "area": "山口県",
        "purpose": (
            "公式サイトから記事候補を抽出し、"
            "本文・公開日候補・分類・地域を記録"
        ),
        "note": (
            "公開日が明示されたメタ情報を優先します。"
            "本文内の日付を公開日と断定しません。"
            "地域を判定できない場合は空欄です。"
            "すべて未確認のため、自動公開しません。"
        ),
        "sources": source_checks,
        "scanned_pages": scanned_pages,
        "candidates": list(unique.values()),
    }

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            output,
            file,
            ensure_ascii=False,
            indent=2,
        )

    print("確認した情報源:", len(source_checks))
    print("調査したページ:", len(scanned_pages))
    print("記事候補:", len(unique))
    print("保存先:", OUTPUT_FILE)

    for item in unique.values():
        print(
            "-",
            item["category"],
            item["area"],
            item["title"],
            item["url"],
        )


if __name__ == "__main__":
    main()