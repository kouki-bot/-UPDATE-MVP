
import json
import re
import html
import urllib.request
import xml.etree.ElementTree as ET

from collections import Counter
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import (
    urlsplit,
    urlunsplit,
    parse_qsl,
    urlencode,
)


# ==================================================
# 基本設定
# ==================================================

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_FILE = DATA_DIR / "rss_candidates.json"

JST = timezone(timedelta(hours=9))
UTC = timezone.utc

RECENT_DAYS = 30
MAX_ITEMS_PER_SOURCE = 100

USER_AGENT = (
    "Mozilla/5.0 "
    "(compatible; YamaguchiLocalUpdate/1.0)"
)


# ==================================================
# RSSソース
# ==================================================

RSS_SOURCES = [
    {
        "name": "山口宇部経済新聞",
        "url": "https://yamaguchi.keizai.biz/rss.xml",
        "area": [
            "山口市", "宇部市", "山陽小野田市",
            "美祢市", "防府市", "萩市", "長門市",
        ],
    },
    {
        "name": "号外NET 山口市・防府市",
        "url": "https://yamaguchi-hofu.goguynet.jp/feed/",
        "area": ["山口市", "防府市"],
    },
    {
        "name": "号外NET 宇部市・山陽小野田市",
        "url": "https://ube-sanyoonoda.goguynet.jp/feed/",
        "area": ["宇部市", "山陽小野田市"],
    },
]


# ==================================================
# 店舗ニュースの分類キーワード
# ==================================================

KEYWORD_GROUPS = {
    "新店・開店": [
        "新店", "新店舗", "新規開店", "新規出店",
        "オープン", "開店", "開業", "出店",
        "グランドオープン", "プレオープン",
        "初出店", "開店予定", "開業予定",
        "オープン予定", "新たにオープン",
        "新しくオープン", "オープンしました",
        "オープンする",
    ],
    "閉店": [
        "閉店", "営業終了", "閉業", "店じまい",
        "閉店のお知らせ", "閉店しました",
        "閉店予定", "営業を終了",
    ],
    "移転": [
        "移転", "移転オープン", "移転のお知らせ",
        "移転しました", "移転予定", "移転先",
    ],
    "リニューアル": [
        "リニューアル", "改装オープン",
        "リニューアルオープン", "営業再開",
        "リニューアル予定", "改装",
    ],
}


# 店舗ニュースとして扱わない記事のキーワード。
# ただし、店舗ニュースのタイトルに含まれていても
# 一律に除外しないよう、除外対象を限定する。
EXCLUDE_TITLE_KEYWORDS = [
    "求人", "アルバイト募集", "スタッフ募集",
    "採用情報", "正社員募集",
    "イベント情報", "イベント開催",
    "マルシェ開催", "フェス開催",
    "祭り開催", "ワークショップ開催",
    "参加者募集", "出店者募集",
    "整備計画", "建設計画",
    "入札", "議会", "市長会見",
    "補助金", "公共施設の整備",
]

EXCLUDE_ARTICLE_KEYWORDS = [
    "仙台経済新聞",
    "横浜経済新聞",
]


# ==================================================
# 共通処理
# ==================================================

def now_jst():
    return datetime.now(JST)


def clean_text(value):
    if not value:
        return ""

    value = html.unescape(str(value))
    value = re.sub(r"<[^>]+>", " ", value)
    value = value.replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def local_name(tag):
    return tag.split("}")[-1].split(":")[-1].lower()


def get_child_text(element, names):
    names = {
        name.lower().split(":")[-1]
        for name in names
    }

    for child in element:
        if local_name(child.tag) in names:
            value = "".join(child.itertext()).strip()

            if value:
                return clean_text(value)

    return ""


def get_link(element):
    for child in element:
        if local_name(child.tag) != "link":
            continue

        href = child.attrib.get("href", "").strip()

        if href:
            rel = child.attrib.get("rel", "alternate")

            if rel == "alternate":
                return href

        value = "".join(child.itertext()).strip()

        if value:
            return value

    return ""


