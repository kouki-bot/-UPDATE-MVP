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
    {
        "name": "シーモール下関公式・新店情報",
        "url": "https://www.seamall.jp/info/new-shop/",
        "domain": "www.seamall.jp",
        "kind": "shop_listing",
    },
    {
        "name": "イオンタウン防府公式",
        "url": "https://www.aeontown.co.jp/hofu/",
        "domain": "www.aeontown.co.jp",
        "default_area": "防府市",
    },
    {
        "name": "おのだサンパーク公式・新店情報",
        "url": "https://www.sunpark.co.jp/",
        "domain": "www.sunpark.co.jp",
        "default_area": "山陽小野田市",
    },
    {
        "name": "徳山デッキ公式・店舗オープン情報",
        "url": "https://tokuyamadeck.com/",
        "domain": "tokuyamadeck.com",
        "default_area": "周南市",
    },
    {
        "name": "星プラザ公式",
        "url": "https://www.hoshiplaza.co.jp/",
        "domain": "www.hoshiplaza.co.jp",
        "default_area": "下松市",
    },
]

MAX_PAGES_PER_SOURCE = 30
MAX_ARTICLE_CHECKS_PER_SOURCE = 80
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
        "リニューアルオープン", "改装",
    ],
}

# 探索対象にするリンクの目印
PRIORITY_WORDS = [
    "news", "notice", "topics", "release",
    "oshirase", "koho", "お知らせ", "新着",
    "報道", "press", "event", "event-info", "information", "search", "news",
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
    VOID_TAGS = {
        "area", "base", "br", "col", "embed", "hr", "img",
        "input", "link", "meta", "param", "source", "track", "wbr",
    }

    def __init__(self):
        super().__init__()
        self.links = []
        self.current_href = None
        self.current_text = []
        self.title_parts = []
        self.meta_dates = []
        self.text_parts = []
        self.article_parts = []
        self.press_body_parts = []
        self.tag_stack = []
        self.in_title = False

    def _is_skipping(self):
        return any(item["skip"] for item in self.tag_stack)

    def _inside(self, key):
        return any(item[key] for item in self.tag_stack)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        parent_skip = self._is_skipping()
        parent_press = self._inside("in_press")
        parent_article = self._inside("in_article")
        is_press = parent_press or (
            tag == "div" and attrs.get("id") == "press_main_body"
        )
        is_article = parent_article or tag in ("main", "article")
        skip = parent_skip or tag in SKIP_TAGS

        if tag == "meta":
            name = (
                attrs.get("property")
                or attrs.get("name")
                or ""
            ).strip().lower()
            content = (attrs.get("content") or "").strip()
            if content and name in PUBLISHED_META_NAMES:
                self.meta_dates.append({
                    "name": name,
                    "value": content,
                })

        if not skip:
            if tag == "title":
                self.in_title = True
            if tag == "a":
                self.current_href = attrs.get("href")
                self.current_text = []

        if tag not in self.VOID_TAGS:
            self.tag_stack.append({
                "tag": tag,
                "skip": skip,
                "in_press": is_press,
                "in_article": is_article,
            })

    def handle_endtag(self, tag):
        for index in range(len(self.tag_stack) - 1, -1, -1):
            if self.tag_stack[index]["tag"] == tag:
                del self.tag_stack[index:]
                break

        if tag == "title":
            self.in_title = False

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

    def handle_data(self, data):
        if self._is_skipping():
            return

        text = re.sub(r"\s+", " ", data).strip()
        if not text:
            return

        self.text_parts.append(text)

        if self._inside("in_press"):
            self.press_body_parts.append(text)

        if self._inside("in_article"):
            self.article_parts.append(text)

        if self.in_title:
            self.title_parts.append(text)

        if self.current_href:
            self.current_text.append(text)


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

def extract_shop_listing_entries(text_parts, facility_name, area):
    """商業施設の公式新店一覧から、店舗名と開店日を抽出する。"""
    text = clean_text(" ".join(text_parts))
    date_pattern = re.compile(
        r"((?:20\d{2}|\d{2})年\d{1,2}月\d{1,2}日)\s*オープン"
    )
    matches = list(date_pattern.finditer(text))
    entries = []

    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        section = text[match.end():end]
        name_match = re.search(
            r"店名\s*[:：]?\s*(.+?)\s*(?=(?:業種|場所|電話番号|$))",
            section,
        )
        if not name_match:
            continue

        store_name = clean_text(name_match.group(1)).strip(" ・|")
        if not store_name or len(store_name) > 80:
            continue

        industry_match = re.search(
            r"業種\s*[:：]?\s*(.+?)\s*(?=(?:場所|電話番号|$))",
            section,
        )
        location_match = re.search(
            r"場所\s*[:：]?\s*((?:地下)?[1-9]階|屋上|本館|別館)",
            section,
        )
        industry = clean_text(industry_match.group(1)) if industry_match else ""
        floor = clean_text(location_match.group(1)) if location_match else ""

        # 店舗情報サイトの対象外となる公共窓口・福祉支援拠点は除外する。
        non_retail_terms = [
            "ハローワーク", "公共職業安定所",
            "就労移行支援", "障害福祉サービス",
            "LITALICOワークス", "就労支援",
        ]
        if any(term in store_name + " " + industry for term in non_retail_terms):
            continue

        entries.append({
            "store_name": store_name,
            "opening_date": match.group(1),
            "facility_name": facility_name,
            "area": area,
            "industry": industry,
            "floor": floor,
        })

    return entries


def is_article_url(url):
    """対応する公式サイトの個別記事URLを判定する。"""
    path = urlparse(url).path.lower()
    return bool(
        re.search(r"/press/\d+\.html$", path)
        or re.search(r"/site/topics/\d+\.html$", path)
        or re.search(r"/information/detail/$", path)
        or re.search(r"/information/[^/]+/?$", path)
        or re.search(r"/(?:sp/)?news/detail\.html$", path)
        or re.search(r"/search/detail\.html$", path)
    )


def fetch_page(url):
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "(compatible; YamaguchiLocalUpdate/2.1)"
            )
        },
    )

    last_error = None
    for attempt in range(2):
        try:
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
                    charset_match.group(1).strip("\"\'")
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
        except (URLError, TimeoutError, OSError) as error:
            last_error = error
            if attempt == 0:
                print("一時的な取得失敗、再試行:", url, str(error)[:120])
                time.sleep(1)

    raise last_error

