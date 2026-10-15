import json
import os
import re
import hashlib
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from xml.etree import ElementTree

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

def classify_text(text):
    text = clean_text(text)
    categories = []

    for category, keywords in KEYWORD_GROUPS.items():
        if any(keyword in text for keyword in keywords):
            categories.append(category)

    # 「オープンデータ」などの誤判定を抑える
    if "オープンデータ" in text:
        categories = [
            category for category in categories
            if category != "新店・開店"
        ]

    return categories


def get_priority(categories):
    # 数字が小さいほど優先度が高い
    if "新店・開店" in categories:
        return 1

    if "閉店" in categories:
        return 1

    if "移転" in categories or "リニューアル" in categories:
        return 2

    if "求人" in categories:
        return 3

    if "イベント" in categories:
        return 4

    return 5
    
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

    categories = classify_text(
        title + " " + description
    )
    
    priority = get_priority(categories)
    
    item_id = hashlib.sha256(
        link.encode("utf-8")
    ).hexdigest()[:16]

    return {
        "id": item_id,
        "title": title,
        "url": link,
        "source_name": source["name"],
        "source_url": source["url"],
        "area": source["area"],
        "category": categories,
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

    # UTF-8として読み込み、文字コードの問題を確認しやすくする
    text = raw_data.decode("utf-8-sig", errors="replace")

    # XMLで禁止されている制御文字を除去
    text = re.sub(
        r"[\x00-\x08\x0B\x0C\x0E-\x1F]",
        "",
        text,
    )

    return text.encode("utf-8")
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

            # 取得したデータの冒頭をログに出す
            preview = xml_data[:500].decode(
                "utf-8", errors="replace"
            )
            print("RSS取得先:", source["url"])
            print("取得データの冒頭:", repr(preview))

            root = ElementTree.fromstring(xml_data)

            items = [
                element
                for element in root.iter()
                if element.tag.split("}")[-1].lower()
                in ("item", "entry")
            ]

            result["items_read"] = min(
                len(items), MAX_ITEMS_PER_SOURCE
            )
            result["status"] = "取得成功"

            for item in items[:MAX_ITEMS_PER_SOURCE]:
                candidate = make_candidate(
                    item, source
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
            print("取得失敗:", result["error"])

        source_results.append(result)

    # URLで重複を除外
    unique = {}

    for item in candidates:
        unique[item["url"]] = item

    output = {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "source_count": len(source_results),
        "candidate_count": len(unique),
        "sources": source_results,
        "note": (
            "RSSから取得した候補です。"
            "分類はキーワードによる仮判定です。"
            "公開前に元記事を確認してください。"
        ),
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

    print("情報源:", len(source_results))
    print("記事候補:", len(unique))
    print("保存先:", OUTPUT_FILE)

    for item in unique.values():
        print(
            "-", item["category"],
            item["title"],
            item["url"],
        )

if __name__ == "__main__":
    main()