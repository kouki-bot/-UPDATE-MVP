import html
from html.parser import HTMLParser
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_FILE = DATA_DIR / "rss_candidates.json"
JST = timezone(timedelta(hours=9))
UTC = timezone.utc
RECENT_DAYS = 30
MAX_ITEMS_PER_SOURCE = 100
USER_AGENT = "Mozilla/5.0 (compatible; YamaguchiLocalUpdate/1.1)"

RSS_SOURCES = [
    {"name": "山口宇部経済新聞", "url": "https://yamaguchi.keizai.biz/rss.xml",
     "area": ["山口市", "宇部市", "山陽小野田市", "美祢市", "防府市", "萩市", "長門市"]},
    {"name": "号外NET 山口市・防府市", "url": "https://yamaguchi-hofu.goguynet.jp/feed/",
     "area": ["山口市", "防府市"]},
    {"name": "号外NET 宇部市・山陽小野田市", "url": "https://ube-sanyoonoda.goguynet.jp/feed/",
     "area": ["宇部市", "山陽小野田市"]},
]
HTML_SOURCES = [
    {"name": "山口新聞 開店・閉店一覧", "url": "https://yama.minato-yamaguchi.co.jp/topics/shops/",
     "area": ["山口県内"]},
    {"name": "開店閉店.com 山口カテゴリ", "url": "https://kaiten-heiten-24.com/category/yamaguchi/",
     "area": ["山口県内"]},
]
KEYWORD_GROUPS = {
    "新店・開店": ["新店", "新店舗", "新規開店", "新規出店", "オープン", "開店", "開業", "出店",
                  "グランドオープン", "プレオープン", "初出店", "開店予定", "開業予定",
                  "オープン予定", "新たにオープン", "新しくオープン"],
    "閉店": ["閉店", "営業終了", "閉業", "店じまい", "閉店のお知らせ", "閉店しました", "閉店予定", "営業を終了"],
    "移転": ["移転", "移転オープン", "移転のお知らせ", "移転しました", "移転予定", "移転先"],
    "リニューアル": ["リニューアル", "改装オープン", "リニューアルオープン", "営業再開", "リニューアル予定", "改装"],
}
EXCLUDE_TITLE_KEYWORDS = [
    "求人", "アルバイト募集", "スタッフ募集", "採用情報", "正社員募集",
    "イベント情報", "イベント開催", "マルシェ開催", "フェス開催", "祭り開催",
    "ワークショップ開催", "参加者募集", "出店者募集", "整備計画", "建設計画",
    "入札", "議会", "市長会見", "補助金", "公式ウェブサイト", "公式サイト",
    "ホームページをリニューアル", "市役所", "県庁", "図書館", "学校", "小学校",
    "中学校", "高校", "公民館", "体育館", "庁舎", "公共施設", "交流拠点施設",
    "郷土館", "体験交流公園", "子育て支援拠点",
]
STRONG_STORE_WORDS = ["新店", "新店舗", "オープン", "開店", "閉店", "移転", "リニューアル", "改装オープン"]

def now_jst():
    return datetime.now(JST)

def clean_text(value):
    if not value:
        return ""
    value = html.unescape(str(value))
    value = re.sub(r"<[^>]+>", " ", value).replace("\xa0", " ")
    return re.sub(r"\s+", " ", value).strip()

def local_name(tag):
    return tag.split("}")[-1].split(":")[-1].lower()

def get_child_text(element, names):
    names = {n.lower().split(":")[-1] for n in names}
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
        if href and child.attrib.get("rel", "alternate") == "alternate":
            return href
        value = "".join(child.itertext()).strip()
        if value:
            return value
    return ""

def normalize_url(url):
    try:
        p = urlsplit((url or "").strip())
        tracking = {"fbclid", "gclid", "yclid", "mc_cid", "mc_eid"}
        query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
                 if k.lower() not in tracking and not k.lower().startswith("utm_")]
        return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/") or "/", urlencode(query), ""))
    except (ValueError, TypeError, AttributeError):
        return (url or "").strip()

def parse_date(value):
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value.strip())
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(JST)
    except (TypeError, ValueError, OverflowError):
        pass
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(JST)
    except (TypeError, ValueError, OverflowError):
        return None

