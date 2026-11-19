import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PUBLISHER = ROOT / "scripts" / "publish_approved.py"
SEO_BUILDER = ROOT / "scripts" / "build_seo_pages.py"

class PublicationPipelineIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        (self.base / "scripts").mkdir()
        (self.base / "data").mkdir()
        (self.base / "articles").mkdir()
        shutil.copy2(PUBLISHER, self.base / "scripts" / "publish_approved.py")
        shutil.copy2(SEO_BUILDER, self.base / "scripts" / "build_seo_pages.py")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, value):
        (self.base / "data" / name).write_text(
            json.dumps(value, ensure_ascii=False), encoding="utf-8"
        )

    def run_script(self, name):
        return subprocess.run(
            [sys.executable, str(self.base / "scripts" / name)],
            cwd=self.base, capture_output=True, text=True
        )

    def test_only_human_approved_article_reaches_seo_and_withdrawal_removes_page(self):
        now = datetime.now(timezone(timedelta(hours=9))).isoformat()
        review = {
            "review_status": "確認済み",
            "headline": "山口店 <script>alert(1)</script>",
            "municipality": "山口市",
            "published_date": "2026-11-19",
            "event_date": "2026-11-20",
            "business_status": "営業中",
            "reviewed_at": now,
            "reviewer_checked_source": True,
            "review_checks": {
                "store_name_verified": True,
                "municipality_verified": True,
                "published_date_verified": True,
                "event_date_verified": True,
                "business_status_verified": True,
                "source_url_verified": True,
            },
            "cleared_review_flags": [],
            "body": "確認済みの店舗情報",
        }
        approved = {
            "id": "approved-1",
            "title": "山口店の開店",
            "category": ["新店・開店"],
            "content_type": "店舗・商業施設",
            "source_name": "公式情報",
            "source_url": "https://example.com/store",
            "source_urls": [{"source_name": "公式情報", "url": "https://example.com/store"}],
            "source_link_checks": [{
                "url": "https://example.com/store", "status": "ok", "http_status": 200
            }],
            "published_date": "2026-11-19",
            "event_date": "2026-11-20",
            "business_status": "営業中",
            "municipality": "山口市",
            "status": "未確認・公開禁止",
            "freshness": "直近30日",
            "review_flags": [],
            "body_excerpt": "候補本文",
        }
        unapproved = dict(approved, id="unapproved-2", title="未承認店")
        self.write("drafts.json", {"drafts": [approved, unapproved]})
        self.write("publication_approvals.json", {
            "approved_ids": ["approved-1"],
            "reviewed_articles": {"approved-1": review},
        })
        self.write("published.json", {"updated_at": "", "articles": []})

        published = self.run_script("publish_approved.py")
        self.assertEqual(published.returncode, 0, published.stderr)
        rows = json.loads((self.base / "data" / "published.json").read_text(encoding="utf-8"))["articles"]
        self.assertEqual([row["id"] for row in rows], ["approved-1"])

        seo = self.run_script("build_seo_pages.py")
        self.assertEqual(seo.returncode, 0, seo.stderr)
        page = self.base / "articles" / "approved-1.html"
        self.assertTrue(page.exists())
        html = page.read_text(encoding="utf-8")
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertNotIn("unapproved-2", (self.base / "sitemap.xml").read_text(encoding="utf-8"))

        # A single deliberate revocation remains possible; generated SEO output is withdrawn too.
        self.write("publication_approvals.json", {"approved_ids": [], "reviewed_articles": {}})
        withdrawn = self.run_script("publish_approved.py")
        self.assertEqual(withdrawn.returncode, 0, withdrawn.stderr)
        seo_after = self.run_script("build_seo_pages.py")
        self.assertEqual(seo_after.returncode, 0, seo_after.stderr)
        self.assertFalse(page.exists())
        sitemap = (self.base / "sitemap.xml").read_text(encoding="utf-8")
        self.assertNotIn("approved-1.html", sitemap)

if __name__ == "__main__":
    unittest.main()
