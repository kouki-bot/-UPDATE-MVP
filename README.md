山口ローカル店舗ニュース収集 修正版 v4

置き換えるファイル
- scripts/collect_rss.py
- scripts/generate_drafts.py

今回の改善
- RSS説明文が空、または短い場合、元記事ページから meta description / 本文段落を取得します。
- 最大60記事まで取得し、取得時間とアクセス負荷を抑えます。
- 取得できなかった記事は空欄のまま残し、内容を推測して補いません。
- drafts.json に body_excerpt_method を追加し、本文の取得方法を確認できます。
- 既存の「未確認・公開禁止」運用を維持します。
- data/published.json は読み書きしません。

GitHubでの適用
1. ZIPを解凍します。
2. GitHubリポジトリの scripts/collect_rss.py と scripts/generate_drafts.py を開き、各ファイルを全置換します。
3. コミットします。
4. GitHub Actions「Yamaguchi Local Update」を手動実行します。
5. data/drafts.json で body_excerpt と body_excerpt_method を確認します。

注意
- サイト側のアクセス制限、HTML構造、JavaScript描画、利用規約等により本文が取得できない場合があります。
- 本文は確認用の短い抜粋であり、公開用文章としてそのまま転載する用途ではありません。
- 店舗所在地、実際の開店・閉店日、現在の営業状況は別途確認してください。
- 公開処理は追加していません。data/published.json は変更しません。
