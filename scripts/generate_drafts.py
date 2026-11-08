import hashlib
import json
import re
import unicodedata
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
    "グランドオープン", "プレオープン", "閉店", "閉館", "営業終了", "閉業", "廃業", "店じまい",
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
    """タイトル・本文抜粋から市町名候補を抽出。所在地の確定や推測は行わない。"""
    text = clean_text(f"{title or ''} {body_excerpt or ''}")
    # 「山口県山口市黒川」のような住所表記を優先する。
    # 本文中の他市の比較情報・県内店舗数などを所在地候補に混ぜない。
    municipality_pattern = "|".join(
        re.escape(name) for name in YAMAGUCHI_MUNICIPALITIES
    )
    explicit_addresses = re.findall(
        r"山口県\s*(" + municipality_pattern + r")", text
    )
    if explicit_addresses:
        return sorted(
            set(explicit_addresses),
            key=lambda x: YAMAGUCHI_MUNICIPALITIES.index(x)
        )

    found = []
    for name in YAMAGUCHI_MUNICIPALITIES:
        if name in text:
            found.append(name)

    aliases = {
        "山陽小野田": "山陽小野田市", "周防大島": "周防大島町",
        "田布施": "田布施町", "上関": "上関町", "平生": "平生町",
        "和木": "和木町", "阿武": "阿武町", "下関": "下関市",
        "宇部": "宇部市", "山口": "山口市", "萩": "萩市",
        "防府": "防府市", "下松": "下松市", "岩国": "岩国市",
        "長門": "長門市", "柳井": "柳井市", "美祢": "美祢市",
        "周南": "周南市", "光": "光市",
    }
    suffix_pattern = (
        r"(?:店|店舗|支店|営業所|施設|ホテル|駅(?:前|周辺|近く)?|"
        r"市内|町内|市|町|周辺|市街地|商店街|中央町|新川|"
        r"で開店|に開店|でオープン|にオープン|で閉店|に閉店|"
        r"の店舗|の店|にある|に誕生|で営業)"
    )
    for alias, official in aliases.items():
        if official in found:
            continue
        if alias == "山口":
            pattern = r"山口(?!県|新聞|放送|銀行|合同庁舎)(?:" + suffix_pattern + r")"
        else:
            pattern = re.escape(alias) + r"(?:" + suffix_pattern + r")"
        if re.search(pattern, text):
            found.append(official)

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
        "閉店": ["閉店", "閉館", "営業終了", "閉業", "廃業", "店じまい"],
        "移転": ["移転"],
        "リニューアル": ["リニューアル", "改装オープン", "営業再開", "改装"],
    }
    return [cat for cat, words in mapping.items() if any(w in title for w in words)]

def has_body_movement_evidence(body_excerpt):
    """RSS本文に実際の店舗移動アクションが明記されている場合だけ補完する。"""
    body_excerpt = clean_text(body_excerpt)
    # 既存店の周年紹介は新規開店の根拠にしない。
    if re.search(r"(?:オープン|開店|開業)から.{0,12}\d+周年", body_excerpt):
        return False
    return bool(re.search(
        r"(?:オープン|開店|開業|出店|移転|閉店|営業終了|リニューアル)"
        r"(?:しました|していました|しています|した|している|します|する|を開始|予定|を予定)",
        body_excerpt,
    ))

def is_event_only_content(title, body_excerpt=""):
    """店舗の開業・閉店ではなく、単発イベント告知と判断できる候補を除外する。"""
    title_text = clean_text(title)
    event_markers = (
        "オープンキャンパス", "一日限定イベント", "1日限定イベント",
        "一日イベント", "イベント開催", "マルシェ", "フェス開催",
        "祭り開催", "ワークショップ", "参加者募集", "出店者募集",
        "説明会", "体験会",
    )
    body_text = clean_text(body_excerpt)
    # 学校の授業・実習として一日だけ営業するレストランは新規店舗ではない。
    if re.search(r"(?:専門学校|高校|大学).{0,40}(?:在校生|学生).{0,30}(?:調理|接客).{0,30}(?:レストラン|飲食)", body_text):
        return True
    if re.search(r"(?:一日限り|1日限り|一日だけ|1日だけ|一日限定|1日限定).{0,30}(?:営業|開店|レストラン|飲食店)", body_text):
        return True
    if not any(marker in title_text for marker in event_markers):
        return False
    store_movement = re.search(
        r"(?:新店|新店舗|新規開店|新規出店|オープン|開店|開業|閉店|営業終了|閉業|移転|リニューアル|改装オープン)",
        title_text,
    )
    return not bool(store_movement)


