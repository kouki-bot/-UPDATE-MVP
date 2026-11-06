import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "generate_drafts.py"
spec = importlib.util.spec_from_file_location("generate_drafts", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DraftSortingTests(unittest.TestCase):
    def test_newer_date_wins_over_priority(self):
        older = {"freshness": "直近30日", "published_date": "2026-10-20", "priority": 1}
        newer = {"freshness": "直近30日", "published_date": "2026-10-25", "priority": 5}
        self.assertLess(module.sort_key(newer), module.sort_key(older))

    def test_freshness_group_wins_over_date(self):
        recent = {"freshness": "直近30日", "published_date": "2026-10-01", "priority": 5}
        older_group = {"freshness": "31〜90日前", "published_date": "2026-10-30", "priority": 1}
        self.assertLess(module.sort_key(recent), module.sort_key(older_group))

    def test_missing_date_sorts_as_unknown_group(self):
        unknown = {"freshness": "日付確認が必要", "published_date": "", "priority": 1}
        dated = {"freshness": "直近30日", "published_date": "2026-10-01", "priority": 5}
        self.assertLess(module.sort_key(dated), module.sort_key(unknown))

    def test_review_flagging_keeps_draft_unverified(self):
        drafts = [{"id": "x", "title": "店舗", "category": ["閉店"],
                   "source_url": "", "source_urls": [], "body_excerpt": "",
                   "published_date": "", "municipality": "",
                   "municipality_candidates": [], "freshness": "日付確認が必要",
                   "status": "公開可能"}]
        module.annotate_review_flags(drafts)
        self.assertEqual(drafts[0]["status"], "未確認・公開禁止")



    def test_missing_core_information_is_put_on_hold(self):
        drafts = [{
            "id": "missing", "title": "宇部の新店", "category": ["新店・開店"],
            "source_url": "https://example.jp/article", "source_urls": [],
            "body_excerpt": "", "published_date": "", "event_date": "",
            "municipality": "", "municipality_candidates": [],
            "freshness": "日付確認が必要", "status": "公開可能",
        }]
        module.annotate_review_flags(drafts)
        self.assertEqual(drafts[0]["review_priority"], "情報不足・保留")
        self.assertEqual(drafts[0]["status"], "未確認・公開禁止")

    def test_duplicate_candidate_gets_separate_review_priority(self):
        drafts = [{
            "id": "dup", "title": "宇部の新店オープン", "category": ["新店・開店"],
            "source_url": "https://example.jp/article", "source_urls": [],
            "body_excerpt": "店舗が宇部市にオープンしました。", "published_date": "2026-11-01",
            "event_date": "2026-11-01", "municipality": "宇部市",
            "municipality_candidates": ["宇部市"], "freshness": "直近30日",
            "duplicate_review": "重複の可能性・要確認", "status": "公開可能",
        }]
        module.annotate_review_flags(drafts)
        self.assertEqual(drafts[0]["review_priority"], "重複確認")
        self.assertEqual(drafts[0]["status"], "未確認・公開禁止")

    def test_complete_metadata_still_requires_human_review(self):
        drafts = [{
            "id": "complete", "title": "宇部の新店オープン", "category": ["新店・開店"],
            "source_url": "https://example.jp/article", "source_urls": [],
            "body_excerpt": "店舗が宇部市にオープンしました。", "published_date": "2026-11-01",
            "event_date": "2026-11-01", "municipality": "宇部市",
            "municipality_candidates": ["宇部市"], "freshness": "直近30日",
            "status": "公開可能",
        }]
        module.annotate_review_flags(drafts)
        self.assertEqual(drafts[0]["review_priority"], "基本項目あり・内容確認は必要")
        self.assertEqual(drafts[0]["status"], "未確認・公開禁止")


    def test_lodging_is_outside_store_scope(self):
        item = {"title": "山口市に新しいホテルがオープン", "body_excerpt": ""}
        self.assertFalse(module.is_in_store_scope(item))

    def test_tourism_and_leisure_are_outside_store_scope(self):
        item = {"title": "観光農園が新規オープン", "body_excerpt": ""}
        self.assertFalse(module.is_in_store_scope(item))

    def test_public_facility_is_outside_store_scope(self):
        item = {"title": "新しい図書館が開館", "body_excerpt": ""}
        self.assertFalse(module.is_in_store_scope(item))

    def test_retail_shop_remains_in_store_scope(self):
        item = {"title": "山口市に新しいカフェがオープン", "body_excerpt": ""}
        self.assertTrue(module.is_in_store_scope(item))

if __name__ == "__main__":
    unittest.main()
