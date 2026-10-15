import json
import re
import urllib.request
import xml.etree.ElementTree as ET

from collections import Counter
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.error import HTTPError, URLError


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
# 収集するRSS
# 求人情報は対象外
# ==================================================

RSS_SOURCES = [
    {
        "name": "山口宇部経済新聞",
        "url": "https://yamaguchi.keizai.biz/rss.xml",
        "area": [
            "山口市",
            "宇部市",
            "山陽小野田市",
            "美祢市",
            "防府市",
            "萩市",
            "長門市",
        ],
    },
    {
        "name": "号外NET 山口市・防府市",
        "url": "https://yamaguchi-hofu.goguynet.jp/feed/",
        "area": [
            "山口市",
            "防府市",
        ],
    },
    {
        "name": "号外NET 宇部市・山陽小野田市",
        "url": "https://ube-sanyoonoda.goguynet.jp/feed/",
        "area": [
            "宇部市",
            "山陽小野田市",
        ],
    },
]


# ==================================================
# 分類キーワード
# 求人カテゴリーは削除
# ==================================================

KEYWORD_GROUPS = {
    "新店・開店": [
        "新店",
        "新規開店",
        "オープン",
        "開店",
        "出店",
        "開業",
        "新店舗",
        "グランドオープン",
        "プレオープン",
        "オープン予定",
        "新たにオープン",
        "新しくオープン",
        "オープンしました",
        "開店予定",
        "開業予定",
        "初出店",
        "新規出店",
        "オープンする",
    ],
    "閉店": [
        "閉店",
        "営業終了",
        "閉業",
        "閉店のお知らせ",
        "閉店しました",
        "閉店予定",
        "営業を終了",
        "店じまい",
        "閉鎖",
    ],
    "移転": [
        "移転",
        "移転オープン",
        "移転のお知らせ",
        "移転しました",
        "移転予定",
        "移転先",
    ],
    "リニューアル": [
        "リニューアル",
        "改装オープン",
        "リニューアルオープン",
        "営業再開",
        "リニューアル予定",
    ],
    "イベント": [
        "イベント",
        "開催",
        "フェス",
        "祭り",
        "マルシェ",
        "展示会",
        "ワークショップ",
        "催し",
    ],
    "新施設・地域の動き": [
        "新施設",
        "新設",
        "整備計画",
        "建設計画",
        "商業施設",
        "公共施設",
        "複合施設",
        "開設",
        "供用開始",
    ],
}


# 明らかに対象外の地域記事などを除外する
EXCLUDE_KEYWORDS = [
    "仙台経済新聞",
    "横浜経済新聞",
]


# ==================================================
# 共通処理
# ==================================================

def now_jst():
    return datetime.now(JST)


def clean_text(text):
    if not text:
        return ""

    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&nbsp;", " ")
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def local_name(tag):
    """XMLタグから名前空間を取り除く"""
    return tag.split("}")[-1].lower()


def get_child_text(element, names):
    """指定した名前の子要素からテキストを取得する"""
    names = {name.lower() for name in names}

    for child in element:
        if local_name(child.tag) in names:
            text = "".join(child.itertext()).strip()

            if text:
                return clean_text(text)

    return ""


def get_link(element):
    """RSS・Atomのリンクを取得する"""
    for child in element:
        if local_name(child.tag) != "link":
            continue

        href = child.attrib.get("href", "").strip()

        if href:
            rel = child.attrib.get("rel", "alternate")

            if rel == "alternate":
                return href

        text = "".join(child.itertext()).strip()

        if text:
            return text

    return ""


def parse_date(value):
    """RSSの日付をタイムゾーン付き日時に変換する"""
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
    """RSS・Atomから公開日を取得する"""
    value = get_child_text(
        element,
        [
            "pubDate",
            "published",
            "updated",
            "date",
            "dc:date",
        ],
    )

    # 名前空間付きdc:dateにも対応
    if not value:
        for child in element.iter():
            if local_name(child.tag) == "date":
                value = "".join(child.itertext()).strip()

                if value:
                    break

    return parse_date(value)


# ==================================================
# 分類処理
# ==================================================

def classify_text(text):
    """文字列に含まれるキーワードからカテゴリーを判定"""
    text = clean_text(text)

    categories = []

    for category, keywords in KEYWORD_GROUPS.items():
        if any(keyword in text for keyword in keywords):
            categories.append(category)

    return categories


def classify_article(title, description):
    """
    タイトルを優先して分類する。

    タイトルで分類できた場合、説明文のキーワードは
    原則として分類に追加しない。
    これにより、別店舗の閉店・移転情報による誤分類を減らす。
    """

    title_categories = classify_text(title)

    if title_categories:
        return title_categories, "タイトル"

    description_categories = classify_text(description)

    if description_categories:
        return description_categories, "概要・要確認"

    return ["未分類"], "未分類"


def get_priority(categories):
    """優先順位が高い記事ほど数字を小さくする"""

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
# 記事の鮮度判定
# ==================================================

