import json
import os
import re
import hashlib

from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse, urlunparse


# ==================================================
# 基本設定
# ==================================================

OFFICIAL_FILE = "data/source_checks.json"
RSS_FILE = "data/rss_candidates.json"
OUTPUT_FILE = "data/drafts.json"

JST = timezone(timedelta(hours=9))
UTC = timezone.utc

RECENT_DAYS = 30

# 求人は収集対象から除外
ALLOWED_CATEGORIES = {
    "新店・開店",
    "閉店",
    "移転",
    "リニューアル",
    "イベント",
    "新施設・地域の動き",
}


# ==================================================
# 共通処理
# ==================================================

def now_jst():
    return datetime.now(JST)


def clean_text(value):
    return re.sub(
        r"\s+",
        " ",
        str(value or ""),
    ).strip()


def normalize_url(url):
    url = clean_text(url)

    if not url:
        return ""

    try:
        parsed = urlparse(url)

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
            dt = dt.replace(tzinfo=UTC)

        return dt.astimezone(JST)

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
                tzinfo=JST,
            )

        except ValueError:
            return None

    return None


def load_json(path):
    if not os.path.exists(path):
        print("ファイルなし:", path)
        return {}

    try:
        with open(
            path,
            "r",
            encoding="utf-8",
        ) as file:
            return json.load(file)

    except (json.JSONDecodeError, OSError) as error:
        print(
            "読み込み失敗:",
            path,
            str(error),
        )
        return {}


def normalize_categories(item):
    """
    新旧両方のデータ形式に対応する。

    旧形式: category
    新形式: categories
    """

    categories = item.get(
        "categories",
        item.get("category", []),
    )

    if not isinstance(categories, list):
        categories = (
            [categories]
            if categories
            else []
        )

    result = []

    for category in categories:
        category = clean_text(category)

        if (
            category in ALLOWED_CATEGORIES
            and category not in result
        ):
            result.append(category)

    return result


# ==================================================
# 公式サイト候補の取得
# ==================================================

def get_official_candidates():
    data = load_json(OFFICIAL_FILE)
    results = []

    for item in data.get("candidates", []):
        title = clean_text(item.get("title"))
        url = clean_text(item.get("url"))

        if not title or not url:
            continue

        categories = normalize_categories(item)

        results.append({
            "title": title,
            "url": url,
            "source_name": clean_text(
                item.get("source_name")
            ),
            "category": categories,
            "published_date": clean_text(
                item.get("published_date")
            ),
            "body_excerpt": clean_text(
                item.get("body_excerpt")
            )[:1500],
            "collection_method": "公式サイト",
            "category_basis": clean_text(
                item.get("category_basis")
            ),
            "area": item.get("area", []),
            "source_priority": 1,
        })

    return results


# ==================================================
# RSS候補の取得
# ==================================================

def get_rss_candidates():
    data = load_json(RSS_FILE)
    results = []

    for item in data.get("candidates", []):
        title = clean_text(item.get("title"))
        url = clean_text(item.get("url"))

        if not title or not url:
            continue

        categories = normalize_categories(item)

        results.append({
            "title": title,
            "url": url,
            "source_name": clean_text(
                item.get("source_name")
            ),
            "category": categories,
            "published_date": clean_text(
                item.get("published_date")
            ),
            "body_excerpt": clean_text(
                item.get("description")
            )[:1500],
            "collection_method": "RSS",
            "category_basis": clean_text(
                item.get("category_basis")
            ),
            "area": item.get("area", []),
            "source_priority": 2,
        })

    return results


# ==================================================
# 鮮度判定
# ==================================================

def get_freshness(published_date):
    parsed_date = parse_date(published_date)

    if parsed_date is None:
        return "日付確認が必要", None

    now = now_jst()

    age_days = (
        now.date() - parsed_date.date()
    ).days

    if age_days < -1:
        return "未来日付・要確認", age_days

    if age_days < 0:
        age_days = 0

    if age_days <= RECENT_DAYS:
        return "直近30日", age_days

    if age_days <= 90:
        return "31〜90日前", age_days

    return "90日より前", age_days


# ==================================================
# 優先順位
# ==================================================

def get_priority(categories):
    if any(
        category in categories
        for category in [
            "新店・開店",
            "閉店",
        ]
    ):
        return 1

    if any(
        category in categories
        for category in [
            "移転",
            "リニューアル",
        ]
    ):
        return 2

    if "イベント" in categories:
        return 3

    if "新施設・地域の動き" in categories:
        return 4

    return 5


# ==================================================
# 下書き生成
# ==================================================

