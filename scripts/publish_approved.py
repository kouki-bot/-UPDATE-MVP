#!/usr/bin/env python3
"""Publish only records with current approval and all six human review checks.

Rebuild all approved public records from the latest private review snapshot, including newly reviewed store updates and regional shop openings, including Ube and Ajisu updates.
"""
import json
import math
import os
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
 approved_raw=approvals.get("approved_ids")
 reviews=approvals.get("reviewed_articles")
 if not isinstance(approved_raw,list) or not isinstance(reviews,dict):
  raise SystemExit("承認データの形式が不正です。公開処理を中止しました")
 approved_list=[str(value).strip() for value in approved_raw]
 if any(not value for value in approved_list) or len(set(approved_list))!=len(approved_list):
  raise SystemExit("承認IDに空欄または重複があります。公開処理を中止しました")
 approved=set(approved_list)
 draft_by_id={str(a.get("id")):a for a in drafts if isinstance(a,dict) and a.get("id")}
 existing={str(a.get("id")):a for a in published.get("articles",[]) if isinstance(a,dict) and a.get("id")}
 allow_bulk_withdrawal=os.environ.get("ALLOW_BULK_WITHDRAWAL","").strip().lower()=="true"
 if existing and not approved and not allow_bulk_withdrawal:
  raise SystemExit("承認IDが0件ですが公開済み記事があります。承認データ欠落の可能性があるため公開・一括削除を中止しました。意図的な全件取り下げの場合のみ手動実行で ALLOW_BULK_WITHDRAWAL=true を指定してください")
 missing_records=sorted(aid for aid in approved if not isinstance(reviews.get(aid),dict))
 if missing_records:
  raise SystemExit("承認IDに対応する審査記録がありません: "+", ".join(missing_records[:10]))
 unknown_ids=sorted(aid for aid in approved if aid not in draft_by_id and aid not in existing)
 if unknown_ids:
  raise SystemExit("候補・公開済みデータのどちらにも存在しない承認IDがあります: "+", ".join(unknown_ids[:10]))
 removed_ids=set(existing)-approved
 removal_limit=max(3,math.ceil(len(existing)*0.25))
 if len(removed_ids)>removal_limit and not allow_bulk_withdrawal:
  raise SystemExit(
   f"公開済み記事 {len(existing)}件中 {len(removed_ids)}件の一括取り下げを検出しました。"
   f"安全上限（{removal_limit}件）を超えたため公開処理を中止しました。"
   "意図的な一括取り下げの場合のみ手動実行で ALLOW_BULK_WITHDRAWAL=true を指定してください"
  )
 next_articles={}
 now=datetime.now(JST).isoformat()
 for aid in sorted(approved):
  # 候補一覧から外れた既存記事も、最新の承認記録で再照合する。
  draft=draft_by_id.get(aid) or existing.get(aid)
  if not draft: continue
  review=reviews.get(aid,{})
  # 店舗情報サイトの対象カテゴリ以外は、承認済みでも公開しない。
  if draft.get("content_type") != "店舗・商業施設":
   print(f"公開保留 {aid}: 店舗サイトの対象外または未分類カテゴリ ({draft.get('content_type')})"); continue
  # 追加確認フラグは、通常の承認操作だけでは解除できない。
  if draft.get("manual_hold") is True:
   print(f"公開保留 {aid}: manual_hold=true（追加確認が必要）"); continue
  if draft.get("published_date") not in (None,"") and not valid_date(draft.get("published_date")):
   print(f"公開保留 {aid}: 下書きの記事公開日が不正。元情報を再確認してください"); continue
  article=dict(draft)
  for key in ("municipality","body","published_date","event_date","business_status","source_url","title"):
   if review.get(key) not in (None,""): article[key]=review[key]
  # Photo data is copied only from the human review record after explicit rights approval.
  photo_fields=("image_url","image_source_url","image_credit","image_rights_status","image_type","image_permission_note","image_usage_approved")
  for key in photo_fields: article.pop(key,None)
  image_url=str(review.get("image_url") or "").strip()
  image_source_url=str(review.get("image_source_url") or "").strip()
  image_credit=str(review.get("image_credit") or "").strip()
  image_rights_status=review.get("image_rights_status")
  image_type=review.get("image_type")
  image_permission_note=str(review.get("image_permission_note") or "").strip()
  photo_approved=(
   review.get("image_usage_approved") is True
   and image_url.startswith(("https://","http://"))
   and image_source_url.startswith(("https://","http://"))
   and bool(image_credit)
   and image_rights_status in ("許可確認済み","利用条件確認済み")
   and image_type in ("provided","official")
   and bool(image_permission_note)
  )
  if photo_approved:
   article.update({
    "image_url":image_url,"image_source_url":image_source_url,
    "image_credit":image_credit,"image_rights_status":image_rights_status,
    "image_type":image_type,"image_permission_note":image_permission_note,
    "image_usage_approved":True
   })
  # Public area filters must use only the human-confirmed store municipality.
  # Candidate extraction may include neighboring cities from regional source names.
  municipality=str(article.get("municipality") or "").strip()
  if municipality:
   article["area"]=[municipality]
   article["municipality_group"]=municipality
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
  # 新規公開記事は、直近7日以内の人による再確認と、全出典URLの正常確認を必須にする。
  if aid not in existing:
   try:
    reviewed_at=datetime.fromisoformat(str(review.get("reviewed_at","")).replace("Z","+00:00"))
    if reviewed_at.tzinfo is None: reviewed_at=reviewed_at.replace(tzinfo=JST)
    review_age=(datetime.now(JST)-reviewed_at.astimezone(JST)).total_seconds()
   except (TypeError,ValueError):
    print(f"公開保留 {aid}: 再確認日時が不正"); continue
   if review_age < 0 or review_age > 7*24*60*60:
    print(f"公開保留 {aid}: 人による最終確認から7日を超過"); continue
   link_checks=draft.get("source_link_checks")
   if not isinstance(link_checks,list) or not link_checks:
    print(f"公開保留 {aid}: 出典URLのリンク確認記録がありません"); continue
   checked={str(row.get("url") or "").strip():row.get("status") for row in link_checks if isinstance(row,dict)}
   required_urls={str(draft.get("source_url") or "").strip()}
   extra_sources=draft.get("source_urls",[])
   if isinstance(extra_sources,list):
    required_urls.update(str(row.get("url") or "").strip() for row in extra_sources if isinstance(row,dict) and row.get("url"))
   required_urls.discard("")
   if not required_urls or any(checked.get(url)!="ok" for url in required_urls):
    print(f"公開保留 {aid}: 主出典・追加出典のすべてで正常なURL確認が必要"); continue
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
  if article.get("business_status")=="一時休業中":
   categories=article.get("category",[])
   if isinstance(categories,str): categories=[categories]
   article["category"]=[c for c in categories if c!="閉店"]
   if "リニューアル" not in article["category"]: article["category"].append("リニューアル")
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
