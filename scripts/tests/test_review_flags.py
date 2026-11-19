import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "generate_drafts.py"
spec = importlib.util.spec_from_file_location("generate_drafts", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class ReviewFlagTests(unittest.TestCase):
    def test_store_name_variant_normalization_is_limited(self):
        self.assertEqual(
            module.normalize_store_name_variant("Cafe青空"),
            module.normalize_store_name_variant("カフェ青空"),
        )
        self.assertNotEqual(
            module.normalize_store_name_variant("Cafe青空 宇部店"),
            module.normalize_store_name_variant("Cafe青空 山口店"),
        )
        self.assertEqual(module.normalize_store_name_variant("青空珈琲"), "青空珈琲")

    def test_store_name_variant_requires_matching_municipality(self):
        base = {
            "category": ["新店・開店"],
            "event_date": "2026-11-10",
            "published_date": "2026-11-01",
            "municipality_candidates": ["宇部市"],
        }
        a = dict(base, title="Cafe青空が宇部市にオープン")
        b = dict(base, title="カフェ青空がオープン")
        self.assertTrue(module.same_store_news_candidate(a, b))
        b["municipality_candidates"] = ["山口市"]
        self.assertFalse(module.same_store_news_candidate(a, b))

    def test_similar_titles_flagged_not_removed(self):
        drafts = [
            {"id":"a","title":"【開店】カフェ青空 宇部店","category":["新店・開店"],"source_url":"https://example.com/a","source_urls":[{"url":"https://example.com/a"}],"body_excerpt":"紹介文","published_date":"2026-10-01","municipality":"宇部市","municipality_candidates":["宇部市"],"freshness":"直近30日","status":"x"},
            {"id":"b","title":"2026年10月1日 【開店】カフェ青空 宇部店","category":["新店・開店"],"source_url":"https://example.com/b","source_urls":[{"url":"https://example.com/b"}],"body_excerpt":"別記事","published_date":"2026-10-01","municipality":"宇部市","municipality_candidates":["宇部市"],"freshness":"直近30日","status":"x"},
        ]
        summary = module.annotate_review_flags(drafts)
        self.assertEqual(len(drafts), 2)
        self.assertEqual(summary["duplicate_group_count"], 1)
        self.assertTrue(all(x["duplicate_review"] == "重複の可能性・要確認" for x in drafts))
        self.assertTrue(all(x["status"] == "未確認・公開禁止" for x in drafts))

    def test_body_without_store_movement_is_flagged_and_held(self):
        drafts = [{"id":"body-check","title":"カフェ青空がオープン","category":["新店・開店"],"source_url":"https://example.com/story","source_urls":[{"url":"https://example.com/story"}],"body_excerpt":"地域の皆さまに愛される店舗を目指します。営業時間は午前10時からです。","published_date":"2026-10-01","municipality":"宇部市","municipality_candidates":["宇部市"],"freshness":"直近30日","status":"x"}]
        module.annotate_review_flags(drafts)
        self.assertIn("本文で店舗動作を確認できず", drafts[0]["review_flags"])
        self.assertEqual(drafts[0]["review_bucket"], "確認待ち")
        self.assertEqual(drafts[0]["status"], "未確認・公開禁止")

    def test_body_movement_evidence_does_not_add_flag(self):
        drafts = [{"id":"body-ok","title":"カフェ青空がオープン","category":["新店・開店"],"source_url":"https://example.com/story","source_urls":[{"url":"https://example.com/story"}],"body_excerpt":"カフェ青空は10月1日にオープンしました。","published_date":"2026-10-01","event_date":"2026-10-01","municipality":"宇部市","municipality_candidates":["宇部市"],"freshness":"直近30日","status":"x"}]
        module.annotate_review_flags(drafts)
        self.assertNotIn("本文で店舗動作を確認できず", drafts[0]["review_flags"])

    def test_title_body_movement_category_mismatch_is_held(self):
        drafts = [{
            "id": "mismatch", "title": "カフェ青空が閉店",
            "category": ["閉店"], "source_url": "https://example.com/story",
            "source_urls": [{"url": "https://example.com/story"}],
            "body_excerpt": "カフェ青空は11月に新規オープンしました。",
            "published_date": "2026-11-01", "event_date": "2026-11-01",
            "municipality": "宇部市", "municipality_candidates": ["宇部市"],
            "freshness": "直近30日", "status": "x",
        }]
        module.annotate_review_flags(drafts)
        self.assertIn("見出しと本文の店舗動作が不一致", drafts[0]["review_flags"])
        self.assertEqual(drafts[0]["review_bucket"], "確認待ち")
        self.assertEqual(drafts[0]["status"], "未確認・公開禁止")

    def test_title_body_matching_movement_category_is_not_flagged(self):
        drafts = [{
            "id": "matching", "title": "カフェ青空が閉店",
            "category": ["閉店"], "source_url": "https://example.com/story",
            "source_urls": [{"url": "https://example.com/story"}],
            "body_excerpt": "カフェ青空は11月30日に閉店しました。",
            "published_date": "2026-11-01", "event_date": "2026-11-30",
            "municipality": "宇部市", "municipality_candidates": ["宇部市"],
            "freshness": "直近30日", "status": "x",
        }]
        module.annotate_review_flags(drafts)
        self.assertNotIn("見出しと本文の店舗動作が不一致", drafts[0]["review_flags"])

    def test_missing_data_flagged(self):
        drafts = [{"id":"x","title":"店舗","category":["閉店"],"source_url":"","source_urls":[],"body_excerpt":"","published_date":"","municipality":"","municipality_candidates":[],"freshness":"日付確認が必要","status":"x"}]
        module.annotate_review_flags(drafts)
        self.assertIn("情報源URLなし", drafts[0]["review_flags"])
        self.assertIn("本文抜粋なし", drafts[0]["review_flags"])
        self.assertIn("公開日未確認", drafts[0]["review_flags"])
        self.assertEqual(drafts[0]["status"], "未確認・公開禁止")

    def test_manual_review_flags_are_preserved(self):
        drafts = [{"id":"manual-flags","title":"やよい軒 山口大学前店","category":["リニューアル"],"source_url":"https://example.com/story","source_urls":[{"url":"https://example.com/story"}],"body_excerpt":"11月12日にリニューアルオープンしました。","published_date":"2026-11-11","event_date":"2026-11-12","municipality":"山口市","municipality_candidates":["山口市"],"freshness":"直近30日","review_flags":["公式情報の日付に不一致あり"],"status":"x"}]
        module.annotate_review_flags(drafts)
        self.assertIn("公式情報の日付に不一致あり", drafts[0]["review_flags"])

    def test_manual_hold_forces_review_bucket_and_unpublished_status(self):
        drafts = [{"id":"manual-hold","title":"やよい軒 山口大学前店","category":["リニューアル"],"source_url":"https://example.com/story","source_urls":[{"url":"https://example.com/story"}],"body_excerpt":"11月12日にリニューアルオープンしました。","published_date":"2026-11-11","event_date":"2026-11-12","municipality":"山口市","municipality_candidates":["山口市"],"freshness":"直近30日","manual_hold":True,"review_flags":["公式情報の日付に不一致あり"],"status":"x"}]
        module.annotate_review_flags(drafts)
        self.assertEqual(drafts[0]["review_bucket"], "確認待ち")
        self.assertEqual(drafts[0]["review_priority"], "要優先確認")
        self.assertEqual(drafts[0]["status"], "未確認・公開禁止")
        self.assertIn("公式情報の日付に不一致あり", drafts[0]["review_flags"])

if __name__ == "__main__":
    unittest.main()
