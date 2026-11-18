import re
import json
from pathlib import Path
from uuid import uuid4
import html
from datetime import datetime, timezone, timedelta
from urllib.parse import quote
import xml.etree.ElementTree as ET

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf

st.set_page_config(page_title='My Stock Watch', page_icon='📈', layout='wide')
st.title('📈 My Stock Watch v0.9')
st.caption('日本株・米国株の株価と関連ニュースをまとめて確認｜投資判断の参考情報です')
alert_placeholder = st.empty()

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

# 設定はこのブラウザのlocalStorageに保存します。異なる端末には同期しません。
STORAGE_KEY = 'my_stock_watch_v06_preferences'
preferences_storage = components.declare_component(
    'preferences_storage', path=str(Path(__file__).parent / 'preferences_storage')
)

def parse_url_settings():
    # v0.5のURLからも移行可能
    favorites = [x for x in st.query_params.get('favorites', '').split(',') if normalize(x) == x]
    alerts = {}
    for part in st.query_params.get('alerts', '').split(','):
        try:
            symbol, direction, target = part.split(':')
            target = float(target)
            if normalize(symbol) == symbol and direction in ('above', 'below') and 0 < target < 1e9:
                alerts[symbol] = (direction, target)
        except (ValueError, TypeError):
            continue
    raw_symbols = st.query_params.get('symbols')
    symbols = DEFAULT.copy() if raw_symbols is None else raw_symbols.split(',')
    return sanitize_settings({'symbols': symbols, 'favorites': favorites, 'alerts': alerts})

def sanitize_settings(value):
    if not isinstance(value, dict):
        return None
    raw_symbols = value.get('symbols', DEFAULT)
    if not isinstance(raw_symbols, list):
        raw_symbols = DEFAULT
    symbols = list(dict.fromkeys(s for s in raw_symbols[:100] if isinstance(s, str) and normalize(s) == s))
    raw_favs = value.get('favorites', [])
    favorites = [s for s in raw_favs if isinstance(s, str) and s in symbols] if isinstance(raw_favs, list) else []
    alerts = {}
    raw_alerts = value.get('alerts', {})
    if isinstance(raw_alerts, dict):
        for symbol, item in raw_alerts.items():
            try:
                direction, target = item
                target = float(target)
                if symbol in symbols and direction in ('above', 'below') and 0 < target < 1e9:
                    alerts[symbol] = (direction, target)
            except (ValueError, TypeError):
                pass
    return {'symbols': symbols, 'favorites': favorites, 'alerts': alerts}

def current_settings():
    return {'symbols': st.session_state.symbols,
            'favorites': st.session_state.favorites,
            'alerts': {s: [d, t] for s, (d, t) in st.session_state.alerts.items()}}

def save_preferences():
    st.session_state.preferences_pending = {
        'id': uuid4().hex,
        'value': json.dumps(current_settings(), ensure_ascii=False),
    }
    st.session_state.preferences_status = 'saving'


def restore_settings(data):
    st.session_state.symbols = data['symbols']
    st.session_state.favorites = data['favorites']
    st.session_state.alerts = data['alerts']


pending = st.session_state.get('preferences_pending')
loading = 'symbols' not in st.session_state
command = {'id': 'load'} if loading else pending
storage_result = preferences_storage(storage_key=STORAGE_KEY, command=command, key='preferences_storage')

if loading:
    if not storage_result or storage_result.get('id') != 'load':
        st.caption('ブラウザに保存された設定を読み込んでいます…')
        st.stop()
    data = None
    stored = storage_result.get('value')
    if isinstance(stored, str):
        try:
            value = json.loads(stored)
            # 旧コンポーネントは保存キーで包んだJSON文字列を格納していた。
            if isinstance(value, dict) and isinstance(value.get(STORAGE_KEY), str):
                value = json.loads(value[STORAGE_KEY])
            elif isinstance(value, str):
                value = json.loads(value)
            data = sanitize_settings(value)
        except ValueError:
            pass
    restore_settings(parse_url_settings() if data is None else data)
    if not storage_result.get('ok'):
        st.session_state.preferences_status = 'read_error'
