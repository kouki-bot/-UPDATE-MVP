import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "collect_rss.py"
spec = importlib.util.spec_from_file_location("collect_rss", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RssCandidateMergeTests(unittest.TestCase):
    def candidate(self, title, url, area, categories=None, description="", published_date=""):
        return {
            "title": title,
            "url": url,
            "area": [area],
            "categories": categories or ["新店・開店"],
            "description": description,
        } | ({"published_date": published_date} if published_date else {})

    def test_same_title_with_different_urls_is_kept_separate(self):
        rows = [
            self.candidate("同名店舗がオープン", "https://news.example/a", "宇部市"),
            self.candidate("同名店舗がオープン", "https://news.example/b", "下関市"),
        ]
        merged = module.merge_candidates(rows)
        self.assertEqual(len(merged), 2)
        self.assertEqual({row["area"][0] for row in merged}, {"宇部市", "下関市"})

    def test_same_title_with_different_sources_is_not_assumed_duplicate(self):
        rows = [
            self.candidate("カフェがオープン", "https://media-one.example/story", "山口市"),
            self.candidate("カフェがオープン", "https://media-two.example/story", "防府市"),
        ]
        self.assertEqual(len(module.merge_candidates(rows)), 2)

    def test_tracking_parameter_variants_of_same_url_are_merged(self):
        rows = [
            self.candidate("宇部にカフェがオープン", "https://news.example/story?utm_source=rss", "宇部市"),
            self.candidate("宇部にカフェがオープン", "https://news.example/story?fbclid=abc", "山口県内", ["移転"], "詳しい本文"),
        ]
        merged = module.merge_candidates(rows)
        self.assertEqual(len(merged), 1)
        self.assertEqual(set(merged[0]["area"]), {"宇部市", "山口県内"})
        self.assertEqual(set(merged[0]["categories"]), {"新店・開店", "移転"})
        self.assertEqual(merged[0]["description"], "詳しい本文")

    def test_same_url_merges_missing_publication_date(self):
        rows = [
            self.candidate("新店オープン", "https://news.example/story", "宇部市"),
            self.candidate("別表記のタイトル", "https://news.example/story", "宇部市", published_date="2026-11-18T09:00:00+09:00"),
        ]
        merged = module.merge_candidates(rows)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["published_date"], "2026-11-18T09:00:00+09:00")


if __name__ == "__main__":
    unittest.main()
