import json
import os
import re
import hashlib
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from xml.etree import ElementTree


# ==========================================
# RSS情報源
# ==========================================

RSS_SOURCES = [
    {
        "name": "山口宇部経済新聞",
        "url": "https://yamaguchi.keizai.biz/rss.xml",
        "area": [
            "山口市", "宇部市", "山陽小野田市",
            "美祢市", "防府市", "萩市", "長門市"
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


OUTPUT_FILE = "data/rss_candidates.json"
MAX_ITEMS_PER_SOURCE = 100


# ==========================================
# 分類キーワード
# ==========================================

KEYWORD_GROUPS = {
    "新店・開店": [
        "新店", "新規開店", "オープン",
        "開店", "出店", "開業", "新店舗",
        "グランドオープン", "プレオープン",
        "オープン予定", "新たにオープン",
        "新しくオープン", "オープンしました",
        "開店予定", "開業予定", "初出店",
        "新規出店", "オープンする",
    ],
    "閉店": [
        "閉店", "営業終了", "閉業",
        "閉店のお知らせ", "閉店しました",
        "閉店予定", "営業を終了",
        "店じまい", "閉鎖",
    ],
    "移転": [
        "移転", "移転オープン",
        "移転のお知らせ", "移転しました",
        "移転予定", "移転先",
    ],
    "リニューアル": [
        "リニューアル", "改装オープン",
        "リニューアルオープン",
        "営業再開", "リニューアル予定",
    ],
    "求人": [
        "求人", "スタッフ募集",
        "オープニングスタッフ", "採用",
        "アルバイト募集", "パート募集",
    ],
    "イベント": [
        "イベント", "開催", "フェス",
        "祭り", "マルシェ", "展示会",
        "ワークショップ", "催し",
    ],
}


EXCLUDE_KEYWORDS = [
    "みんなの経済新聞",
    "仙台経済新聞",
    "横浜経済新聞",
]


# ==========================================
# 文字列処理
# ==========================================

def clean_text(value):
    value = re.sub(r"<[^>]+>", " ", str(value or ""))
    value = value.replace("&nbsp;", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def get_text(element, names):
    for child in element:
        tag = child.tag.split("}")[-1].lower()

        if tag in names:
            return clean_text("".join(child.itertext()))

    return ""


def get_link(element):
    for child in element:
        tag = child.tag.split("}")[-1].lower()

        if tag == "link":
            href = child.attrib.get("href", "")
            rel = child.attrib.get("rel", "alternate")

            if href and rel == "alternate":
                return href

            if child.text and child.text.strip():
                return child.text.strip()

    return ""


# ==========================================
# 日付処理
# ==========================================

def parse_date(value):
    if not value:
        return ""

    value = value.strip()

    try:
        dt = parsedate_to_datetime(value)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc).isoformat()

    except (TypeError, ValueError, OverflowError):
        pass

    try:
        dt = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc).isoformat()

    except (TypeError, ValueError, OverflowError):
        return ""


# ==========================================
# 記事分類
# ==========================================

def classify_text(text):
    text = clean_text(text)
    categories = []

    for category, keywords in KEYWORD_GROUPS.items():
        if any(keyword in text for keyword in keywords):
            categories.append(category)

    # オープンデータ関連の記事を開店情報と誤認しない
    if "オープンデータ" in text:
        categories = [
            category
            for category in categories
            if category != "新店・開店"
        ]

    return categories


def get_priority(categories):
    """
    数字が小さいほど確認の優先順位が高い。
    """

    # 新店・閉店を最優先
    if (
        "新店・開店" in categories
        or "閉店" in categories
    ):
        return 1

    # 移転・リニューアル
    if (
        "移転" in categories
        or "リニューアル" in categories
    ):
        return 2

    # 求人
    if "求人" in categories:
        return 3

    # イベント
    if "イベント" in categories:
        return 4

    # 分類できなかった記事
    return 5


# ==========================================
# RSS記事を候補データに変換
# ==========================================

def make_candidate(item, source):
    title = get_text(item, {"title"})
    link = get_link(item)

    description = get_text(
        item,
        {"description", "summary", "encoded"}
    )

    date_text = get_text(
        item,
        {"pubdate", "published", "updated", "date"}
    )

    published_date = parse_date(date_text)

    if not title or not link:
        return None

    if any(word in title for word in EXCLUDE_KEYWORDS):
        return None

    # タイトルと概要から分類
    combined_text = title + " " + description
    categories = classify_text(combined_text)

    # 優先順位を計算
    priority = get_priority(categories)

    # 記事URLからIDを生成
    item_id = hashlib.sha256(
        link.encode("utf-8")
    ).hexdigest()[:16]

    # 保存する候補データ
    return {
        "id": item_id,
        "title": title,
        "url": link,
        "source_name": source["name"],
        "source_url": source["url"],
        "area": source["area"],
        "category": categories,
        "priority": priority,
        "published_date": published_date,
        "description": description[:1500],
        "relevance": (
            "関連キーワードあり"
            if categories
            else "内容確認が必要"
        ),
        "status": "未確認・公開禁止",
        "checked_at": datetime.now(
            timezone.utc
        ).isoformat(),
    }


# ==========================================
# RSS取得
# ==========================================

def fetch_rss(source):
    request = Request(
        source["url"],
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "(compatible; YamaguchiLocalUpdate/1.0)"
            ),
            "Accept": (
                "application/rss+xml, "
                "application/atom+xml, "
                "application/xml, text/xml"
            ),
        },
    )

    with urlopen(request, timeout=20) as response:
        raw_data = response.read(3_000_000)

    text = raw_data.decode(
        "utf-8-sig",
        errors="replace"
    )

    # XMLで禁止されている制御文字を削除
    text = re.sub(
        r"[\x00-\x08\x0B\x0C\x0E-\x1F]",
        "",
        text,
    )

    return text.encode("utf-8")


