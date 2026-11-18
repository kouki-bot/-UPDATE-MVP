import unittest

from scripts.generate_drafts import add_manual_candidates


class ManualCandidateDeduplicationTests(unittest.TestCase):
    def candidate(self, url, source_name="公式情報"):
        return {
            "id": url.rsplit("/", 1)[-1],
            "title": "【山口市】「テストカフェ」が2026年11月1日オープン",
            "category": ["新店・開店"],
            "published_date": "2026-10-20",
            "event_date": "2026-11-01",
            "municipality": "山口市",
            "source_name": source_name,
            "source_url": url,
            "source_urls": [{"source_name": source_name, "url": url}],
            "status": "未確認・公開禁止",
        }

    def test_manual_duplicate_adds_source_instead_of_second_candidate(self):
        existing = self.candidate("https://example.com/news-a", "地域メディア")
        existing["source_urls"] = [
            {"source_name": "地域メディア", "url": "https://example.com/news-a"}
        ]
        drafts = [existing]
        manual = self.candidate("https://example.com/news-b", "店舗公式")

        added = add_manual_candidates(drafts, [manual], [])

        self.assertEqual(added, 0)
        self.assertEqual(len(drafts), 1)
        self.assertEqual(drafts[0]["duplicate_sources_count"], 2)
        self.assertTrue(drafts[0]["manual_duplicate_sources_added"])
        self.assertEqual(
            {source["url"] for source in drafts[0]["source_urls"]},
            {"https://example.com/news-a", "https://example.com/news-b"},
        )

    def test_manual_duplicate_of_published_article_is_not_added(self):
        published = self.candidate("https://example.com/published", "公式情報")
        drafts = []
        manual = self.candidate("https://example.com/another-report", "地域メディア")

        added = add_manual_candidates(drafts, [manual], [published])

        self.assertEqual(added, 0)
        self.assertEqual(drafts, [])

    def test_different_event_date_is_not_merged(self):
        existing = self.candidate("https://example.com/news-a")
        manual = self.candidate("https://example.com/news-b", "店舗公式")
        manual["event_date"] = "2026-11-15"
        drafts = [existing]

        added = add_manual_candidates(drafts, [manual], [])

        self.assertEqual(added, 1)
        self.assertEqual(len(drafts), 2)
        self.assertEqual(drafts[1]["status"], "未確認・公開禁止")


if __name__ == "__main__":
    unittest.main()
