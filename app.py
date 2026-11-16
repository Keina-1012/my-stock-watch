import os
import re
import json
import html
from datetime import datetime, timezone
from urllib.parse import quote
import xml.etree.ElementTree as ET

import pandas as pd
import requests
import streamlit as st
import yfinance as yf

st.set_page_config(page_title='My Stock Watch', page_icon='📈', layout='wide')
st.title('📈 My Stock Watch')
st.caption('日本株・米国株の株価と関連ニュースをまとめて確認｜投資判断の参考情報です')

DEFAULT = ['6857.T', '8035.T', '7011.T', '6501.T', 'GOOGL', 'AVGO', 'MSFT', 'VRT', 'NVDA', 'PG']
COMPANIES = {
    '6857.T': ('アドバンテスト', 'アドバンテスト 半導体 決算'),
    '8035.T': ('東京エレクトロン', '東京エレクトロン 半導体 決算'),
    '7011.T': ('三菱重工業', '三菱重工業 防衛 エネルギー 決算'),
    '6501.T': ('日立製作所', '日立製作所 デジタル 決算'),
    'GOOGL': ('Alphabet', 'Alphabet Google earnings AI'),
    'AVGO': ('Broadcom', 'Broadcom semiconductor earnings AI'),
    'MSFT': ('Microsoft', 'Microsoft Azure earnings AI'),
    'VRT': ('Vertiv', 'Vertiv Holdings data center earnings'),
    'NVDA': ('NVIDIA', 'NVIDIA earnings AI chips'),
    'PG': ('Procter & Gamble (P&G)', '"Procter & Gamble" earnings consumer products pricing'),
}

def display_name(symbol):
    return COMPANIES.get(symbol, (symbol, symbol))[0]


def normalize(s):
    s = s.strip().upper()
    if re.fullmatch(r'\d{4}', s):
        return s + '.T'
    if re.fullmatch(r'[A-Z0-9.^=-]{1,20}(\.T)?', s):
        return s
    return None

if 'symbols' not in st.session_state:
    st.session_state.symbols = DEFAULT.copy()

with st.sidebar:
    st.header('ウォッチリスト')
    new_symbol = st.text_input('銘柄コードを追加', placeholder='例: 9432 / MSFT')
    if st.button('追加', use_container_width=True):
        symbol = normalize(new_symbol)
        if not symbol:
            st.error('銘柄コードの形式を確認してください。')
        elif symbol not in st.session_state.symbols:
            st.session_state.symbols.append(symbol)
            st.rerun()
    for symbol in st.session_state.symbols.copy():
        c1, c2 = st.columns([3, 1])
        c1.write(f'{display_name(symbol)} ({symbol})')
        if c2.button('✕', key=f'remove_{symbol}'):
            st.session_state.symbols.remove(symbol)
            st.rerun()
    st.caption('日本株は4桁の証券コード、米国株はAAPLなどのティッカーを入力。銘柄はこのセッション中に保持されます。')
    if st.button('🔄 データを再取得', use_container_width=True):
        st.cache_data.clear()
        st.rerun()

@st.cache_data(ttl=900, show_spinner=False)
def load_price(symbol):
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period='1y', interval='1d', auto_adjust=True)
    if hist.empty:
        raise ValueError('株価データが取得できませんでした')
    closes = hist['Close'].dropna()
    if closes.empty:
        raise ValueError('終値が取得できませんでした')
    current = float(closes.iloc[-1])
    previous = float(closes.iloc[-2]) if len(closes) >= 2 else None
    change = (current / previous - 1) * 100 if previous else None
    currency = 'JPY' if symbol.endswith('.T') else 'USD'
    return hist, current, change, currency, str(closes.index[-1].date())

