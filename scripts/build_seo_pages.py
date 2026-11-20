#!/usr/bin/env python3
"""Build SEO detail pages from approved, fully reviewed public articles only."""
import html
import json
import re
from pathlib import Path
from urllib.parse import urlparse, quote
from xml.etree.ElementTree import Element, SubElement, ElementTree

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://local-life-lab.github.io/-UPDATE-MVP"
DATA = ROOT / "data" / "published.json"
OUT = ROOT / "articles"
ALLOWED_CATEGORIES = {
    "新店・開店", "新店", "開店", "閉店", "閉店・営業終了",
    "移転", "移転・リニューアル", "リニューアル", "長期休業",
}
ALLOWED_STATUSES = {
    "開店予定", "営業中", "閉店予定", "閉店済み", "一時休業中",
    "移転予定", "移転済み", "リニューアル予定", "リニューアル済み",
}


def esc(value):
    return html.escape(str(value or ""), quote=True)


def safe_slug(article):
    return re.sub(r"[^a-zA-Z0-9_-]", "", str(article.get("id", "")))


def is_http_url(value):
    parsed = urlparse(str(value or ""))
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def is_eligible(article):
    categories = article.get("category", [])
    if not isinstance(categories, list):
        categories = [categories]
    review_flags = article.get("review_flags", [])
    return (
        article.get("status") in ("公開", "公開済み")
        and bool(article.get("approved_at"))
        and isinstance(review_flags, list)
        and len(review_flags) == 0
        and bool(str(article.get("title") or "").strip())
        and is_http_url(article.get("source_url"))
        and any(category in ALLOWED_CATEGORIES for category in categories)
        and article.get("business_status") in ALLOWED_STATUSES
        and bool(safe_slug(article))
    )


