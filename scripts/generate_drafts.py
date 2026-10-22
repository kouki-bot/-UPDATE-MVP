
import json
import re
import hashlib

from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode


# ==================================================
# 基本設定
# ==================================================

BASE_DIR = Path(__file__).resolve().parent.parent

OFFICIAL_FILE = BASE_DIR / "data" / "source_checks.json"
RSS_FILE = BASE_DIR / "data" / "rss_candidates.json"
OUTPUT_FILE = BASE_DIR / "data" / "drafts.json"

JST = timezone(timedelta(hours=9))
UTC = timezone.utc

RECENT_DAYS = 30

ALLOWED_CATEGORIES = {
    "新店・開店",
    "閉店",
    "移転",
    "リニューアル",
}

STORE_KEYWORDS = [
    "新店", "新店舗", "新規開店", "新規出店",
    "オープン", "開店", "開業", "出店",
    "グランドオープン", "プレオープン",
    "閉店", "営業終了", "閉業", "店じまい",
    "移転", "移転オープン", "移転先",
    "リニューアル", "改装オープン",
    "リニューアルオープン", "営業再開",
]

EXCLUDE_KEYWORDS = [
    "求人", "アルバイト募集", "スタッフ募集",
    "採用情報", "正社員募集",
    "イベント開催", "イベント情報",
    "マルシェ開催", "フェス開催",
    "祭り開催", "ワークショップ開催",
    "参加者募集", "出店者募集",
    "整備計画", "建設計画", "入札",
    "議会", "市長会見", "補助金",
]


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
        parsed = urlsplit(url)

        tracking_names = {
            "fbclid", "gclid", "yclid",
            "mc_cid", "mc_eid",
        }

        query = [
            (key, value)
            for key, value in parse_qsl(
                parsed.query,
                keep_blank_values=True,
            )
            if key.lower() not in tracking_names
            and not key.lower().startswith("utm_")
        ]

        return urlunsplit((
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path.rstrip("/") or "/",
            urlencode(query),
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
    if not path.exists():
        print("ファイルなし:", path)
        return {}

    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        return data if isinstance(data, dict) else {}

    except (json.JSONDecodeError, OSError) as error:
        print("読み込み失敗:", path, str(error))
        return {}


# ==================================================
# 対象記事の判定
# ==================================================

def normalize_categories(item):
    categories = item.get(
        "categories",
        item.get("category", []),
    )

    if not isinstance(categories, list):
        categories = [categories] if categories else []

    return list(dict.fromkeys(
        clean_text(category)
        for category in categories
        if clean_text(category) in ALLOWED_CATEGORIES
    ))


def is_store_news(title, body="", categories=None):
    """
    店舗の動きが確認できる記事だけを対象にする。
    イベント・求人・公共事業などは除外する。
    """

    title = clean_text(title)
    body = clean_text(body)

    if not title:
        return False

    # タイトルに除外語があれば原則として除外
    if any(keyword in title for keyword in EXCLUDE_KEYWORDS):
        # 店舗の閉店などが明確な場合は残す
        if not any(keyword in title for keyword in [
            "新店", "新店舗", "オープン", "開店",
            "閉店", "移転", "リニューアル",
        ]):
            return False

    # タイトルで店舗ニュースを判定
    if any(keyword in title for keyword in STORE_KEYWORDS):
        return True

    # カテゴリーが許可対象でも、タイトルに店舗の動きが
    # なければ自動的には採用しない
    return False


# ==================================================
# 候補データの取得
# ==================================================

def convert_candidate(item, method, source_priority):
    title = clean_text(item.get("title"))
    url = clean_text(item.get("url"))

    if not title or not url:
        return None

    body = clean_text(
        item.get("body_excerpt", item.get("description", ""))
    )[:1500]

    categories = normalize_categories(item)

    if not is_store_news(title, body, categories):
        return None

    # タイトルの語句からカテゴリーを補完
    detected = []

    keyword_map = {
        "新店・開店": [
            "新店", "新店舗", "新規開店", "新規出店",
            "オープン", "開店", "開業", "出店",
            "グランドオープン", "プレオープン",
        ],
        "閉店": [
            "閉店", "営業終了", "閉業", "店じまい",
        ],
        "移転": [
            "移転",
        ],
        "リニューアル": [
            "リニューアル", "改装オープン",
            "営業再開", "改装",
        ],
    }

    for category, keywords in keyword_map.items():
        if any(keyword in title for keyword in keywords):
            detected.append(category)

    categories = list(dict.fromkeys(categories + detected))

    if not categories:
        return None

    area = item.get("area", [])

    if not isinstance(area, list):
        area = [area] if area else []

    return {
        "title": title,
        "url": url,
        "normalized_url": normalize_url(url),
        "source_name": clean_text(item.get("source_name")),
        "category": categories,
        "published_date": clean_text(item.get("published_date")),
        "body_excerpt": body,
        "collection_method": method,
        "category_basis": clean_text(item.get("category_basis")),
        "area": area,
        "source_priority": source_priority,
    }


def get_official_candidates():
    data = load_json(OFFICIAL_FILE)
    results = []

    for item in data.get("candidates", []):
        candidate = convert_candidate(item, "公式サイト", 1)

        if candidate:
            results.append(candidate)

    return results


def get_rss_candidates():
    data = load_json(RSS_FILE)
    results = []

    for item in data.get("candidates", []):
        candidate = convert_candidate(item, "RSS", 2)

        if candidate:
            results.append(candidate)

    return results


# ==================================================
# 鮮度・優先順位
# ==================================================

def get_freshness(published_date):
    parsed = parse_date(published_date)

    if parsed is None:
        return "日付確認が必要", None

    age_days = (now_jst().date() - parsed.date()).days

    if age_days < -1:
        return "未来日付・要確認", age_days

    age_days = max(age_days, 0)

    if age_days <= RECENT_DAYS:
        return "直近30日", age_days

    if age_days <= 90:
        return "31〜90日前", age_days

    return "90日より前", age_days


def get_priority(categories):
    if "閉店" in categories or "新店・開店" in categories:
        return 1

    if "移転" in categories or "リニューアル" in categories:
        return 2

    return 5


# ==================================================
# 重複整理
# ==================================================

def merge_candidates(combined):
    unique = {}

    for item in combined:
        url = item.get("normalized_url") or normalize_url(item["url"])

        if not url:
            continue

        if url not in unique:
            unique[url] = item.copy()
            continue

        existing = unique[url]

        # 公式サイトの情報を優先
        if item.get("source_priority", 2) < existing.get("source_priority", 2):
            preferred, other = item, existing
        else:
            preferred, other = existing, item

        merged = preferred.copy()

        merged["category"] = list(dict.fromkeys(
            preferred.get("category", []) + other.get("category", [])
        ))

        merged["area"] = list(dict.fromkeys(
            preferred.get("area", []) + other.get("area", [])
        ))

        if not merged.get("body_excerpt"):
            merged["body_excerpt"] = other.get("body_excerpt", "")

        if not merged.get("published_date"):
            merged["published_date"] = other.get("published_date", "")

        unique[url] = merged

    return list(unique.values())


# ==================================================
# 下書き生成
# ==================================================

def make_draft(item):
    title = item["title"]
    url = item["url"]
    categories = item["category"]
    published_date = item["published_date"]
    body = item["body_excerpt"]

    freshness, age_days = get_freshness(published_date)
    priority = get_priority(categories)

    if item.get("category_basis") == "タイトル":
        relevance = "タイトルによる仮分類・要確認"
    else:
        relevance = "店舗ニュース候補・要確認"

    if freshness == "直近30日":
        freshness_note = "比較的新しい情報です。掲載前に現状を確認してください。"
    elif freshness == "31〜90日前":
        freshness_note = "公開から31〜90日経過しています。現在も有効か確認してください。"
    elif freshness == "90日より前":
        freshness_note = "古い情報です。新着記事としての掲載は慎重に判断してください。"
    elif freshness == "未来日付・要確認":
        freshness_note = "日付が未来になっています。元記事の日付を確認してください。"
    else:
        freshness_note = "公開日を確認できていません。元記事で確認してください。"

    summary = (
        "【公開前の確認事項】"
        "店舗名・所在地・開店日または閉店日・"
        "現在の営業状況・情報源を確認してください。"
        + freshness_note
    )

    if not body:
        summary += " 元記事の概要を取得できていないため、本文の確認が必要です。"

    draft_id = hashlib.sha256(
        normalize_url(url).encode("utf-8")
    ).hexdigest()[:16]

    return {
        "id": draft_id,
        "title": title,
        "suggested_headline": title,
        "category": categories,
        "priority": priority,
        "published_date": published_date,
        "freshness": freshness,
        "age_days": age_days,
        "area": item.get("area", []),
        "source_name": item.get("source_name", ""),
        "source_url": url,
        "body_excerpt": body,
        "draft_summary": summary,
        "relevance": relevance,
        "collection_method": item.get("collection_method", ""),
        "status": "未確認・公開禁止",
        "created_at": now_jst().isoformat(),
    }


def draft_sort_key(item):
    freshness_order = {
        "直近30日": 0,
        "31〜90日前": 1,
        "日付確認が必要": 2,
        "未来日付・要確認": 3,
        "90日より前": 4,
    }

    parsed = parse_date(item.get("published_date", ""))
    timestamp = parsed.timestamp() if parsed else 0

    return (
        freshness_order.get(item.get("freshness", ""), 5),
        item.get("priority", 5),
        -timestamp,
        item.get("title", ""),
    )


# ==================================================
# メイン処理
# ==================================================

def main():
    official = get_official_candidates()
    rss = get_rss_candidates()

    combined = official + rss
    unique_candidates = merge_candidates(combined)

    drafts = [make_draft(item) for item in unique_candidates]
    drafts.sort(key=draft_sort_key)

    freshness_counts = {}
    category_counts = {}

    for draft in drafts:
        freshness = draft["freshness"]
        freshness_counts[freshness] = freshness_counts.get(freshness, 0) + 1

        for category in draft["category"]:
            category_counts[category] = category_counts.get(category, 0) + 1

    output = {
        "generated_at": now_jst().isoformat(),
        "draft_count": len(drafts),
        "recent_draft_count": freshness_counts.get("直近30日", 0),
        "freshness_counts": freshness_counts,
        "category_counts": category_counts,
        "note": (
            "対象は新店・開店、閉店、移転、リニューアルです。"
            "自動分類結果は未確認です。"
            "すべて未確認・公開禁止であり、確認前に公開しないでください。"
        ),
        "drafts": drafts,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT_FILE.open("w", encoding="utf-8") as file:
        json.dump(output, file, ensure_ascii=False, indent=2)

    print("公式サイト候補:", len(official))
    print("RSS候補:", len(rss))
    print("統合後の下書き:", len(drafts))
    print("直近30日の下書き:", output["recent_draft_count"])
    print("カテゴリー別:", category_counts)
    print("鮮度別:", freshness_counts)
    print("保存先:", OUTPUT_FILE)


if __name__ == "__main__":
    main()
