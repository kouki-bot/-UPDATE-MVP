#!/usr/bin/env python3
"""Build indexable detail pages and sitemap from manually approved public articles only."""
import html, json, re
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, ElementTree

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://kouki-bot.github.io/-UPDATE-MVP"
DATA = ROOT / "data" / "published.json"
OUT = ROOT / "articles"
ALLOWED = {"新店・開店", "新店", "開店", "閉店", "閉店・営業終了", "移転", "リニューアル", "長期休業"}

def esc(value):
    return html.escape(str(value or ""), quote=True)

def safe_slug(article):
    # Stable ID-based URLs avoid collisions between similar shop names.
    return re.sub(r"[^a-zA-Z0-9_-]", "", str(article.get("id", "")))

def main():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    articles = data.get("articles", [])
    eligible = []
    for a in articles:
        cats = a.get("category", [])
        cats = cats if isinstance(cats, list) else [cats]
        if (a.get("status") in ("公開", "公開済み")
            and a.get("approved_at")
            and a.get("title") and a.get("source_url", "").startswith(("https://", "http://"))
            and any(c in ALLOWED for c in cats)
            and a.get("business_status") in ("開店予定","営業中","閉店予定","閉店済み","移転予定","移転済み","リニューアル予定","リニューアル済み")):
            eligible.append(a)
    OUT.mkdir(exist_ok=True)
    keep = set()
    for a in eligible:
        slug = safe_slug(a)
        if not slug:
            continue
        keep.add(slug + ".html")
        title = str(a.get("title", "山口のお店情報")).strip()
        area = a.get("area") or ["山口県"]\n        if isinstance(area, str): area = [area]\n        municipality = str(a.get("municipality") or area[0])
        category = "・".join(cats if isinstance(cats, list) else [str(cats)])
        summary = str(a.get("body") or a.get("body_excerpt") or a.get("draft_summary") or "詳細は情報提供元をご確認ください。").strip()
        source_name = str(a.get("source_name") or "情報提供元")
        source_url = str(a.get("source_url"))
        published = str(a.get("published_date") or "")
        event = str(a.get("event_date") or "")
        status = str(a.get("business_status") or "")
        canonical = f"{BASE}/articles/{slug}.html"
        structured = {
            "@context":"https://schema.org", "@type":"Article",
            "headline":title, "datePublished":published,
            "dateModified":str(a.get("published_at") or published),
            "mainEntityOfPage":canonical, "inLanguage":"ja",
            "author":{"@type":"Organization","name":"山口ローカルUPDATE"},
            "publisher":{"@type":"Organization","name":"山口ローカルUPDATE"},
            "about":{"@type":"Thing","name":title}
        }
        body = f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}｜山口ローカルUPDATE</title>
<meta name="description" content="{esc((municipality + "の" + title + "。店舗の状態：" + status + "。 " + summary)[:150])}">
<link rel="canonical" href="{esc(canonical)}">
<meta property="og:type" content="article"><meta property="og:site_name" content="山口ローカルUPDATE">
<meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc((municipality + "の" + title + "。 " + summary)[:150])}">
<meta property="og:url" content="{esc(canonical)}">
<script async src="https://www.googletagmanager.com/gtag/js?id=G-J79VXDWMTV"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());gtag('config','G-J79VXDWMTV');</script>
<link rel="stylesheet" href="../index.css"><link rel="stylesheet" href="../detail.css">
<script type="application/ld+json">{json.dumps(structured, ensure_ascii=False).replace("</", "<\\/")}</script>
<style>.story-wrap{{max-width:820px;margin:0 auto;padding:64px 22px 90px}}.story-label{{color:#8a7258;font-size:.78rem;letter-spacing:.14em}}.story-wrap h1{{font-size:clamp(1.65rem,4vw,2.5rem);line-height:1.5;margin:16px 0 22px}}.story-meta{{display:flex;flex-wrap:wrap;gap:10px;color:#746e66;font-size:.9rem;border-bottom:1px solid #e8e3da;padding-bottom:20px}}.story-content{{font-size:1rem;line-height:2.05;margin:30px 0;white-space:pre-wrap}}.story-source{{display:inline-block;margin:10px 0 28px}}.story-back{{display:inline-block;margin-top:24px;color:#6d5742}}.story-note{{background:#f7f5ef;padding:18px 20px;border-radius:12px;font-size:.9rem;line-height:1.8}}</style>
</head><body><header class="site-header"><a class="brand" href="../index.html"><span class="brand-mark">LU<span>.</span></span><span class="brand-name">YAMAGUCHI<br>LOCAL UPDATE</span></a><nav class="header-nav"><a href="../index.html">トップ</a><a href="../new.html">新店情報</a><a href="../closed.html">閉店情報</a><a href="../listing.html">掲載依頼</a></nav></header>
<main class="story-wrap"><p class="story-label">YAMAGUCHI LOCAL UPDATE / {esc(category)}</p><p class="story-label">{esc(municipality)}</p><h1>{esc(title)}</h1>
<div class="story-meta"><span>店舗の状態：{esc(status)}</span><span>情報確認日：{esc(published)}</span>{'<span>開店・閉店等の日付：'+esc(event)+'</span>' if event else ''}</div>
<div class="story-content">{esc(summary)}</div>
<div class="story-note">掲載内容は確認時点の情報です。営業状況・日程は変更される場合があります。最新情報は店舗または施設の公式案内をご確認ください。</div>
<p>情報元：<a class="story-source" href="{esc(source_url)}" target="_blank" rel="noopener noreferrer">{esc(source_name)}（元情報を確認） ↗</a></p>
<a class="story-back" href="../index.html#latest">← 山口ローカルUPDATEの最新情報へ戻る</a></main>
<footer class="site-footer"><a class="footer-brand" href="../index.html">YAMAGUCHI LOCAL UPDATE<span>.</span></a><small>© YAMAGUCHI LOCAL UPDATE</small></footer></body></html>"""
        (OUT / (slug + ".html")).write_text(body, encoding="utf-8")
    # Remove stale generated pages so withdrawn/unapproved records cannot remain indexed.
    for path in OUT.glob("*.html"):
        if path.name not in keep:
            path.unlink()
    urls = [
        (f"{BASE}/", "daily", "1.0"),
        (f"{BASE}/new.html", "daily", "0.9"),
        (f"{BASE}/closed.html", "daily", "0.9"),
        (f"{BASE}/listing.html", "monthly", "0.6"),
        (f"{BASE}/contact.html", "monthly", "0.5"),
    ] + [(f"{BASE}/articles/{name}", "weekly", "0.7") for name in sorted(keep)]
    root = Element("urlset", {"xmlns":"http://www.sitemaps.org/schemas/sitemap/0.9"})
    for loc, freq, priority in urls:
        u = SubElement(root, "url")
        SubElement(u, "loc").text = loc
        SubElement(u, "changefreq").text = freq
        SubElement(u, "priority").text = priority
    ElementTree(root).write(ROOT / "sitemap.xml", encoding="utf-8", xml_declaration=True)
    print(f"SEO detail pages generated: {len(keep)} (approved public records only)")
if __name__ == "__main__":
    main()
