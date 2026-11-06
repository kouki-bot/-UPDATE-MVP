#!/usr/bin/env python3
"""Publish manually approved drafts without losing approvals during regeneration."""
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone
BASE_DIR=Path(__file__).resolve().parent.parent
DATA=BASE_DIR/"data"
JST=timezone(timedelta(hours=9))
def load(name, default):
 p=DATA/name
 return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default
def valid_date(value):
 try:
  text=str(value or "").strip()
  if not text: return False
  datetime.fromisoformat(text.replace("Z","+00:00"))
  return True
 except (TypeError,ValueError):
  return False
def main():
 drafts=load("drafts.json",{"drafts":[]}).get("drafts",[])
 approvals=load("publication_approvals.json",{"approved_ids":[],"reviewed_articles":{}})
 published=load("published.json",{"updated_at":"","articles":[]})
 approved=set(map(str,approvals.get("approved_ids",[])))
 reviews=approvals.get("reviewed_articles",{})
 existing={str(a.get("id")):a for a in published.get("articles",[]) if a.get("id")}
 added=0
 for draft in drafts:
  aid=str(draft.get("id",""))
  if not aid or aid not in approved: continue
  review=reviews.get(aid,{})
  # 下書き段階で明示された記事公開日が不正なら、承認データの上書きで隠さず公開を止める。
  if draft.get("published_date") not in (None,"") and not valid_date(draft.get("published_date")):
   print(f"公開保留 {aid}: 下書きの記事公開日が不正。元情報を再確認してください"); continue
  article=dict(draft)
  for key in ("municipality","body","published_date","event_date","business_status","source_url","title"):
   if review.get(key) not in (None,""): article[key]=review[key]
  if review.get("headline"): article["title"]=review["headline"]
  missing=[k for k in ("title","source_url","published_date","event_date","business_status","municipality") if not str(article.get(k,"")).strip()]
  flags=set(draft.get("review_flags") or [])-set(review.get("cleared_review_flags") or [])
  if missing:
   print(f"公開保留 {aid}: 必須項目不足 {', '.join(missing)}"); continue
  if flags:
   print(f"公開保留 {aid}: 未解消フラグ {', '.join(sorted(flags))}"); continue
  if draft.get("duplicate_review")=="重複の可能性・要確認" and review.get("duplicate_resolution")!="別記事として掲載":
   print(f"公開保留 {aid}: 重複候補の確認結果が未確定または同一ニュース"); continue
  if draft.get("freshness") in ("未来日付・要確認","90日より前"):
   print(f"公開保留 {aid}: 日付・鮮度の確認が必要"); continue
  if review.get("review_status") != "確認済み":
   print(f"公開保留 {aid}: review_status=確認済み が必要"); continue
  if not review.get("reviewed_at") or review.get("reviewer_checked_source") is not True:
   print(f"公開保留 {aid}: reviewed_at と reviewer_checked_source=true が必要"); continue
  if not valid_date(article.get("published_date")) or not valid_date(str(article.get("event_date",""))[:10]):
   print(f"公開保留 {aid}: 記事公開日または店舗動作日の日付形式が不正"); continue
  if article.get("business_status") not in ("開店予定","営業中","閉店済み","移転済み","リニューアル済み"):
   print(f"公開保留 {aid}: 店舗の現在の状態が不正"); continue
  if not str(article.get("source_url","")).startswith(("https://","http://")):
   print(f"公開保留 {aid}: 元記事URLが不正"); continue
  article["status"]="公開済み"
  article["approved_at"]=review["reviewed_at"]
  article["published_at"]=datetime.now(JST).isoformat()
  article["body"]=article.get("body") or article.get("body_excerpt","")
  existing[aid]=article; added+=1
 if added:
  published["updated_at"]=datetime.now(JST).isoformat()
  published["articles"]=sorted(existing.values(),key=lambda a:(a.get("published_date",""),a.get("title","")),reverse=True)
  (DATA/"published.json").write_text(json.dumps(published,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 print(f"公開候補として反映: {added}件")
 if not added: print("公開可能な承認済み記事がないため published.json は変更していません。")
if __name__=="__main__": main()