def build_article_page(article):
    slug = safe_slug(article)
    title = str(article.get("title", "山口のお店情報")).strip()
    categories = article.get("category", [])
    if not isinstance(categories, list):
        categories = [categories]
    category = "・".join(str(value) for value in categories if value)
    area = article.get("area") or ["山口県"]
    if isinstance(area, str):
        area = [area]
    municipality = str(article.get("municipality") or (area[0] if area else "山口県"))
    summary = str(
        article.get("body")
        or article.get("body_excerpt")
        or article.get("draft_summary")
        or "詳細は情報提供元をご確認ください。"
    ).strip()
    source_name = str(article.get("source_name") or "情報提供元")
    source_url = str(article.get("source_url"))
    published = str(article.get("published_date") or "")
    approved_at = str(article.get("approved_at") or "")
    checked_date = approved_at[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", approved_at) else ""
    source_records = article.get("source_urls", [])
    if not isinstance(source_records, list):
        source_records = []
    normalized_sources = []
    seen_source_urls = set()
    for record in source_records:
        if not isinstance(record, dict):
            continue
        record_url = str(record.get("url") or "").strip()
        record_name = str(record.get("source_name") or "情報提供元").strip()
        if is_http_url(record_url) and record_url not in seen_source_urls:
            normalized_sources.append((record_name, record_url))
            seen_source_urls.add(record_url)
    if is_http_url(article.get("source_url")) and str(article.get("source_url")) not in seen_source_urls:
        normalized_sources.insert(0, (str(article.get("source_name") or "主な情報源"), str(article.get("source_url"))))
    if not normalized_sources and is_http_url(source_url):
        normalized_sources = [(source_name, source_url)]
    source_items_html = "".join(
        f'<li><span>{esc(name)}</span><a href="{esc(url)}" target="_blank" rel="noopener noreferrer">情報源を開く ↗</a></li>'
        for name, url in normalized_sources
    )
    if not source_items_html:
        source_items_html = '<li><span>情報源の詳細は確認できません</span></li>'
    # Optional store details are displayed only when a dedicated verification record
    # and its source URL are present. Never infer these values from article prose.
    verified_info = article.get("verified_store_info", {})
    if not isinstance(verified_info, dict):
        verified_info = {}
    verified_source = str(verified_info.get("source_url") or "").strip()
    verified_checked = str(verified_info.get("checked_at") or "").strip()
    verified_rows = []
    if is_http_url(verified_source):
        for key, label in (("address", "所在地"), ("business_hours", "営業時間"), ("regular_holiday", "定休日")):
            value = str(verified_info.get(key) or "").strip()
            if value:
                verified_rows.append(f'<div class="story-store-row"><dt>{label}</dt><dd>{esc(value)}</dd></div>')
        address = str(verified_info.get("address") or "").strip()
        if address:
            map_url = "https://www.google.com/maps/search/?api=1&query=" + quote(address)
            verified_rows.append(f'<div class="story-store-map"><a href="{esc(map_url)}" target="_blank" rel="noopener noreferrer">地図で場所を確認 ↗</a></div>')
        official_links = []
        for key, label in (("official_website", "公式サイト"), ("official_instagram", "Instagram"), ("official_x", "公式X"), ("official_line", "公式LINE")):
            value = str(verified_info.get(key) or "").strip()
            if is_http_url(value):
                official_links.append(f'<a href="{esc(value)}" target="_blank" rel="noopener noreferrer">{label} ↗</a>')
        if official_links:
            verified_rows.append('<div class="story-store-links">' + "".join(official_links) + '</div>')
    verified_info_html = ""
    if verified_rows:
        checked_label = esc(verified_checked[:10]) if re.match(r"^\d{4}-\d{2}-\d{2}", verified_checked) else "確認日記載なし"
        verified_info_html = f'<section class="story-store-panel" aria-label="確認済み店舗情報"><div class="story-section-heading"><span>02</span><div><small>VERIFIED STORE INFO</small><h2>店舗の基本情報</h2></div></div><dl class="story-store-list">{"".join(verified_rows)}</dl><p class="story-store-meta">情報確認日：{checked_label}　／　<a href="{esc(verified_source)}" target="_blank" rel="noopener noreferrer">確認元を開く ↗</a></p></section>'
    event = str(article.get("event_date") or "")
    status = str(article.get("business_status") or "")
    photo_url = article.get("image_url") if article.get("image_usage_approved") is True and article.get("image_rights_status") in ("許可確認済み", "利用条件確認済み") and is_http_url(article.get("image_url")) else ""
    photo_source = article.get("image_source_url") if photo_url and is_http_url(article.get("image_source_url")) else ""
    photo_credit = str(article.get("image_credit") or "").strip() if photo_url and photo_source else ""
    if not photo_credit:
        photo_url = photo_source = ""
    photo_caption = "店舗提供写真" if article.get("image_type") == "provided" else "公式掲載写真"
    canonical = f"{BASE}/articles/{slug}.html"
    is_closed = any(category in ("閉店", "閉店・営業終了") for category in categories)
    section_label = "閉店情報" if is_closed else "新店舗・更新情報"
    section_url = f"{BASE}/closed.html" if is_closed else f"{BASE}/new.html"

    structured = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": title,
        "mainEntityOfPage": canonical,
        "inLanguage": "ja",
        "author": {"@type": "Organization", "name": "山口ローカルUPDATE"},
        "publisher": {"@type": "Organization", "name": "山口ローカルUPDATE"},
        "about": {"@type": "Thing", "name": title},
        "breadcrumb": {
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "トップ", "item": BASE + "/"},
                {"@type": "ListItem", "position": 2, "name": section_label, "item": section_url},
                {"@type": "ListItem", "position": 3, "name": title, "item": canonical},
            ],
        },
    }
    if published:
        structured["datePublished"] = published
    if article.get("published_at") or published:
        structured["dateModified"] = str(article.get("published_at") or published)

    description = (municipality + "の" + title + "。店舗の状態：" + status + "。 " + summary)[:150]
    safe_json = json.dumps(structured, ensure_ascii=False).replace("</", "<\\/")
    page = f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}｜山口ローカルUPDATE</title>
<meta name="description" content="{esc(description)}">
<link rel="canonical" href="{esc(canonical)}">
<meta property="og:type" content="article"><meta property="og:site_name" content="山口ローカルUPDATE">
<meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(description)}">
<meta property="og:url" content="{esc(canonical)}">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(description)}">
<script async src="https://www.googletagmanager.com/gtag/js?id=G-J79VXDWMTV"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());gtag('config','G-J79VXDWMTV');</script>
<link rel="stylesheet" href="../index.css"><link rel="stylesheet" href="../newsroom.css"><link rel="stylesheet" href="../article.css">
<script type="application/ld+json">{safe_json}</script>

