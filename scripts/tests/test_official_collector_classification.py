import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "collect_news.py"
spec = importlib.util.spec_from_file_location("collect_news", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class OfficialCollectorClassificationTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
