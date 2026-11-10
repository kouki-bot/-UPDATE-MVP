import json
import os
import socket
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
INPUT = ROOT / 'data' / 'drafts.json'
TIMEOUT = 8
MAX_URLS = 60

def check_url(url, opener=urlopen):
    request = Request(url, headers={'User-Agent': 'YamaguchiLocalUpdate-LinkHealth/1.0', 'Range': 'bytes=0-0'}, method='GET')
    try:
        with opener(request, timeout=TIMEOUT) as response:
            status = getattr(response, 'status', response.getcode())
            if status in (404, 410):
                return {'url': url, 'status': 'broken', 'http_status': status}
            if 200 <= status < 400:
                return {'url': url, 'status': 'ok', 'http_status': status}
            return {'url': url, 'status': 'inconclusive', 'http_status': status}
    except HTTPError as exc:
        status = exc.code
        return {'url': url, 'status': 'broken' if status in (404, 410) else 'inconclusive', 'http_status': status}
    except (URLError, TimeoutError, socket.timeout, OSError) as exc:
        return {'url': url, 'status': 'inconclusive', 'error': type(exc).__name__}

def collect_urls(drafts):
    urls = []
    for draft in drafts:
        url = str(draft.get('source_url') or '').strip()
        if url.startswith(('https://', 'http://')) and url not in urls:
            urls.append(url)
    return urls[:MAX_URLS]

def main():
    data = json.loads(INPUT.read_text(encoding='utf-8'))
    drafts = data.get('drafts', [])
    if not isinstance(drafts, list):
        raise SystemExit('Invalid drafts schema: drafts must be an array')
    results = [check_url(url) for url in collect_urls(drafts)]
    broken = [x for x in results if x['status'] == 'broken']
    uncertain = [x for x in results if x['status'] == 'inconclusive']
    lines = ['## 出典URLリンク確認', '', f'- 確認対象: {len(results)}件', f'- 正常: {len(results) - len(broken) - len(uncertain)}件', f'- 404/410: {len(broken)}件', f'- 確認不能: {len(uncertain)}件', '']
    if broken:
        lines += ['### リンク切れの可能性が高いURL（人による確認が必要）', '']
        lines += [f"- HTTP {x['http_status']}: {x['url']}" for x in broken]
    if uncertain:
        lines += ['', '### アクセス制限・一時エラー等で確認できなかったURL', '']
        lines += [f"- {x.get('http_status', x.get('error', '不明'))}: {x['url']}" for x in uncertain]
    lines += ['', 'この検査は候補の公開可否を判断しません。404/410も自動削除せず、人による確認対象にします。']
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a', encoding='utf-8') as handle:
            handle.write('\n'.join(lines) + '\n')
    print('\n'.join(lines))

if __name__ == '__main__':
    main()