"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const page = fs.readFileSync("admin/review.html", "utf8");

function requireText(value, label) {
  assert.ok(page.includes(value), "Missing security safeguard: " + label);
}

// Token entry and handling: transient password input, memory-only use, and clearing.
requireText('id="privateSyncToken" type="password" autocomplete="off"', "password token field");
requireText('var privateSyncToken="";', "in-memory token variable");
requireText('"Authorization":"Bearer "+privateSyncToken', "Bearer authorization header");
requireText('fetch("https://api.github.com"+path', "HTTPS GitHub API origin");
assert.equal((page.match(/el\("privateSyncToken"\)\.value="";privateSyncToken="";/g) || []).length, 4,
  "Token must be cleared after each load/save success and failure path");
assert.ok(!/localStorage\.(?:setItem|getItem)\([^\n)]*privateSyncToken/.test(page),
  "Token must never be read from or written to localStorage");
assert.ok(!/sessionStorage\.(?:setItem|getItem)\([^\n)]*privateSyncToken/.test(page),
  "Token must never be read from or written to sessionStorage");

// Validate URLs before using source-provided links.
requireText('u.protocol==="https:"||u.protocol==="http:"', "HTTP(S)-only URL validation");
requireText('target="_blank" rel="noopener noreferrer"', "safe new-tab link attributes");

// Dynamic values interpolated into HTML must pass through the escaping helper.
requireText('var esc=function(v){return String(v==null?"":v).replace(/[&<>"\']/g', "HTML escaping helper");
[
  'esc(row.title||"タイトル未設定")',
  'esc(row.exclusion_reason||"理由不明")',
  'esc(row.source_name||"情報元不明")',
  'esc(row.body_excerpt||"本文抜粋なし")',
  'esc(d.title||"タイトル未設定")',
  'esc(d.municipality||d.municipality_group||"地域未特定")',
  'esc(d.body_excerpt||"本文抜粋なし。元記事を直接確認してください。")',
  'esc(r.headline||d.suggested_headline||d.title||"")',
  'esc(r.image_permission_note||"")'
].forEach((value) => requireText(value, "escaped dynamic HTML value: " + value));

console.log("Admin token handling and untrusted rendering regression tests passed.");
