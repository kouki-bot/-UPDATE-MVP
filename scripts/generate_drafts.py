import json
import os
import re
from datetime import datetime, timezone

INPUT_FILE = "data/source_checks.json"
OUTPUT_FILE = "data/drafts.json"

def clean_text(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()

def make_draft(item):
    title = clean_text(item.get("title"))
    url = clean_text(item.get("url"))
    source = clean_text(item.get("source_name"))
    category = item.get("category", [])
    published_date = clean_text(item.get("published_date"))
    body = clean_text(item.get("body_excerpt"))

    if not isinstance(category, list):
        category = [str(category)] if category else []

    # タイトルや本文にない事実は追加しない
    summary = (
        "この記事候補は、公開前に出典と内容の確認が必要です。"
    )

    if body:
        summary += " 取得できた本文の一部を確認し、"
        summary += "店舗名・場所・日付などの事実関係を確認してください。"
    else:
        summary += " 本文を取得できていないため、リンク先を直接確認してください。"

    return {
        "title": title,
        "category": category,
        "published_date": published_date,
        "source_name": source,
        "source_url": url,
        "body_excerpt": body[:1000],
        "draft_summary": summary,
        "status": "未確認・公開禁止",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

def main():
    if not os.path.exists(INPUT_FILE):
        raise FileNotFoundError(
            f"入力ファイルがありません: {INPUT_FILE}"
        )

    with open(INPUT_FILE, "r", encoding="utf-8") as file:
        data = json.load(file)

    candidates = data.get("candidates", [])
    drafts = []
    seen_urls = set()

    for item in candidates:
        url = clean_text(item.get("url"))

        if not url or url in seen_urls:
            continue

        seen_urls.add(url)

        title = clean_text(item.get("title"))
        if not title:
            continue

        drafts.append(make_draft(item))

    os.makedirs("data", exist_ok=True)

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "draft_count": len(drafts),
        "note": (
            "自動生成された下書きです。"
            "内容を確認するまで公開しないでください。"
        ),
        "drafts": drafts,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
        json.dump(output, file, ensure_ascii=False, indent=2)

    print(f"下書き生成数: {len(drafts)}")
    print(f"保存先: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()