def is_store_news(title, body_excerpt=""):
    # 単発イベント・学校行事は店舗の開閉店情報ではないため除外。
    title_text = clean_text(title)
    if is_event_only_content(title_text, body_excerpt):
        return False
    # 学校行事・イベント告知の「オープン」は施設や店舗の開業を意味しない。
    if "オープンキャンパス" in title_text:
        return False
    if any(word in title_text for word in ["イベント", "フェア", "説明会", "体験会"]):
        actual_opening = re.search(
            r"(?:オープン|開店|開業|開館|開園)(?:し(?:た|ます|ました)|する|しました|しました)",
            title_text + " " + clean_text(body_excerpt),
        )
        if not actual_opening:
            return False
    # タイトルに動きがなくても、本文に明確な実施表現があれば候補化する。
    if not title or (not detect_categories(title) and not has_body_movement_evidence(body_excerpt)):
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

# Explicit non-Yamaguchi locations are excluded only when the title clearly ties
# the place name to a store/location. Missing Yamaguchi evidence alone is not enough.
FOREIGN_CITY_STORE_PATTERNS = [
    r"伊勢崎(?:市)?(?:南店|店|市内)",
    r"船橋市?(?:新船橋|船橋)(?:店|駅前|市内)",
    r"中目黒(?:店|駅周辺|エリア)",
    r"名古屋市?(?:ささしま|名駅|栄)(?:店|エリア)",
]

LISTING_URL_PARTS = ("/category/", "/tag/", "/page/", "/archive/", "/archives/")
LISTING_TITLE_PATTERNS = (
    "開店・閉店情報一覧", "開店閉店情報一覧", "新店・閉店一覧",
    "オープン情報一覧", "閉店情報まとめ", "開店情報まとめ",
    "閉店情報-業種別", "開店情報-業種別", "閉店情報 業種別", "開店情報 業種別",
)

def is_listing_candidate(title, url, source_url=""):
    """明らかな一覧・カテゴリーページだけを除外する。"""
    for candidate_url in (url, source_url):
        path = urlsplit(clean_text(candidate_url)).path.lower()
        if any(part in path for part in LISTING_URL_PARTS):
            return True
        # 開店閉店.com の業種別カテゴリーページなど、category パスを使わない一覧URL
        if re.search(r"/(?:kaiten|heiten)-gyousyubetsu/?$", path):
            return True
    normalized_title = clean_text(title)
    return any(pattern in normalized_title for pattern in LISTING_TITLE_PATTERNS)

NON_YAMAGUCHI_PREFECTURES = [
    "北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県",
    "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県",
    "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県", "岐阜県",
    "静岡県", "愛知県", "三重県", "滋賀県", "京都府", "大阪府", "兵庫県",
    "奈良県", "和歌山県", "鳥取県", "島根県", "岡山県", "広島県",
    "徳島県", "香川県", "愛媛県", "高知県", "福岡県", "佐賀県", "長崎県",
    "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県",
]

def is_clearly_outside_yamaguchi(title, body_excerpt=""):
    """タイトルまたは記事冒頭の所在地表記から県外と確認できる場合のみ除外する。"""
    title_text = clean_text(title)
    body_text = clean_text(body_excerpt)

    # 明示された山口県内の市町名は県外判定しない。
    if any(name in title_text for name in YAMAGUCHI_MUNICIPALITIES) or "山口県" in title_text:
        return False

    # 店舗記事の冒頭にある所在地（例: 群馬県伊勢崎市、東京都目黒区）を確認。
    # 配信元のareaメタデータは判定に使用しない。
    location_prefix = body_text[:120]
    if any(prefecture in location_prefix for prefecture in NON_YAMAGUCHI_PREFECTURES):
        return True

    combined = f"{title_text} {location_prefix}"
    return any(re.search(pattern, combined) for pattern in FOREIGN_CITY_STORE_PATTERNS)

def extract_approximate_event_date_text(title, body_excerpt):
    """店舗名に結び付く「11月中旬」等の曖昧な予定日を記録。日付には変換しない。"""
    title_text = unicodedata.normalize("NFKC", clean_text(title))
    body_text = unicodedata.normalize("NFKC", clean_text(body_excerpt))
    targets = re.findall(r"[「『]([^」』]{2,24})[」』]", title_text)
    relevant_sentences = [
        sentence for sentence in re.split(r"(?<=[。！？!?])", body_text)
        if any(target in sentence for target in targets)
    ] if targets else []
    search_text = " ".join(relevant_sentences) if relevant_sentences else body_text
    pattern = re.compile(r"(?P<date>\d{1,2}月(?:上旬|中旬|下旬))")
    action = re.compile(r"オープン|開店|開業|出店|閉店|営業終了|移転|リニューアル|営業再開")
    for sentence in re.split(r"(?<=[。！？!?])", search_text):
        if not action.search(sentence):
            continue
        match = pattern.search(sentence)
        if match:
            return match.group("date")
    return ""