elif pending and storage_result and storage_result.get('id') == pending['id']:
    del st.session_state.preferences_pending
    if storage_result.get('ok'):
        st.session_state.preferences_status = 'saved'
        # 既存のURLバックアップも保存内容とそろえる。
        st.query_params.update({
            'symbols': ','.join(st.session_state.symbols),
            'favorites': ','.join(st.session_state.favorites),
            'alerts': ','.join(f'{s}:{d}:{t}' for s, (d, t) in st.session_state.alerts.items()),
        })
    else:
        st.session_state.preferences_status = 'write_error'

with st.sidebar:
    st.header('ウォッチリスト')
    new_symbol = st.text_input('銘柄コードを追加', placeholder='例: 9432 / MSFT')
    if st.button('追加', use_container_width=True):
        symbol = normalize(new_symbol)
        if not symbol:
            st.error('銘柄コードの形式を確認してください。')
        elif symbol not in st.session_state.symbols:
            if len(st.session_state.symbols) >= 100:
                st.error('登録できる銘柄は100件までです。')
            else:
                st.session_state.symbols.append(symbol)
                save_preferences()
                st.rerun()
    for index, symbol in enumerate(st.session_state.symbols.copy()):
        if index:
            st.divider()
        st.write(f'{display_name(symbol)} ({symbol})')
        with st.container(horizontal=True, gap='small'):
            favorite = symbol in st.session_state.favorites
            if st.button('★' if favorite else '☆', key=f'fav_{symbol}', help='お気に入りを切り替え'):
                if favorite:
                    st.session_state.favorites.remove(symbol)
                else:
                    st.session_state.favorites.append(symbol)
                save_preferences()
                st.rerun()
            if st.button('✕', key=f'remove_{symbol}', help='銘柄を削除'):
                st.session_state.symbols.remove(symbol)
                if symbol in st.session_state.favorites:
                    st.session_state.favorites.remove(symbol)
                st.session_state.alerts.pop(symbol, None)
                save_preferences()
                st.rerun()
    st.caption('設定はこのブラウザに保存します。別の端末には自動同期されません。')
    status = st.session_state.get('preferences_status')
    if status == 'saving':
        st.caption('設定を保存しています…')
    elif status == 'saved':
        st.caption('設定をこのブラウザに保存しました。')
    elif status == 'read_error':
        st.warning('ブラウザの保存データを読み込めませんでした。')
    elif status == 'write_error':
        st.warning('このブラウザに設定を保存できませんでした。')
        if st.button('設定の保存を再試行'):
            save_preferences()
            st.rerun()
    st.subheader('💾 設定バックアップ')
    st.download_button('設定をJSONで保存', json.dumps(current_settings(), ensure_ascii=False, indent=2),
                       file_name='my_stock_watch_settings.json', mime='application/json', use_container_width=True)
    uploaded = st.file_uploader('保存した設定を復元', type=['json'])
    if uploaded is not None and st.button('バックアップを読み込む', use_container_width=True):
        try:
            data = sanitize_settings(json.load(uploaded))
            if data is None:
                raise ValueError('設定の形式が正しくありません')
            restore_settings(data)
            save_preferences()
            st.rerun()
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            st.error(f'設定を読み込めませんでした: {exc}')
    if st.button('🔄 最新データを取得（キャッシュを消去）', use_container_width=True):
        st.cache_data.clear()
        st.rerun()