def make_draft(item):
    title = item["title"]
    url = item["url"]
    source = item["source_name"]
    categories = item["category"]
    published_date = item["published_date"]
    body = item["body_excerpt"]

    freshness, age_days = get_freshness(
        published_date
    )

    priority = get_priority(categories)

    if not categories:
        relevance = "分類要確認"
    elif item.get("category_basis") == "概要・要確認":
        relevance = "概要による仮分類・要確認"
    elif item.get("category_basis") == "タイトル":
        relevance = "タイトルによる仮分類"
    else:
        relevance = "自動分類・要確認"

    if freshness == "直近30日":
        freshness_note = (
            "比較的新しい情報ですが、"
            "公開前に現在の状況を確認してください。"
        )

    elif freshness == "31〜90日前":
        freshness_note = (
            "公開から31〜90日経過しています。"
            "現在も有効な情報か確認してください。"
        )

    elif freshness == "90日より前":
        freshness_note = (
            "古い情報です。原則として新着記事にせず、"
            "現在の状況を再確認してください。"
        )

    elif freshness == "未来日付・要確認":
        freshness_note = (
            "公開日が未来になっています。"
            "日付と情報源を確認してください。"
        )

    else:
        freshness_note = (
            "公開日を確認できていません。"
            "元記事で日付を確認してください。"
        )

    summary = (
        "【公開前の確認事項】"
        "店舗名・所在地・開店日・営業状況を"
        "元記事や公式情報で確認してください。"
        + freshness_note
    )

    if not body:
        summary += (
            " 元記事の説明文を取得できていないため、"
            "本文の追加確認が必要です。"
        )

    normalized_url = normalize_url(url)

    draft_id = hashlib.sha256(
        normalized_url.encode("utf-8")
    ).hexdigest()[:16]

    area = item.get("area", [])

    if not isinstance(area, list):
        area = [area] if area else []

    return {
        "id": draft_id,
        "title": title,
        "suggested_headline": title,
        "category": categories,
        "priority": priority,
        "published_date": published_date,
        "freshness": freshness,
        "age_days": age_days,
        "area": area,
        "source_name": source,
        "source_url": url,
        "body_excerpt": body,
        "draft_summary": summary,
        "relevance": relevance,
        "collection_method": item["collection_method"],
        "status": "未確認・公開禁止",
        "created_at": now_jst().isoformat(),
    }


# ==================================================
# 重複整理
# ==================================================

def merge_candidates(combined):
    unique = {}

    for item in combined:
        normalized = normalize_url(item["url"])

        if not normalized:
            continue

        if normalized not in unique:
            unique[normalized] = item
            continue

        existing = unique[normalized]

        # 公式サイト由来の情報を優先
        if (
            item.get("source_priority", 2)
            < existing.get("source_priority", 2)
        ):
            preferred = item
            other = existing

        else:
            preferred = existing
            other = item

        merged = dict(preferred)

        # 本文が不足している場合は補完
        if not merged.get("body_excerpt"):
            merged["body_excerpt"] = (
                other.get("body_excerpt", "")
            )

        # カテゴリーは許可されたものだけ統合
        merged["category"] = list(
            dict.fromkeys(
                preferred.get("category", [])
                + other.get("category", [])
            )
        )

        # 地域を統合
        merged["area"] = list(
            dict.fromkeys(
                preferred.get("area", [])
                + other.get("area", [])
            )
        )

        # 日付が欠けていれば補完
        if not merged.get("published_date"):
            merged["published_date"] = (
                other.get("published_date", "")
            )

        unique[normalized] = merged

    return list(unique.values())


# ==================================================
# 並び替え
# ==================================================

def draft_sort_key(item):
    freshness_order = {
        "直近30日": 0,
        "31〜90日前": 1,
        "日付確認が必要": 2,
        "未来日付・要確認": 3,
        "90日より前": 4,
    }

    parsed_date = parse_date(
        item.get("published_date", "")
    )

    timestamp = (
        parsed_date.timestamp()
        if parsed_date
        else 0
    )

    return (
        freshness_order.get(
            item.get("freshness", ""),
            5,
        ),
        item.get("priority", 5),
        -timestamp,
        item.get("title", ""),
    )


# ==================================================
# メイン処理
# ==================================================

def main():
    os.makedirs("data", exist_ok=True)

    official = get_official_candidates()
    rss = get_rss_candidates()

    combined = official + rss

    unique_candidates = merge_candidates(
        combined
    )

    drafts = [
        make_draft(item)
        for item in unique_candidates
    ]

    drafts.sort(
        key=draft_sort_key
    )

    freshness_counts = {}

    for draft in drafts:
        freshness = draft["freshness"]

        freshness_counts[freshness] = (
            freshness_counts.get(freshness, 0) + 1
        )

    category_counts = {}

    for draft in drafts:
        for category in draft["category"]:
            category_counts[category] = (
                category_counts.get(category, 0) + 1
            )

    output = {
        "generated_at": now_jst().isoformat(),
        "draft_count": len(drafts),
        "recent_draft_count": freshness_counts.get(
            "直近30日",
            0,
        ),
        "freshness_counts": freshness_counts,
        "category_counts": category_counts,
        "note": (
            "公式サイトとRSSの候補を統合しています。"
            "求人情報は対象外です。"
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
    print("直近30日の下書き:", output["recent_draft_count"])
    print("カテゴリー別:", category_counts)
    print("鮮度別:", freshness_counts)
    print("保存先:", OUTPUT_FILE)


if __name__ == "__main__":
    main()