def extract_event_date(title, body_excerpt, published_date=""):
    """店舗の動作語に近接する日付だけを抽出。記事公開日や無関係な日付は転用しない。"""
    body = unicodedata.normalize("NFKC", clean_text(body_excerpt))
    title_text = unicodedata.normalize("NFKC", clean_text(title))
    base = parse_date(published_date)
    action_words = (
        "オープン", "開店", "開業", "出店", "閉店", "閉業",
        "営業終了", "営業を終了", "移転", "リニューアル", "営業再開",
    )
    action_re = re.compile(
        r"オープン(?!セール|場所|情報|記念|キャンペーン)|"
        r"開店|開業|出店|閉店|閉業|営業終了|営業を終了|移転|リニューアル|営業再開"
    )
    # タイトルで特定できる店舗名が本文にある場合、その店舗に関係する文を優先する。
    # 商業施設自体のリニューアル日を、入居テナントの開店日として誤採用しない。
    title_targets = re.findall(r"[「『]([^」』]{2,24})[」』]", title_text)
    if title_targets:
        target_sentences = [
            sentence for sentence in re.split(r"(?<=[。！？!?])", body)
            if any(target in sentence for target in title_targets)
        ]
        if target_sentences:
            body = " ".join(target_sentences)
    # URL内やリンク先の年月日は、本文の店舗動作日と誤認しない。
    body = re.sub(r"https?://\S+", " ", body)

    def find_action_date(text):
        patterns = [
            re.compile(r"(?P<year>20\d{2})年(?P<month>\d{1,2})月(?:(?P<day>\d{1,2})日|(?P<end>末))"),
            re.compile(r"(?P<month>\d{1,2})月(?P<day>\d{1,2})日"),
            re.compile(r"(?<!\d)(?P<day>\d{1,2})日"),
        ]
        matches = []
        for pattern_index, pattern in enumerate(patterns):
            for match in pattern.finditer(text):
                # 日付と店舗動作語は同じ文の中にある場合だけ関連付ける。
                separators = "。！？!?\\n"
                sentence_left = max(
                    [text.rfind(mark, 0, match.start()) for mark in separators] + [-1]
                ) + 1
                following = [
                    pos for mark in separators
                    if (pos := text.find(mark, match.end())) >= 0
                ]
                sentence_right = min(following) if following else len(text)
                sentence = text[sentence_left:sentence_right]
                actions = list(action_re.finditer(sentence))
                if not actions:
                    continue
                local_start = match.start() - sentence_left
                local_end = match.end() - sentence_left
                # 「閉店した翌日」の日付は閉店日ではないため採用しない。
                valid_actions = []
                for action in actions:
                    action_start = sentence_left + action.start()
                    action_end = sentence_left + action.end()
                    date_start = match.start()
                    gap = text[min(action_end, date_start):max(action_start, date_start)]
                    if re.search(r"翌日|翌週|翌月|翌年", gap):
                        continue
                    valid_actions.append(action)
                if not valid_actions:
                    continue
                distance = min(
                    0 if a.start() <= local_start <= a.end() else
                    min(abs(a.start() - local_start), abs(a.end() - local_end))
                    for a in valid_actions
                )
                year_text = match.groupdict().get("year")
                month_text = match.groupdict().get("month")
                day_text = match.groupdict().get("day")
                is_month_end = bool(match.groupdict().get("end"))
                try:
                    if year_text:
                        year = int(year_text)
                        month = int(month_text)
                        if is_month_end:
                            next_month = datetime(year + (month == 12), month % 12 + 1, 1, tzinfo=JST)
                            value = (next_month.date() - timedelta(days=1)).isoformat()
                        else:
                            value = datetime(year, month, int(day_text), tzinfo=JST).date().isoformat()
                    elif month_text and day_text:
                        if not base:
                            continue
                        year = base.year
                        candidate = datetime(year, int(month_text), int(day_text), tzinfo=JST)
                        if abs((candidate.date() - base.date()).days) > 120:
                            continue
                        value = candidate.date().isoformat()
                    else:
                        if not base:
                            continue
                        candidate = datetime(base.year, base.month, int(match.group("day")), tzinfo=JST)
                        if abs((candidate.date() - base.date()).days) > 31:
                            continue
                        value = candidate.date().isoformat()
                    matches.append((pattern_index, distance, match.start(), value))
                except (ValueError, OverflowError):
                    continue
        if not matches:
            return ""
        matches.sort(key=lambda x: (x[0], x[1], x[2]))
        return matches[0][3]

    # 店舗名に結び付く曖昧な日付がある場合、別施設の正確な日付を流用しない。
    if extract_approximate_event_date_text(title_text, body):
        return ""
    # 本文の店舗動作日を最優先。タイトルは本文にない場合だけ調べる。
    return find_action_date(body) or find_action_date(title_text)


