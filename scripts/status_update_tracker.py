#!/usr/bin/env python3
"""Flag possible status updates to already published stores; never edit public records."""
import json
import os
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DRAFTS = ROOT / "data" / "drafts.json"
PUBLISHED = ROOT / "data" / "published.json"

def normalize(value):
    value = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"[\\s　・･「」『』【】（）():：,，.。!！?？〜～ー\\-_/]+", "", value)

def quoted_store_names(*values):
    found = set()
    for value in values:
        text = unicodedata.normalize("NFKC", str(value or ""))
        for name in re.findall(r"[「『\"']([^」』\"']{2,40})[」』\"']", text):
            name = normalize(name)
            if len(name) >= 2:
                found.add(name)
    return found

def categories(row):
    value = row.get("category", row.get("categories", []))
    return set(value if isinstance(value, list) else [value])

def find_possible_updates(drafts, published):
    alerts = []
    target_categories = {"閉店", "移転", "リニューアル"}
    for draft in drafts:
        draft_cats = categories(draft)
        if not draft_cats.intersection(target_categories):
            continue
        draft_url = str(draft.get("source_url") or draft.get("url") or "").strip()
        draft_city = str(draft.get("municipality") or "").strip()
        draft_names = quoted_store_names(draft.get("title"), draft.get("body_excerpt"), draft.get("body"))
        if not draft_city or not draft_names:
            continue
        for article in published:
            if str(article.get("id") or "") == str(draft.get("id") or ""):
                continue
            if str(article.get("source_url") or "").strip() == draft_url:
                continue
            if str(article.get("municipality") or "").strip() != draft_city:
                continue
            old_names = quoted_store_names(article.get("title"), article.get("body"), article.get("body_excerpt"))
            matched = sorted(draft_names.intersection(old_names))
            if not matched:
                continue
            alerts.append({
                "draft_id": draft.get("id", ""),
                "draft_title": draft.get("title", ""),
                "draft_source_url": draft_url,
                "published_id": article.get("id", ""),
                "published_title": article.get("title", ""),
                "published_status": article.get("business_status", ""),
                "candidate_categories": sorted(draft_cats.intersection(target_categories)),
                "municipality": draft_city,
                "matched_store_names": matched,
            })
    return alerts

def main():
    drafts_data = json.loads(DRAFTS.read_text(encoding="utf-8"))
    published_data = json.loads(PUBLISHED.read_text(encoding="utf-8")) if PUBLISHED.exists() else {"articles": []}
    drafts = drafts_data.get("drafts", [])
    published = published_data.get("articles", [])
    if not isinstance(drafts, list) or not isinstance(published, list):
        raise SystemExit("Invalid schema: drafts and published articles must be arrays")
    alerts = find_possible_updates(drafts, published)
    lines = [
        "## 掲載済み店舗の状態変更候補",
        "",
        f"- 照合対象：閉店・移転・リニューアル候補 {sum(bool(categories(x).intersection({'閉店', '移転', 'リニューアル'})) for x in drafts)}件",
        f"- 同一市町・店舗名一致の確認候補：{len(alerts)}件",
        "",
    ]
    if alerts:
        lines += ["### 人による確認が必要な候補", ""]
        for item in alerts[:50]:
            lines += [
                f"- **{item['municipality']}／{', '.join(item['matched_store_names'])}**",
                f"  - 既存記事：{item['published_title']}（状態：{item['published_status'] or '未設定'}）",
                f"  - 新候補：{item['draft_title']}（区分：{'・'.join(item['candidate_categories'])}）",
                f"  - 出典：{item['draft_source_url']}",
            ]
        lines.append("")
    lines.append("この照合は同一店舗の可能性を示すだけです。既存記事の変更・削除・公開は行いません。所在地と店舗名、元情報を人が確認してください。")
    report = "\n".join(lines)
    print(report)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(report + "\n")

if __name__ == "__main__":
    main()
