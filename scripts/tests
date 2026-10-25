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

    def test_missing_data_flagged(self):
        drafts = [{"id":"x","title":"店舗","category":["閉店"],"source_url":"","source_urls":[],"body_excerpt":"","published_date":"","municipality":"","municipality_candidates":[],"freshness":"日付確認が必要","status":"x"}]
        module.annotate_review_flags(drafts)
        self.assertIn("情報源URLなし", drafts[0]["review_flags"])
        self.assertIn("本文抜粋なし", drafts[0]["review_flags"])
        self.assertIn("公開日未確認", drafts[0]["review_flags"])
        self.assertEqual(drafts[0]["status"], "未確認・公開禁止")

if __name__ == "__main__":
    unittest.main()
