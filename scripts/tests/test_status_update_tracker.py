import sys
import unittest
from pathlib import Path

# Make scripts/ importable when unittest discovers tests from scripts/tests.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from status_update_tracker import find_possible_updates

class StatusUpdateTrackerTests(unittest.TestCase):
    def setUp(self):
        self.published = [{
            "id": "old1", "title": "【宇部市】「カフェ青空」が開店",
            "municipality": "宇部市", "business_status": "営業中",
            "source_url": "https://example.com/old"
        }]

    def test_same_store_same_city_flags_possible_closure(self):
        drafts = [{
            "id": "new1", "title": "【宇部市】「カフェ青空」が閉店",
            "municipality": "宇部市", "category": ["閉店"],
            "source_url": "https://example.com/new"
        }]
        result = find_possible_updates(drafts, self.published)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["published_id"], "old1")

    def test_different_city_does_not_match(self):
        drafts = [{
            "id": "new1", "title": "【山口市】「カフェ青空」が閉店",
            "municipality": "山口市", "category": ["閉店"],
            "source_url": "https://example.com/new"
        }]
        self.assertEqual(find_possible_updates(drafts, self.published), [])

    def test_different_store_does_not_match(self):
        drafts = [{
            "id": "new1", "title": "【宇部市】「別のカフェ」が閉店",
            "municipality": "宇部市", "category": ["閉店"],
            "source_url": "https://example.com/new"
        }]
        self.assertEqual(find_possible_updates(drafts, self.published), [])

    def test_opening_candidate_is_not_a_status_update(self):
        drafts = [{
            "id": "new1", "title": "【宇部市】「カフェ青空」が開店",
            "municipality": "宇部市", "category": ["新店・開店"],
            "source_url": "https://example.com/new"
        }]
        self.assertEqual(find_possible_updates(drafts, self.published), [])

    def test_same_source_url_is_ignored(self):
        drafts = [{
            "id": "new1", "title": "【宇部市】「カフェ青空」が閉店",
            "municipality": "宇部市", "category": ["閉店"],
            "source_url": "https://example.com/old"
        }]
        self.assertEqual(find_possible_updates(drafts, self.published), [])

if __name__ == "__main__":
    unittest.main()
