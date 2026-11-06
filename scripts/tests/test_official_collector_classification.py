import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "collect_news.py"
spec = importlib.util.spec_from_file_location("collect_news", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class OfficialCollectorClassificationTests(unittest.TestCase):
    def test_official_press_article_url_is_detected(self):
        self.assertTrue(
            module.is_article_url(
                "https://www.pref.yamaguchi.lg.jp/press/369077.html"
            )
        )

    def test_city_topic_article_url_is_detected(self):
        self.assertTrue(
            module.is_article_url(
                "https://www.city.yamaguchi.lg.jp/site/topics/201713.html"
            )
        )

    def test_archive_page_is_not_article_url(self):
        self.assertFalse(
            module.is_article_url(
                "https://www.pref.yamaguchi.lg.jp/press/search.php?search_ym=202611"
            )
        )

    def test_store_opening_is_kept(self):
        categories, basis = module.classify_text(
            "山口市に新しいカフェがオープン"
        )
        self.assertIn("新店・開店", categories)

    def test_named_store_opening_is_kept(self):
        categories, _ = module.classify_text(
            "宇部市にドラッグストア新規オープン"
        )
        self.assertIn("新店・開店", categories)

    def test_closure_is_kept(self):
        categories, _ = module.classify_text(
            "山口市のスーパーが閉店"
        )
        self.assertIn("閉店", categories)

    def test_store_relocation_is_kept(self):
        categories, _ = module.classify_text(
            "山口市の美容室が移転"
        )
        self.assertIn("移転", categories)

    def test_store_renovation_is_kept(self):
        categories, _ = module.classify_text(
            "山口市の商業施設がリニューアルオープン"
        )
        self.assertEqual(categories, ["リニューアル"])

    def test_public_park_renovation_is_excluded(self):
        categories, basis = module.classify_text(
            "重源の郷体験交流公園がリニューアルオープンしました"
        )
        self.assertEqual(categories, [])
        self.assertEqual(basis, "公共・文化施設除外")

    def test_local_history_museum_event_is_excluded(self):
        categories, basis = module.classify_text(
            "鋳銭司郷土館展示リニューアルオープン式典を行いました"
        )
        self.assertEqual(categories, [])
        self.assertEqual(basis, "公共・文化施設除外")

    def test_roadside_station_renovation_is_excluded(self):
        categories, basis = module.classify_text(
            "道の駅「きらら あじす」がリニューアルオープンしました"
        )
        self.assertEqual(categories, [])
        self.assertEqual(basis, "公共・文化施設除外")

    def test_community_exchange_space_opening_is_excluded(self):
        categories, basis = module.classify_text(
            "中心商店街に地域の魅力発信・交流スペース「コトサイト」がオープンしました"
        )
        self.assertEqual(categories, [])
        self.assertEqual(basis, "公共・文化施設除外")

    def test_open_campus_is_excluded(self):
        categories, basis = module.classify_text(
            "山口県立農業大学校 夏のオープンキャンパス"
        )
        self.assertEqual(categories, [])
        self.assertEqual(basis, "イベント除外")

    def test_calendar_page_is_excluded(self):
        categories, _ = module.classify_text(
            "カレンダーで探す",
            "イベント検索、開催日、講座一覧",
        )
        self.assertEqual(categories, [])

    def test_store_category_listing_page_is_excluded(self):
        categories, basis = module.classify_text(
            "山口県の新店・開店情報一覧"
        )
        self.assertEqual(categories, [])
        self.assertEqual(basis, "一覧・ナビ除外")

    def test_public_meeting_is_excluded(self):
        categories, _ = module.classify_text(
            "子育て文化審議会の開催について"
        )
        self.assertEqual(categories, [])

    def test_museum_renovation_is_not_shop_feed(self):
        categories, _ = module.classify_text(
            "秋吉台エコ・ミュージアムのリニューアル工事について"
        )
        self.assertEqual(categories, [])

    def test_market_event_is_not_store_opening(self):
        categories, _ = module.classify_text(
            "ノウフクマルシェを開催します"
        )
        self.assertEqual(categories, [])

    def test_open_word_without_business_context_is_excluded(self):
        categories, _ = module.classify_text(
            "新しい取り組みがオープンします"
        )
        self.assertEqual(categories, [])

    def test_body_only_store_opening_is_review_candidate(self):
        categories, basis = module.classify_text(
            "宇部・恩田の新スポット",
            "新しいピラティススタジオが10月1日にオープンしました。",
        )
        self.assertIn("新店・開店", categories)
        self.assertEqual(basis, "本文・要確認")

    def test_unrelated_body_keywords_in_separate_sentences_are_excluded(self):
        categories, _ = module.classify_text(
            "中村心さんにアンバサダーを委嘱します",
            "県内の店舗を紹介します。アンバサダーを委嘱しました。",
        )
        self.assertEqual(categories, [])

    def test_campaign_visit_is_not_store_opening(self):
        categories, _ = module.classify_text(
            "旬の桃を届けに関係者が市長を表敬訪問",
            "キャンペーンクルーが市長を表敬訪問されました。",
        )
        self.assertEqual(categories, [])

    def test_business_and_opening_in_same_body_sentence_is_kept(self):
        categories, basis = module.classify_text(
            "宇部・恩田の新スポット",
            "宇部市に新しいピラティススタジオが10月1日にオープンしました。",
        )
        self.assertIn("新店・開店", categories)
        self.assertEqual(basis, "本文・要確認")


    def test_ambassador_appointment_article_is_excluded_even_if_body_mentions_store_opening(self):
        categories, basis = module.classify_text(
            "中村心さんに「やまぐち和牛燦アンバサダー」を委嘱します！",
            "県内の店舗がオープンしました。アンバサダーの委嘱式を行います。",
        )
        self.assertEqual(categories, [])
        self.assertEqual(basis, "行政活動・表敬訪問除外")

    def test_campaign_mayor_visit_article_is_excluded_even_if_body_mentions_store_opening(self):
        categories, basis = module.classify_text(
            "旬の桃を届けに福島市副市長とミスピーチキャンペーンクルーが市長を表敬訪問されました",
            "県内の店舗がオープンしました。キャンペーンクルーが市長を訪問しました。",
        )
        self.assertEqual(categories, [])
        self.assertEqual(basis, "行政活動・表敬訪問除外")

    def test_body_only_opening_requires_actual_business_predicate(self):
        categories, _ = module.classify_text(
            "地域の取り組みについて",
            "県内の店舗の需要拡大に向けた取り組みを開始しました。",
        )
        self.assertEqual(categories, [])

    def test_body_only_store_opening_accepts_completed_action(self):
        categories, basis = module.classify_text(
            "宇部・恩田の新スポット",
            "新しいピラティススタジオが10月1日にオープンしました。",
        )
        self.assertIn("新店・開店", categories)
        self.assertEqual(basis, "本文・要確認")


    def test_known_chain_store_opening_without_industry_word_is_review_candidate(self):
        categories, basis = module.classify_text(
            "ケーズデンキ山口店がオープン",
            "山口市内に新店舗がオープンします。",
        )
        self.assertIn("新店・開店", categories)
        self.assertEqual(basis, "地域・店舗名・動向／要確認")

    def test_named_restaurant_opening_with_area_is_review_candidate(self):
        categories, basis = module.classify_text(
            "サイゼリヤおのだサンパーク店オープン",
            "山陽小野田市の商業施設に出店します。",
        )
        self.assertIn("新店・開店", categories)

    def test_closure_word_haigyo_is_detected(self):
        categories, basis = module.classify_text(
            "山口県内の長寿製パンが廃業へ",
            "長年営業してきた店舗を閉じる予定です。",
        )
        self.assertIn("閉店", categories)

    def test_body_only_sales_start_planned_is_review_candidate(self):
        categories, basis = module.classify_text(
            "宇部市の新店舗について",
            "新しい専門店が11月に営業を開始する予定です。",
        )
        self.assertIn("新店・開店", categories)
        self.assertEqual(basis, "本文・要確認")

    def test_area_and_generic_opening_without_store_name_is_not_enough(self):
        categories, _ = module.classify_text(
            "山口市で新しい取り組みがオープン",
            "地域の活動を開始します。",
        )
        self.assertEqual(categories, [])

    def test_event_with_store_word_is_not_misclassified(self):
        categories, _ = module.classify_text(
            "山口市の店舗でマルシェイベントを開催",
            "店舗でイベントを開催します。",
        )
        self.assertEqual(categories, [])


    def test_generic_new_store_title_without_movement_is_not_opening(self):
        categories, _ = module.classify_text(
            "宇部市の新店舗について",
            "新しい専門店の出店に向けて準備を進めています。",
        )
        self.assertEqual(categories, [])

    def test_new_store_opening_phrase_is_detected(self):
        categories, _ = module.classify_text(
            "山口市に新店オープン",
            "",
        )
        self.assertIn("新店・開店", categories)

    def test_store_closure_with_haigyo_word_is_detected(self):
        categories, _ = module.classify_text(
            "山口県内のパン店が廃業へ",
            "",
        )
        self.assertIn("閉店", categories)


    def test_seamall_new_store_listing_extracts_name_and_opening_date(self):
        entries = module.extract_shop_listing_entries(
            [
                "2026年11月21日オープン 店名 LUNA STUDIO 場所 5階 "
                "2026年11月3日オープン 店名 ナイスネイル 場所 3階"
            ],
            facility_name="シーモール下関",
            area="下関市",
        )
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["store_name"], "LUNA STUDIO")
        self.assertEqual(entries[0]["opening_date"], "2026年11月21日")
        self.assertEqual(entries[1]["store_name"], "ナイスネイル")

    def test_seamall_listing_without_store_name_is_ignored(self):
        entries = module.extract_shop_listing_entries(
            ["2026年11月21日オープン 場所 5階"],
            facility_name="シーモール下関",
            area="下関市",
        )
        self.assertEqual(entries, [])


if __name__ == "__main__":
    unittest.main()