@st.cache_data(ttl=1800, show_spinner=False)
def get_news(symbol, limit=6):
    query = COMPANIES.get(symbol, (symbol, f'{symbol} stock earnings'))[1]
    lang, region, ceid = ('ja', 'JP', 'JP:ja') if symbol.endswith('.T') else ('en', 'US', 'US:en')
    url = f'https://news.google.com/rss/search?q={quote(query)}&hl={lang}&gl={region}&ceid={ceid}'
    response = requests.get(url, timeout=12, headers={'User-Agent':'Mozilla/5.0'})
    response.raise_for_status()
    root = ET.fromstring(response.content)
    items = []
    for item in root.findall('./channel/item')[:limit]:
        title = html.unescape(item.findtext('title') or '')
        link = item.findtext('link') or ''
        published = item.findtext('pubDate') or ''
        source = item.find('source')
        items.append({'title':title, 'link':link, 'published':published, 'source':source.text if source is not None else ''})
    return items

symbols = st.session_state.symbols
if not symbols:
    st.info('サイドバーから銘柄を追加してください。')
    st.stop()

prices = {}
with st.spinner('株価を取得しています…'):
    for symbol in symbols:
        try:
            prices[symbol] = load_price(symbol)
        except Exception as exc:
            st.warning(f'{symbol}: データ取得に失敗しました（{exc}）')

if prices:
    cols = st.columns(min(4, len(prices)))
    for i, (symbol, (hist, price, change, currency, date)) in enumerate(prices.items()):
        with cols[i % len(cols)]:
            st.metric(f'{display_name(symbol)} ({symbol})', f'{price:,.2f} {currency}', f'{change:+.2f}%' if change is not None else None)
            st.caption(f'最終取引日: {date}（遅延の可能性あり）')

selected = st.selectbox('詳細を見る銘柄', symbols)
if selected in prices:
    hist, price, change, currency, date = prices[selected]
    period = st.radio('チャート期間', ['1か月','3か月','1年'], horizontal=True)
    days = {'1か月':30,'3か月':90,'1年':365}[period]
    st.line_chart(hist['Close'].tail(days), y_label=f'調整後終値 ({currency})')
    st.caption('チャートは日足の調整後終値です。現在値やリアルタイム気配値ではありません。')

st.subheader(f'📰 {display_name(selected)} ({selected}) の関連ニュース')
try:
    news = get_news(selected)
    if not news:
        st.info('ニュースが見つかりませんでした。')
    for n in news:
        st.markdown(f'**[{n["title"]}]({n["link"]})**')
        st.caption(f'{n["source"]} ｜ {n["published"]}')
except Exception as exc:
    news = []
    st.warning(f'ニュースの取得に失敗しました: {exc}')

st.subheader('✨ AIニュース分析（オプション）')
st.caption('ニュースの見出しだけを使った参考分析です。記事本文の検証や株価変動の因果関係の証明ではありません。')
api_key = None
try:
    api_key = st.secrets.get('OPENAI_API_KEY')
except Exception:
    pass
api_key = api_key or os.environ.get('OPENAI_API_KEY')
if not api_key:
    st.info('OpenAI APIキーをサーバーのSecretsに設定するとAI分析を利用できます。キーを画面に入力したり、ソースコードに埋め込んだりしないでください。')
if st.button('この銘柄のニュースをAIで分析', disabled=not api_key or not news):
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        headlines = '\n'.join(f'- {n["title"]} ({n["published"]}, {n["source"]})' for n in news)
        response = client.responses.create(
            model='gpt-4.1-mini',
            instructions='あなたは慎重な金融ニュース解説者です。与えられた見出しは未検証であり、記事本文は読んでいません。日本語で、重要ニュースの概要、プラス材料、マイナス材料、不確実性を簡潔に整理してください。見出しから推測できない事実は断定せず、株価変動の原因と断定せず、売買指示や価格予測をしないでください。',
            input=f'対象銘柄: {display_name(selected)} ({selected})\nニュース見出し:\n{headlines}'
        )
        st.markdown(response.output_text)
    except Exception as exc:
        st.error(f'AI分析に失敗しました: {exc}')

st.divider()
st.caption('免責事項: 非公式データやRSSの内容には遅延・欠落・誤りがあり得ます。投資助言ではありません。売買前には証券会社や公式IRで確認してください。')