def convert_candidate(item, method, source_priority):
    title, url = clean_text(item.get("title")), clean_text(item.get("url"))
    if not title or not url or not is_store_news(title, item.get("body_excerpt") or item.get("description", "")):
        return None
    if is_listing_candidate(title, url, item.get("source_url", "")) or is_clearly_outside_yamaguchi(title, item.get("body_excerpt") or item.get("description", "")):
        return None
    body = clean_text(item.get("body_excerpt") or item.get("description", ""))[:1500]
    # 公共・行政施設は店舗ニュースの主対象外。ホテル・観光施設は別カテゴリで残す。
    if classify_content_type(title, body) == "公共・地域施設":
        return None
    body_categories = detect_categories(body)
    categories = list(dict.fromkeys(
        normalize_categories(item) + detect_categories(title) + body_categories
    ))
    categories = [c for c in categories if c in ALLOWED_CATEGORIES]
    if not categories:
        return None
    area = item.get("area", [])
    if not isinstance(area, list):
        area = [area] if area else []
    date_value = clean_text(item.get("published_date"))
    event_date = extract_event_date(title, body, date_value)
    event_date_text = extract_approximate_event_date_text(title, body)
    # 記事公開日は取得元の明示情報だけを使用する。タイトル内の日付は店舗動作日かもしれないため流用しない。
    return {
        "title": title, "url": url, "normalized_url": normalize_url(url),
        "event_date": event_date, "event_date_text": event_date_text,
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
        "リニューアル", "改装", "営業再開", "新規", "のお知らせ", "お知らせ",
        "について", "します", "しました", "予定", "決定", "へ", "が", "で", "に", "の",
    ]
    for word in stop_words:
        title = title.replace(word, " ")
    return re.sub(r"\s+", " ", title).strip()

def same_store_news_candidate(a, b):
    """同じ店舗・同じ動作日を報じる別媒体記事を統合する。"""
    if not (set(a.get("category", [])) & set(b.get("category", []))):
        return False
    names_a = set(duplicate_store_entity(a.get("title", ""), a.get("body_excerpt", "")))
    names_b = set(duplicate_store_entity(b.get("title", ""), b.get("body_excerpt", "")))
    if not names_a or not (names_a & names_b):
        return False

    # 公開日が離れていても、店舗動作日が同一なら同じ案件として扱う。
    event_a = clean_text(a.get("event_date", "")) or extract_event_date(
        a.get("title", ""), a.get("body_excerpt", ""), a.get("published_date", "")
    )
    event_b = clean_text(b.get("event_date", "")) or extract_event_date(
        b.get("title", ""), b.get("body_excerpt", ""), b.get("published_date", "")
    )
    if event_a and event_b:
        if event_a != event_b:
            return False
    else:
        date_a = parse_date(a.get("published_date", ""))
        date_b = parse_date(b.get("published_date", ""))
        if not date_a or not date_b or abs((date_a.date() - date_b.date()).days) > 21:
            return False

    # 同名チェーンでも別市町なら統合しない。
    towns_a = set(extract_municipality_candidates(a.get("title", ""), a.get("body_excerpt", "")))
    towns_b = set(extract_municipality_candidates(b.get("title", ""), b.get("body_excerpt", "")))
    if towns_a and towns_b and not (towns_a & towns_b):
        return False
    return True


def same_event(a, b):
    """誤統合を避け、明確に同じニュースと判断できる場合だけ統合する。"""

    categories_a = set(a.get("category", []))
    categories_b = set(b.get("category", []))

    # カテゴリーが異なるニュースは統合しない
    if categories_a and categories_b and not (categories_a & categories_b):
        return False

    title_a = title_fingerprint(a.get("title", ""))
    title_b = title_fingerprint(b.get("title", ""))

    if not title_a or not title_b:
        return False

    # タイトルが完全一致する場合
    if title_a == title_b:
        return True

    # 短いタイトルが長いタイトルに含まれるだけでは
    # 誤統合の可能性があるため、ここでは統合しない
    terms_a = event_terms(a)
    terms_b = event_terms(b)

    if len(terms_a) < 6 or len(terms_b) < 6:
        return False

    # 店舗名などの主要語が一致する場合に限定する
    if terms_a == terms_b:
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
            old_urls.update(
                normalize_url(s.get("url", ""))
                for s in old.get("source_urls", [])
            )
            if normalized in old_urls or same_event(candidate, old) or same_store_news_candidate(candidate, old):
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

