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

    def test_explicit_address_wins_over_other_city_mentions(self):
        candidates = module.extract_municipality_candidates(
            "ケーズデンキ山口店オープン",
            "山口県山口市黒川にオープン。県内では宇部、岩国市に次いで3店目。"
        )
        self.assertEqual(candidates, ["山口市"])

    def test_multiple_explicit_addresses_remain_uncertain(self):
        candidates = module.extract_municipality_candidates(
            "県内2店舗の話題",
            "山口県山口市に新店、山口県岩国市にも新店がオープン。"
        )
        self.assertEqual(set(candidates), {"山口市", "岩国市"})

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

    def test_industry_category_pages_are_excluded_by_url(self):
        cases = [
            ("閉店情報-業種別", "https://kaiten-heiten-24.com/heiten-gyousyubetsu/"),
            ("開店情報-業種別", "https://kaiten-heiten-24.com/kaiten-gyousyubetsu/"),
        ]
        for title, url in cases:
            with self.subTest(title=title):
                self.assertTrue(module.is_listing_candidate(title, url))

    def test_industry_category_page_is_excluded_via_source_url(self):
        item = {
            "title": "【閉店】山口県の店舗が閉店",
            "url": "https://example.com/feed/item/123",
            "source_url": "https://kaiten-heiten-24.com/heiten-gyousyubetsu/",
            "description": "閉店情報を業種別にまとめたページ",
            "categories": ["閉店"],
        }
        self.assertIsNone(module.convert_candidate(item, "RSS", 2))

    def test_individual_article_with_industry_word_is_kept(self):
        self.assertFalse(module.is_listing_candidate(
            "【開店】山口市に新しい美容室がオープン",
            "https://example.com/2026/11/04/new-salon"
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

    def test_body_only_pilates_opening_is_kept(self):
        item = {
            "title": "宇部・恩田にピラティススタジオ「UNO」 マシン完備で個別ケア提供",
            "url": "https://example.com/uno",
            "body_excerpt": "女性専用のピラティススタジオが宇部市に10月1日オープンしました。",
        }
        converted = module.convert_candidate(item, "RSS", 2)
        self.assertIsNotNone(converted)
        self.assertIn("新店・開店", converted["category"])

    def test_body_only_cafe_opening_is_kept(self):
        item = {
            "title": "宇部にカフェ＆デリ「にくとはな」 肉料理メインに、キッチンカーも継続",
            "url": "https://example.com/niku-to-hana",
            "body_excerpt": "カフェ＆デリ「にくとはな」が10月23日にオープンしました。",
        }
        converted = module.convert_candidate(item, "RSS", 2)
        self.assertIsNotNone(converted)
        self.assertIn("新店・開店", converted["category"])

    def test_body_only_specialty_store_opening_is_kept(self):
        item = {
            "title": "防府駅前に解体専門店「ブラスト」 来店相談で空き家問題解決へ",
            "url": "https://example.com/blast",
            "body_excerpt": "解体専門店「ブラスト」が防府駅前に10月22日オープンしました。",
        }
        converted = module.convert_candidate(item, "RSS", 2)
        self.assertIsNotNone(converted)
        self.assertIn("新店・開店", converted["category"])

    def test_anniversary_mention_is_not_body_movement_evidence(self):
        self.assertFalse(module.has_body_movement_evidence(
            "同店はオープンから10周年を迎えました。"
        ))

    def test_event_venue_mention_is_not_body_movement_evidence(self):
        self.assertFalse(module.has_body_movement_evidence(
            "既存カフェを会場にマルシェを開催します。新店の紹介ではありません。"
        ))

    def test_unknown_location_remains_reviewable(self):
        item = {
            "title": "【閉店】所在地不明の店舗",
            "url": "https://example.com/unknown-store/",
            "body_excerpt": "閉店のお知らせ。所在地の記載なし。",
            "categories": ["閉店"],
            "area": ["山口県内"],
        }
        self.assertIsNotNone(module.convert_candidate(item, "RSS", 2))

    def test_one_day_event_is_excluded(self):
        self.assertFalse(module.is_store_news(
            "山口市で一日限定イベント開催・マルシェ出店者募集",
            "地域イベントの案内です。"
        ))

    def test_store_opening_with_event_word_is_kept(self):
        self.assertTrue(module.is_store_news(
            "宇部市に新しいカフェがオープン、記念イベント開催",
            "カフェが新規開店しました。"
        ))

    def test_same_store_news_with_different_headlines_is_merged(self):
        a = {
            "title": "【新店】ケーズデンキ山口店がオープン",
            "url": "https://example.com/news/a",
            "normalized_url": "https://example.com/news/a",
            "category": ["新店・開店"], "source_name": "媒体A",
            "source_priority": 2, "body_excerpt": "山口店が開店しました。",
        }
        b = {
            "title": "ケーズデンキ山口店 新規開店のお知らせ",
            "url": "https://example.net/news/b",
            "normalized_url": "https://example.net/news/b",
            "category": ["新店・開店"], "source_name": "媒体B",
            "source_priority": 2, "body_excerpt": "山口店が新規開店しました。",
        }
        merged = module.merge_candidates([a, b])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["duplicate_sources_count"], 2)


if __name__ == "__main__":
    unittest.main()
