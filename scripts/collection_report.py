import json
import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

ROOT = Path(__file__).resolve().parent.parent
FILES = {
    "official": ROOT / "data" / "source_checks.json",
    "rss": ROOT / "data" / "rss_candidates.json",
    "drafts": ROOT / "data" / "drafts.json",
    "excluded": ROOT / "data" / "excluded_candidates.json",
}

def read_json(path):
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path.name}: JSON root must be an object")
    return data


def normalize_candidate_url(value):
    try:
        p = urlsplit(str(value or "").strip())
        if p.scheme not in ("http", "https") or not p.netloc:
            return ""
        tracking = {"fbclid", "gclid", "yclid", "mc_cid", "mc_eid"}
        query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
                 if k.lower() not in tracking and not k.lower().startswith("utm_")]
        return urlunsplit((p.scheme.lower(), p.netloc.lower(),
                           p.path.rstrip("/") or "/", urlencode(query), ""))
    except ValueError:
        return ""

def normalize_candidate_title(value):
    value = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"[\\s　・･「」『』【】（）():：,，.。!！?？〜～ー\\-_/]+", "", value)

def parse_collection_time(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None

def audit_duplicates(official_candidates, rss_candidates):
    groups = {}
    for kind, rows in (("公式", official_candidates), ("RSS", rss_candidates)):
        for row in rows:
            url = normalize_candidate_url(row.get("url") or row.get("source_url"))
            title = normalize_candidate_title(row.get("title") or row.get("store_name"))
            area = str(row.get("area") or "").strip()
            keys = []
            if url:
                keys.append(("URL", url))
            if title and len(title) >= 5:
                keys.append(("タイトル・地域", title + "|" + area))
            for key in keys:
                groups.setdefault(key, []).append({
                    "source": kind,
                    "title": row.get("title") or row.get("store_name") or "タイトル不明",
                    "url": row.get("url") or row.get("source_url") or "",
                })
    output = []
    seen = set()
    for (match_type, _), entries in groups.items():
        if len(entries) < 2:
            continue
        signature = tuple(sorted((x["source"], normalize_candidate_url(x["url"]),
                                  normalize_candidate_title(x["title"])) for x in entries))
        if signature in seen:
            continue
        seen.add(signature)
        output.append({"match": match_type, "entries": entries})
    return output

def count_draft_values(rows, field, allow_lists=False):
    counts = {}
    for row in rows:
        value = row.get(field)
        values = value if allow_lists and isinstance(value, list) else [value]
        for item in values:
            label = str(item or "").strip()
            if label:
                counts[label] = counts.get(label, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def build_report(official, rss, drafts, excluded=None):
    excluded = excluded or {}
    excluded_rows = excluded.get('candidates', [])
    excluded_reason_counts = excluded.get('reason_counts', {})
    official_sources = official.get("sources", [])
    rss_sources = rss.get("sources", [])
    official_candidates = official.get("candidates", [])
    rss_candidates = rss.get("candidates", [])
    draft_rows = drafts.get("drafts", [])

    if not all(isinstance(x, list) for x in (
        official_sources, rss_sources, official_candidates, rss_candidates, draft_rows
    )):
        raise ValueError("Collection JSON schema invalid: expected arrays")

    reachable = sum(1 for x in official_sources if x.get("status") == "reachable")
    partial = sum(1 for x in official_sources if x.get("status") == "partial")
    unavailable = sum(1 for x in official_sources if x.get("status") == "check_needed")
    rss_items = sum(int(x.get("items_read", 0) or 0) for x in rss_sources)
    flagged = sum(1 for x in draft_rows if x.get("review_flags"))
    unpublished = sum(1 for x in draft_rows if x.get("status") == "未確認・公開禁止")
    unsafe = len(draft_rows) - unpublished
    category_counts = count_draft_values(draft_rows, "category", allow_lists=True)
    municipality_counts = count_draft_values(draft_rows, "municipality_group")
    freshness_counts = count_draft_values(draft_rows, "freshness")
    review_bucket_counts = count_draft_values(draft_rows, "review_bucket")
    content_type_counts = count_draft_values(draft_rows, "content_type")
    review_flag_counts = count_draft_values(draft_rows, "review_flags", allow_lists=True)

    now = datetime.now(timezone.utc)
    freshness = {}
    for name, payload in (("official", official), ("rss", rss), ("drafts", drafts)):
        stamp = parse_collection_time(payload.get("generated_at"))
        age = round((now - stamp).total_seconds() / 3600, 1) if stamp else None
        freshness[name] = {"age_hours": age, "stale": age is None or age > 8}

    rss_issues = []
    for source in rss_sources:
        status = (source.get("diagnostics") or {}).get("http_status")
        if isinstance(status, int) and not 200 <= status < 400:
            rss_issues.append({"name": source.get("name", "名称不明"), "http_status": status})
        elif status in ("request_failed", "timeout", "parse_error"):
            rss_issues.append({"name": source.get("name", "名称不明"), "http_status": status})

    duplicates = audit_duplicates(official_candidates, rss_candidates)
    if not isinstance(excluded_rows, list) or not isinstance(excluded_reason_counts, dict):
        raise ValueError("Excluded audit JSON schema invalid")

    return {
        "official_source_count": len(official_sources),
        "official_reachable": reachable,
        "official_partial": partial,
        "official_unavailable": unavailable,
        "official_candidates": len(official_candidates),
        "rss_source_count": len(rss_sources),
        "rss_items_read": rss_items,
        "rss_candidates": len(rss_candidates),
        "draft_count": len(draft_rows),
        "excluded_audit_count": int(excluded.get("excluded_count", len(excluded_rows)) or 0),
        "excluded_reason_counts": excluded_reason_counts,
        "excluded_candidates": excluded_rows,
        "category_counts": category_counts,
        "municipality_counts": municipality_counts,
        "freshness_counts": freshness_counts,
        "review_bucket_counts": review_bucket_counts,
        "content_type_counts": content_type_counts,
        "review_flag_counts": review_flag_counts,
        "flagged_drafts": flagged,
        "review_only_drafts": unpublished,
        "unsafe_drafts": unsafe,
        "freshness": freshness,
        "duplicates": duplicates,
        "duplicate_count": len(duplicates),
        "rss_issues": rss_issues,
        "source_issues": [
            {"name": x.get("name", "名称不明"), "status": x.get("status", "不明"),
             "errors": len(x.get("fetch_errors", []))}
            for x in official_sources if x.get("status") != "reachable"
        ],
        "rss_sources": [
            {"name": x.get("name", "名称不明"), "items": int(x.get("items_read", 0) or 0)}
            for x in rss_sources
        ],
    }

def render_markdown(report):
    lines = [
        "## 山口ローカルUPDATE 情報収集レポート",
        "",
        "| 項目 | 結果 |",
        "|---|---:|",
        f"| 公式情報源 | {report['official_reachable']}件正常 / {report['official_partial']}件一部失敗 / {report['official_unavailable']}件取得要確認（全{report['official_source_count']}件） |",
        f"| 公式候補 | {report['official_candidates']}件 |",
        f"| RSS情報源 | {report['rss_source_count']}件 |",
        f"| RSS取得項目 | {report['rss_items_read']}件 |",
        f"| RSS候補 | {report['rss_candidates']}件 |",
        f"| 審査用下書き | {report['draft_count']}件 |",
        f"| 要確認フラグ付き | {report['flagged_drafts']}件 |",
        f"| 未確認・公開禁止 | {report['review_only_drafts']}件 |",
        f"| 公開禁止ルール違反 | {report['unsafe_drafts']}件 |",
        f"| 重複候補（要確認） | {report['duplicate_count']}組 |",
        "",
    ]
    for key, heading in (
        ("category_counts", "カテゴリー別の審査候補"),
        ("municipality_counts", "市町別の審査候補"),
        ("freshness_counts", "情報の鮮度別"),
        ("review_bucket_counts", "審査優先度別"),
        ("content_type_counts", "施設・サービス種別"),
        ("review_flag_counts", "確認事項・不足情報の内訳"),
        ("excluded_reason_counts", "除外理由の内訳（誤検出監査用）"),
    ):
        counts = report.get(key, {})
        if counts:
            lines += [f"### {heading}", ""]
            lines += [f"- {name}: {count}件" for name, count in counts.items()]
            lines.append("")
    if report.get("rss_issues"):
        lines += ["### RSS取得に問題がある情報源", ""]
        lines += [f"- {x['name']}: HTTP {x['http_status']}" for x in report["rss_issues"]]
        lines.append("")
    if report.get("duplicates"):
        lines += ["### 重複の可能性がある候補（自動削除しません）", ""]
        for group in report["duplicates"][:30]:
            lines.append(f"- {group['match']}: " + " / ".join(x["title"] for x in group["entries"]))
        lines.append("")
    stale = [name for name, value in report.get("freshness", {}).items() if value["stale"]]
    if stale:
        lines += ["### 古い、または生成日時を確認できないデータ", ""]
        lines += [f"- {name}: 8時間以上経過、または日時不明" for name in stale]
        lines.append("")
    if report["source_issues"]:
        lines += ["### 取得に注意が必要な公式情報源", ""]
        for source in report["source_issues"]:
            lines.append(f"- {source['name']}: {source['status']}（取得エラー{source['errors']}件）")
        lines.append("")
    if report["rss_sources"]:
        lines += ["### RSS・一覧情報源", ""]
        for source in report["rss_sources"]:
            lines.append(f"- {source['name']}: {source['items']}件")
        lines.append("")
    lines.append("候補はすべて審査専用です。このレポートは候補の正確性や公開可否を承認するものではありません。")
    return "\n".join(lines)

def main():
    official = read_json(FILES["official"])
    rss = read_json(FILES["rss"])
    drafts = read_json(FILES["drafts"])
    excluded = read_json(FILES["excluded"])
    report = build_report(official, rss, drafts, excluded)
    markdown = render_markdown(report)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write(markdown + "\n")
    print(markdown)
    if any(value["stale"] for value in report.get("freshness", {}).values()):
        raise SystemExit("Collection data is stale or missing timestamps")
    if report["unsafe_drafts"]:
        raise SystemExit(f"Safety failure: {report['unsafe_drafts']} draft(s) are not review-only")

if __name__ == "__main__":
    main()
