import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "generate_drafts.py"
spec = importlib.util.spec_from_file_location("generate_drafts_manual", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ManualCandidateTests(unittest.TestCase):
    def candidate(self, **overrides):
        row = {
            "id": "manual-1",
            "title": "【山口市】テスト店が11月1日オープン",
            "category": ["新店・開店"],
            "published_date": "2026-11-01",
            "event_date": "2026-11-01",
            "municipality": "山口市",
            "source_url": "https://example.com/store",
            "status": "未確認・公開禁止",
        }
        row.update(overrides)
        return row

    def test_manual_candidate_is_added_as_review_only(self):
        drafts = []
        added = module.add_manual_candidates(drafts, [self.candidate()])
        self.assertEqual(added, 1)
        self.assertEqual(len(drafts), 1)
        self.assertEqual(drafts[0]["status"], "未確認・公開禁止")

    def test_published_source_url_is_not_added_again(self):
        drafts = []
        published = [{"source_url": "https://example.com/store"}]
        added = module.add_manual_candidates(drafts, [self.candidate()], published)
        self.assertEqual(added, 0)
        self.assertEqual(drafts, [])

    def test_duplicate_draft_source_url_is_not_added(self):
        existing = self.candidate()
        added = module.add_manual_candidates([existing], [self.candidate(id="manual-2")])
        self.assertEqual(added, 0)

    def test_candidate_with_unsafe_status_is_rejected(self):
        with self.assertRaises(ValueError):
            module.add_manual_candidates([], [self.candidate(status="公開済み")])

    def test_candidate_without_source_url_is_ignored(self):
        added = module.add_manual_candidates([], [self.candidate(source_url="")])
        self.assertEqual(added, 0)


if __name__ == "__main__":
    unittest.main()