</head><body class="article-story-page"><header class="site-header"><a class="brand" href="../index.html"><span class="brand-mark">LU<span>.</span></span><span class="brand-name">YAMAGUCHI<br>LOCAL UPDATE</span></a><nav class="header-nav"><a href="../index.html">トップ</a><a href="../new.html">新店情報</a><a href="../closed.html">閉店情報</a><a href="../areas/index.html">地域別</a><a class="nav-contact" href="../listing.html">掲載依頼</a></nav></header>
<main class="story-wrap">
<nav class="story-breadcrumb" aria-label="パンくずリスト"><a href="../index.html">トップ</a><span aria-hidden="true">/</span><a href="../{ "closed.html" if is_closed else "new.html" }">{esc(section_label)}</a><span aria-hidden="true">/</span><span aria-current="page">{esc(title)}</span></nav>
<section class="story-hero">
<div class="story-kicker"><span class="story-kicker-line"></span>YAMAGUCHI LOCAL UPDATE <span class="story-kicker-divider">/</span>{esc(category)}</div>
<div class="story-area">{esc(municipality)}</div>
<h1>{esc(title)}</h1>
<div class="story-status"><span class="status-dot"></span>{esc(status)}</div>
</section>
{f'<figure class="story-photo"><img src="{esc(photo_url)}" alt="{esc(title)}の{esc(photo_caption)}" loading="eager" decoding="async"><figcaption>{esc(photo_caption)}　写真：{esc(photo_credit)}　<a href="{esc(photo_source)}" target="_blank" rel="noopener noreferrer">写真の出典 ↗</a></figcaption></figure>' if photo_url else '<div class="story-photo-placeholder" role="img" aria-label="写真はありません"><span>LOCAL UPDATE</span><small>PHOTO NOT AVAILABLE</small></div>'}
<section class="story-facts" aria-label="店舗情報">
<div class="story-fact"><span>STATUS</span><strong>{esc(status)}</strong></div>
<div class="story-fact"><span>AREA</span><strong>{esc(municipality)}</strong></div>
<div class="story-fact"><span>DATE</span><strong>{esc(event) if event else "日付未掲載"}</strong></div>
<div class="story-fact"><span>POSTED</span><strong>{esc(published) if published else "掲載日未掲載"}</strong></div>
<div class="story-fact"><span>CHECKED</span><strong>{esc(checked_date) if checked_date else "確認日未掲載"}</strong></div>
</section>
{verified_info_html}
<article class="story-article">
<div class="story-section-heading"><span>01</span><div><small>ARTICLE</small><h2>店舗情報</h2></div></div>
<div class="story-content">{esc(summary)}</div>
<div class="story-note"><strong>掲載情報について</strong><p>この記事は確認できた情報をもとに掲載しています。営業状況・日程は変更される場合があります。訪問前に店舗または施設の公式案内をご確認ください。</p></div>
</article>
<section class="story-source-panel"><div><span class="source-kicker">SOURCE / INFORMATION</span><h2>情報の確認元</h2><p>記事作成時に参照した情報源を掲載しています。複数の情報源がある場合は、それぞれ確認できます。</p><ul class="story-source-list">{source_items_html}</ul></div></section>
<div class="story-bottom-nav"><a href="../{ "closed.html" if is_closed else "new.html" }">← {esc(section_label)}一覧へ戻る</a><a href="../index.html">トップページへ</a></div>
</main>
<footer class="site-footer"><a class="footer-brand" href="../index.html">YAMAGUCHI LOCAL UPDATE<span>.</span></a><small>© YAMAGUCHI LOCAL UPDATE</small></footer></body></html>"""
    return slug, page



AREA_OUT = ROOT / "areas"
AREA_SLUGS = {
    "山口市": "yamaguchi",
    "宇部市": "ube",
    "下関市": "shimonoseki",
    "防府市": "hofu",
    "周南市": "shunan",
    "山陽小野田市": "sanyo-onoda",
    "岩国市": "iwakuni",
    "萩市": "hagi",
    "光市": "hikari",
    "長門市": "nagato",
    "柳井市": "yanai",
    "美祢市": "mine",
    "阿武町": "abu",
    "平生町": "hirao",
    "田布施町": "tabuse",
    "周防大島町": "suo-oshima",
    "和木町": "waku",
    "上関町": "kaminoseki",
}


def build_area_page(municipality, articles):
    slug = AREA_SLUGS.get(municipality)
    if not slug or len(articles) < 3:
        return None
    items = []
    for article in sorted(articles, key=lambda a: (str(a.get("event_date") or ""), str(a.get("published_date") or "")), reverse=True):
        article_slug = safe_slug(article)
        if not article_slug:
            continue
        title = esc(article.get("title") or "店舗情報")
        category = esc("・".join(article.get("category", [])) if isinstance(article.get("category"), list) else article.get("category", ""))
        status = esc(article.get("business_status") or "")
        date = esc(article.get("event_date") or article.get("published_date") or "")
        items.append(f'<li class="area-item"><a href="../articles/{article_slug}.html"><span class="area-category">{category}</span><strong>{title}</strong><span class="area-meta">{status}　／　{date}</span></a></li>')
    if len(items) < 3:
        return None
    title = f"{municipality}の新店・閉店・リニューアル情報"
    description = f"{municipality}の新店舗・開店、閉店、移転、リニューアル情報を掲載。情報源を確認した記事を一覧で紹介します。"
    return f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}｜山口ローカルUPDATE</title><meta name="description" content="{esc(description)}">
<link rel="canonical" href="{BASE}/areas/{slug}.html">
<meta property="og:type" content="website"><meta property="og:title" content="{esc(title)}｜山口ローカルUPDATE"><meta property="og:description" content="{esc(description)}"><meta property="og:url" content="{BASE}/areas/{slug}.html">
<script async src="https://www.googletagmanager.com/gtag/js?id=G-J79VXDWMTV"></script><script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());gtag('config','G-J79VXDWMTV');</script>
<link rel="stylesheet" href="../index.css"><link rel="stylesheet" href="../newsroom.css">
<style>.area-wrap{{max-width:900px;margin:0 auto;padding:42px 22px 70px}}.area-wrap h1{{font-size:clamp(25px,4vw,38px);line-height:1.45}}.area-intro{{color:#62695f;line-height:2;margin:16px 0 28px}}.area-list{{list-style:none;padding:0;margin:0;display:grid;gap:12px}}.area-item a{{display:grid;gap:7px;padding:19px 20px;border:1px solid #e3e2d8;border-radius:9px;background:#fffefa;color:inherit;text-decoration:none}}.area-item strong{{font-size:16px;line-height:1.7}}.area-category,.area-meta{{font-size:11px;color:#747b70}}.area-back{{display:flex;gap:18px;flex-wrap:wrap;margin-top:30px}}</style></head>
<body class="detail-page"><header class="site-header"><a class="brand" href="../index.html"><span class="brand-mark">LU<span>.</span></span><span class="brand-name">YAMAGUCHI<br>LOCAL UPDATE</span></a><nav class="header-nav"><a href="../index.html">トップ</a><a href="../new.html">新店情報</a><a href="../closed.html">閉店情報</a><a href="../areas/index.html">地域別</a><a href="../listing.html">掲載・相談</a></nav></header>
<main class="area-wrap"><span class="eyebrow">LOCAL STORE UPDATE</span><h1>{esc(title)}</h1><p class="area-intro">{esc(municipality)}で確認・公開した店舗の新規開店、閉店、移転、リニューアル情報をまとめています。各記事には確認元を掲載しています。営業状況や日程は変更される場合があるため、訪問前に店舗の公式案内をご確認ください。</p><p>掲載記事：{len(items)}件</p><ul class="area-list">{"".join(items)}</ul><div class="area-back"><a href="../new.html">新店・開店情報一覧</a><a href="../closed.html">閉店・移転情報一覧</a><a href="../index.html">トップページ</a></div></main><footer class="footer"><div class="container"><small>© 2026 山口ローカルUPDATE</small></div></footer></body></html>"""


