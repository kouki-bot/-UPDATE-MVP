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


YAMAGUCHI_MUNICIPALITIES = [
    "山陽小野田市", "周防大島町", "田布施町", "上関町", "平生町", "和木町", "阿武町",
    "下関市", "宇部市", "山口市", "萩市", "防府市", "下松市", "岩国市", "光市",
    "長門市", "柳井市", "美祢市", "周南市",
]

def extract_municipality_candidates(title, body_excerpt):
    """タイトル・本文抜粋に明記された山口県内市町名のみを候補として抽出。推測はしない。"""
    text = clean_text(f"{title} {body_excerpt}")
    found = []
    # まず市町名の正式表記を優先する。
    for name in YAMAGUCHI_MUNICIPALITIES:
        if name in text:
            found.append(name)
    # 接尾辞なしの地名は、場所を示す語が近くにある場合のみ候補にする。
    aliases = {
        "山陽小野田": "山陽小野田市", "周防大島": "周防大島町",
        "田布施": "田布施町", "上関": "上関町", "平生": "平生町",
        "和木": "和木町", "阿武": "阿武町", "下関": "下関市",
        "宇部": "宇部市", "山口": "山口市", "萩": "萩市",
        "防府": "防府市", "下松": "下松市", "岩国": "岩国市",
        "長門": "長門市", "柳井": "柳井市", "美祢": "美祢市", "周南": "周南市",
        "光": "光市",
    }
    # 市町名の直後に駅名・施設名などが続く記事見出しにも対応する。
    location_context = r"(?:市内|町内|市|町|駅(?:前|周辺|近く)?|周辺|市街地|商店街|で開店|に開店|でオープン|にオープン|で閉店|に閉店|の店舗|の店|にある|に誕生|で営業|新川駅|駅)"
    for alias, official in aliases.items():
        if official in found:
            continue
        # 「宇部新川駅」のように、市町名の後ろに駅名が直結するケースを拾う。
        # 「山口」は県名・新聞名などを除外し、駅名/場所表現に限定する。
        if alias == "山口":
            pattern = r"山口(?!県|新聞|放送|銀行|合同庁舎)(?:" + location_context + r")"
        else:
            pattern = re.escape(alias) + r"(?:" + location_context + r")"
        if re.search(pattern, text):
            found.append(official)
    # 長い地名を先にし、順序を安定させる。
    # 代表的な駅名を使った補完。所在地の確定ではなく、確認用候補として扱う。
    station_aliases = {
        "宇部新川駅": "宇部市", "山口駅": "山口市", "下関駅": "下関市",
        "徳山駅": "周南市", "新山口駅": "山口市", "防府駅": "防府市",
        "岩国駅": "岩国市", "下松駅": "下松市", "柳井駅": "柳井市",
        "長門市駅": "長門市", "美祢駅": "美祢市", "厚狭駅": "山陽小野田市",
        "小野田駅": "山陽小野田市", "光駅": "光市", "萩駅": "萩市",
    }
    for station, municipality in station_aliases.items():
        if station in text and municipality not in found:
            found.append(municipality)

    return sorted(set(found), key=lambda x: YAMAGUCHI_MUNICIPALITIES.index(x))

def now_jst():
    return datetime.now(JST)

def clean_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()

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
    match = re.search(r"(20\d{2})[年./-](\d{1,2})[月./-](\d{1,2})日?", value)
    if match:
        try:
            return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)), tzinfo=JST)
        except ValueError:
            return None
    return None

