# My Stock Watch — 個人用株価監視アプリ

初期登録10社（アドバンテスト、東京エレクトロン、三菱重工業、日立製作所、Alphabet、Broadcom、Microsoft、Vertiv、NVIDIA、Procter & Gamble）に対応し、日本株・米国株の終値、騰落率、日足チャート、関連ニュースを表示するStreamlitアプリです。OpenAI APIキーを設定するとニュース見出しのAI要約も利用できます。

## セットアップ

Python 3.10以降をインストールし、このフォルダで以下を実行します。

```bash
python -m venv .venv
```

Windowsの場合:

```powershell
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

macOS / Linuxの場合:

```bash
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

表示される `http://localhost:8501` にPCのブラウザでアクセスします。

## AI機能（任意・API利用料が別途発生）

プロジェクト直下に `.streamlit/secrets.toml` を作成し、以下を記入してください。

```toml
OPENAI_API_KEY = "ご自身のAPIキー"
```

**APIキーをGitHubに公開しないでください。** `.gitignore` を同梱しています。公開環境ではStreamlit CloudのSecrets設定を利用します。

## スマホから使うには

Streamlit Community Cloudなどにデプロイすればブラウザからアクセスできます。ただし、公開URLには第三者もアクセスできる可能性があるため、個人情報・保有株数・APIキーを画面やコードに埋め込まないでください。非公開で使いたい場合は認証・アクセス制限を追加してください。

## 現段階の制約

- 株価は日足の調整後終値であり、リアルタイムの約定価格ではありません。
- データはyfinance経由の非公式データで、取得不能・遅延・利用条件の変更があり得ます。
- ニュースはGoogleニュースのRSS検索結果です。銘柄コードだけでは無関係な記事が混じる可能性があります。
- AIは見出しのみを分析します。記事本文を読んだり、ニュースと値動きの因果関係を証明したりしません。
- ウォッチリストはセッション中のみ保存され、再接続やサーバー再起動後に初期値へ戻ることがあります。
- データ取得は15分間キャッシュします。「データを再取得」で手動更新できます。
- 個人学習・情報確認向けの試作品です。投資判断には証券会社や公式IRの情報を確認してください。

## 初期登録銘柄

6857.T / 8035.T / 7011.T / 6501.T / GOOGL / AVGO / MSFT / VRT / NVDA

AlphabetはClass A株（GOOGL）を使用しています。銘柄はサイドバーから追加・削除できます。