def extract_page_text(parser):
    """
    山口県のプレスリリース本文を優先し、
    見つからない場合は main/article、通常テキストの順で使用する。
    """
    press_text = clean_text(" ".join(parser.press_body_parts))
    article_text = clean_text(" ".join(parser.article_parts))
    full_text = clean_text(" ".join(parser.text_parts))

    if len(press_text) >= 100:
        return press_text[:MAX_BODY_CHARS]

    if len(article_text) >= 100:
        return article_text[:MAX_BODY_CHARS]

    return full_text[:MAX_BODY_CHARS]

def classify_text(title, body=""):
    """
    店舗の新規開店・閉店・移転・改装だけを抽出する。
    本文だけで候補にする場合は、店舗語と実際の動作表現を厳格に確認する。
    """

    title = clean_text(title)
    body = clean_text(body)
    combined = title + " " + body

    navigation_words = [
        "カレンダーで探す", "情報一覧", "記事一覧",
        "店舗一覧", "開店一覧", "閉店一覧",
        "検索結果", "カテゴリ一覧", "サイトマップ",
    ]
    if any(word in title for word in navigation_words):
        return [], "一覧・ナビ除外"

    # 行政発表・表敬訪問・任命などは店舗の開閉店情報ではない。
    administrative_title_words = [
        "委嘱", "表敬訪問", "キャンペーン", "アンバサダー",
        "任命", "就任", "激励会", "贈呈", "寄贈",
        "感謝状", "設立報告", "訪問されました",
    ]
    if any(word in title for word in administrative_title_words):
        return [], "行政活動・表敬訪問除外"

    non_shop_facility_words = [
        "公園", "郷土館", "資料館", "博物館", "美術館",
        "ミュージアム", "道の駅", "交流スペース",
    ]
    explicit_shop_words = [
        "店舗", "売店", "テナント", "カフェ", "飲食店",
        "レストラン", "ショップ", "専門店",
    ]
    if (
        any(word in title for word in non_shop_facility_words)
        and not any(word in title for word in explicit_shop_words)
    ):
        return [], "公共・文化施設除外"

    business_words = [
        "店舗", "飲食店", "商業施設", "テナント",
        "カフェ", "喫茶", "レストラン", "美容室", "理容室",
        "サロン", "ジム", "フィットネス", "スタジオ",
        "専門店", "ショップ", "スーパー", "ドラッグストア",
        "書店", "薬局", "コンビニ", "百貨店", "ショッピング",
        "モール", "売場", "小売", "物販",
    ]
    event_words = [
        "イベント", "開催", "フェア", "祭り", "マルシェ",
        "講座", "体験会", "研修会", "審議会", "会議",
        "大会", "式典", "表彰", "募集", "オープンキャンパス",
        "ワークショップ", "説明会", "講演会",
    ]
    strong_movement_words = [
        "新店", "新規開店", "新規オープン", "閉店",
        "営業終了", "閉業", "廃業", "店舗移転",
        "リニューアルオープン", "改装オープン",
    ]

    title_has_business = any(word in title for word in business_words)
    strong_movement = any(word in title for word in strong_movement_words)
    event_context = any(word in title for word in event_words)

    if event_context and not strong_movement:
        return [], "イベント除外"

    categories = []
    if any(word in title for word in ["閉店", "営業終了", "閉業", "廃業", "営業を終了"]):
        categories.append("閉店")

    if any(word in title for word in ["移転", "店舗移転"]):
        if title_has_business or "店舗移転" in title:
            categories.append("移転")

    if any(word in title for word in [
        "リニューアル", "改装オープン",
        "リニューアルオープン", "改装",
    ]):
        if title_has_business or "リニューアルオープン" in title:
            categories.append("リニューアル")

    explicit_new_store = bool(re.search(
        r"新店(?:オープン|開店|が|を|、|「|『|：|:)",
        title,
    ))
    english_new_open = bool(
        re.search(r"\b(?:NEW\s+)?OPEN\b", title, flags=re.IGNORECASE)
        and ("新店" in title or "NEW" in title.upper())
    )
    if explicit_new_store or english_new_open or any(word in title for word in [
        "新規開店", "新規オープン",
        "オープン", "開店", "出店", "開業",
    ]):
        explicit_opening = (
            explicit_new_store
            or english_new_open
            or any(word in title for word in ["新規開店", "新規オープン"])
        )
        if (
            (explicit_opening or title_has_business)
            and "リニューアル" not in categories
        ):
            categories.append("新店・開店")

    # 地域名と店舗の動きがタイトルに明記されている場合は、
    # 店名に業種語がなくても「要確認候補」として拾う。
    # 例:「ケーズデンキ山口店オープン」「サイゼリヤ...山陽小野田市...オープン」
    local_context = any(area in combined for area in JAPAN_AREAS) or "山口県内" in combined
    if not categories and local_context:
        title_has_shop_name = bool(re.search(
            r"(?:[一-龥ぁ-んァ-ヶA-Za-z0-9ー・]{2,}(?:店|店舗)|県内初(?:出店|進出))",
            title,
        ))
        if title_has_shop_name:
            if any(word in title for word in ["閉店", "営業終了", "営業を終了", "閉業", "廃業"]):
                categories.append("閉店")
            elif any(word in title for word in ["移転", "移転オープン"]):
                categories.append("移転")
            elif any(word in title for word in ["リニューアル", "改装オープン"]):
                categories.append("リニューアル")
            elif any(word in title for word in ["オープン", "開店", "開業", "出店", "進出"]):
                categories.append("新店・開店")
        if categories:
            return list(dict.fromkeys(categories)), "地域・店舗名・動向／要確認"

    # 本文のみで候補にする場合は、汎用語「店」「市場」では判定しない。
    # 「店舗がオープンしました」など、実際の動作が完了・予定した表現を要求する。
    if not categories and body:
        body_business_words = [
            "店舗", "飲食店", "商業施設", "テナント",
            "カフェ", "喫茶", "レストラン", "美容室", "理容室",
            "サロン", "ジム", "フィットネス", "スタジオ",
            "専門店", "ショップ", "スーパー", "ドラッグストア",
            "書店", "薬局", "コンビニ", "百貨店", "モール",
        ]
        body_patterns = [
            ("閉店", r"(?:閉店|営業終了|営業を終了|閉業|廃業)(?:しました|します|することになりました|いたします|する予定です|予定です|へ)"),
            ("移転", r"(?:移転|移転オープン)(?:しました|します|することになりました|する予定です|予定です)"),
            ("リニューアル", r"(?:リニューアルオープン|改装オープン)(?:しました|します|する予定です|予定です)"),
            ("新店・開店", r"(?:オープン|開店|開業|出店|営業開始|営業を開始|開設)(?:しました|します|いたしました|いたします|する予定です|予定です|予定|へ)"),
        ]
        body_sentences = [
            clean_text(part)
            for part in re.split(r"[。.!?！？\n]+", body)
            if clean_text(part)
        ]
        for sentence in body_sentences:
            if not any(word in sentence for word in body_business_words):
                continue
            for category, pattern in body_patterns:
                if re.search(pattern, sentence):
                    categories.append(category)
                    break
            if categories:
                break

        if categories:
            return list(dict.fromkeys(categories)), "本文・要確認"

    if categories:
        return list(dict.fromkeys(categories)), "タイトル"

    return [], "分類要確認"

