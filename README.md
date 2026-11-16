# My Stock Watch v0.6 — 設定保存版

日本株・米国株の株価・ニュースを表示し、ChatGPTにニュース分析を依頼するための質問文を生成します。OpenAI APIキーは不要です。

## v0.6 の追加機能

- 監視銘柄・お気に入り・株価アラートをブラウザのlocalStorageに保存
- 設定をJSONファイルとしてダウンロード／読み込み
- v0.5のURLパラメータ（favorites / alerts）を初期復元に利用

**重要:** ブラウザごとの保存です。AndroidとPC間では同期されません。ブラウザデータ削除やシークレットモードでは設定が消えます。JSONバックアップをおすすめします。Streamlit Community Cloudで実機動作を確認する前の試作品です。

## Androidから更新

GitHubリポジトリのルートにある `app.py` と `requirements.txt` を、ZIP内の同名ファイルに置き換えてコミットしてください。Streamlitが自動的に再デプロイします。必要に応じて `README.md` も更新できます。

## 起動

```bash
pip install -r requirements.txt
streamlit run app.py
```

株価はyfinanceの取得可能な日足終値で、リアルタイム配信ではありません。アラートは閲覧時にだけ判定され、バックグラウンド通知はありません。