def extract_published_date(element):
    # RSS/Atomの公開日フィールドのみを採用。本文の日付は公開日と誤認しやすいため使用しない。
    for child in element.iter():
        if local_name(child.tag) in {"pubdate", "published", "updated", "date"}:
            parsed = parse_date("".join(child.itertext()).strip())
            if parsed:
                return parsed
    return None

def classify_text(text):
    text = clean_text(text)
    return [cat for cat, words in KEYWORD_GROUPS.items() if any(w in text for w in words)]

def is_excluded(title, description):
    title = clean_text(title)
    if not classify_text(title):
        return True
    # 公共施設・行政・求人・イベント告知を除外。ただしタイトル自体に明確な店舗動向がある場合は要確認候補に残す。
    if any(w in title for w in EXCLUDE_TITLE_KEYWORDS):
        if not any(w in title for w in STRONG_STORE_WORDS):
            return True
    if any(w in title for w in ["ウェブサイト", "ホームページ", "公式サイト"]):
        return True
    if any(w in (title + " " + clean_text(description)) for w in ["仙台経済新聞", "横浜経済新聞"]):
        return True
    return False

def get_freshness(published):
    if not published:
        return "日付確認が必要", None
    age = (now_jst().date() - published.date()).days
    if age < -1:
        return "未来日付・要確認", age
    age = max(age, 0)
    if age <= RECENT_DAYS:
        return "直近30日", age
    if age <= 90:
        return "31〜90日前", age
    return "90日より前", age

def fetch_rss(source):
    req = urllib.request.Request(source["url"], headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            raw = response.read()
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        print(f"[取得失敗] {source['name']}: {exc}")
        return []
    text = raw.decode("utf-8-sig", errors="replace")
    text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", "", text)
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
        description = get_child_text(element, ["description", "summary", "content", "encoded"])
        if not title or not link or is_excluded(title, description):
            continue
        categories = classify_text(title)
        if not categories:
            continue
        published = extract_published_date(element)
        freshness, age = get_freshness(published)
        items.append({
            "title": title, "url": link, "normalized_url": normalize_url(link),
            "source_name": source["name"], "source_url": source["url"],
            "area": source["area"], "area_status": "配信元の対象地域・店舗所在地は未確認",
            "categories": categories, "category_basis": "タイトル",
            "priority": 1 if any(c in categories for c in ["新店・開店", "閉店"]) else 2,
            "published_date": published.isoformat() if published else "",
            "freshness": freshness, "age_days": age, "description": description[:1000],
            "relevance": "タイトルから仮分類・要確認", "status": "未確認・公開禁止",
            "checked_at": now_jst().isoformat(),
        })
        if len(items) >= MAX_ITEMS_PER_SOURCE:
            break
    print(f"[取得完了] {source['name']}: {len(items)}件")
    return items


class AnchorParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.anchors = []
        self.current = None
    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            attrs = dict(attrs)
            href = attrs.get("href", "")
            if href.startswith("http"):
                self.current = {"url": href, "text": ""}
    def handle_data(self, data):
        if self.current is not None:
            self.current["text"] += data
    def handle_endtag(self, tag):
        if tag.lower() == "a" and self.current is not None:
            self.current["text"] = clean_text(self.current["text"])
            if self.current["text"]:
                self.anchors.append(self.current)
            self.current = None

def date_from_url(url):
    m = re.search(r"/(20\d{2})/(\d{1,2})/(\d{1,2})(?:/|$)", url)
    if not m:
        m = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", url)
    if not m:
        return None
    try:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=JST)
    except ValueError:
        return None