def classify_content_type(title, body_excerpt=''):
    '''ニュース対象の施設・事業者タイプを分類。判断材料が弱い場合は要確認にする。'''
    # 施設種別は原則タイトルで判定し、本文中に偶然登場したホテル等で誤分類しない。
    title_text = clean_text(title)
    text = title_text or clean_text(body_excerpt)
    public = [
        'ハローワーク', '郵便局', '市役所', '町役場', '村役場', '県庁', '図書館',
        '公民館', '公共施設', '公共サービス', '行政窓口', '支所', '出張所',
        '地域交流センター', 'コミュニティセンター', '税務署', '年金事務所',
        '警察署', '交番', '消防署',
    ]
    if any(word in text for word in public):
        return '公共・地域施設'
    # 市民参加・地域発信を目的とする常設の共創拠点は、一般店舗と分ける。
    # 「交流拠点」だけでは民間施設もあり得るため、目的語との組み合わせで判定する。
    if '拠点' in text and any(word in text for word in ['市民共創', 'シティープロモーション', '市民自ら', '地域の魅力を発信']):
        return '公共・地域施設'
    lodging = ['ホテル', '旅館', '宿泊施設', '民宿', '民泊', 'ゲストハウス', 'ペンション', 'コテージ', '簡易宿所', '東横イン']
    if any(word in text for word in lodging):
        return '宿泊施設'
    leisure = ['観光農園', 'キャンプ場', '遊園地', '観光施設', 'レジャー', 'テーマパーク', '観光牧場', '果樹園', '体験農園']
    if any(word in text for word in leisure):
        return '観光・レジャー'
    commercial = ['店', '店舗', 'カフェ', '飲食店', 'レストラン', 'スーパー', 'ショッピング', '商業施設', '家電', '美容室', 'サロン', 'ドラッグストア', 'コンビニ', '書店', 'アパレル', '飲食', 'ピラティス', 'スタジオ', 'フィットネス', 'ジム']
    if any(word in text for word in commercial):
        return '店舗・商業施設'
    return 'その他施設・サービス（要確認）'


def is_in_store_scope(item):
    """店舗情報サイトの対象外となる宿泊・観光・公共施設を除外する。"""
    content_type = classify_content_type(
        item.get("title", ""), item.get("body_excerpt", "")
    )
    excluded_types = {
        "宿泊施設",
        "観光・レジャー",
        "公共・地域施設",
    }
    return content_type not in excluded_types

def make_draft(item):
    date_value = item.get("published_date", "")
    freshness_basis = item.get("event_date", "") or date_value
    freshness, age = get_freshness(freshness_basis)
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
    if not date_value and item.get("event_date"):
        summary += " 鮮度は記事公開日ではなく、本文から抽出した店舗動作日を基準にしています。"
    if item.get("event_date_text"):
        summary += f" 店舗動作日は「{item['event_date_text']}」と記載されていますが、正確な日付は未確認です。"
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
        "published_date": date_value, "event_date": clean_text(item.get("event_date")),
        "event_date_text": clean_text(item.get("event_date_text")),
        "freshness": freshness, "age_days": age,
        "area": item.get("area", []), "area_status": area_status,
        "municipality": municipality, "municipality_candidates": municipality_candidates,
        "municipality_group": municipality if municipality else "地域要確認",
        "municipality_status": municipality_status,
        "source_name": item.get("source_name", ""), "source_url": url,
        "source_urls": item.get("source_urls", [{"source_name": item.get("source_name", ""), "url": url}]),
        "duplicate_sources_count": item.get("duplicate_sources_count", 1),
        "body_excerpt": item.get("body_excerpt", ""), "body_excerpt_method": item.get("body_excerpt_method", ""), "draft_summary": summary,
        "relevance": "店舗ニュース候補・要確認",
        "content_type": classify_content_type(item.get("title", ""), item.get("body_excerpt", "")),
        "collection_method": item.get("collection_method", ""),
        "status": "未確認・公開禁止", "created_at": now_jst().isoformat(),
    }

def sort_key(item):
    order = {"直近30日": 0, "31〜90日前": 1, "日付確認が必要": 2, "未来日付・要確認": 3, "90日より前": 4}
    date = parse_date(item.get("published_date", ""))
    # Keep newer articles ahead of priority; priority only breaks date ties.
    return (order.get(item.get("freshness", ""), 5),
            -(date.timestamp() if date else 0),
            item.get("priority", 5), item.get("title", ""))

