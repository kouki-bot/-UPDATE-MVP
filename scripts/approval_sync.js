(function(root,factory){
 var api=factory();
 if(typeof module==="object"&&module.exports)module.exports=api;
 else root.YLUApprovalSync=api;
})(typeof window!=="undefined"?window:this,function(){
 "use strict";
 function clone(value){return JSON.parse(JSON.stringify(value));}
 function validObject(value){return !!value&&typeof value==="object"&&!Array.isArray(value);}
 function timestamp(record){
  var value=record&&record.updated_at;
  if(!value&&record&&record.reviewed_at)value=record.reviewed_at;
  var parsed=Date.parse(String(value||""));
  return Number.isFinite(parsed)?parsed:null;
 }
 function sameContent(a,b){
  var left=clone(a||{}),right=clone(b||{});
  delete left.updated_at;delete right.updated_at;
  return JSON.stringify(left)===JSON.stringify(right);
 }
 function mergePrivateApprovals(remote,local,nowValue){
  if(!validObject(remote)||!Array.isArray(remote.approved_ids)||!validObject(remote.reviewed_articles))
   throw new Error("非公開側の承認データ形式が正しくありません");
  if(!validObject(local)||!Array.isArray(local.approved_ids)||!validObject(local.reviewed_articles))
   throw new Error("端末側の承認データ形式が正しくありません");
  var now=String(nowValue||new Date().toISOString()),nowMs=Date.parse(now);
  if(!Number.isFinite(nowMs))throw new Error("同期日時が不正です");
  var merged=clone(remote),conflicts=[],migratedCount=0;
  merged.reviewed_articles=merged.reviewed_articles||{};
  Object.keys(local.reviewed_articles).forEach(function(id){
   var localRecord=local.reviewed_articles[id],remoteRecord=merged.reviewed_articles[id];
   if(!remoteRecord){merged.reviewed_articles[id]=clone(localRecord);return;}
   if(!validObject(remoteRecord)||!validObject(localRecord))throw new Error("審査記録の形式が正しくありません："+id);
   var remoteTime=timestamp(remoteRecord),localTime=timestamp(localRecord);
   if(!remoteRecord.updated_at){
    remoteRecord.updated_at=remoteRecord.reviewed_at||now;
    remoteTime=timestamp(remoteRecord);
    migratedCount++;
   }
   var localIsNewer=localTime!==null&&remoteTime!==null&&localTime>remoteTime&&localTime<=nowMs+300000;
   if(localIsNewer)merged.reviewed_articles[id]=clone(localRecord);
   else if(!sameContent(localRecord,remoteRecord))conflicts.push(id);
  });
  Object.keys(merged.reviewed_articles).forEach(function(id){
   var record=merged.reviewed_articles[id];
   if(!record.updated_at){record.updated_at=record.reviewed_at||now;migratedCount++;}
  });
  var histories=merged.published_change_reviews||{},localHistories=local.published_change_reviews||{};
  Object.keys(localHistories).forEach(function(key){
   var current=histories[key]&&Array.isArray(histories[key].history)?histories[key].history:[];
   var incoming=Array.isArray(localHistories[key].history)?localHistories[key].history:[];
   var seen={};
   current.concat(incoming).forEach(function(item){
    var stamp=String(item.recorded_at||"")+"|"+JSON.stringify(item);
    seen[stamp]=item;
   });
   histories[key]=Object.assign({},histories[key]||{},localHistories[key]||{},{
    history:Object.keys(seen).sort().map(function(k){return seen[k];})
   });
  });
  merged.published_change_reviews=histories;
  merged.approved_ids=Object.keys(merged.reviewed_articles).filter(function(id){
   return merged.reviewed_articles[id]&&merged.reviewed_articles[id].review_status==="確認済み";
  }).sort();
  merged.description=remote.description||local.description||"人が確認した記事だけ公開許可する";
  return {approvals:merged,conflicts:conflicts,migratedCount:migratedCount};
 }
 return {mergePrivateApprovals:mergePrivateApprovals};
});
