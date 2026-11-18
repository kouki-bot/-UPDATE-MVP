import json
import os
import socket
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
INPUT = ROOT / 'data' / 'drafts.json'
TIMEOUT = 8
MAX_URLS = 150


def check_url(url, opener=urlopen):
    # 日本語を含むパス・クエリをASCIIのURL表現に変換してからHTTPリクエストする。
    request_url = quote(url, safe=":/?&=#%[]@!$()*+,;~-._")
    request = Request(
        request_url,
        headers={
            'User-Agent': 'YamaguchiLocalUpdate-LinkHealth/1.1',
            'Range': 'bytes=0-0',
        },
        method='GET',
    )
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
        return {
            'url': url,
            'status': 'broken' if status in (404, 410) else 'inconclusive',
            'http_status': status,
        }
    except (URLError, TimeoutError, socket.timeout, OSError) as exc:
        return {'url': url, 'status': 'inconclusive', 'error': type(exc).__name__}


def collect_sources(drafts):
    """候補の主出典と追加出典をまとめ、URL単位で重複を除く。"""
    sources = []
    seen = set()

    for draft in drafts:
        if not isinstance(draft, dict):
            continue

        title = str(draft.get('title') or draft.get('suggested_headline') or '').strip()
        candidates = []

        primary_url = str(draft.get('source_url') or '').strip()
        if primary_url:
            candidates.append({
                'url': primary_url,
                'source_name': str(draft.get('source_name') or '').strip(),
            })

        extra_sources = draft.get('source_urls', [])
        if isinstance(extra_sources, list):
            for source in extra_sources:
                if not isinstance(source, dict):
                    continue
                candidates.append({
                    'url': str(source.get('url') or '').strip(),
                    'source_name': str(source.get('source_name') or '').strip(),
                })

        for source in candidates:
            url = source['url']
            if not url.startswith(('https://', 'http://')) or url in seen:
                continue
            seen.add(url)
            sources.append({
                **source,
                'title': title,
            })

    return sources[:MAX_URLS]


def collect_urls(drafts):
    """後方互換用のURL一覧。"""
    return [source['url'] for source in collect_sources(drafts)]



def check_sources(sources, checker=check_url):
    """全出典を確認し、URLごとの結果を返す。"""
    results = {}
    for source in sources:
        url = source['url']
        if url not in results:
            results[url] = checker(url)
    return results


def annotate_draft_source_checks(drafts, results):
    """各候補に出典ごとのリンク確認結果を付与する。"""
    for draft in drafts:
        if not isinstance(draft, dict):
            continue
        checks = []
        for source in collect_sources([draft]):
            result = results.get(source['url'])
            if result is None:
                status = 'not_checked_limit'
                http_status = None
                error = '確認上限を超過'
            else:
                status = result.get('status', 'inconclusive')
                http_status = result.get('http_status')
                error = result.get('error')
            checks.append({
                'url': source['url'],
                'source_name': source['source_name'],
                'status': status,
                'http_status': http_status,
                'error': error,
            })
        draft['source_link_checks'] = checks
    return drafts

def main():
    data = json.loads(INPUT.read_text(encoding='utf-8'))
    drafts = data.get('drafts', [])
    if not isinstance(drafts, list):
        raise SystemExit('Invalid drafts schema: drafts must be an array')

    sources = collect_sources(drafts)
    results = check_sources(sources)
    annotate_draft_source_checks(drafts, results)

    broken = [x for x in results.values() if x['status'] == 'broken']
    uncertain = [x for x in results.values() if x['status'] == 'inconclusive']
    lines = [
        '## 出典URLリンク確認',
        '',
        f'- 確認対象: {len(results)}件（候補の主出典・追加出典を含む）',
        f'- 正常: {len(results) - len(broken) - len(uncertain)}件',
        f'- 404/410: {len(broken)}件',
        f'- 確認不能: {len(uncertain)}件',
        '',
    ]

    if broken:
        lines += ['### リンク切れの可能性が高いURL（人による確認が必要）', '']
        lines += [
            f"- HTTP {x['http_status']}: {x['url']}"
            for x in broken
        ]

    if uncertain:
        lines += ['', '### アクセス制限・一時エラー等で確認できなかったURL', '']
        lines += [
            f"- {x.get('http_status', x.get('error', '不明'))}: {x['url']}"
            for x in uncertain
        ]

    unchecked = sum(
        1 for draft in drafts if isinstance(draft, dict)
        for check in draft.get('source_link_checks', [])
        if check.get('status') == 'not_checked_limit'
    )
    lines += [
        '',
        f'- 上限超過で未確認: {unchecked}件',
        'この検査は候補の公開可否を判断しません。404/410も自動削除せず、人による確認対象にします。',
        'アクセス制限・一時エラーはリンク切れと断定せず、確認不能として扱います。',
    ]

    # 確認結果を候補JSONに保持し、審査画面でも出典単位で参照できるようにする。
    INPUT.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )

    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a', encoding='utf-8') as handle:
            handle.write('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