def duplicate_fingerprint(draft):
    """重複確認用のタイトル判定。記事は削除しない。"""
    title = (draft.get("title") or "").lower()
    title = re.sub(r"^\s*\d{4}[年/.-]\d{1,2}[月/.-]\d{0,2}[^ ]*\s*", "", title)
    title = re.sub(r"【[^】]*】", " ", title)
    title = re.sub(r"\[[^\]]*\]", " ", title)
    title = re.sub(
        r"(開店|新店|閉店|移転|リニューアル|オープン|営業再開|営業終了|情報|まとめ)",
        " ",
        title,
    )
    title = re.sub(r"[^\wぁ-んァ-ヶ一-龠]", "", title)
    return title[:100]


def duplicate_store_entity(title, body_excerpt=""):
    """タイトル・本文から重複確認に使う店舗名候補を抽出する。"""
    title_text = unicodedata.normalize("NFKC", clean_text(title))
    body_text = unicodedata.normalize("NFKC", clean_text(body_excerpt))

    title_text = re.sub(
        r"^\s*20\d{2}[年/.-]\d{1,2}[月/.-]\d{1,2}日?"
        r"(?:\s+\d{1,2}:\d{2})?\s*",
        "",
        title_text,
    )
    title_text = re.sub(r"【[^】]*】|\[[^\]]*\]", " ", title_text)

    candidates = []

    # 「ロフト」オープンなど、動作表現に隣接する引用店舗名
    for match in re.finditer(r"[「『]([^」』]{2,20})[」』]", title_text):
        nearby = title_text[max(0, match.start() - 12):match.end() + 18]
        if re.search(
            r"オープン|開店|開業|出店|閉店|移転|リニューアル",
            nearby,
        ):
            candidates.append(match.group(1))

    # 店名の直後に所在地が続く本文表現を優先して抽出
    store_chars = r"A-Za-z0-9一-龯ぁ-んァ-ヶー・＆&"
    municipality_pattern = "|".join(
        re.escape(name) for name in YAMAGUCHI_MUNICIPALITIES
    )
    for text in (title_text, body_text):
        for match in re.finditer(
            rf"([{store_chars}]{{2,20}}店)[（(](?:山口県)?(?:{municipality_pattern})",
            text,
        ):
            token = match.group(1)
            for town in YAMAGUCHI_MUNICIPALITIES:
                if token.endswith(town + "店"):
                    token = token[:-(len(town) + 1)]
                    break
            if len(token) >= 2:
                candidates.append(token)

    # 助詞・句読点で区切った短い語句から「○○店」を抽出する。
    # 文全体を店舗名として扱わず、記事ごとの前置き表現を避ける。
    separators = r"[、。！？!?（）()\[\]「」『』\s　はがをにでとのへもや]"
    for text in (title_text, body_text):
        for segment in re.split(separators, text):
            segment = segment.strip("・：:／/｜|—―-〜～…")
            match = re.search(rf"([{store_chars}]{{2,20}}店)$", segment)
            if not match:
                continue
            token = match.group(1)
            for town in YAMAGUCHI_MUNICIPALITIES:
                if token.endswith(town + "店"):
                    token = token[:-(len(town) + 1)]
                    break
            if len(token) >= 2:
                candidates.append(token)

    # 「生活雑貨専門店ロフトが開店」など、業態語＋ブランド名の見出しを扱う。
    for text in (title_text, body_text):
        for match in re.finditer(
            rf"(?:生活雑貨|雑貨|家具|家電|衣料品|紳士服|婦人服|インテリア|スポーツ用品)?専門店"
            rf"([{store_chars}]{{2,12}}?)(?=が|は|（|\(|[、。\s　])",
            text,
        ):
            brand = match.group(1).strip()
            if len(brand) >= 2:
                candidates.append(brand)

    # 「にロフトがオープン」など、ブランド名＋動作表現を抽出する。
    for text in (title_text, body_text):
        for match in re.finditer(
            rf"(?:に|で)\s*([{store_chars}]{{2,12}}?)(?:が|は)(?:新規)?(?:オープン|開店|開業|出店)",
            text,
        ):
            brand = match.group(1).strip()
            if len(brand) >= 2:
                candidates.append(brand)

    # 「生活雑貨専門店ロフト（東京都）」等は業態語を除いてブランド名を取る。
    for match in re.finditer(
        rf"([{store_chars}]{{2,24}})[（(]東京都",
        body_text,
    ):
        token = match.group(1)
        token = re.sub(
            r"^(?:生活雑貨|雑貨|家具|家電|衣料品|紳士服|婦人服|"
            r"インテリア|スポーツ用品)?専門店",
            "",
            token,
        )
        token = token.strip()
        if len(token) >= 2:
            candidates.append(token)

    # 文の形が異なる記事でも、本文・見出しに同じ店名が明記されていれば候補に含める。
    # 「大丸下関店（下関市…）」のような所在地併記を優先し、店名本体を抽出する。
    for text in (title_text, body_text):
        for match in re.finditer(
            rf"([{store_chars}]{{2,20}}店)(?=[（(]|は|が|を|に|で|、|。|\s|$)",
            text,
        ):
            token = match.group(1)
            # 「来夏閉店の大丸下関店」「発表した大丸下関店」のような
            # 前置きが店名に混入しないよう、直近の述語・助詞以降を採用する。
            token = re.split(
                r"(?:発表した|発表|営業終了する|営業終了|閉店する|閉店|閉館|"
                r"来夏|今夏|来年|今年|の|を|は|が|で|に)",
                token,
            )[-1]
            for town in YAMAGUCHI_MUNICIPALITIES:
                if token.endswith(town + "店"):
                    token = token[:-(len(town) + 1)]
                    break
            if len(token) >= 2:
                candidates.append(token)

    # 記号・空白を正規化し、短すぎる候補や一般語を除外
    generic = {"店舗", "専門店", "衣料品店", "飲食店", "小売店", "販売店", "雑貨店"}
    normalized = []
    for name in candidates:
        name = re.sub(r"\s+", "", name).strip("・、。")
        if len(name) >= 2 and name not in generic and name not in normalized:
            normalized.append(name)

    return normalized


