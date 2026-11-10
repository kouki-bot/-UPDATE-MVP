import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "track_published_changes.py"
spec = importlib.util.spec_from_file_location("track_published_changes", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PublishedStoreChangeTests(unittest.TestCase):
    def article(self, id, title, category, town="宇部市", url="https://example.jp/a", status="営業中"):
        return {
            "id": id, "title": title, "category": category,
            "municipality": town, "municipality_candidates": [town],
            "source_url": url, "business_status": status,
            "body_excerpt": f"{town}にある{title}",
        }

    def test_closure_for_published_opening_is_flagged(self):
        published = [self.article("old", "カフェ青空店が宇部市にオープン", ["新店・開店"])]
        drafts = [self.article("new", "宇部市のカフェ青空店が閉店", ["閉店"],
                               url="https://example.jp/b", status="未確認・公開禁止")]
        alerts = module.find_status_changes(drafts, published)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["candidate_status"], "閉店")

    def test_same_store_different_city_is_not_flagged(self):
        published = [self.article("old", "カフェ青空店が宇部市にオープン", ["新店・開店"])]
        drafts = [self.article("new", "カフェ青空店が下関市で閉店", ["閉店"],
                               town="下関市", url="https://example.jp/b")]
        self.assertEqual(module.find_status_changes(drafts, published), [])

    def test_different_store_same_city_is_not_flagged(self):
        published = [self.article("old", "カフェ青空店が宇部市にオープン", ["新店・開店"])]
        drafts = [self.article("new", "カフェ木漏れ日店が宇部市で閉店", ["閉店"],
                               url="https://example.jp/b")]
        self.assertEqual(module.find_status_changes(drafts, published), [])

    def test_same_source_url_is_not_flagged(self):
        published = [self.article("old", "カフェ青空店が宇部市にオープン", ["新店・開店"])]
        drafts = [self.article("new", "カフェ青空店が宇部市で閉店", ["閉店"])]
        self.assertEqual(module.find_status_changes(drafts, published), [])

    def test_same_status_category_is_not_flagged(self):
        published = [self.article("old", "カフェ青空店が宇部市で閉店", ["閉店"])]
        drafts = [self.article("new", "カフェ青空店が宇部市で閉店", ["閉店"],
                               url="https://example.jp/b")]
        self.assertEqual(module.find_status_changes(drafts, published), [])

    def test_unknown_municipality_is_not_matched(self):
        published = [self.article("old", "カフェ青空店が宇部市にオープン", ["新店・開店"])]
        candidate = self.article("new", "カフェ青空店が閉店", ["閉店"],
                                 url="https://example.jp/b")
        candidate["municipality"] = ""
        candidate["municipality_candidates"] = []
        self.assertEqual(module.find_status_changes([candidate], published), [])


if __name__ == "__main__":
    unittest.main()
