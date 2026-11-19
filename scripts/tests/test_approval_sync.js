"use strict";
const assert=require("node:assert/strict");
const {mergePrivateApprovals}=require("../approval_sync.js");
function record(status,updatedAt,extra={}){
 const value=Object.assign({review_status:status},extra);
 if(updatedAt)value.updated_at=updatedAt;
 return value;
}
function store(rec){
 return {description:"review",approved_ids:rec.review_status==="確認済み"?["shop-1"]:[],reviewed_articles:{"shop-1":rec},published_change_reviews:{}};
}
{
 const remote=store(record("未確認","2026-11-19T10:00:00.000Z"));
 const local=store(record("確認済み","2026-11-19T09:00:00.000Z",{reviewed_at:"2026-11-19T09:00:00.000Z"}));
 const result=mergePrivateApprovals(remote,local,"2026-11-19T11:00:00.000Z");
 assert.equal(result.approvals.reviewed_articles["shop-1"].review_status,"未確認");
 assert.deepEqual(result.approvals.approved_ids,[]);
 assert.deepEqual(result.conflicts,["shop-1"]);
}
{
 const remote=store(record("未確認","2026-11-19T09:00:00.000Z"));
 const local=store(record("確認済み","2026-11-19T10:00:00.000Z",{reviewed_at:"2026-11-19T10:00:00.000Z"}));
 const result=mergePrivateApprovals(remote,local,"2026-11-19T11:00:00.000Z");
 assert.equal(result.approvals.reviewed_articles["shop-1"].review_status,"確認済み");
 assert.deepEqual(result.approvals.approved_ids,["shop-1"]);
}
{
 const remote=store(record("未確認",null));
 const local=store(record("確認済み","2026-11-19T10:30:00.000Z"));
 const result=mergePrivateApprovals(remote,local,"2026-11-19T11:00:00.000Z");
 assert.equal(result.approvals.reviewed_articles["shop-1"].review_status,"未確認");
 assert.equal(result.approvals.reviewed_articles["shop-1"].updated_at,"2026-11-19T11:00:00.000Z");
 assert.equal(result.migratedCount,1);
}
{
 const remote={description:"review",approved_ids:[],reviewed_articles:{},published_change_reviews:{}};
 const local={description:"review",approved_ids:["new"],reviewed_articles:{new:record("確認済み","2026-11-19T10:00:00.000Z")},published_change_reviews:{}};
 const result=mergePrivateApprovals(remote,local,"2026-11-19T11:00:00.000Z");
 assert.deepEqual(result.approvals.approved_ids,["new"]);
 assert.equal(result.approvals.reviewed_articles.new.review_status,"確認済み");
}
{
 const remote=store(record("確認済み","2026-11-19T09:00:00.000Z"));
 const local=store(record("確認済み","2026-11-19T09:00:00.000Z"));
 const result=mergePrivateApprovals(remote,local,"2026-11-19T11:00:00.000Z");
 assert.deepEqual(result.conflicts,[]);
 assert.deepEqual(result.approvals.approved_ids,["shop-1"]);
}
console.log("Approval sync conflict and revocation safety tests passed.");
