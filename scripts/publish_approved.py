#!/usr/bin/env python3
"""Build published.json from explicitly approved, safe draft records."""
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DRAFTS_PATH = ROOT / "data" / "drafts.json"
APPROVALS_PATH = ROOT / "data" / "publication_approvals.json"
PUBLISHED_PATH = ROOT / "data" / "published.json"

BLOCKED_STATUS = {"未確認・公開禁止"}
BLOCKED_DUPLICATE = {"重複の可能性・要確認"}

def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def get_articles(data):
    if isinstance(data, dict):
        articles = data.get("articles", [])
        return articles if isinstance(articles, list) else []
    return data if isinstance(data, list) else []

def is_publishable(article, approved_ids):
    article_id = str(article.get("id", "")).strip()
    if not article_id or article_id not in approved_ids:
        return False
    if article.get("status") in BLOCKED_STATUS:
        return False
    if article.get("duplicate_review") in BLOCKED_DUPLICATE:
        return False
    if article.get("review_flags"):
        return False
    if not str(article.get("title", "")).strip():
        return False
    if not str(article.get("source_url", "")).strip():
        return False
    if not str(article.get("body_excerpt", "")).strip():
        return False
    if not str(article.get("published_date", "")).strip():
        return False
    if not str(article.get("municipality", "")).strip():
        return False
    return True

def main():
    drafts_data = load_json(DRAFTS_PATH)
    approvals = load_json(APPROVALS_PATH)
    approved_ids = {
        str(item).strip()
        for item in approvals.get("approved_ids", [])
        if str(item).strip()
    }
    drafts = get_articles(drafts_data)
    selected = [a for a in drafts if is_publishable(a, approved_ids)]

    # Fail safe: never wipe existing public data just because no items pass.
    if not selected:
        print("公開条件を満たす記事が0件のため、published.json は変更しません。")
        return

    existing_data = load_json(PUBLISHED_PATH) if PUBLISHED_PATH.exists() else {}
    existing = get_articles(existing_data)
    by_id = {}
    for article in existing:
        if isinstance(article, dict) and article.get("id"):
            by_id[str(article["id"])] = article
    for article in selected:
        by_id[str(article["id"])] = article

    output = {
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "articles": list(by_id.values()),
    }
    temp_path = PUBLISHED_PATH.with_suffix(".json.tmp")
    with temp_path.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
        f.write("\\n")
    temp_path.replace(PUBLISHED_PATH)
    print(f"公開データを更新しました: 今回の追加・更新 {len(selected)} 件 / 合計 {len(output['articles'])} 件")

if __name__ == "__main__":
    main()
