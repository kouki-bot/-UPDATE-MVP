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


if __name__ == "__main__":
    unittest.main()
