import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PANEL = (ROOT / "admin" / "review.html").read_text(encoding="utf-8")
PUBLISHER = (ROOT / "scripts" / "publish_approved.py").read_text(encoding="utf-8")


class TestPublicationReadinessPanelAlignment(unittest.TestCase):
    def test_panel_uses_publisher_review_status_and_source_attestation(self):
        self.assertIn("r.review_status==='確認済み'", PANEL)
        self.assertIn("r.reviewer_checked_source===true", PANEL)
        self.assertIn('review.get("review_status") != "確認済み"', PUBLISHER)
        self.assertIn('review.get("reviewer_checked_source") is not True', PUBLISHER)

    def test_panel_uses_business_status_from_review_or_draft(self):
        self.assertIn("r.business_status||d.business_status||''", PANEL)
        self.assertIn('"business_status"', PUBLISHER)

    def test_panel_requires_all_six_review_checks(self):
        for key in (
            "store_name_verified",
            "municipality_verified",
            "published_date_verified",
            "event_date_verified",
            "business_status_verified",
            "source_url_verified",
        ):
            self.assertIn(key, PANEL)
            self.assertIn(key, PUBLISHER)

    def test_panel_keeps_new_article_link_checks_and_existing_article_exception(self):
        self.assertIn("existing?true:linksOk", PANEL)
        self.assertIn("if aid not in existing:", PUBLISHER)
        self.assertIn('checked.get(url)!="ok"', PUBLISHER)

    def test_panel_does_not_treat_suggested_headline_as_final_title(self):
        self.assertIn("r.headline||d.title||''", PANEL)
        self.assertNotIn("r.headline||d.suggested_headline||d.title||''", PANEL)

    def test_panel_date_validation_rejects_impossible_calendar_dates(self):
        self.assertIn("calendarDate.getFullYear()!==year", PANEL)
        self.assertIn("calendarDate.getMonth()!==month-1", PANEL)
        self.assertIn("calendarDate.getDate()!==day", PANEL)

    def test_panel_uses_case_sensitive_http_scheme_like_publisher(self):
        self.assertIn("/^https?:\\/\\//.test(sourceUrl)", PANEL)
        self.assertNotIn("/^https?:\\/\\//i.test(sourceUrl)", PANEL)
        self.assertIn('startswith(("https://","http://"))', PUBLISHER)


if __name__ == "__main__":
    unittest.main()