def fetch_html_source(source):
    req = urllib.request.Request(source["url"], headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            raw = response.read()
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        print(f"[HTML取得失敗] {source['name']}: {exc}")
        return []
    text = raw.decode("utf-8", errors="replace")
    parser = AnchorParser()
    parser.feed(text)
    items, seen = [], set()
    
    for a in parser.anchors:
        title, url = a["text"], a["url"]
        parsed_url = urlsplit(url)
        host = parsed_url.netloc.lower()
        path = parsed_url.path.rstrip("/") or "/"

        # 対象サイト以外のリンクは除外
        if not any(
            domain in host
            for domain in [
                "minato-yamaguchi.co.jp",
                "kaiten-heiten-24.com",
                "kaiten-heiten.com",
            ]
        ):
            continue

        # トップページ・カテゴリ一覧・サイト名だけの候補を除外
        normalized = normalize_url(url)
        source_normalized = normalize_url(source["url"])
        generic_titles = {
            "開店閉店.com",
            "開店・閉店",
            "続きを読む",
            "次へ",
            "前へ",
        }

        if normalized == source_normalized:
            continue
        if (
            path.startswith("/category/")
            or path.startswith("/tag/")
            or path.startswith("/page/")
            or path in {"/", ""}
        ):
            continue
        if title in generic_titles or len(title) < 8:
            continue
        
        if normalized in seen:
            continue
        if not classify_text(title) or is_excluded(title, ""):
            continue

        seen.add(normalized)

        published = date_from_url(url)
        freshness, age = get_freshness(published)
        items.append({
            "title": title, "url": url, "normalized_url": normalize_url(url),
            "source_name": source["name"], "source_url": source["url"],
            "area": source["area"], "area_status": "配信元の対象地域・店舗所在地は未確認",
            "categories": classify_text(title), "category_basis": "一覧タイトル",
            "priority": 1 if any(c in classify_text(title) for c in ["新店・開店", "閉店"]) else 2,
            "published_date": published.isoformat() if published else "",
            "freshness": freshness, "age_days": age, "description": "",
            "relevance": "一覧タイトルから仮分類・要確認", "status": "未確認・公開禁止",
            "checked_at": now_jst().isoformat(),
        })
        if len(items) >= MAX_ITEMS_PER_SOURCE:
            break
    print(f"[HTML取得完了] {source['name']}: {len(items)}件")
    return items

def merge_candidates(candidates):
    merged = {}
    title_index = {}
    for item in candidates:
        url_key = normalize_url(item.get("url", ""))
        if not url_key:
            continue
        title_key = re.sub(r"[\W_]+", "", item.get("title", "").lower())
        key = url_key
        if key not in merged and title_key and title_key in title_index:
            key = title_index[title_key]
        if key not in merged:
            merged[key] = item.copy()
            merged[key]["area"] = list(item.get("area", []))
            merged[key]["categories"] = list(item.get("categories", []))
            if title_key:
                title_index[title_key] = key
            continue
        old = merged[key]
        old["categories"] = list(dict.fromkeys(old.get("categories", []) + item.get("categories", [])))
        old["area"] = list(dict.fromkeys(old.get("area", []) + item.get("area", [])))
        if not old.get("published_date") and item.get("published_date"):
            old["published_date"] = item["published_date"]
            old["freshness"] = item.get("freshness", "日付確認が必要")
            old["age_days"] = item.get("age_days")
        if len(item.get("description", "")) > len(old.get("description", "")):
            old["description"] = item.get("description", "")
    return list(merged.values())

def sort_key(item):
    order = {"直近30日": 0, "31〜90日前": 1, "日付確認が必要": 2, "未来日付・要確認": 3, "90日より前": 4}
    date = parse_date(item.get("published_date", ""))
    return (order.get(item.get("freshness", ""), 5), item.get("priority", 5),
            -(date.timestamp() if date else 0), item.get("title", ""))


class ArticleTextParser(HTMLParser):
    """Extract a conservative article summary from meta descriptions and main text."""
    def __init__(self):
        super().__init__()
        self.meta_description = ""
        self.title_parts = []
        self.paragraphs = []
        self._in_title = False
        self._capture = None
        self._buffer = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrs = dict(attrs)
        if tag in {"script", "style", "noscript", "svg", "nav", "footer", "header", "aside"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "meta":
            name = (attrs.get("name") or attrs.get("property") or "").lower()
            content = clean_text(attrs.get("content", ""))
            if name in {"description", "og:description", "twitter:description"} and content:
                if len(content) > len(self.meta_description):
                    self.meta_description = content
        elif tag == "title":
            self._in_title = True
        elif tag in {"p", "article"}:
            self._capture = tag
            self._buffer = []

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg", "nav", "footer", "header", "aside"}:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return
        if tag == "title":
            self._in_title = False
        if self._capture == tag and tag in {"p", "article"}:
            text = clean_text(" ".join(self._buffer))
            if len(text) >= 25:
                self.paragraphs.append(text)
            self._capture = None
            self._buffer = []

    def handle_data(self, data):
        if self._skip_depth:
            return
        value = clean_text(data)
        if not value:
            return
        if self._in_title:
            self.title_parts.append(value)
        if self._capture in {"p", "article"}:
            self._buffer.append(value)

def fetch_article_excerpt(url):
    """Fetch one article page and return a short extract; failure is non-fatal."""
    if not url or urlsplit(url).scheme not in {"http", "https"}:
        return ""
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "ja,en-US;q=0.7,en;q=0.5",
    })
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            content_type = response.headers.get("Content-Type", "").lower()
            if content_type and "html" not in content_type and "text/" not in content_type:
                return ""
            raw = response.read(1_500_000)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        print(f"[記事本文取得失敗] {url}: {exc}")
        return ""
    charset = "utf-8"
    match = re.search(rb"charset=['\"]?([a-zA-Z0-9._-]+)", raw[:4096], re.I)
    if match:
        try:
            charset = match.group(1).decode("ascii", errors="ignore")
        except Exception:
            charset = "utf-8"
    try:
        page = raw.decode(charset, errors="replace")
    except LookupError:
        page = raw.decode("utf-8", errors="replace")
    parser = ArticleTextParser()
    try:
        parser.feed(page)
    except Exception:
        return ""
    # Prefer a publisher-provided meta description; otherwise use a short article paragraph.
    if parser.meta_description and len(parser.meta_description) >= 25:
        return parser.meta_description[:1000]
    paragraphs = []
    seen = set()
    for paragraph in parser.paragraphs:
        if paragraph not in seen and len(paragraph) >= 25:
            seen.add(paragraph)
            paragraphs.append(paragraph)
    if paragraphs:
        return " ".join(paragraphs[:3])[:1000]
    return ""

