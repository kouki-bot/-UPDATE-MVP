import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

class PublicDisplaySafetyTests(unittest.TestCase):
    def test_all_public_lists_require_full_approval(self):
        required = [
            'approved_at',
            'Array.isArray(',
            'review_flags',
            'length===0',
            'source_url',
        ]
        for filename in ('index.html', 'new.html', 'closed.html'):
            source = (ROOT / filename).read_text(encoding='utf-8')
            with self.subTest(filename=filename):
                for token in required:
                    self.assertIn(token, source, f'{filename} missing {token}')
                self.assertRegex(source, r"status\\s*===\\s*['\\"]公開['\\"]")
                self.assertRegex(source, r"status\\s*===\\s*['\\"]公開済み['\\"]")

    def test_homepage_detail_links_are_not_hardcoded(self):
        source = (ROOT / 'index.html').read_text(encoding='utf-8')
        self.assertNotIn('const detailPageIds=new Set(', source)
        self.assertIn('encodeURIComponent(article.id)', source)

if __name__ == '__main__':
    unittest.main()
