import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "track_published_changes.py"
spec = importlib.util.spec_from_file_location("track_published_changes", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PublishedStoreChangeTests(unittest.TestCase):
    def published(self, town="宇部市", title="カフェ青空店がオープン", status="営業中"):
        return {
            "id": "published-1", "title": title,
            "body": "宇部市のカフェ青空店。", "municipality": town,
            "business_status": status, "category": ["新店・開店"],
            "source_url": "https://example.jp/old",
        }

    def candidate(self, town="宇部市", title="カフェ青空店が閉店", category=None, status="未確認・公開禁止"):
        return {
            "id": "draft-1", "title": title,
            "body_excerpt": "宇部市のカフェ青空店が閉店する。",
            "municipality": town, "category": category or ["閉店"],
            "source_url": "https://example.jp/new", "status": status,
        }

    def test_flags_closure_for_published_store_and_marks_review_candidate(self):
        draft = self.candidate()
        alerts = module.find_status_changes([draft], [self.published()])
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["candidate_status"], "閉店")
        self.assertTrue(draft["published_change_candidates"][0]["review_required"])

    def test_does_not_match_different_municipality(self):
        self.assertEqual(
            module.find_status_changes([self.candidate("下関市")], [self.published()]), []
        )

    def test_does_not_match_different_store(self):
        draft = self.candidate(title="カフェ木漏れ日店が閉店")
        draft["body_excerpt"] = "宇部市のカフェ木漏れ日店が閉店する。"
        self.assertEqual(module.find_status_changes([draft], [self.published()]), [])

    def test_does_not_alert_same_category_coverage(self):
        draft = self.candidate(category=["新店・開店"])
        self.assertEqual(module.find_status_changes([draft], [self.published()]), [])

    def test_does_not_alert_same_source_url(self):
        draft = self.candidate()
        draft["source_url"] = "https://example.jp/old?utm_source=rss"
        self.assertEqual(module.find_status_changes([draft], [self.published()]), [])

    def test_ignores_candidates_that_are_not_review_only(self):
        draft = self.candidate(status="公開済み")
        self.assertEqual(module.find_status_changes([draft], [self.published()]), [])

    def test_store_names_discards_shared_branch_suffix_when_full_name_exists(self):
        published = {
            "title": "【山口市】スーパーセンタートライアル山口小郡店がオープン",
            "body": "スーパーセンタートライアル山口小郡店（山口市陶）。",
        }
        candidate = {
            "title": "【山口市】長崎ちゃんめん 山口小郡店がリニューアル",
            "body_excerpt": "長崎ちゃんめん 山口小郡店（山口市小郡）。",
        }
        old_names = module.store_names(published)
        new_names = module.store_names(candidate)
        self.assertTrue(old_names)
        self.assertTrue(new_names)
        self.assertFalse(old_names & new_names)

    def test_does_not_flag_different_brands_sharing_same_area_suffix(self):
        published = self.published(
            town="山口市",
            title="【山口市】スーパーセンタートライアル山口小郡店がオープン",
        )
        published["body"] = "スーパーセンタートライアル山口小郡店（山口市陶）。"
        candidate = self.candidate(
            town="山口市",
            title="【山口市】長崎ちゃんめん 山口小郡店がリニューアル",
        )
        candidate["body_excerpt"] = "長崎ちゃんめん 山口小郡店（山口市小郡）。"
        self.assertEqual(module.find_status_changes([candidate], [published]), [])

    def test_store_names_normalizes_whitespace_in_full_branch_names(self):
        article = {
            "title": "宇部市の『長崎ちゃんめん 山口小郡店』が開店",
            "body": "長崎ちゃんめん 山口小郡店が宇部市に開店しました。",
        }
        names = module.store_names(article)
        self.assertIn("長崎ちゃんめん山口小郡店", names)
        self.assertNotIn("山口小郡店", names)

    def test_alert_preserves_all_valid_source_urls_for_human_review(self):
        draft = self.candidate()
        draft["source_urls"] = [
            {"source_name": "媒体A", "url": "https://news-a.example/story?utm_source=rss"},
            {"source_name": "媒体B", "url": "https://news-b.example/story"},
            {"source_name": "不正URL", "url": "javascript:alert(1)"},
            {"source_name": "媒体A重複", "url": "https://news-a.example/story"},
        ]
        alerts = module.find_status_changes([draft], [self.published()])
        sources = alerts[0]["sources"]
        self.assertEqual(len(sources), 2)
        self.assertEqual(
            {item["source_name"] for item in sources}, {"媒体A", "媒体B"}
        )
        self.assertTrue(all(item["url"].startswith("https://") for item in sources))
        change = draft["published_change_candidates"][0]
        self.assertEqual(change["candidate_sources"], sources)

    def test_report_explicitly_says_manual_review_only(self):
        report = module.render_markdown([])
        self.assertIn("自動承認・公開記事の自動変更を行いません", report)


if __name__ == "__main__":
    unittest.main()
