import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

BASE_DIR = Path(__file__).resolve().parent.parent
OFFICIAL_FILE = BASE_DIR / "data" / "source_checks.json"
RSS_FILE = BASE_DIR / "data" / "rss_candidates.json"
OUTPUT_FILE = BASE_DIR / "data" / "drafts.json"
JST = timezone(timedelta(hours=9))
UTC = timezone.utc
RECENT_DAYS = 30
MAX_DRAFT_AGE_DAYS = 90
ALLOWED_CATEGORIES = {"新店・開店", "閉店", "移転", "リニューアル"}

STORE_KEYWORDS = [
    "新店", "新店舗", "新規開店", "新規出店", "オープン", "開店", "開業", "出店",
    "グランドオープン", "プレオープン", "閉店", "営業終了", "閉業", "店じまい",
    "移転", "移転オープン", "移転先", "リニューアル", "改装オープン", "リニューアルオープン",
    "営業再開", "改装",
]
EXCLUDE_KEYWORDS = [
    "求人", "アルバイト募集", "スタッフ募集", "採用情報", "正社員募集", "イベント開催",
    "イベント情報", "マルシェ開催", "フェス開催", "祭り開催", "ワークショップ開催",
    "参加者募集", "出店者募集", "整備計画", "建設計画", "入札", "議会", "市長会見",
    "補助金", "公式ウェブサイト", "公式サイト", "ホームページをリニューアル",
]
PUBLIC_KEYWORDS = [
    "市役所", "県庁", "図書館", "小学校", "中学校", "高校", "公民館", "体育館",
    "庁舎", "公共施設", "交流拠点施設", "郷土館", "体験交流公園", "子育て支援拠点",
]

def now_jst():
    return datetime.now(JST)

def clean_text(value):
    return re.sub(r"\\s+", " ", str(value or "")).strip()

def normalize_url(url):
    url = clean_text(url)
    if not url:
        return ""
    try:
        p = urlsplit(url)
        tracking = {"fbclid", "gclid", "yclid", "mc_cid", "mc_eid"}
        query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
                 if k.lower() not in tracking and not k.lower().startswith("utm_")]
        return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/") or "/", urlencode(query), ""))
    except ValueError:
        return url

def parse_date(value):
    value = clean_text(value)
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(JST)
    except (TypeError, ValueError, OverflowError):
        pass
    match = re.search(r"(20\\d{2})[年./-](\\d{1,2})[月./-](\\d{1,2})日?", value)
    if match:
        try:
            return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)), tzinfo=JST)
        except ValueError:
            return None
    return None

def load_json(path):
    if not path.exists():
        print("ファイルなし:", path)
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError) as error:
        print("読み込み失敗:", path, str(error))
        return {}

def normalize_categories(item):
    categories = item.get("categories", item.get("category", []))
    if not isinstance(categories, list):
        categories = [categories] if categories else []
    return list(dict.fromkeys(clean_text(x) for x in categories if clean_text(x) in ALLOWED_CATEGORIES))

def detect_categories(title):
    mapping = {
        "新店・開店": ["新店", "新店舗", "新規開店", "新規出店", "オープン", "開店", "開業", "出店", "グランドオープン", "プレオープン"],
        "閉店": ["閉店", "営業終了", "閉業", "店じまい"],
        "移転": ["移転"],
        "リニューアル": ["リニューアル", "改装オープン", "営業再開", "改装"],
    }
    return [cat for cat, words in mapping.items() if any(w in title for w in words)]

def is_store_news(title):
    if not title or not detect_categories(title):
        return False
    # 店舗の動きが明確なタイトルだけを対象にし、公共施設等は原則除外。
    if any(w in title for w in EXCLUDE_KEYWORDS):
        if not any(w in title for w in ["新店", "新店舗", "オープン", "開店", "閉店", "移転", "リニューアル"]):
            return False
    if any(w in title for w in PUBLIC_KEYWORDS):
        if not any(w in title for w in ["店舗", "店", "カフェ", "飲食店", "美容室", "サロン", "商業施設"]):
            return False
    if any(w in title for w in ["ウェブサイト", "ホームページ", "公式サイト"]):
        return False
    return True

def convert_candidate(item, method, source_priority):
    title, url = clean_text(item.get("title")), clean_text(item.get("url"))
    if not title or not url or not is_store_news(title):
        return None
    body = clean_text(item.get("body_excerpt", item.get("description", "")))[:1500]
    categories = list(dict.fromkeys(normalize_categories(item) + detect_categories(title)))
    categories = [c for c in categories if c in ALLOWED_CATEGORIES]
    if not categories:
        return None
    area = item.get("area", [])
    if not isinstance(area, list):
        area = [area] if area else []
    return {
        "title": title, "url": url, "normalized_url": normalize_url(url),
        "source_name": clean_text(item.get("source_name")), "category": categories,
        "published_date": clean_text(item.get("published_date")), "body_excerpt": body,
        "collection_method": method, "category_basis": clean_text(item.get("category_basis")),
        "area": area,
        "area_status": clean_text(item.get("area_status")) or "地域は未確認。配信元の対象地域を店舗所在地として扱わない。",
        "source_priority": source_priority,
    }

def get_official_candidates():
    data = load_json(OFFICIAL_FILE)
    return [x for item in data.get("candidates", [])
            if (x := convert_candidate(item, "公式サイト", 1))]