def normalize_url(url):
    """追跡用パラメータを除いてURLを整理する"""
    try:
        parts = urlsplit(url.strip())

        tracking_prefixes = ("utm_",)
        tracking_names = {
            "fbclid", "gclid", "yclid",
            "mc_cid", "mc_eid",
        }

        query = [
            (key, value)
            for key, value in parse_qsl(
                parts.query,
                keep_blank_values=True,
            )
            if key.lower() not in tracking_names
            and not key.lower().startswith(tracking_prefixes)
        ]

        path = parts.path.rstrip("/") or "/"

        return urlunsplit((
            parts.scheme.lower(),
            parts.netloc.lower(),
            path,
            urlencode(query),
            "",
        ))

    except (ValueError, TypeError):
        return url.strip()


def parse_date(value):
    if not value:
        return None

    value = value.strip()

    try:
        dt = parsedate_to_datetime(value)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)

        return dt.astimezone(JST)

    except (TypeError, ValueError, OverflowError):
        pass

    try:
        dt = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)

        return dt.astimezone(JST)

    except (TypeError, ValueError, OverflowError):
        return None


def extract_published_date(element):
    for child in element.iter():
        if local_name(child.tag) in {
            "pubdate", "published", "updated", "date"
        }:
            value = "".join(child.itertext()).strip()

            if value:
                parsed = parse_date(value)

                if parsed:
                    return parsed

    return None


# ==================================================
# 分類・除外判定
# ==================================================

def classify_text(text):
    text = clean_text(text)

    return [
        category
        for category, keywords in KEYWORD_GROUPS.items()
        if any(keyword in text for keyword in keywords)
    ]


def is_excluded(title, description):
    """
    イベント・求人・公共事業などを候補から除外。
    店舗の動きが明確なタイトルは一律除外しない。
    """
    title = clean_text(title)
    description = clean_text(description)

    title_categories = classify_text(title)

    # 店舗の動きがタイトルで明確なら、
    # 概要にイベント等の語があっても残す。
    if title_categories:
        return any(
            keyword in title
            for keyword in EXCLUDE_TITLE_KEYWORDS
            if not any(
                store_keyword in title
                for store_keyword in [
                    "新店", "新店舗", "オープン",
                    "開店", "閉店", "移転",
                    "リニューアル", "改装",
                ]
            )
        )

    combined = title + " " + description

    if any(
        keyword in combined
        for keyword in EXCLUDE_ARTICLE_KEYWORDS
    ):
        return True

    # タイトルに店舗ニュースの分類語がない記事は
    # 原則として候補に入れない。
    return True


def classify_article(title, description):
    title_categories = classify_text(title)

    if title_categories:
        return title_categories, "タイトル"

    description_categories = classify_text(description)

    if description_categories:
        return description_categories, "概要・要確認"

    return [], "未分類"


def get_priority(categories, category_basis):
    if category_basis != "タイトル":
        return 3

    if "閉店" in categories:
        return 1

    if "新店・開店" in categories:
        return 1

    if "移転" in categories or "リニューアル" in categories:
        return 2

    return 3


# ==================================================
# 鮮度判定
# ==================================================

def get_freshness(published_date):
    if not published_date:
        return "日付確認が必要", None

    age_days = (
        now_jst().date() - published_date.date()
    ).days

    if age_days < -1:
        return "未来日付・要確認", age_days

    age_days = max(age_days, 0)

    if age_days <= RECENT_DAYS:
        return "直近30日", age_days

    if age_days <= 90:
        return "31〜90日前", age_days

    return "90日より前", age_days


# ==================================================
# RSS取得
# ==================================================

