#!/usr/bin/env python3
"""Flag possible status changes to already published stores; never edits public records."""
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from generate_drafts import duplicate_store_entity, clean_text

DRAFTS = ROOT / "data" / "drafts.json"
PUBLISHED = ROOT / "data" / "published.json"
CHANGE_CATEGORIES = {"閉店", "移転", "リニューアル"}


def normalize_url(value):
    try:
        parts = urlsplit(str(value or "").strip())
        if parts.scheme not in ("http", "https") or not parts.netloc:
            return ""
        query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                 if k.lower() not in {"fbclid", "gclid", "yclid", "mc_cid", "mc_eid"}
                 and not k.lower().startswith("utm_")]
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(),
                           parts.path.rstrip("/") or "/", urlencode(query), ""))
    except ValueError:
        return ""


def store_names(article):
    return set(duplicate_store_entity(
        article.get("title", ""), article.get("body_excerpt", "") or article.get("body", "")
    ))


def municipality(article):
    value = clean_text(article.get("municipality", ""))
    if value:
        return value
    candidates = article.get("municipality_candidates", [])
    return clean_text(candidates[0]) if isinstance(candidates, list) and len(candidates) == 1 else ""


def find_status_changes(drafts, published):
    """Only exact store-name + same municipality matches are reported for human review."""
    alerts = []
    seen = set()
    for candidate in drafts:
        # Only unreviewed candidates may create alerts; never use a public or approved record as a candidate.
        if candidate.get("status") != "未確認・公開禁止":
            continue
        new_categories = set(candidate.get("category", [])) & CHANGE_CATEGORIES
        if not new_categories:
            continue
        new_town = municipality(candidate)
        new_names = store_names(candidate)
        new_url = normalize_url(candidate.get("source_url", ""))
        if not new_town or not new_names:
            continue
        for article in published:
            old_town = municipality(article)
            old_names = store_names(article)
            old_url = normalize_url(article.get("source_url", ""))
            if old_town != new_town or not (new_names & old_names):
                continue
            if new_url and old_url and new_url == old_url:
                continue
            old_categories = set(article.get("category", []))
            # Same status category is not a transition; avoid flagging duplicate coverage.
            changed = new_categories - old_categories
            if not changed:
                continue
            key = (str(article.get("id", "")), str(candidate.get("id", "")), tuple(sorted(changed)))
            if key in seen:
                continue
            seen.add(key)
            alert = {
                "published_title": article.get("title", "タイトル不明"),
                "published_id": article.get("id", ""),
                "published_status": article.get("business_status", "") or "状態記載なし",
                "candidate_title": candidate.get("title", "タイトル不明"),
                "candidate_id": candidate.get("id", ""),
                "candidate_status": "・".join(sorted(changed)),
                "municipality": new_town,
                "source_url": candidate.get("source_url", ""),
            }
            alerts.append(alert)
            candidate.setdefault("published_change_candidates", []).append({
                "published_id": article.get("id", ""),
                "published_status": article.get("business_status", "") or "状態記載なし",
                "possible_change": "・".join(sorted(changed)),
                "review_required": True,
            })
    return alerts


def render_markdown(alerts):
    lines = [
        "## 掲載済み店舗の状況変化チェック",
        "",
        f"- 照合した変更候補: {len(alerts)}件",
        "- 対象: 閉店・移転・リニューアル情報",
        "- 条件: 店舗名が一致し、市町も一致する候補のみ",
        "",
    ]
    if alerts:
        lines += ["### 人による確認が必要な可能性のある変更", ""]
        for item in alerts[:50]:
            lines += [
                f"- **{item['municipality']} / {item['published_title']}**",
                f"  - 掲載済み状態: {item['published_status']}",
                f"  - 新しい候補: {item['candidate_title']}",
                f"  - 変更候補: {item['candidate_status']}",
                f"  - 出典: {item['source_url']}",
            ]
    else:
        lines.append("掲載済み店舗と一致する状況変化候補は見つかりませんでした。")
    lines += [
        "",
        "このチェックは候補の自動承認・公開記事の自動変更を行いません。"
        "同名店舗の誤一致もあり得るため、所在地・公式情報・日付を人が確認してください。",
    ]
    return "\n".join(lines)


def main():
    drafts_data = json.loads(DRAFTS.read_text(encoding="utf-8"))
    published_data = json.loads(PUBLISHED.read_text(encoding="utf-8"))
    drafts = drafts_data.get("drafts", [])
    published = published_data.get("articles", [])
    if not isinstance(drafts, list) or not isinstance(published, list):
        raise SystemExit("Invalid drafts/published schema")
    for draft in drafts:
        draft.pop("published_change_candidates", None)
    alerts = find_status_changes(drafts, published)
    # Carry the review-only flags into the private review artifact; public article data is untouched.
    DRAFTS.write_text(json.dumps(drafts_data, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")
    report = render_markdown(alerts)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(report + "\n")
    print(report)


if __name__ == "__main__":
    main()