@st.cache_data(ttl=300, show_spinner=False)
def load_price(symbol):
    ticker = yf.Ticker(symbol)
    # 長期チャート用の日足と、直近の価格確認用の時間足を分ける。
    hist = ticker.history(period='1y', interval='1d', auto_adjust=True)
    if hist.empty or hist['Close'].dropna().empty:
        raise ValueError('日足の株価データを取得できませんでした')
    closes = hist['Close'].dropna()
    previous_close = float(closes.iloc[-2]) if len(closes) >= 2 else None
    latest_price = float(closes.iloc[-1])
    latest_time = closes.index[-1]
    source = '日足（終値）'
    try:
        intraday = ticker.history(period='5d', interval='5m', auto_adjust=True, prepost=False)
        if not intraday.empty and not intraday['Close'].dropna().empty:
            recent = intraday['Close'].dropna()
            intraday_time = recent.index[-1]
            # 取得した時間足が日足より新しい場合のみ採用。
            if intraday_time.date() >= latest_time.date():
                latest_price = float(recent.iloc[-1])
                latest_time = intraday_time
                source = '5分足（遅延の可能性あり）'
    except Exception:
        pass  # 時間足が取れない場合は日足にフォールバック
    # 日足最終行が当日なら、前日終値はひとつ前の行。
    # 時間足の日付が日足最終日より新しい場合は日足最終行が前日終値。
    if latest_time.date() > closes.index[-1].date():
        previous_close = float(closes.iloc[-1])
    change = (latest_price / previous_close - 1) * 100 if previous_close and previous_close > 0 else None
    currency = 'JPY' if symbol.endswith('.T') else 'USD'
    if getattr(latest_time, 'tzinfo', None) is not None:
        from zoneinfo import ZoneInfo
        shown_time = latest_time.tz_convert(ZoneInfo('Asia/Tokyo')).strftime('%Y-%m-%d %H:%M JST')
        age = datetime.now(timezone.utc) - latest_time.to_pydatetime().astimezone(timezone.utc)
    else:
        shown_time = latest_time.strftime('%Y-%m-%d') + '（取引日）'
        age = None
    stale = age is not None and age > timedelta(days=4)
    return hist, latest_price, change, currency, shown_time, source, stale

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

# オルカンの基準価額は株価ではなく、原則として営業日ごとに公表されます。
# 株式ティッカーで代用せず、投資信託そのものの公表値を参照します。
FUND_URL = 'https://fs.bk.mufg.jp/webasp/mufg/fund/detail/m00355920.html'
FUND_BACKUP_URL = 'https://www.rakuten-sec.co.jp/web/fund/detail/?ID=JP90C000H1T1'
FUND_NAME = 'eMAXIS Slim 全世界株式（オール・カントリー）'


def _normalize_fund_text(value):
    import unicodedata
    value = unicodedata.normalize('NFKC', value)
    return re.sub(r'\s+', ' ', value)


def _parse_fund_nav(page, provider):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(page, 'html.parser')
    for tag in soup(['script', 'style', 'noscript']):
        tag.decompose()
    text = _normalize_fund_text(soup.get_text(' ', strip=True))
    # ISINを含む公式商品ページのみを使用し、名称の異なる投信を誤認しない。
    if not ('オール・カントリー' in text and 'Slim' in text and '全世界株式' in text):
        raise ValueError('ファンド名を確認できません')
    if provider == '三菱UFJ銀行':
        match = re.search(r'基準価額\s*[?？:]?\s*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{4,6})\s*円', text)
        date_match = re.search(r'基準日\s*[:：]?\s*(20\d{2})[年/.-]\s*(\d{1,2})[月/.-]\s*(\d{1,2})', text)
    else:
        # 楽天証券の表示例: 基準価額 | 37,852 円 (11/12)
        match = re.search(r'基準価額\s*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{4,6})\s*円\s*[（(]\s*(\d{1,2})/(\d{1,2})\s*[）)]', text)
        date_match = None
    if not match:
        raise ValueError('基準価額の表示を確認できません')
    nav = int(match.group(1).replace(',', ''))
    if not 1000 <= nav <= 1000000:
        raise ValueError('基準価額が想定範囲外です')
    today = datetime.now(timezone(timedelta(hours=9))).date()
    if provider == '三菱UFJ銀行':
        if not date_match:
            raise ValueError('公表基準日を確認できません')
        asof_date = datetime(int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3))).date()
    else:
        month, day = int(match.group(2)), int(match.group(3))
        asof_date = datetime(today.year, month, day).date()
        if asof_date > today:
            asof_date = datetime(today.year - 1, month, day).date()
    if asof_date > today or (today - asof_date).days > 14:
        raise ValueError('公表基準日が古いか未来の日付です')
    return nav, asof_date.isoformat()


