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

    def test_three_observed_foreign_articles_are_excluded(self):
        cases = [
            ("【閉店】A&Fカントリーささしま店",
             "愛知県名古屋市中村区 2026年10月31日閉店 住所 愛知県名古屋市中村区名駅1丁目"),
            ("【閉店】GEO ゲオ 伊勢崎南店",
             "群馬県伊勢崎市 2026年11月29日閉店 住所 群馬県伊勢崎市富塚町"),
            ("【閉店】グラフィカリー中目黒",
             "東京都目黒区 2026年11月30日閉店 住所 東京都目黒区青葉台"),
            ("【閉店】東武ストア 新船橋店",
             "千葉県船橋市 2026年11月5日閉店 住所 千葉県船橋市山手"),
        ]
        for title, body in cases:
            with self.subTest(title=title):
                self.assertTrue(module.is_clearly_outside_yamaguchi(title, body))

    def test_foreign_article_is_rejected_even_when_feed_area_says_yamaguchi(self):
        item = {
            "title": "【閉店】東武ストア 新船橋店",
            "url": "https://example.com/tobustore-shinfunabashi/",
            "body_excerpt": "千葉県船橋市 2026年11月5日閉店",
            "categories": ["閉店"],
            "area": ["山口県内"],
        }
        self.assertIsNone(module.convert_candidate(item, "RSS", 2))

    def test_unknown_location_remains_reviewable(self):
        item = {
            "title": "【閉店】所在地不明の店舗",
            "url": "https://example.com/unknown-store/",
            "body_excerpt": "閉店のお知らせ。所在地の記載なし。",
            "categories": ["閉店"],
            "area": ["山口県内"],
        }
        self.assertIsNotNone(module.convert_candidate(item, "RSS", 2))


if __name__ == "__main__":
    unittest.main()