def date_from_title(title):
    """タイトルに含まれる YYYY/MM/DD・YYYY年M月D日 を日付候補として抽出する。"""
    title = clean_text(title)
    match = re.search(r"(20\d{2})[年./-](\d{1,2})[月./-](\d{1,2})日?", title)
    if not match:
        return None
    try:
        return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)), tzinfo=JST)
    except ValueError:
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
    body = clean_text(item.get("body_excerpt") or item.get("description", ""))[:1500]
    categories = list(dict.fromkeys(normalize_categories(item) + detect_categories(title)))
    categories = [c for c in categories if c in ALLOWED_CATEGORIES]
    if not categories:
        return None
    area = item.get("area", [])
    if not isinstance(area, list):
        area = [area] if area else []
    date_value = clean_text(item.get("published_date"))
    if not parse_date(date_value):
        title_date = date_from_title(title)
        if title_date:
            date_value = title_date.isoformat()
    return {
        "title": title, "url": url, "normalized_url": normalize_url(url),
        "source_name": clean_text(item.get("source_name")), "category": categories,
        "published_date": date_value, "body_excerpt": body,
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

def title_fingerprint(title):
    """タイトル比較用。日付・媒体名・記号などを除き、比較しやすくする。"""
    value = clean_text(title).lower()
    value = re.sub(r"20\d{2}[年./-]\d{1,2}[月./-]\d{1,2}日?", " ", value)
    value = re.sub(r"[【】\[\]（）()「」『』〈〉《》・：:／/｜|—―\-〜～…!！?？,.，。]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value

def event_terms(item):
    """重複判定用の店舗・イベント語。日付や一般的なニュース語は除く。"""
    title = title_fingerprint(item.get("title", ""))
    stop_words = [
        "山口県", "山口市", "宇部市", "下関市", "周南市", "防府市", "岩国市",
        "オープン", "開店", "新店", "新店舗", "新規出店", "グランドオープン",
        "プレオープン", "閉店", "営業終了", "閉業", "店じまい", "移転",
        "リニューアル", "改装", "営業再開", "のお知らせ", "について", "します",
        "しました", "予定", "決定", "へ", "が", "で", "に", "の",
    ]
    for word in stop_words:
        title = title.replace(word, " ")
    return re.sub(r"\s+", " ", title).strip()

def same_event(a, b):
    """誤統合を避けるため、タイトルの一致度が高い場合だけ同一候補とみなす。"""
    if set(a.get("category", [])) and set(b.get("category", [])):
        if not (set(a["category"]) & set(b["category"])):
            return False
    ta = title_fingerprint(a.get("title", ""))
    tb = title_fingerprint(b.get("title", ""))
    if not ta or not tb:
        return False
    if ta == tb or ta in tb or tb in ta:
        return True
    ea, eb = event_terms(a), event_terms(b)
    if len(ea) >= 5 and len(eb) >= 5 and (ea in eb or eb in ea):
        return True
    # タイトル全体の共通部分が十分に長く、短い方の大半を占める場合のみ統合
    shorter, longer = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    if len(shorter) >= 10 and shorter in longer:
        return True
    return False

def merge_candidates(items):
    """URL重複に加え、タイトルが明確に一致する別媒体記事も統合する。"""
    merged_items = []
    for item in items:
        normalized = item.get("normalized_url") or normalize_url(item.get("url", ""))
        if not normalized:
            continue
        candidate = item.copy()
        candidate["normalized_url"] = normalized
        candidate["source_urls"] = [{
            "source_name": candidate.get("source_name", ""),
            "url": candidate.get("url", ""),
        }]
        match_index = None
        for index, old in enumerate(merged_items):
            old_urls = {old.get("normalized_url", "")}
            old_urls.update(normalize_url(s.get("url", "")) for s in old.get("source_urls", []))
            if normalized in old_urls or same_event(candidate, old):
                match_index = index
                break
        if match_index is None:
            merged_items.append(candidate)
            continue

        old = merged_items[match_index]
        if candidate.get("source_priority", 2) < old.get("source_priority", 2):
            preferred, other = candidate, old
        else:
            preferred, other = old, candidate
        combined = preferred.copy()
        combined["category"] = list(dict.fromkeys(
            preferred.get("category", []) + other.get("category", [])
        ))
        combined["area"] = list(dict.fromkeys(
            preferred.get("area", []) + other.get("area", [])
        ))
        if len(other.get("body_excerpt", "")) > len(combined.get("body_excerpt", "")):
            combined["body_excerpt"] = other.get("body_excerpt", "")
            combined["body_excerpt_method"] = other.get("body_excerpt_method", "")
        if not combined.get("published_date") and other.get("published_date"):
            combined["published_date"] = other.get("published_date", "")
        sources = []
        for source in preferred.get("source_urls", []) + other.get("source_urls", []):
            if source.get("url") and source.get("url") not in [x.get("url") for x in sources]:
                sources.append(source)
        combined["source_urls"] = sources
        combined["duplicate_sources_count"] = len(sources)
        merged_items[match_index] = combined
    return merged_items

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
    municipality_candidates = extract_municipality_candidates(
        item.get("title", ""), item.get("body_excerpt", "")
    )
    if len(municipality_candidates) == 1:
        municipality = municipality_candidates[0]
        municipality_status = "要確認（タイトル・本文から抽出した候補）"
        area_status = "市町名候補を抽出済み。店舗所在地として公開する前に元記事で要確認。"
    elif len(municipality_candidates) > 1:
        municipality = ""
        municipality_status = "要確認（複数の市町名候補）"
        area_status = "複数の市町名候補あり。店舗所在地は元記事で要確認。"
    else:
        municipality = ""
        municipality_status = "要確認（市町名を抽出できず）"
        area_status = "市町名を抽出できず。店舗所在地は元記事で要確認。"
    return {
        "id": hashlib.sha256(normalize_url(url).encode("utf-8")).hexdigest()[:16],
        "title": item["title"], "suggested_headline": item["title"],
        "category": item["category"], "priority": get_priority(item["category"]),
        "published_date": date_value, "freshness": freshness, "age_days": age,
        "area": item.get("area", []), "area_status": area_status,
        "municipality": municipality, "municipality_candidates": municipality_candidates,
        "municipality_status": municipality_status,
        "source_name": item.get("source_name", ""), "source_url": url,
        "source_urls": item.get("source_urls", [{"source_name": item.get("source_name", ""), "url": url}]),
        "duplicate_sources_count": item.get("duplicate_sources_count", 1),
        "body_excerpt": item.get("body_excerpt", ""), "body_excerpt_method": item.get("body_excerpt_method", ""), "draft_summary": summary,
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
