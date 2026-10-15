import json
import os
import re
import hashlib
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse, urlunparse

OFFICIAL_FILE = "data/source_checks.json"
RSS_FILE = "data/rss_candidates.json"
OUTPUT_FILE = "data/drafts.json"

# 新しい情報を優先する期間
RECENT_DAYS = 30

# 記事候補として扱うカテゴリ
ALLOWED_CATEGORIES = {
    "新店・開店",
    "閉店",
    "移転",
    "リニューアル",
    "求人",
    "イベント",
}

def clean_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()

def normalize_url(url):
    url = clean_text(url)

    if not url:
        return ""

    try:
        parsed = urlparse(url)

        # URL末尾のスラッシュや追跡用パラメータなどを整理
        path = parsed.path.rstrip("/") or "/"

        return urlunparse((
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            "",
            "",
            "",
        ))
    except ValueError:
        return url

def parse_date(value):
    value = clean_text(value)

    if not value:
        return None

    try:
        dt = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc)

    except (TypeError, ValueError, OverflowError):
        pass

    match = re.search(
        r"(20\d{2})[年./-](\d{1,2})[月./-](\d{1,2})日?",
        value,
    )

    if match:
        try:
            return datetime(
                int(match.group(1)),
                int(match.group(2)),
                int(match.group(3)),
                tzinfo=timezone.utc,
            )
        except ValueError:
            return None

    return None

def load_json(path):
    if not os.path.exists(path):
        print("ファイルなし:", path)
        return {}

    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError) as error:
        print("読み込み失敗:", path, str(error))
        return {}

def get_official_candidates():
    data = load_json(OFFICIAL_FILE)
    results = []

    for item in data.get("candidates", []):
        title = clean_text(item.get("title"))
        url = clean_text(item.get("url"))

        if not title or not url:
            continue

        categories = item.get("category", [])

        if not isinstance(categories, list):
            categories = [categories] if categories else []

        categories = [
            clean_text(category)
            for category in categories
            if clean_text(category) in ALLOWED_CATEGORIES
        ]

        results.append({
            "title": title,
            "url": url,
            "source_name": clean_text(
                item.get("source_name")
            ),
            "source_url": url,
            "category": categories,
            "published_date": clean_text(
                item.get("published_date")
            ),
            "body_excerpt": clean_text(
                item.get("body_excerpt")
            )[:1500],
            "collection_method": "公式サイト",
        })

    return results

def get_rss_candidates():
    data = load_json(RSS_FILE)
    results = []

    for item in data.get("candidates", []):
        title = clean_text(item.get("title"))
        url = clean_text(item.get("url"))

        if not title or not url:
            continue

        categories = item.get("category", [])

        if not isinstance(categories, list):
            categories = [categories] if categories else []

        categories = [
            clean_text(category)
            for category in categories
            if clean_text(category) in ALLOWED_CATEGORIES
        ]

        results.append({
            "title": title,
            "url": url,
            "source_name": clean_text(
                item.get("source_name")
            ),
            "source_url": url,
            "category": categories,
            "published_date": clean_text(
                item.get("published_date")
            ),
            "body_excerpt": clean_text(
                item.get("description")
            )[:1500],
            "collection_method": "RSS",
        })

    return results

def make_draft(item):
    title = item["title"]
    url = item["url"]
    source = item["source_name"]
    categories = item["category"]
    published_date = item["published_date"]
    body = item["body_excerpt"]

    parsed_date = parse_date(published_date)
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=RECENT_DAYS)

    if parsed_date is None:
        freshness = "日付確認が必要"
    elif parsed_date > now + timedelta(days=1):
        freshness = "日付要確認"
    elif parsed_date < cutoff:
        freshness = "30日より前"
    else:
        freshness = "直近30日"

    if not categories:
        relevance = "分類要確認"
    else:
        relevance = "キーワードによる仮分類"

    summary = (
        "公開前に元記事を確認してください。"
        "記事タイトル、掲載日、地域、店舗名、"
        "営業状況などの事実確認が必要です。"
    )

    if not body:
        summary += " 本文の情報が不足しています。"

    draft_id = hashlib.sha256(
        normalize_url(url).encode("utf-8")
    ).hexdigest()[:16]

    return {
        "id": draft_id,
        "title": title,
        "suggested_headline": title,
        "category": categories,
        "published_date": published_date,
        "freshness": freshness,
        "source_name": source,
        "source_url": url,
        "body_excerpt": body,
        "draft_summary": summary,
        "relevance": relevance,
        "collection_method": item["collection_method"],
        "status": "未確認・公開禁止",
        "created_at": now.isoformat(),
    }

def main():
    os.makedirs("data", exist_ok=True)

    official = get_official_candidates()
    rss = get_rss_candidates()

    combined = official + rss
    unique = {}

    for item in combined:
        normalized = normalize_url(item["url"])

        if not normalized:
            continue

        if normalized not in unique:
            unique[normalized] = item
        else:
            # RSSと公式サイトで重複した場合は情報を補完
            existing = unique[normalized]

            if (
                not existing["body_excerpt"]
                and item["body_excerpt"]
            ):
                existing["body_excerpt"] = item["body_excerpt"]

            existing["category"] = sorted(
                set(
                    existing["category"]
                    + item["category"]
                )
            )

            if (
                not existing["source_name"]
                and item["source_name"]
            ):
                existing["source_name"] = item["source_name"]

    drafts = [
        make_draft(item)
        for item in unique.values()
    ]

    # 新しい情報、日付不明、古い情報の順で整理
    priority = {
        "直近30日": 0,
        "日付確認が必要": 1,
        "日付要確認": 2,
        "30日より前": 3,
    }

    drafts.sort(
        key=lambda item: (
            priority.get(item["freshness"], 4),
            item["title"],
        )
    )

    output = {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "draft_count": len(drafts),
        "note": (
            "公式サイトとRSSの候補を統合しています。"
            "分類・日付・本文は自動取得結果です。"
            "すべて未確認のため、内容を確認するまで"
            "公開しないでください。"
        ),
        "drafts": drafts,
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

    print("公式サイト候補:", len(official))
    print("RSS候補:", len(rss))
    print("統合後の下書き:", len(drafts))
    print("保存先:", OUTPUT_FILE)

if __name__ == "__main__":
    main()