def extract_opening_date(text):
    """開店・営業開始の語に近接する明示日付だけを抽出し、掲載日との混同を防ぐ。"""
    text = clean_text(text)
    match = re.search(
        r"(?<!\d)((?:20\d{2}|\d{2})年\d{1,2}月\d{1,2}日)"
        r"(?:[（(][月火水木金土日](?:曜)?[）)])?"
        r"(?:\s*(?:に|から|より))?\s*(?:新規)?(?:オープン|開店|営業開始)",
        text,
    )
    if not match:
        return ""
    date_text = match.group(1)
    year_match = re.match(r"(20\d{2}|\d{2})年", date_text)
    year = int(year_match.group(1))
    if year < 100:
        year += 2000
        date_text = re.sub(r"^\d{2}年", f"{year}年", date_text)
    return date_text


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


def resolve_area(text, default_area=""):
    """記事本文に地域があれば優先し、公式施設の所在地は補完情報として使う。"""
    areas = extract_area(text)
    return areas if areas else ([default_area] if default_area else [])


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
    default_area="",
    audit_log=None,
):
    article_title = clean_text(link_title)
    body = ""
    published_date = ""
    date_basis = "日付確認が必要"
    status = "未確認・公開禁止"

    try:
        html = fetch_page(target_url)

        if not html:
            if audit_log is not None:
                audit_log.append({
                    "title": article_title,
                    "url": target_url,
                    "source_name": source_name,
                    "result": "取得不可",
                    "reason": "HTML本文を取得できませんでした",
                })
            return None

        parser = PageParser()
        parser.feed(html)
        article_title = (
            clean_text(" ".join(parser.title_parts))
            or article_title
        )

        body = extract_page_text(parser)
        published_date, date_basis = (
            extract_published_date(parser, body)
        )

        categories, category_basis = classify_text(
            article_title,
            body,
        )

        if not categories:
            if audit_log is not None:
                audit_log.append({
                    "title": article_title,
                    "url": target_url,
                    "source_name": source_name,
                    "result": "除外",
                    "reason": category_basis,
                })
            return None

        if audit_log is not None:
            audit_log.append({
                "title": article_title,
                "url": target_url,
                "source_name": source_name,
                "result": "候補",
                "reason": category_basis,
                "category": categories,
            })

        area = resolve_area(
            article_title + " " + body,
            default_area,
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
            "opening_date": extract_opening_date(article_title + " " + body),
            "opening_date_basis": "本文・見出し記載／要確認",
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
        if audit_log is not None:
            audit_log.append({
                "title": article_title,
                "url": target_url,
                "source_name": source_name,
                "result": "取得失敗",
                "reason": str(error)[:180],
            })

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
    article_audit = []
    inspected_article_urls = set()

    for source in SOURCES:
        print("調査開始:", source["name"])

        result = {
            "name": source["name"],
            "url": source["url"],
            "checked_at": checked_at,
            "status": "check_needed",
            "pages_scanned": 0,
            "fetch_errors": [],
            "note": "",
        }

        queue = [source["url"]]
        visited = set()
        queued = {source["url"]}
        successful_pages = 0
        article_checks = 0

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

                successful_pages += 1
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

                if source.get("kind") == "shop_listing":
                    entries = extract_shop_listing_entries(
                        parser.text_parts,
                        facility_name="シーモール下関",
                        area="下関市",
                    )
                    for entry in entries:
                        title = (
                            f"{entry['store_name']}（{entry['facility_name']}）"
                            f"{entry['opening_date']}オープン"
                        )
                        item_id = hashlib.sha256(
                            f"{current_url}|{entry['store_name']}|{entry['opening_date']}".encode("utf-8")
                        ).hexdigest()[:16]
                        candidate = {
                            "id": item_id,
                            "title": title,
                            "url": current_url,
                            "source_name": source["name"],
                            "source_page": current_url,
                            "category": ["新店・開店"],
                            "category_basis": "商業施設公式・新店一覧／要確認",
                            "published_date": "",
                            "date_basis": "掲載ページの更新日と開店日を区別して確認",
                            "opening_date": entry["opening_date"],
                            "area": entry["area"],
                            "industry": entry.get("industry", ""),
                            "floor": entry.get("floor", ""),
                            "body_excerpt": "",
                            "checked_at": checked_at,
                            "status": "未確認・公開禁止",
                        }
                        candidates.append(candidate)
                        article_audit.append({
                            "title": title,
                            "url": current_url,
                            "source_name": source["name"],
                            "result": "候補",
                            "reason": "商業施設公式・新店一覧／要確認",
                            "category": ["新店・開店"],
                            "opening_date": entry["opening_date"],
                        })
                    if entries:
                        print("施設公式の新店掲載:", len(entries))
                    continue

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

                    # 見出しだけでは判定できない記事もあるため、
                    # 公式サイトの個別記事URLは本文を確認する。
                    # 一覧・検索ページを大量取得しないよう上限を設ける。
                    check_article_body = (
                        is_article_url(target_url)
                        and article_checks < MAX_ARTICLE_CHECKS_PER_SOURCE
                    )
                    if not categories and not check_article_body:
                        continue

                    # 同じ記事が複数の一覧ページに掲載されていても、
                    # 本文取得・監査ログはURLごとに1回だけ行う。
                    if target_url in inspected_article_urls:
                        continue
                    inspected_article_urls.add(target_url)

                    if check_article_body:
                        article_checks += 1

                    candidate = inspect_candidate(
                        target_url=target_url,
                        link_title=title,
                        source_name=source["name"],
                        source_page=current_url,
                        default_area=source.get("default_area", ""),
                        audit_log=article_audit,
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
                error_record = {
                    "url": current_url,
                    "error": str(error)[:180],
                }
                result["fetch_errors"].append(error_record)
                print(
                    "取得失敗:",
                    current_url,
                    str(error)[:150],
                )

        result["pages_scanned"] = successful_pages

        if successful_pages and result["fetch_errors"]:
            result["status"] = "partial"
        elif successful_pages:
            result["status"] = "reachable"
        else:
            result["status"] = "check_needed"

        result["note"] = (
            "成功ページ数と取得失敗を分けて記録。"
            "一時的な通信・SSLエラーは1回再試行。"
            "公開日は明示的なメタ情報を優先。"
            "公開前に元記事を確認してください。"
        )

        source_checks.append(result)

    # URL単位で重複を整理
    unique = {}

    for item in candidates:
        dedup_key = item.get("id") or item["url"]

        if dedup_key not in unique:
            unique[dedup_key] = item
            continue

        existing = unique[dedup_key]

        if (
            len(item.get("body_excerpt", ""))
            > len(existing.get("body_excerpt", ""))
        ):
            unique[dedup_key] = item

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
        "article_audit": article_audit,
        "article_audit_count": len(article_audit),
        "article_audit_unique_urls": len({
            item.get("url") for item in article_audit
            if item.get("url")
        }),
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