def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    all_items, source_results = [], []
    for source in RSS_SOURCES:
        items = fetch_rss(source)
        source_results.append({"name": source["name"], "url": source["url"], "area": source["area"], "items_read": len(items)})
        all_items.extend(items)
    for source in HTML_SOURCES:
        items = fetch_html_source(source)
        source_results.append({"name": source["name"], "url": source["url"], "area": source["area"], "items_read": len(items), "method": "HTML一覧取得", "date_note": "記事URLから日付が取得できない場合は日付確認が必要"})
        all_items.extend(items)
    candidates = merge_candidates(all_items)
    # Fetch article-page summaries only when RSS/list metadata has no useful excerpt.
    # Limit page requests to reduce load and keep GitHub Actions runtime bounded.
    fetch_count = 0
    for item in candidates:
        if item.get("description") and len(clean_text(item.get("description"))) >= 40:
            item["body_excerpt"] = clean_text(item.get("description"))[:1000]
            item["body_excerpt_method"] = "RSS description"
            continue
        if fetch_count >= 60:
            item["body_excerpt"] = ""
            item["body_excerpt_method"] = "not_fetched_limit"
            continue
        excerpt = fetch_article_excerpt(item.get("url", ""))
        fetch_count += 1
        item["body_excerpt"] = excerpt
        item["body_excerpt_method"] = "article_meta_or_paragraph" if excerpt else "unavailable"
    candidates.sort(key=sort_key)
    cats, freshness = Counter(), Counter()
    for item in candidates:
        cats.update(item["categories"])
        freshness[item["freshness"]] += 1
    result = {
        "generated_at": now_jst().isoformat(),
        "purpose": "山口県内の新店舗・閉店・移転・リニューアル情報の候補収集",
        "total_candidates": len(candidates),
        "recent_candidate_count": sum(1 for x in candidates if x["freshness"] == "直近30日"),
        "category_counts": dict(cats), "freshness_counts": dict(freshness),
        "sources": source_results, "candidates": candidates,
        "notice": "すべて未確認です。自動公開は禁止。配信元の対象地域は店舗所在地を保証しません。掲載前に店舗名・所在地・日付・営業状況・情報源を確認してください。",
    }
    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("RSS候補:", len(candidates), "直近30日:", result["recent_candidate_count"])
    print("カテゴリー:", dict(cats), "鮮度:", dict(freshness), "保存先:", OUTPUT_FILE)

if __name__ == "__main__":
    main()
