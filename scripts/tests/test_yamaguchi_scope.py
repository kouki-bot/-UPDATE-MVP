import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "generate_drafts.py"
spec = importlib.util.spec_from_file_location("generate_drafts", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class YamaguchiScopeTests(unittest.TestCase):
    def test_clear_foreign_city_is_excluded(self):
        self.assertTrue(module.is_clearly_outside_yamaguchi("【開店】伊勢崎南店がオープン"))

    def test_yamaguchi_city_is_not_excluded(self):
        self.assertFalse(module.is_clearly_outside_yamaguchi("【開店】宇部市に新店舗"))

    def test_unknown_location_is_not_excluded(self):
        self.assertFalse(module.is_clearly_outside_yamaguchi("【開店】新しいカフェがオープン"))

    def test_listing_path_is_excluded(self):
        self.assertTrue(module.is_listing_candidate(
            "山口県の開店・閉店情報一覧",
            "https://example.com/category/yamaguchi"
        ))

    def test_article_path_is_kept(self):
        self.assertFalse(module.is_listing_candidate(
            "【開店】山口市に新しいカフェ",
            "https://example.com/2026/11/04/cafe-open"
        ))

    def test_foreign_filter_does_not_use_publisher_area(self):
        item = {
            "title": "【開店】伊勢崎南店がオープン",
            "url": "https://example.com/2026/11/04/store",
            "description": "新店舗の情報",
            "categories": ["新店・開店"],
            "area": ["山口県"],
        }
        self.assertIsNone(module.convert_candidate(item, "RSS", 2))

    def test_uncertain_candidate_is_not_removed_by_scope_filter(self):
        item = {
            "title": "【開店】新しいカフェがオープン",
            "url": "https://example.com/2026/11/04/cafe",
            "description": "詳細は公式サイトで確認",
            "categories": ["新店・開店"],
        }
        # Geographic uncertainty is not itself a rejection condition.
        self.assertFalse(module.is_clearly_outside_yamaguchi(item["title"], item["description"]))


if __name__ == "__main__":
    unittest.main()
