#!/usr/bin/env python3
"""Synchronize review-only candidate data and private publication approvals."""
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRIVATE_REPO = "kouki-bot/yamaguchi-review-private"
API = "https://api.github.com"
TOKEN = os.environ.get("PRIVATE_REVIEW_TOKEN", "").strip()
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "yamaguchi-local-update",
}

def request(method, path, payload=None):
    if not TOKEN:
        raise SystemExit("PRIVATE_REVIEW_TOKEN is not configured")
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(API + path, data=data, headers=HEADERS, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read()
            return json.loads(raw.decode("utf-8")) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise SystemExit(f"Private repository API failed ({exc.code}): {detail}") from exc

def read_json(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))

def put_private(local_path, remote_path):
    raw = (ROOT / local_path).read_bytes()
    parsed = json.loads(raw.decode("utf-8"))
    key = "drafts" if local_path.endswith("drafts.json") else "candidates"
    rows = parsed.get(key, [])
    unsafe = [row for row in rows if row.get("status") != "未確認・公開禁止"]
    if unsafe:
        raise SystemExit(f"{local_path}: {len(unsafe)} candidate(s) are not review-only")
    api_path = f"/repos/{PRIVATE_REPO}/contents/{remote_path}"
    try:
        current = request("GET", api_path + "?ref=main")
        sha = current.get("sha")
    except SystemExit as exc:
        if "API failed (404)" in str(exc):
            sha = None
        else:
            raise
    payload = {
        "message": f"Update private review candidates: {Path(local_path).name}",
        "content": base64.b64encode(raw).decode("ascii"),
        "branch": "main",
    }
    if sha:
        payload["sha"] = sha
    request("PUT", api_path, payload)
    print(f"Uploaded private review data: {Path(local_path).name} ({len(rows)} records)")

def download_approvals():
    remote_path = "data/publication_approvals.json"
    result = request("GET", f"/repos/{PRIVATE_REPO}/contents/{remote_path}?ref=main")
    if result.get("encoding") != "base64" or not result.get("content"):
        raise SystemExit("Private approval file is missing or has an unsupported encoding")
    raw = base64.b64decode(result["content"])
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data.get("approved_ids"), list) or not isinstance(data.get("reviewed_articles"), dict):
        raise SystemExit("Private approval JSON schema is invalid")
    (ROOT / "data/publication_approvals.json").write_bytes(raw)
    print(f"Loaded private approvals: {len(data['approved_ids'])} approved ID(s)")

def main():
    if len(sys.argv) != 2 or sys.argv[1] not in {"upload", "download"}:
        raise SystemExit("Usage: private_review_sync.py upload|download")
    if sys.argv[1] == "upload":
        put_private("data/source_checks.json", "incoming/source_checks.json")
        put_private("data/rss_candidates.json", "incoming/rss_candidates.json")
        put_private("data/drafts.json", "incoming/drafts.json")
    else:
        download_approvals()

if __name__ == "__main__":
    main()