# ==========================================
# メイン処理
# ==========================================

def main():
    os.makedirs("data", exist_ok=True)

    candidates = []
    source_results = []

    for source in RSS_SOURCES:
        print("RSS取得開始:", source["name"])

        result = {
            "name": source["name"],
            "url": source["url"],
            "status": "取得失敗",
            "items_read": 0,
            "error": "",
        }

        try:
            xml_data = fetch_rss(source)

            root = ElementTree.fromstring(xml_data)

            items = [
                element
                for element in root.iter()
                if element.tag.split("}")[-1].lower()
                in ("item", "entry")
            ]

            result["items_read"] = min(
                len(items),
                MAX_ITEMS_PER_SOURCE
            )

            result["status"] = "取得成功"

            print(
                "取得記事数:",
                source["name"],
                result["items_read"]
            )

            for item in items[:MAX_ITEMS_PER_SOURCE]:
                candidate = make_candidate(
                    item,
                    source
                )

                if candidate:
                    candidates.append(candidate)

        except (
            URLError,
            HTTPError,
            TimeoutError,
            ElementTree.ParseError,
            ValueError,
        ) as error:
            result["error"] = str(error)[:300]

            print(
                "取得失敗:",
                source["name"],
                result["error"]
            )

        source_results.append(result)

    # ======================================
    # URLで重複排除
    # ======================================

    unique = {}

    for item in candidates:
        url = item["url"]

        if url not in unique:
            unique[url] = item
        else:
            existing = unique[url]

            # 概要が空なら、別の候補にある概要を補う
            if (
                not existing["description"]
                and item["description"]
            ):
                existing["description"] = item["description"]

            # 分類を統合
            existing["category"] = sorted(
                set(
                    existing["category"]
                    + item["category"]
                )
            )

            # 優先順位を再計算
            existing["priority"] = get_priority(
                existing["category"]
            )

            # エリア情報を統合
            existing["area"] = sorted(
                set(
                    existing["area"]
                    + item["area"]
                )
            )

    # ======================================
    # 優先順位で並べ替え
    # ======================================

    sorted_candidates = sorted(
        unique.values(),
        key=lambda item: (
            item["priority"],
            item["published_date"] or "",
            item["title"],
        ),
        reverse=False,
    )

    # ======================================
    # 分類別の件数を集計
    # ======================================

    category_counts = {}

    for item in sorted_candidates:
        if not item["category"]:
            category_counts["未分類"] = (
                category_counts.get("未分類", 0) + 1
            )

        for category in item["category"]:
            category_counts[category] = (
                category_counts.get(category, 0) + 1
            )

    # ======================================
    # JSON保存
    # ======================================

    output = {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "source_count": len(source_results),
        "candidate_count": len(sorted_candidates),
        "category_counts": category_counts,
        "sources": source_results,
        "note": (
            "RSSから取得した候補です。"
            "分類と優先順位はキーワードによる仮判定です。"
            "優先順位1は新店・閉店の確認候補です。"
            "すべて未確認のため、元記事を確認するまで"
            "公開しないでください。"
        ),
        "candidates": sorted_candidates,
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

    print("情報源:", len(source_results))
    print("記事候補:", len(sorted_candidates))
    print("分類別件数:", category_counts)
    print("保存先:", OUTPUT_FILE)

    print("\n優先順位の高い記事:")

    for item in sorted_candidates:
        if item["priority"] <= 2:
            print(
                "- 優先順位:",
                item["priority"],
                "| 分類:",
                item["category"],
                "| タイトル:",
                item["title"],
                "| URL:",
                item["url"],
            )


if __name__ == "__main__":
    main()