def same_store_duplicate(a, b):
    """同じ店舗・同じ動作日・同じ市町の重複候補を検出する。"""
    return same_store_news_candidate(a, b)


def annotate_review_flags(drafts):
    """重複候補と確認事項を記録する。自動削除はしない。"""
    groups = {}
    for draft in drafts:
        fingerprint = duplicate_fingerprint(draft)
        if len(fingerprint) >= 4:
            key = (fingerprint, tuple(sorted(draft.get("category", []))))
            groups.setdefault(key, []).append(draft)

    # 見出しの表現が異なる同一店舗ニュースも、店舗名・市町・カテゴリ・日付で保守的に検知する。
    entity_groups = []
    adjacency = {i: set() for i in range(len(drafts))}

    for i in range(len(drafts)):
        for j in range(i + 1, len(drafts)):
            if same_store_duplicate(drafts[i], drafts[j]):
                adjacency[i].add(j)
                adjacency[j].add(i)

    visited = set()

    for i in range(len(drafts)):
        if i in visited or not adjacency[i]:
            continue

        stack = [i]
        component = []
        visited.add(i)

        while stack:
            current = stack.pop()
            component.append(drafts[current])

            for neighbor in adjacency[current]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append(neighbor)

        if len(component) >= 2:
            entity_groups.append(component)

    seen_group_ids = {
        frozenset(x.get("id", "") for x in group)
        for group in groups.values() if len(group) >= 2
    }
    for group in entity_groups:
        key = frozenset(x.get("id", "") for x in group)
        if key not in seen_group_ids:
            groups[("store_entity", tuple(sorted(key)))] = group
            seen_group_ids.add(key)

    duplicate_group_count = 0
    duplicate_candidate_count = 0

    for group in groups.values():
        if len(group) < 2:
            continue

        duplicate_group_count += 1
        group_id = hashlib.sha256(
            "|".join(sorted(x.get("id", "") for x in group)).encode("utf-8")
        ).hexdigest()[:10]

        for draft in group:
            draft["duplicate_review"] = "重複の可能性・要確認"
            draft["duplicate_group_id"] = group_id
            draft["duplicate_candidate_ids"] = [
                x.get("id", "") for x in group if x is not draft
            ]
            duplicate_candidate_count += 1

    quality_counts = {}
    for draft in drafts:
        flags = []

        if not draft.get("source_url") and not draft.get("source_urls"):
            flags.append("情報源URLなし")
        if not draft.get("body_excerpt"):
            flags.append("本文抜粋なし")
        if not draft.get("published_date"):
            flags.append("公開日未確認")
        if not draft.get("event_date"):
            flags.append("開店・閉店等の日付未確認")
        if len(draft.get("municipality_candidates", [])) > 1:
            flags.append("市町候補が複数")
        elif not draft.get("municipality"):
            flags.append("市町未特定")
        if draft.get("freshness") == "未来日付・要確認":
            flags.append("未来日付")
        if draft.get("duplicate_review"):
            flags.append("重複の可能性・要確認")

        draft["review_flags"] = list(dict.fromkeys(flags))
        critical_flags = {"情報源URLなし", "未来日付", "市町候補が複数"}
        missing_information_flags = {
            "本文抜粋なし", "公開日未確認",
            "開店・閉店等の日付未確認", "市町未特定",
        }
        if any(flag in critical_flags for flag in flags):
            draft["review_priority"] = "要優先確認"
        elif "重複の可能性・要確認" in flags:
            draft["review_priority"] = "重複確認"
        elif any(flag in missing_information_flags for flag in flags):
            draft["review_priority"] = "情報不足・保留"
        elif flags:
            draft["review_priority"] = "確認推奨"
        else:
            draft["review_priority"] = "基本項目あり・内容確認は必要"

        hold_flags = {
            "情報源URLなし", "本文抜粋なし", "公開日未確認",
            "開店・閉店等の日付未確認", "市町候補が複数",
            "市町未特定", "未来日付", "重複の可能性・要確認",
        }
        if draft.get("freshness") not in {"直近30日", "31〜90日前"}:
            draft["review_bucket"] = "確認待ち"
        elif any(flag in hold_flags for flag in flags):
            draft["review_bucket"] = "確認待ち"
        elif draft.get("content_type") == "その他施設・サービス（要確認）":
            draft["review_bucket"] = "確認待ち"
        else:
            draft["review_bucket"] = "通常候補（要確認）"

        draft["status"] = "未確認・公開禁止"

        for flag in flags:
            quality_counts[flag] = quality_counts.get(flag, 0) + 1

    return {
        "duplicate_group_count": duplicate_group_count,
        "duplicate_candidate_count": duplicate_candidate_count,
        "review_flag_counts": dict(sorted(quality_counts.items())),
        "review_note": "重複は候補表示のみで自動削除しません。全記事は未確認・公開禁止です。",
    }

