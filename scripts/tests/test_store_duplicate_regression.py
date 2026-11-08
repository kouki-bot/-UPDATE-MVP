import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "generate_drafts.py"
spec = importlib.util.spec_from_file_location("generate_drafts", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class StoreDuplicateRegressionTests(unittest.TestCase):
    def make_item(self, title, body, event_date, town):
        return {
            "title": title,
            "body_excerpt": body,
            "category": ["閉店"] if "閉店" in title or "閉店" in body else ["新店・開店"],
            "event_date": event_date,
            "published_date": "2026-11-01",
            "municipality": town,
            "municipality_candidates": [town] if town else [],
        }

    def test_same_daimaru_shimonoseki_closure_is_matched(self):
        article_a = self.make_item(
            "2026/11/06 【まとめ】来夏閉店の大丸下関店 最近の話題",
            "大丸下関店は2027年8月末に営業終了することを発表した。下関市役所で会見した。",
            "2027-08-31",
            "下関市",
        )
        article_b = self.make_item(
            "大丸閉店「下関の象徴が」市民衝撃",
            "JR下関駅前の大丸下関店（下関市竹崎町）が2027年8月末で閉店する。",
            "2027-08-31",
            "下関市",
        )
        self.assertTrue(module.same_store_news_candidate(article_a, article_b))

    def test_same_loft_opening_is_matched(self):
        article_a = self.make_item(
            "おのだサンパークに「ロフト」オープン",
            "山口県山陽小野田市中川の商業施設内に生活雑貨専門店ロフト（東京都）がオープンした。",
            "2026-09-11",
            "山陽小野田市",
        )
        article_b = self.make_item(
            "生活雑貨専門店ロフトが山陽小野田市に開店",
            "山口県山陽小野田市中川にロフトがオープンした。",
            "2026-09-11",
            "山陽小野田市",
        )
        self.assertTrue(module.same_store_news_candidate(article_a, article_b))

    def test_different_stores_in_same_city_are_not_matched(self):
        article_a = self.make_item(
            "カフェ青空店が宇部市にオープン",
            "宇部市にカフェ青空店が開店した。",
            "2026-11-01",
            "宇部市",
        )
        article_b = self.make_item(
            "カフェ木漏れ日店が宇部市にオープン",
            "宇部市にカフェ木漏れ日店が開店した。",
            "2026-11-01",
            "宇部市",
        )
        self.assertFalse(module.same_store_news_candidate(article_a, article_b))

    def test_same_store_on_different_event_dates_is_not_matched(self):
        article_a = self.make_item(
            "カフェ青空店がオープン",
            "宇部市にカフェ青空店が開店した。",
            "2026-11-01",
            "宇部市",
        )
        article_b = self.make_item(
            "カフェ青空店が移転オープン",
            "宇部市のカフェ青空店が移転した。",
            "2026-12-01",
            "宇部市",
        )
        article_b["category"] = ["新店・開店"]
        self.assertFalse(module.same_store_news_candidate(article_a, article_b))

    def test_same_chain_name_in_different_cities_is_not_matched(self):
        article_a = self.make_item(
            "カフェ青空店が宇部市にオープン",
            "山口県宇部市にカフェ青空店が開店した。",
            "2026-11-01",
            "宇部市",
        )
        article_b = self.make_item(
            "カフェ青空店が下関市にオープン",
            "山口県下関市にカフェ青空店が開店した。",
            "2026-11-01",
            "下関市",
        )
        self.assertFalse(module.same_store_news_candidate(article_a, article_b))


    def test_tenant_opening_does_not_use_shopping_mall_renovation_date(self):
        title = "【防府市】ゆめタウン防府に「地球文化屋」が11月中旬オープン予定"
        body = (
            "防府市八王子のゆめタウン防府2階に、専門店「地球文化屋」が11月中旬にオープンする予定です。"
            "2026年10月15日にリニューアルオープンしたゆめタウン防府に加わる店舗です。"
        )
        self.assertEqual(module.extract_event_date(title, body, "2026-11-07"), "")
        self.assertEqual(module.extract_approximate_event_date_text(title, body), "11月中旬")

    def test_real_daimaru_shimonoseki_articles_are_duplicate_candidates(self):
        articles = [
            self.make_item(
                "2026/11/06 【まとめ】来夏閉店の大丸下関店 最近の話題",
                "大丸下関店は2027年8月末に営業終了することを発表した。下関市役所で会見した。",
                "2027-08-31", "下関市",
            ),
            self.make_item(
                "2026/07/03 大丸下関店閉店で利用客から惜しむ声",
                "2027年8月末で営業を終了することを発表した大丸下関店（山口県下関市）。",
                "2027-08-31", "下関市",
            ),
            self.make_item(
                "2026/07/01 大丸閉店「下関の象徴が」市民衝撃",
                "大丸下関店（下関市竹崎町）が2027年8月末で閉店する。",
                "2027-08-31", "下関市",
            ),
        ]
        self.assertTrue(module.same_store_news_candidate(articles[0], articles[1]))
        self.assertTrue(module.same_store_news_candidate(articles[0], articles[2]))

    def test_duplicate_review_never_removes_or_publishes_candidates(self):
        drafts = [
            {
                "id": "a", "title": "大丸下関店が閉店",
                "category": ["閉店"], "source_url": "https://example.jp/a",
                "source_urls": [{"url": "https://example.jp/a"}],
                "body_excerpt": "大丸下関店は2027年8月末に営業終了する。下関市。",
                "published_date": "2026-11-01", "event_date": "2027-08-31",
                "municipality": "下関市", "municipality_candidates": ["下関市"],
                "freshness": "直近30日", "status": "未確認・公開禁止",
            },
            {
                "id": "b", "title": "下関の大丸閉店",
                "category": ["閉店"], "source_url": "https://example.jp/b",
                "source_urls": [{"url": "https://example.jp/b"}],
                "body_excerpt": "大丸下関店（下関市竹崎町）が2027年8月末で閉店する。",
                "published_date": "2026-11-02", "event_date": "2027-08-31",
                "municipality": "下関市", "municipality_candidates": ["下関市"],
                "freshness": "直近30日", "status": "未確認・公開禁止",
            },
        ]
        summary = module.annotate_review_flags(drafts)
        self.assertEqual(len(drafts), 2)
        self.assertEqual(summary["duplicate_group_count"], 1)
        self.assertTrue(all(x["status"] == "未確認・公開禁止" for x in drafts))
        self.assertTrue(all(x.get("duplicate_review") == "重複の可能性・要確認" for x in drafts))


    def test_actual_daimaru_candidates_with_resolved_municipality_are_matched(self):
        article_a = {
            "title": "2026/11/06 11:00 【まとめ】来夏閉店の大丸下関店 最近の話題や直営化後の動き",
            "body_excerpt": "大丸下関店は６月３０日、２０２７年８月末に営業終了することを発表した。下関市役所で会見し、理由について説明。",
            "category": ["閉店", "リニューアル"],
            "event_date": "2027-08-31",
            "published_date": "2026-11-06T11:00:00+09:00",
            "municipality": "下関市",
            "municipality_candidates": ["下関市"],
        }
        article_b = {
            "title": "2026/07/01 06:00 大丸閉店「下関の象徴が」市民衝撃前田市長「影響最小限に抑える」",
            "body_excerpt": "戦後から昭和、平成、令和と三つの時代にわたって愛されてきた百貨店。JR下関駅前の一等地に位置する大丸下関店（下関市竹崎町）が２０２７年８月末で閉店する。",
            "category": ["閉店"],
            "event_date": "2027-08-31",
            "published_date": "2026-07-01T06:00:00+09:00",
            "municipality": "下関市",
            "municipality_candidates": ["下関市"],
        }
        self.assertTrue(module.same_store_news_candidate(article_a, article_b))

if __name__ == "__main__":
    unittest.main()