def get_freshness(published_date):
    """
    記事の公開日から鮮度を判定する。

    30日以内       : 直近30日
    31〜90日前     : 31〜90日前
    90日より前     : 90日より前
    日付不明       : 日付確認が必要
    未来日付       : 未来日付・要確認
    """

    if not published_date:
        return "日付確認が必要", None

    now = now_jst()

    age_days = (now.date() - published_date.date()).days

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
# RSS取得処理
# ==================================================

def fetch_rss(source):
    request = urllib.request.Request(
        source["url"],
        headers={
            "User-Agent": USER_AGENT,
        },
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=20,
        ) as response:
            raw_data = response.read()

    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        print(
            f"[取得失敗] {source['name']}: {exc}"
        )
        return []

    # 不正な制御文字を除去
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
        print(
            f"[XML解析失敗] {source['name']}: {exc}"
        )
        return []

    items = []

    for element in root.iter():
        tag = local_name(element.tag)

        if tag not in ["item", "entry"]:
            continue

        title = get_child_text(
            element,
            ["title"],
        )

        link = get_link(element)

        description = get_child_text(
            element,
            [
                "description",
                "summary",
                "content",
                "encoded",
            ],
        )

        published = extract_published_date(element)

        if not title or not link:
            continue

        if any(
            keyword in title
            for keyword in EXCLUDE_KEYWORDS
        ):
            continue

        categories, category_basis = classify_article(
            title,
            description,
        )

        freshness, age_days = get_freshness(
            published
        )

        published_date = (
            published.isoformat()
            if published
            else ""
        )

        priority = get_priority(categories)

        candidate = {
            "title": title,
            "url": link,
            "source_name": source["name"],
            "source_url": source["url"],
            "area": source["area"],
            "categories": categories,
            "category_basis": category_basis,
            "priority": priority,
            "published_date": published_date,
            "freshness": freshness,
            "age_days": age_days,
            "description": description[:1000],
            "relevance": (
                "タイトルから分類"
                if category_basis == "タイトル"
                else "概要から仮分類・要確認"
                if category_basis == "概要・要確認"
                else "分類できず・要確認"
            ),
            "status": "未確認・公開禁止",
            "checked_at": now_jst().isoformat(),
        }

        items.append(candidate)

        if len(items) >= MAX_ITEMS_PER_SOURCE:
            break

    print(
        f"[取得完了] {source['name']}: "
        f"{len(items)}件"
    )

    return items


# ==================================================
# 重複整理・並び替え
# ==================================================

def merge_candidates(candidates):
    """同じURLの記事を統合する"""

    merged = {}

    for item in candidates:
        url = item["url"].strip()

        if not url:
            continue

        if url not in merged:
            merged[url] = item
            continue

        existing = merged[url]

        # カテゴリーを統合
        categories = list(
            dict.fromkeys(
                existing["categories"]
                + item["categories"]
            )
        )

        existing["categories"] = categories
        existing["priority"] = get_priority(categories)

        # 地域を統合
        existing["area"] = list(
            dict.fromkeys(
                existing["area"] + item["area"]
            )
        )

    return list(merged.values())


def sort_key(item):
    """新しい記事を先に、同じ鮮度なら重要度順にする"""

    freshness_order = {
        "直近30日": 0,
        "31〜90日前": 1,
        "90日より前": 2,
        "日付確認が必要": 3,
        "未来日付・要確認": 4,
    }

    published = parse_date(
        item.get("published_date", "")
    )

    timestamp = (
        published.timestamp()
        if published
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
    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

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

    candidates = merge_candidates(
        all_candidates
    )

    candidates.sort(
        key=sort_key
    )

    category_counts = Counter()
    freshness_counts = Counter()
    priority_counts = Counter()

    for item in candidates:
        for category in item["categories"]:
            category_counts[category] += 1

        freshness_counts[
            item["freshness"]
        ] += 1

        priority_counts[
            str(item["priority"])
        ] += 1

    recent_count = sum(
        1
        for item in candidates
        if item["freshness"] == "直近30日"
    )

    result = {
        "generated_at": now_jst().isoformat(),
        "purpose": (
            "山口県内の新店・閉店・移転・"
            "リニューアル・イベント・地域情報の候補収集"
        ),
        "total_candidates": len(candidates),
        "recent_candidate_count": recent_count,
        "category_counts": dict(category_counts),
        "freshness_counts": dict(freshness_counts),
        "priority_counts": dict(priority_counts),
        "sources": source_results,
        "candidates": candidates,
        "notice": (
            "収集記事は未確認です。"
            "掲載前に公開日・店舗名・所在地・"
            "営業状況を確認してください。"
        ),
    }

    with OUTPUT_FILE.open(
        "w",
        encoding="utf-8",
    ) as file:
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
    print("")
    print("カテゴリー別:")
    print(json.dumps(
        dict(category_counts),
        ensure_ascii=False,
        indent=2,
    ))
    print("")
    print("鮮度別:")
    print(json.dumps(
        dict(freshness_counts),
        ensure_ascii=False,
        indent=2,
    ))
    print("")
    print(f"保存先: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()