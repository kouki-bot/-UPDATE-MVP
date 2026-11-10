import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from io import BytesIO

SCRIPT = Path(__file__).resolve().parents[1] / 'check_source_links.py'
spec = importlib.util.spec_from_file_location('check_source_links', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class SourceLinkHealthTests(unittest.TestCase):
    def test_collect_urls_deduplicates_and_ignores_invalid(self):
        rows = [{'source_url': 'https://example.jp/a'}, {'source_url': 'https://example.jp/a'}, {'source_url': 'javascript:alert(1)'}, {'source_url': 'http://example.jp/b'}]
        self.assertEqual(module.collect_urls(rows), ['https://example.jp/a', 'http://example.jp/b'])

    def test_404_is_broken(self):
        def opener(*args, **kwargs):
            raise HTTPError('https://example.jp/x', 404, 'Not Found', {}, None)
        result = module.check_url('https://example.jp/x', opener=opener)
        self.assertEqual(result['status'], 'broken')

    def test_403_is_inconclusive_not_broken(self):
        def opener(*args, **kwargs):
            raise HTTPError('https://example.jp/x', 403, 'Forbidden', {}, None)
        result = module.check_url('https://example.jp/x', opener=opener)
        self.assertEqual(result['status'], 'inconclusive')

    def test_200_is_ok(self):
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def getcode(self): return 200
        result = module.check_url('https://example.jp/x', opener=lambda *a, **k: Response())
        self.assertEqual(result['status'], 'ok')

if __name__ == '__main__':
    unittest.main()