def build_area_pages(eligible):
    grouped = {}
    for article in eligible:
        municipality = str(article.get("municipality") or "").strip()
        if municipality:
            grouped.setdefault(municipality, []).append(article)
    AREA_OUT.mkdir(exist_ok=True)
    keep = set()
    for municipality, records in grouped.items():
        page = build_area_page(municipality, records)
        slug = AREA_SLUGS.get(municipality)
        if page and slug:
            filename = slug + ".html"
            keep.add(filename)
            (AREA_OUT / filename).write_text(page, encoding="utf-8")
    for path in AREA_OUT.glob("*.html"):
        if path.name not in keep and path.name != "index.html":
            path.unlink()
    return sorted(keep)


def build_area_index(area_pages, eligible):
    """Create a navigable directory for municipality pages that meet the SEO threshold."""
    records = []
    for filename in area_pages:
        slug = filename[:-5]
        municipality = next((name for name, value in AREA_SLUGS.items() if value == slug), None)
        if not municipality:
            continue
        count = sum(1 for article in eligible if str(article.get("municipality") or "").strip() == municipality)
        records.append((municipality, filename, count))

    if records:
        items = "".join(
            f'<li class="area-directory-item"><a href="{esc(filename)}"><strong>{esc(municipality)}</strong><span>{count}件の記事を見る →</span></a></li>'
            for municipality, filename, count in records
        )
        content = f'<ul class="area-directory-list">{items}</ul>'
        intro = "公開記事が3件以上ある市町の情報を、地域ごとにまとめています。"
    else:
        content = '<p class="area-empty">現在、地域別にまとめている記事はありません。</p>'
        intro = "地域別の記事一覧です。公開記事が一定数に達した市町から順次掲載します。"

    page = f'''<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>地域別の新店・閉店情報｜山口ローカルUPDATE</title><meta name="description" content="山口県内の新店・閉店・移転・リニューアル情報を市町別にまとめています。">
<link rel="canonical" href="{BASE}/areas/index.html">
<meta property="og:type" content="website"><meta property="og:title" content="地域別の新店・閉店情報｜山口ローカルUPDATE"><meta property="og:description" content="山口県内の新店・閉店・移転・リニューアル情報を市町別にまとめています。"><meta property="og:url" content="{BASE}/areas/index.html">
<script async src="https://www.googletagmanager.com/gtag/js?id=G-J79VXDWMTV"></script><script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());gtag('config','G-J79VXDWMTV');</script>
<link rel="stylesheet" href="../index.css"><link rel="stylesheet" href="../newsroom.css">
<style>.area-directory-wrap{{max-width:900px;margin:0 auto;padding:42px 22px 70px}}.area-directory-wrap h1{{font-size:clamp(25px,4vw,38px);line-height:1.45}}.area-directory-intro{{color:#62695f;line-height:2;margin:16px 0 28px}}.area-directory-list{{list-style:none;padding:0;margin:0;display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}}.area-directory-item a{{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:20px;border:1px solid #e3e2d8;border-radius:9px;background:#fffefa;color:inherit;text-decoration:none}}.area-directory-item strong{{font-size:17px}}.area-directory-item span{{font-size:12px;color:#747b70}}.area-empty{{padding:24px;background:#fffefa;border:1px solid #e3e2d8;border-radius:9px;color:#62695f}}</style></head>
<body class="detail-page"><header class="site-header"><a class="brand" href="../index.html"><span class="brand-mark">LU<span>.</span></span><span class="brand-name">YAMAGUCHI<br>LOCAL UPDATE</span></a><nav class="header-nav"><a href="../index.html">トップ</a><a href="../new.html">新店情報</a><a href="../closed.html">閉店情報</a><a href="index.html" aria-current="page">地域別</a><a href="../listing.html">掲載・相談</a></nav></header>
<main class="area-directory-wrap"><span class="eyebrow">LOCAL STORE UPDATE</span><h1>地域別の新店・閉店情報</h1><p class="area-directory-intro">{esc(intro)}</p>{content}<div class="area-back"><a href="../new.html">新店・開店情報一覧</a><a href="../closed.html">閉店・移転情報一覧</a><a href="../index.html">トップページ</a></div></main><footer class="footer"><div class="container"><small>© 2026 山口ローカルUPDATE</small></div></footer></body></html>'''
    (AREA_OUT / "index.html").write_text(page, encoding="utf-8")


