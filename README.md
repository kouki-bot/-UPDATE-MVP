# 山口ローカル店舗ニュース収集 修正版 v3

## 置き換えるファイル
- scripts/collect_rss.py
- scripts/generate_drafts.py

## 主な修正
- `generate_drafts.py` の正規表現のエスケープを修正。
- `published_date` が空欄の場合、タイトル内の日付（例: `2024/02/16 06:00`、`2026年9月24日`）を日付候補として抽出。
- 日付が抽出できない記事は推測で日付を作らず「日付確認が必要」のまま保持。
- 90日より古い記事は通常の下書きから除外。
- 公開処理は追加せず、ステータスは `未確認・公開禁止` のまま。
- `data/published.json` は読み書きしません。

## GitHubでの適用
1. ZIPを解凍。
2. リポジトリ内の `scripts/collect_rss.py` と `scripts/generate_drafts.py` をそれぞれ開く。
3. 各ファイルの内容をZIP内の同名ファイルで全置換してコミット。
4. GitHub Actions `Yamaguchi Local Update` を手動実行。
5. `data/drafts.json` の `freshness_counts` と先頭候補を確認。

注意: 構文チェックと日付抽出のローカルテストは実施済みですが、GitHub Actions上の実際のWeb取得は未検証です。タイトルにある日付は公開日とは限らない場合があるため、すべて公開前確認が必要です。
