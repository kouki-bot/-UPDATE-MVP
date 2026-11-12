#!/usr/bin/env python3
"""Publish only records with current approval and all six human review checks."""
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
 draft_by_id={str(a.get("id")):a for a in drafts if a.get("id")}
 existing={str(a.get("id")):a for a in published.get("articles",[]) if a.get("id")}
 next_articles={}
 now=datetime.now(JST).isoformat()
 for aid in sorted(approved):
  # 候補一覧から外れた既存記事も、最新の承認記録で再照合する。
  draft=draft_by_id.get(aid) or existing.get(aid)
  if not draft: continue
  review=reviews.get(aid,{})
  excluded_types={"宿泊施設","観光・レジャー","公共・地域施設"}
  if draft.get("content_type") in excluded_types:
   print(f"公開保留 {aid}: 店舗サイトの対象外カテゴリ ({draft.get('content_type')})"); continue
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
  required_checks=("store_name_verified","municipality_verified","published_date_verified","event_date_verified","business_status_verified","source_url_verified")
  review_checks=review.get("review_checks",{})
  if not isinstance(review_checks,dict) or not all(review_checks.get(key) is True for key in required_checks):
   print(f"公開保留 {aid}: 必須の照合チェック6項目がすべて完了していません"); continue
  if not review.get("reviewed_at") or review.get("reviewer_checked_source") is not True:
   print(f"公開保留 {aid}: reviewed_at と reviewer_checked_source=true が必要"); continue
  if not valid_date(article.get("published_date")) or not valid_date(str(article.get("event_date",""))[:10]):
   print(f"公開保留 {aid}: 記事公開日または店舗動作日の日付形式が不正"); continue
  if article.get("business_status") not in ("開店予定","営業中","閉店予定","閉店済み","一時休業中","移転予定","移転済み","リニューアル予定","リニューアル済み"):
   print(f"公開保留 {aid}: 店舗の現在の状態が不正"); continue
  if not str(article.get("source_url","")).startswith(("https://","http://")):
   print(f"公開保留 {aid}: 元記事URLが不正"); continue
  article["review_flags"]=[]
  if article.get("business_status")=="一時休業中":
   article["category"]=["リニューアル"]
  article["municipality_status"]="確認済み"
  article["status"]="公開済み"
  article["approved_at"]=review["reviewed_at"]
  article["published_at"]=existing.get(aid,{}).get("published_at") or now
  article["body"]=article.get("body") or article.get("body_excerpt","")
  next_articles[aid]=article
  print(f"公開確認済み {aid}")
 old_articles=published.get("articles",[])
 sorted_articles=sorted(next_articles.values(),key=lambda a:(a.get("published_date",""),a.get("title","")),reverse=True)
 if sorted_articles != old_articles:
  published["updated_at"]=now
  published["articles"]=sorted_articles
  (DATA/"published.json").write_text(json.dumps(published,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
  print(f"公開データを更新: {len(sorted_articles)}件")
 else:
  print(f"公開データに変更なし: {len(sorted_articles)}件")
if __name__=="__main__": main()