def get_rss_candidates():
    data = load_json(RSS_FILE)
    return [x for item in data.get("candidates", [])
            if (x := convert_candidate(item, "RSS", 2))]

def get_freshness(date_value):
    parsed = parse_date(date_value)
    if parsed is None:
        return "日付確認が必要", None
    age = (now_jst().date() - parsed.date()).days
    if age < -1:
        return "未来日付・要確認", age
    age = max(age, 0)
    if age <= RECENT_DAYS:
        return "直近30日", age
    if age <= MAX_DRAFT_AGE_DAYS:
        return "31〜90日前", age
    return "90日より前", age

def get_priority(categories):
    if "閉店" in categories or "新店・開店" in categories:
        return 1
    if "移転" in categories or "リニューアル" in categories:
        return 2
    return 5

def merge_candidates(items):
    unique = {}
    for item in items:
        key = item.get("normalized_url") or normalize_url(item.get("url", ""))
        if not key:
            continue
        if key not in unique:
            unique[key] = item.copy()
            continue
        old = unique[key]
        if item.get("source_priority", 2) < old.get("source_priority", 2):
            preferred, other = item, old
        else:
            preferred, other = old, item
        merged = preferred.copy()
        merged["category"] = list(dict.fromkeys(preferred.get("category", []) + other.get("category", [])))
        merged["area"] = list(dict.fromkeys(preferred.get("area", []) + other.get("area", [])))
        if not merged.get("body_excerpt"):
            merged["body_excerpt"] = other.get("body_excerpt", "")
        if not merged.get("published_date") and other.get("published_date"):
            merged["published_date"] = other.get("published_date", "")
        unique[key] = merged
    return list(unique.values())

def make_draft(item):
    date_value = item.get("published_date", "")
    freshness, age = get_freshness(date_value)
    if freshness == "直近30日":
        note = "直近30日の記事です。掲載前に現在の営業状況を確認してください。"
    elif freshness == "31〜90日前":
        note = "公開から31〜90日経過しています。現在も有効か確認してください。"
    elif freshness == "90日より前":
        note = "90日より前の記事です。新着候補から除外し、必要な場合のみ別途確認してください。"
    elif freshness == "未来日付・要確認":
        note = "日付が未来になっています。元記事の日付を確認してください。"
    else:
        note = "公開日を確認できていません。元記事で確認してください。"
    summary = "【公開前の確認事項】店舗名・所在地・開店日または閉店日・現在の営業状況・情報源を確認してください。" + note
    if not item.get("body_excerpt"):
        summary += " 元記事の概要を取得できていないため、本文の確認が必要です。"
    url = item["url"]
    return {
        "id": hashlib.sha256(normalize_url(url).encode("utf-8")).hexdigest()[:16],
        "title": item["title"], "suggested_headline": item["title"],
        "category": item["category"], "priority": get_priority(item["category"]),
        "published_date": date_value, "freshness": freshness, "age_days": age,
        "area": item.get("area", []), "area_status": item.get("area_status", "地域は未確認。所在地の確認が必要です。"),
        "source_name": item.get("source_name", ""), "source_url": url,
        "body_excerpt": item.get("body_excerpt", ""), "draft_summary": summary,
        "relevance": "店舗ニュース候補・要確認",
        "collection_method": item.get("collection_method", ""),
        "status": "未確認・公開禁止", "created_at": now_jst().isoformat(),
    }

def sort_key(item):
    order = {"直近30日": 0, "31〜90日前": 1, "日付確認が必要": 2, "未来日付・要確認": 3, "90日より前": 4}
    date = parse_date(item.get("published_date", ""))
    return (order.get(item.get("freshness", ""), 5), item.get("priority", 5),
            -(date.timestamp() if date else 0), item.get("title", ""))

def main():
    official, rss = get_official_candidates(), get_rss_candidates()
    unique = merge_candidates(official + rss)
    all_drafts = [make_draft(x) for x in unique]
    old_count = sum(1 for x in all_drafts if x["freshness"] == "90日より前")
    # 古い記事は通常候補から除外。日付不明は確認用に残す。
    drafts = [x for x in all_drafts if x["freshness"] != "90日より前"]
    drafts.sort(key=sort_key)
    freshness_counts, category_counts = {}, {}
    for draft in drafts:
        f = draft["freshness"]
        freshness_counts[f] = freshness_counts.get(f, 0) + 1
        for cat in draft["category"]:
            category_counts[cat] = category_counts.get(cat, 0) + 1
    output = {
        "generated_at": now_jst().isoformat(), "draft_count": len(drafts),
        "recent_draft_count": freshness_counts.get("直近30日", 0),
        "excluded_old_count": old_count, "freshness_counts": freshness_counts,
        "category_counts": category_counts,
        "note": "対象は新店・開店、閉店、移転、リニューアルです。90日より前の記事は通常の下書き候補から除外。日付不明は確認用に保持。すべて未確認・公開禁止です。配信元の対象地域は店舗所在地を保証しません。",
        "drafts": drafts,
    }
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print("公式サイト候補:", len(official), "RSS候補:", len(rss))
    print("統合後:", len(unique), "下書き候補:", len(drafts), "90日より前の除外:", old_count)
    print("直近30日:", output["recent_draft_count"], "カテゴリー:", category_counts)
    print("鮮度:", freshness_counts, "保存先:", OUTPUT_FILE)

if __name__ == "__main__":
    main()