@st.cache_data(ttl=1800, show_spinner=False)
def load_all_country_nav():
    failures = []
    for provider, url in [('三菱UFJ銀行', FUND_URL), ('楽天証券', FUND_BACKUP_URL)]:
        try:
            response = requests.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0 (compatible; MyStockWatch/0.9)'})
            response.raise_for_status()
            nav, asof = _parse_fund_nav(response.content, provider)
            return nav, asof, provider
        except (requests.RequestException, ValueError, OverflowError) as exc:
            failures.append(f'{provider}: {type(exc).__name__}')
    raise ValueError('取得元から有効な基準価額・基準日を確認できません（' + ' / '.join(failures) + '）')


st.subheader('🌏 オルカンの基準価額')
st.caption('eMAXIS Slim 全世界株式（オール・カントリー）｜1万口当たり・円建て。営業日ごとの公表値です。')
try:
    fund_nav, fund_date, fund_source = load_all_country_nav()
    st.metric('取得できた公表基準価額', f'{fund_nav:,} 円')
    st.caption(f'基準日: {fund_date} ｜ 取得元: {fund_source}')
    if (datetime.now(timezone(timedelta(hours=9))).date() - datetime.strptime(fund_date, '%Y-%m-%d').date()).days > 4:
        st.warning('公表基準日が4日以上前です。最新値かどうか取得元で確認してください。')
except Exception as exc:
    st.warning(f'オルカンの基準価額を取得できませんでした: {exc}')
st.link_button('三菱UFJ銀行の公表情報を確認 ↗', FUND_URL)
st.link_button('楽天証券の公表情報を確認 ↗', FUND_BACKUP_URL)
st.divider()

symbols = sorted(st.session_state.symbols, key=lambda symbol: (symbol not in st.session_state.favorites, st.session_state.symbols.index(symbol)))
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
    for i, (symbol, (hist, price, change, currency, date, source, stale)) in enumerate(prices.items()):
        with cols[i % len(cols)]:
            st.metric(f'{display_name(symbol)} ({symbol})', f'{price:,.2f} {currency}', f'{change:+.2f}%' if change is not None else None)
            st.caption(f'データ日時: {date} ｜ {source}')
            if stale:
                st.warning('データが古い可能性があります')

st.subheader('🔔 株価アラート（閲覧時チェック）')
st.caption('取得できる最新の価格で判定します（5分足優先・日足にフォールバック）。リアルタイム保証はなく、アプリを閉じている間の通知はありません。')
with st.expander('アラートを設定・変更する', expanded=False):
    alert_symbol = st.selectbox('監視する銘柄', symbols, key='alert_symbol', format_func=lambda symbol: f'{display_name(symbol)} ({symbol})')
    old_direction, old_target = st.session_state.alerts.get(alert_symbol, ('below', 100.0))
    alert_direction = st.radio('通知条件', ['below', 'above'], index=0 if old_direction == 'below' else 1,
                               format_func=lambda v: '指定価格以下' if v == 'below' else '指定価格以上', horizontal=True)
    alert_target = st.number_input('指定価格（日本株は円、米国株はドル）', min_value=0.01, max_value=999_999_999.99,
                                   value=float(old_target), step=1.0, format='%.2f')
    ac1, ac2 = st.columns(2)
    if ac1.button('条件を保存', use_container_width=True):
        st.session_state.alerts[alert_symbol] = (alert_direction, alert_target)
        save_preferences()
        st.rerun()
    if ac2.button('この銘柄の条件を削除', use_container_width=True):
        st.session_state.alerts.pop(alert_symbol, None)
        save_preferences()
        st.rerun()

