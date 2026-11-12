import json, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path
SOURCE=Path(__file__).resolve().parents[1]/"publish_approved.py"
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.base=Path(self.tmp.name)
  (self.base/"scripts").mkdir(); (self.base/"data").mkdir()
  shutil.copy2(SOURCE,self.base/"scripts/publish_approved.py")
 def tearDown(self): self.tmp.cleanup()
 def write(self,n,d): (self.base/"data"/n).write_text(json.dumps(d,ensure_ascii=False),encoding="utf-8")
 def run_script(self): return subprocess.run([sys.executable,str(self.base/"scripts/publish_approved.py")],capture_output=True,text=True)
 def draft(self,**kw):
  d={"id":"abc","title":"山口店開店","source_url":"https://example.com","published_date":"2026-10-28","municipality":"","status":"未確認・公開禁止","freshness":"直近30日","review_flags":["市町候補が複数"],"body_excerpt":"抜粋"}
  d.update(kw); return d
 def review(self,**kw):
  d={"review_status":"確認済み","municipality":"山口市","published_date":"2026-10-28","event_date":"2026-10-30","business_status":"営業中","reviewed_at":"2026-10-29T10:00:00+09:00","reviewer_checked_source":True,"review_checks":{"store_name_verified":True,"municipality_verified":True,"published_date_verified":True,"event_date_verified":True,"business_status_verified":True,"source_url_verified":True},"cleared_review_flags":["市町候補が複数"],"body":"確認済み本文"}
  d.update(kw); return d
 def setup(self,approved=True,review=None,draft=None,published=None):
  self.write("drafts.json",{"drafts":[draft or self.draft()]})
  self.write("publication_approvals.json",{"approved_ids":["abc"] if approved else [],"reviewed_articles":{"abc":self.review() if review is None else review} if approved else {}})
  self.write("published.json",published or {"updated_at":"","articles":[]})
 def published(self): return json.loads((self.base/"data/published.json").read_text(encoding="utf-8"))
 def test_approved_reviewed_publishes_even_status_unverified(self):
  self.setup(); result=self.run_script(); self.assertEqual(result.returncode,0,result.stderr); self.assertEqual(len(self.published()["articles"]),1); self.assertEqual(self.published()["articles"][0]["municipality"],"山口市"); self.assertEqual(self.published()["articles"][0]["event_date"],"2026-10-30"); self.assertEqual(self.published()["articles"][0]["business_status"],"営業中"); self.assertEqual(self.published()["articles"][0]["review_flags"],[]); self.assertEqual(self.published()["articles"][0]["municipality_status"],"確認済み")
 def test_future_closure_can_publish_as_planned(self):
  self.setup(review=self.review(event_date="2027-08-31",business_status="閉店予定"))
  result=self.run_script()
  self.assertEqual(result.returncode,0,result.stderr)
  self.assertEqual(self.published()["articles"][0]["business_status"],"閉店予定")
 def test_future_relocation_can_publish_as_planned(self):
  self.setup(review=self.review(event_date="2026-12-15",business_status="移転予定"))
  result=self.run_script()
  self.assertEqual(result.returncode,0,result.stderr)
  self.assertEqual(self.published()["articles"][0]["business_status"],"移転予定")
 def test_future_renovation_can_publish_as_planned(self):
  self.setup(review=self.review(event_date="2026-12-15",business_status="リニューアル予定"))
  result=self.run_script()
  self.assertEqual(result.returncode,0,result.stderr)
  self.assertEqual(self.published()["articles"][0]["business_status"],"リニューアル予定")
 def test_lodging_is_blocked_even_if_approved(self):
  self.setup(draft=self.draft(content_type="宿泊施設"))
  self.run_script()
  self.assertEqual(self.published()["articles"],[])
 def test_tourism_is_blocked_even_if_approved(self):
  self.setup(draft=self.draft(content_type="観光・レジャー"))
  self.run_script()
  self.assertEqual(self.published()["articles"],[])
 def test_unapproved_blocked(self):
  self.setup(approved=False); self.run_script(); self.assertEqual(self.published()["articles"],[])
 def test_no_review_record_blocked(self):
  self.setup(review={}); self.run_script(); self.assertEqual(self.published()["articles"],[])
 def test_missing_review_check_blocks_publication(self):
  checks=self.review()["review_checks"]; checks["event_date_verified"]=False
  self.setup(review=self.review(review_checks=checks)); self.run_script()
  self.assertEqual(self.published()["articles"],[])
 def test_missing_review_checks_block_publication(self):
  review=self.review(); review.pop("review_checks")
  self.setup(review=review); self.run_script()
  self.assertEqual(self.published()["articles"],[])
 def test_all_six_review_checks_allow_publication(self):
  self.setup(); result=self.run_script()
  self.assertEqual(result.returncode,0,result.stderr)
  self.assertEqual(len(self.published()["articles"]),1)
 def test_unresolved_flag_blocked(self):
  self.setup(review=self.review(cleared_review_flags=[])); self.run_script(); self.assertEqual(self.published()["articles"],[])
 def test_missing_municipality_blocked(self):
  self.setup(review=self.review(municipality="")); self.run_script(); self.assertEqual(self.published()["articles"],[])
 def test_existing_articles_preserved_if_no_new_approved(self):
  old={"updated_at":"old","articles":[{"id":"old","title":"既存"}]}; self.setup(approved=False,published=old); self.run_script(); self.assertEqual(self.published()["articles"],old["articles"])
 def test_temporary_closure_status_can_publish(self):
  self.setup(review=self.review(event_date="2026-12-15",business_status="一時休業中"))
  result=self.run_script()
  self.assertEqual(result.returncode,0,result.stderr)
  self.assertEqual(self.published()["articles"][0]["business_status"],"一時休業中")

 def test_existing_approved_article_is_rechecked_without_current_draft(self):
  existing=self.draft(municipality="旧データ",municipality_status="要確認",review_flags=["古いフラグ"],status="公開済み")
  self.setup(published={"updated_at":"old","articles":[existing]})
  self.write("drafts.json",{"drafts":[]})
  result=self.run_script()
  self.assertEqual(result.returncode,0,result.stderr)
  article=self.published()["articles"][0]
  self.assertEqual(article["municipality"],"山口市")
  self.assertEqual(article["municipality_status"],"確認済み")
  self.assertEqual(article["review_flags"],[])
 def test_revoked_approval_removes_existing_public_article(self):
  existing=self.draft(status="公開済み")
  self.setup(approved=False,published={"updated_at":"old","articles":[existing]})
  result=self.run_script()
  self.assertEqual(result.returncode,0,result.stderr)
  self.assertEqual(self.published()["articles"],[])
if __name__=="__main__": unittest.main()
