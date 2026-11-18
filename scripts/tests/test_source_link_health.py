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

    def test_check_sources_deduplicates_urls(self):
        sources = [
            {"url": "https://example.jp/a"},
            {"url": "https://example.jp/a"},
            {"url": "https://example.jp/b"},
        ]
        calls = []
        def checker(url):
            calls.append(url)
            return {"url": url, "status": "ok", "http_status": 200}
        results = module.check_sources(sources, checker=checker)
        self.assertEqual(calls, ["https://example.jp/a", "https://example.jp/b"])
        self.assertEqual(len(results), 2)

    def test_annotates_each_candidate_with_link_status(self):
        drafts = [{
            "title": "店舗A",
            "source_url": "https://example.jp/main",
            "source_name": "記事",
            "source_urls": [{"source_name": "公式", "url": "https://example.jp/official"}],
        }]
        results = {
            "https://example.jp/main": {"url": "https://example.jp/main", "status": "ok", "http_status": 200},
            "https://example.jp/official": {"url": "https://example.jp/official", "status": "broken", "http_status": 404},
        }
        module.annotate_draft_source_checks(drafts, results)
        checks = drafts[0]["source_link_checks"]
        self.assertEqual([x["status"] for x in checks], ["ok", "broken"])
        self.assertEqual(checks[1]["http_status"], 404)

    def test_missing_result_is_marked_not_checked_not_broken(self):
        drafts = [{"source_url": "https://example.jp/not-checked"}]
        module.annotate_draft_source_checks(drafts, {})
        check = drafts[0]["source_link_checks"][0]
        self.assertEqual(check["status"], "not_checked_limit")
        self.assertIsNone(check["http_status"])

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