import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "publish_approved.py"
spec = importlib.util.spec_from_file_location("publish_approved", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def good_article(**overrides):
    article = {
        "id": "ok-1",
        "title": "【開店】確認済み店舗",
        "category": ["新店・開店"],
        "source_url": "https://example.com/article",
        "source_urls": [{"url": "https://example.com/article"}],
        "body_excerpt": "公式発表で確認した内容",
        "published_date": "2026-10-01",
        "municipality": "山口市",
        "review_flags": [],
        "duplicate_review": "",
        "status": "公開許可",
    }
    article.update(overrides)
    return article

class PublishApprovedTests(unittest.TestCase):
    def test_explicitly_approved_complete_article_can_pass(self):
        article = good_article()
        self.assertTrue(module.is_publishable(article, {"ok-1"}))

    def test_unapproved_article_is_blocked(self):
        self.assertFalse(module.is_publishable(good_article(), set()))

    def test_unverified_status_is_blocked_even_if_approved(self):
        article = good_article(status="未確認・公開禁止")
        self.assertFalse(module.is_publishable(article, {"ok-1"}))

    def test_duplicate_review_is_blocked(self):
        article = good_article(duplicate_review="重複の可能性・要確認")
        self.assertFalse(module.is_publishable(article, {"ok-1"}))

    def test_missing_source_is_blocked(self):
        article = good_article(source_url="")
        self.assertFalse(module.is_publishable(article, {"ok-1"}))

    def test_review_flags_block_publication(self):
        article = good_article(review_flags=["公開日未確認"])
        self.assertFalse(module.is_publishable(article, {"ok-1"}))

if __name__ == "__main__":
    unittest.main()