def main():
    official, rss = get_official_candidates(), get_rss_candidates()
    unique = merge_candidates(official + rss)
    all_drafts = [make_draft(x) for x in unique]
    excluded_scope_count = sum(1 for x in all_drafts if not is_in_store_scope(x))
    scoped_drafts = [x for x in all_drafts if is_in_store_scope(x)]
    old_count = sum(1 for x in scoped_drafts if x["freshness"] == "90日より前")
    # 宿泊・観光・公共施設は店舗サイトの対象外。古い記事も通常候補から除外。
    drafts = [x for x in scoped_drafts if x["freshness"] != "90日より前"]
    drafts.sort(key=sort_key)
    
    review_summary = annotate_review_flags(drafts)
    review_bucket_counts = {}
    for draft in drafts:
        bucket = draft.get("review_bucket", "確認待ち")
        review_bucket_counts[bucket] = review_bucket_counts.get(bucket, 0) + 1

    freshness_counts, category_counts, municipality_counts, content_type_counts = {}, {}, {}, {}
    for draft in drafts:
        f = draft["freshness"]
        freshness_counts[f] = freshness_counts.get(f, 0) + 1
        for cat in draft["category"]:
            category_counts[cat] = category_counts.get(cat, 0) + 1
        content_type = draft.get("content_type", "その他施設・サービス（要確認）")
        content_type_counts[content_type] = content_type_counts.get(content_type, 0) + 1
        municipality = draft.get("municipality_group") or "地域要確認"
        municipality_counts[municipality] = municipality_counts.get(municipality, 0) + 1
    municipality_counts = dict(sorted(municipality_counts.items(), key=lambda item: (item[0] == "地域要確認", item[0])))
    output = {
        "generated_at": now_jst().isoformat(), "draft_count": len(drafts),
        "recent_draft_count": freshness_counts.get("直近30日", 0),
        "excluded_old_count": old_count, "excluded_scope_count": excluded_scope_count, "freshness_counts": freshness_counts,
        "category_counts": category_counts,
        "content_type_counts": dict(sorted(content_type_counts.items())),
        "municipality_counts": municipality_counts,
        "review_bucket_counts": review_bucket_counts,
        **review_summary,
        "note": "対象は山口県内の店舗・商業サービスの新店・開店、閉店、移転、リニューアルです。宿泊施設・観光レジャー・公共地域施設は対象外。90日より前の記事は通常候補から除外。日付不明は確認用に保持。すべて未確認・公開禁止です。",
        "drafts": drafts,
    }
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print("公式サイト候補:", len(official), "RSS候補:", len(rss))
    print("統合後:", len(unique), "下書き候補:", len(drafts), "対象外施設の除外:", excluded_scope_count, "90日より前の除外:", old_count)
    print("直近30日:", output["recent_draft_count"], "カテゴリー:", category_counts)
    print("鮮度:", freshness_counts, "保存先:", OUTPUT_FILE)
    print("施設タイプ別件数:", output["content_type_counts"])
    print("市町別件数:", municipality_counts)


if __name__ == "__main__":
    main()