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

    def test_report_breaks_down_drafts_for_review_prioritization(self):
        report = module.build_report(
            {"sources": [], "candidates": []},
            {"sources": [], "candidates": []},
            {"drafts": [
                {"status": "未確認・公開禁止", "category": ["新店・開店", "閉店"],
                 "municipality_group": "山口市", "freshness": "直近30日",
                 "review_bucket": "通常候補（要確認）", "content_type": "飲食店"},
                {"status": "未確認・公開禁止", "category": ["新店・開店"],
                 "municipality_group": "下関市", "freshness": "日付確認が必要",
                 "review_bucket": "確認待ち", "content_type": "小売店"},
            ]},
        )
        self.assertEqual(report["category_counts"], {"新店・開店": 2, "閉店": 1})
        self.assertEqual(report["municipality_counts"], {"下関市": 1, "山口市": 1})
        self.assertEqual(report["freshness_counts"], {"日付確認が必要": 1, "直近30日": 1})
        self.assertEqual(report["review_bucket_counts"], {"確認待ち": 1, "通常候補（要確認）": 1})
        self.assertEqual(report["content_type_counts"], {"小売店": 1, "飲食店": 1})
        rendered = module.render_markdown(report)
        self.assertIn("市町別の審査候補", rendered)
        self.assertIn("山口市: 1件", rendered)
        self.assertIn("確認待ち: 1件", rendered)

    def test_review_flags_are_counted_by_type(self):
        report = module.build_report(
            {"sources": [], "candidates": []},
            {"sources": [], "candidates": []},
            {"drafts": [
                {"status": "未確認・公開禁止",
                 "review_flags": ["公開日未確認", "市町未特定"]},
                {"status": "未確認・公開禁止",
                 "review_flags": ["公開日未確認"]},
                {"status": "未確認・公開禁止", "review_flags": []},
            ]},
        )
        self.assertEqual(
            report["review_flag_counts"],
            {"公開日未確認": 2, "市町未特定": 1},
        )
        rendered = module.render_markdown(report)
        self.assertIn("確認事項・不足情報の内訳", rendered)
        self.assertIn("公開日未確認: 2件", rendered)

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

    def test_duplicate_candidates_are_reported_without_removal(self):
        duplicates = module.audit_duplicates(
            [{"title": "新店オープンのお知らせ", "url": "https://example.jp/news/1?utm_source=x", "area": "山口市"}],
            [{"title": "新店オープンのお知らせ", "url": "https://example.jp/news/1", "area": "山口市"}],
        )
        self.assertGreaterEqual(len(duplicates), 1)
        self.assertEqual(len(duplicates[0]["entries"]), 2)

    def test_stale_collection_timestamp_is_detected(self):
        old = module.parse_collection_time("2020-01-01T00:00:00Z")
        age_hours = (module.datetime.now(module.timezone.utc) - old).total_seconds() / 3600
        self.assertGreater(age_hours, 8)

    def test_rss_http_error_is_reported(self):
        report = module.build_report(
            {"sources": [], "candidates": []},
            {"sources": [{"name": "RSS", "items_read": 0, "diagnostics": {"http_status": 503}}], "candidates": []},
            {"drafts": []},
        )
        self.assertEqual(report["rss_issues"][0]["http_status"], 503)

if __name__ == "__main__":
    unittest.main()
