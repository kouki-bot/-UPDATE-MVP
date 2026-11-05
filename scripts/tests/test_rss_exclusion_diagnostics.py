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
            module.exclusion_reason("山口市役所の公式サイトをリニューアル", ""),
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

    def test_is_excluded_remains_boolean_compatible(self):
        self.assertTrue(module.is_excluded("山口市役所の公式サイトをリニューアル", ""))
        self.assertFalse(module.is_excluded("宇部に新しいパン店がオープン", ""))


if __name__ == "__main__":
    unittest.main()
