import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "collection_report.py"
spec = importlib.util.spec_from_file_location("collection_report", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class CollectionReportTests(unittest.TestCase):
    def test_counts_sources_candidates_and_review_only(self):
        report = module.build_report(
            {"sources": [
                {"name": "県", "status": "reachable", "fetch_errors": []},
                {"name": "市", "status": "partial", "fetch_errors": [{"url": "x"}]},
            ], "candidates": [{"id": "a"}]},
            {"sources": [{"name": "RSS", "items_read": 4}], "candidates": [{"id": "b"}]},
            {"drafts": [
                {"id": "a", "status": "未確認・公開禁止", "review_flags": ["公開日未確認"]},
                {"id": "b", "status": "未確認・公開禁止", "review_flags": []},
            ]},
        )
        self.assertEqual(report["official_reachable"], 1)
        self.assertEqual(report["official_partial"], 1)
        self.assertEqual(report["official_candidates"], 1)
        self.assertEqual(report["rss_items_read"], 4)
        self.assertEqual(report["draft_count"], 2)
        self.assertEqual(report["flagged_drafts"], 1)
        self.assertEqual(report["review_only_drafts"], 2)
        self.assertEqual(report["unsafe_drafts"], 0)

    def test_non_review_only_draft_is_detected(self):
        report = module.build_report(
            {"sources": [], "candidates": []},
            {"sources": [], "candidates": []},
            {"drafts": [{"id": "unsafe", "status": "公開"}]},
        )
        self.assertEqual(report["unsafe_drafts"], 1)

    def test_report_discloses_source_issues(self):
        report = module.build_report(
            {"sources": [{"name": "県公式", "status": "check_needed", "fetch_errors": []}], "candidates": []},
            {"sources": [], "candidates": []},
            {"drafts": []},
        )
        rendered = module.render_markdown(report)
        self.assertIn("県公式", rendered)
        self.assertIn("check_needed", rendered)

if __name__ == "__main__":
    unittest.main()