def main():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    articles = data.get("articles", [])
    eligible = [article for article in articles if is_eligible(article)]

    OUT.mkdir(exist_ok=True)
    keep = set()
    for article in eligible:
        slug, page = build_article_page(article)
        filename = slug + ".html"
        keep.add(filename)
        (OUT / filename).write_text(page, encoding="utf-8")

    # Remove stale generated pages so withdrawn or no-longer-eligible records
    # cannot remain available for indexing.
    for path in OUT.glob("*.html"):
        if path.name not in keep:
            path.unlink()

    # Municipality landing pages are generated only where at least three
    # eligible, approved articles exist. Empty/thin locations are not indexed.
    area_pages = build_area_pages(eligible)
    build_area_index(area_pages, eligible)

    urls = [
        (f"{BASE}/", "daily", "1.0"),
        (f"{BASE}/new.html", "daily", "0.9"),
        (f"{BASE}/closed.html", "daily", "0.9"),
        (f"{BASE}/listing.html", "monthly", "0.6"),
        (f"{BASE}/contact.html", "monthly", "0.5"),
    ] + [(f"{BASE}/articles/{name}", "weekly", "0.7") for name in sorted(keep)] + [
        (f"{BASE}/areas/index.html", "weekly", "0.7"),
        *[(f"{BASE}/areas/{name}", "weekly", "0.6") for name in area_pages],
    ]

    root = Element("urlset", {"xmlns": "http://www.sitemaps.org/schemas/sitemap/0.9"})
    for loc, frequency, priority in urls:
        item = SubElement(root, "url")
        SubElement(item, "loc").text = loc
        SubElement(item, "changefreq").text = frequency
        SubElement(item, "priority").text = priority
    ElementTree(root).write(ROOT / "sitemap.xml", encoding="utf-8", xml_declaration=True)
    print(f"SEO detail pages generated: {len(keep)} (approved and review-clear records only)")
    print(f"Municipality landing pages generated: {len(area_pages)} (minimum 3 eligible articles per municipality)")


if __name__ == "__main__":
    main()
