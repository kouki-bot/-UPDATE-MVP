import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = {
    "official": ROOT / "data" / "source_checks.json",
    "rss": ROOT / "data" / "rss_candidates.json",
    "drafts": ROOT / "data" / "drafts.json",
}

def read_json(path):
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path.name}: JSON root must be an object")
    return data

def build_report(official, rss, drafts):
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
        "flagged_drafts": flagged,
        "review_only_drafts": unpublished,
        "unsafe_drafts": unsafe,
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
        "",
    ]
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
    report = build_report(official, rss, drafts)
    markdown = render_markdown(report)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write(markdown + "\n")
    print(markdown)
    if report["unsafe_drafts"]:
        raise SystemExit(f"Safety failure: {report['unsafe_drafts']} draft(s) are not review-only")

if __name__ == "__main__":
    main()