def fetch_rss(source):
    request = urllib.request.Request(
        source["url"],
        headers={"User-Agent": USER_AGENT},
    )

    try:
        with urllib.request.urlopen(
            request, timeout=20
        ) as response:
            raw_data = response.read()

    except (
        HTTPError, URLError, TimeoutError, OSError
    ) as exc:
        print(f"[取得失敗] {source['name']}: {exc}")
        return []

    text = raw_data.decode(
        "utf-8-sig",
        errors="replace",
    )

    text = re.sub(
        r"[\x00-\x08\x0B\x0C\x0E-\x1F]",
        "",
        text,
    )

    try:
        root = ET.fromstring(text)

    except ET.ParseError as exc:
        print(f"[XML解析失敗] {source['name']}: {exc}")
        return []

    items = []

    for element in root.iter():
        if local_name(element.tag) not in {"item", "entry"}:
            continue

        title = get_child_text(element, ["title"])
        link = get_link(element)

        description = get_child_text(
            element,
            ["description", "summary", "content", "encoded"],
        )

        if not title or not link:
            continue

        if is_excluded(title, description):
            continue

        categories, category_basis = classify_article(
            title, description
        )

        if not categories:
            continue

        published = extract_published_date(element)

        freshness, age_days = get_freshness(published)

        # 古い記事は候補から除外せず、
        # 鮮度情報を付けて確認できるようにする。
        published_date = (
            published.isoformat() if published else ""
        )

        items.append({
            "title": title,
            "url": link,
            "normalized_url": normalize_url(link),
            "source_name": source["name"],
            "source_url": source["url"],
            "area": source["area"],
            "categories": categories,
            "category_basis": category_basis,
            "priority": get_priority(
                categories, category_basis
            ),
            "published_date": published_date,
            "freshness": freshness,
            "age_days": age_days,
            "description": description[:1000],
            "relevance": (
                "タイトルから分類"
                if category_basis == "タイトル"
                else "概要から仮分類・要確認"
            ),
            "status": "未確認・公開禁止",
            "checked_at": now_jst().isoformat(),
        })

        if len(items) >= MAX_ITEMS_PER_SOURCE:
            break

    print(
        f"[取得完了] {source['name']}: "
        f"{len(items)}件"
    )

    return items


# ==================================================
# 重複整理
# ==================================================

def merge_candidates(candidates):
    merged = {}
    title_index = {}

    for item in candidates:
        url_key = normalize_url(item.get("url", ""))

        if not url_key:
            continue

        title_key = re.sub(
            r"[\W_]+", "", item.get("title", "").lower()
        )

        key = url_key

        if key not in merged and title_key in title_index:
            key = title_index[title_key]

        if key not in merged:
            merged[key] = item.copy()
            merged[key]["area"] = list(item["area"])
            merged[key]["categories"] = list(item["categories"])
            title_index[title_key] = key
            continue

        existing = merged[key]

        existing["categories"] = list(dict.fromkeys(
            existing["categories"] + item["categories"]
        ))

        existing["area"] = list(dict.fromkeys(
            existing["area"] + item["area"]
        ))

        existing["priority"] = min(
            existing["priority"], item["priority"]
        )

    return list(merged.values())


def sort_key(item):
    freshness_order = {
        "直近30日": 0,
        "31〜90日前": 1,
        "90日より前": 2,
        "日付確認が必要": 3,
        "未来日付・要確認": 4,
    }

    published = parse_date(item.get("published_date", ""))

    timestamp = published.timestamp() if published else 0

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
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    all_candidates = []
    source_results = []

    for source in RSS_SOURCES:
        items = fetch_rss(source)

        source_results.append({
            "name": source["name"],
            "url": source["url"],
            "area": source["area"],
            "items_read": len(items),
        })

        all_candidates.extend(items)

    candidates = merge_candidates(all_candidates)
    candidates.sort(key=sort_key)

    category_counts = Counter()
    freshness_counts = Counter()

    for item in candidates:
        for category in item["categories"]:
            category_counts[category] += 1

        freshness_counts[item["freshness"]] += 1

    recent_count = sum(
        1 for item in candidates
        if item["freshness"] == "直近30日"
    )

    result = {
        "generated_at": now_jst().isoformat(),
        "purpose": (
            "山口県内の新店舗・閉店・移転・"
            "リニューアル情報の候補収集"
        ),
        "total_candidates": len(candidates),
        "recent_candidate_count": recent_count,
        "category_counts": dict(category_counts),
        "freshness_counts": dict(freshness_counts),
        "sources": source_results,
        "candidates": candidates,
        "notice": (
            "すべて未確認です。自動公開は禁止。"
            "掲載前に店舗名・所在地・日付・"
            "営業状況・情報源を確認してください。"
        ),
    }

    with OUTPUT_FILE.open("w", encoding="utf-8") as file:
        json.dump(
            result,
            file,
            ensure_ascii=False,
            indent=2,
        )

    print("")
    print("========== RSS収集結果 ==========")
    print(f"候補記事数: {len(candidates)}")
    print(f"直近30日の記事: {recent_count}件")
    print("カテゴリー別:")
    print(json.dumps(
        dict(category_counts),
        ensure_ascii=False,
        indent=2,
    ))
    print(f"保存先: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
