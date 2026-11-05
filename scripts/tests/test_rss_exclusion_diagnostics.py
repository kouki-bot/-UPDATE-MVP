import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "collect_rss.py"
spec = importlib.util.spec_from_file_location("collect_rss", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RssExclusionDiagnosticsTests(unittest.TestCase):
    def test_reason_identifies_excluded_public_title(self):
        self.assertEqual(
            module.exclusion_reason("山口市役所が営業終了", ""),
            "excluded_title_keyword:市役所",
        )

    def test_reason_identifies_homepage_notice(self):
        self.assertEqual(
            module.exclusion_reason("店舗公式サイトをリニューアル", ""),
            "website_or_homepage",
        )

    def test_relevant_store_opening_is_not_excluded(self):
        self.assertEqual(
            module.exclusion_reason("宇部に新しいパン店がオープン", ""),
            "",
        )

    def test_no_store_movement_keyword_is_identified(self):
        self.assertEqual(
            module.exclusion_reason("山口市でイベント開催", ""),
            "no_store_movement_keyword",
        )

    def test_foreign_syndicated_content_is_identified(self):
        self.assertEqual(
            module.exclusion_reason("宇部に新店オープン", "横浜経済新聞から転載"),
            "foreign_syndicated_content",
        )

    def test_body_only_opening_is_accepted_and_classified(self):
        title = "宇部にカフェ＆デリ「にくとはな」 肉料理メインに"
        description = "カフェ＆デリ「にくとはな」が10月23日、宇部にオープンした。"
        self.assertEqual(module.exclusion_reason(title, description), "")
        self.assertIn("新店・開店", module.classify_text(description))

    def test_body_only_studio_opening_is_accepted(self):
        title = "宇部・恩田にピラティススタジオ「UNO」 マシン完備"
        description = "女性専用ピラティススタジオが10月1日、宇部にオープンした。"
        self.assertEqual(module.exclusion_reason(title, description), "")

    def test_anniversary_story_is_not_treated_as_new_opening(self):
        title = "宇部のハード系パン店「アルメリア」が1周年"
        description = "パン店がオープンから1周年を迎えた。"
        self.assertEqual(
            module.exclusion_reason(title, description),
            "anniversary_existing_store",
        )

    def test_event_with_shop_venue_is_not_accepted_as_opening(self):
        title = "おのだサンパークでグルメフェスタ始まる"
        description = "イベントが商業施設で開催された。"
        self.assertEqual(
            module.exclusion_reason(title, description),
            "no_store_movement_keyword",
        )

    def test_body_only_opening_does_not_override_public_title_exclusion(self):
        title = "宇部市役所に新サービス"
        description = "新サービスがオープンした。"
        self.assertEqual(
            module.exclusion_reason(title, description),
            "excluded_title_keyword:市役所",
        )

    def test_is_excluded_remains_boolean_compatible(self):
        self.assertTrue(module.is_excluded("山口市役所の公式サイトをリニューアル", ""))
        self.assertFalse(module.is_excluded("宇部に新しいパン店がオープン", ""))


if __name__ == "__main__":
    unittest.main()