triggered_alerts = []
for symbol, (direction, target) in st.session_state.alerts.items():
    if symbol not in symbols:
        continue
    unit = '円' if symbol.endswith('.T') else 'ドル'
    cond = '以下' if direction == 'below' else '以上'
    if symbol not in prices:
        st.warning(f'{display_name(symbol)}: 価格取得不可のためアラート判定できません')
        continue
    price = prices[symbol][1]
    hit = price <= target if direction == 'below' else price >= target
    message = f'{display_name(symbol)}: {target:,.2f}{unit}{cond}（取得した終値 {price:,.2f}{unit}）'
    if hit:
        triggered_alerts.append(message)
    else:
        st.caption('監視中: ' + message)

if triggered_alerts:
    with alert_placeholder.container():
        for message in triggered_alerts:
            st.warning('🔔 条件に達しました: ' + message)

selected = st.selectbox('詳細を見る銘柄', symbols, format_func=lambda symbol: f'{display_name(symbol)} ({symbol})')
if selected in prices:
    hist, price, change, currency, date, source, stale = prices[selected]
    st.caption(f'価格データ日時: {date} ｜ {source}')
    period = st.radio('チャート期間', ['1か月','3か月','1年'], horizontal=True)
    days = {'1か月':30,'3か月':90,'1年':365}[period]
    st.line_chart(hist['Close'].tail(days), y_label=f'調整後終値 ({currency})')
    st.caption('チャートは日足の調整後終値です。上部の表示価格とは取得間隔が異なる場合があります。')

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

st.subheader('💬 ChatGPTでニュースを詳しく調べる')
st.caption('APIキー・追加のAPI料金は不要です。質問文をコピーしてChatGPTに貼り付けてください。')

company = display_name(selected)
headlines = "\n".join(
    f'- {item["title"]}（{item["published"]}、{item["source"]}）\n  URL: {item["link"]}'
    for item in news
)
question = (
    f'{company}（{selected}）について、以下のニュースを起点に最新情報を調査してください。\n'
    'ニュースの発表日と出来事の日付を区別し、可能なら企業IRなどの一次情報を優先して出典URLを示してください。\n'
    '①重要ニュースの要点 ②株価へのプラス材料・マイナス材料 ③まだ不明な点 '
    '④今後の注目イベント、の順に日本語で解説してください。\n'
    'ニュースと株価変動の因果関係は断定せず、記事を確認できない場合はその旨を明記してください。\n\n'
    f'参考ニュース（見出し・URL。内容は未検証）：\n{headlines if headlines else "ニュースを取得できませんでした。企業名から調査してください。"}'
)
st.write('**この銘柄のニュースをまとめて分析**')
st.code(question, language=None)
st.caption('右上のコピーアイコンで質問文をコピーできます。')
st.link_button('ChatGPTを開く ↗', 'https://chatgpt.com/', use_container_width=True)

if news:
    with st.expander('記事を1件ずつ詳しく調べる'):
        for index, item in enumerate(news):
            st.markdown(f'**{index + 1}. {item["title"]}**')
            article_question = (
                f'{company}（{selected}）に関する次の記事を詳しく調査してください。\n'
                f'見出し: {item["title"]}\n掲載日時: {item["published"]}\n'
                f'掲載元: {item["source"]}\nURL: {item["link"]}\n\n'
                '記事の内容と一次情報を確認できる範囲で調べ、事実・推測を分けて、'
                '株価への潜在的な影響と注意点を日本語で説明してください。'
            )
            st.code(article_question, language=None)
            st.divider()

st.divider()
st.caption('保存に関する注意: ブラウザのデータ削除、シークレットモード、別ブラウザでは設定が引き継がれません。バックアップJSONを保管してください。')
st.caption('免責事項: 非公式データやRSSの内容には遅延・欠落・誤りがあり得ます。投資助言ではありません。売買前には証券会社や公式IRで確認してください。')
