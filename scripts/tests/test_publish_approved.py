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
  d={"municipality":"山口市","reviewed_at":"2026-10-29T10:00:00+09:00","reviewer_checked_source":True,"cleared_review_flags":["市町候補が複数"],"body":"確認済み本文"}
  d.update(kw); return d
 def setup(self,approved=True,review=None,draft=None,published=None):
  self.write("drafts.json",{"drafts":[draft or self.draft()]})
  self.write("publication_approvals.json",{"approved_ids":["abc"] if approved else [],"reviewed_articles":{"abc":self.review() if review is None else review} if approved else {}})
  self.write("published.json",published or {"updated_at":"","articles":[]})
 def published(self): return json.loads((self.base/"data/published.json").read_text(encoding="utf-8"))
 def test_approved_reviewed_publishes_even_status_unverified(self):
  self.setup(); self.run_script(); self.assertEqual(len(self.published()["articles"]),1); self.assertEqual(self.published()["articles"][0]["municipality"],"山口市")
 def test_unapproved_blocked(self):
  self.setup(approved=False); self.run_script(); self.assertEqual(self.published()["articles"],[])
 def test_no_review_record_blocked(self):
  self.setup(review={}); self.run_script(); self.assertEqual(self.published()["articles"],[])
 def test_unresolved_flag_blocked(self):
  self.setup(review=self.review(cleared_review_flags=[])); self.run_script(); self.assertEqual(self.published()["articles"],[])
 def test_missing_municipality_blocked(self):
  self.setup(review=self.review(municipality="")); self.run_script(); self.assertEqual(self.published()["articles"],[])
 def test_existing_articles_preserved_if_no_new_approved(self):
  old={"updated_at":"old","articles":[{"id":"old","title":"既存"}]}; self.setup(approved=False,published=old); self.run_script(); self.assertEqual(self.published()["articles"],old["articles"])
if __name__=="__main__": unittest.main()
