import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import requests
import warnings
import time
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib3
from requests.exceptions import ChunkedEncodingError, ConnectionError, ReadTimeout
import os
import json
import numpy as np
import xml.etree.ElementTree as ET
from gtts import gTTS
import io

# === 升級套件：斷線重連避震器 ===
try:
    from tenacity import retry, wait_exponential, stop_after_attempt
except ImportError:
    st.error("⚠️ 缺少避震套件，請在終端機執行: pip install tenacity")

# === 非同步連線與自動刷新套件 ===
import asyncio
import aiohttp
try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:
    st_autorefresh = None
    st.error("⚠️ 缺少自動刷新套件，請在終端機執行: pip install streamlit-autorefresh")

# === 1. 系統環境設定與機密管理 ===
warnings.filterwarnings("ignore")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
st.set_page_config(page_title="阿綜專屬：究極軍規雷達 V13.0", page_icon="📡", layout="wide")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
HEADERS = {"User-Agent": UA}

try:
    FUGLE_API_KEY = st.secrets["FUGLE_API_KEY"]
except (FileNotFoundError, KeyError):
    FUGLE_API_KEY = "54f80721-6cad-4ec9-9679-c5a315e7b00b"
    st.sidebar.warning("⚠️ 偵測到尚未設定 secrets.toml，目前使用預設 API Key。")

# === 2. 外部設定檔掛載 ===
CONFIG_FILE = "system_config.json"
DEFAULT_STOCKS = {
    "2330.TW": "台積電", "2317.TW": "鴻海", "2454.TW": "聯發科", "2308.TW": "台達電",
    "2303.TW": "聯電", "3711.TW": "日月光", "2408.TW": "南亞科", "2344.TW": "華邦電",
    "2337.TW": "旺宏", "3443.TW": "創意", "3661.TW": "世芯KY", "3034.TW": "聯詠",
    "2379.TW": "瑞昱", "4966.TW": "譜瑞KY", "6415.TW": "矽力KY", "3529.TW": "力旺",
    "6488.TWO": "環球晶", "5483.TWO": "中美晶", "3105.TWO": "穩懋", "8299.TWO": "群聯",
    "2382.TW": "廣達", "3231.TW": "緯創", "6669.TW": "緯穎", "2356.TW": "英業達",
    "2324.TW": "仁寶", "2353.TW": "宏碁", "2357.TW": "華碩", "2376.TW": "技嘉",
    "2377.TW": "微星", "3017.TW": "奇鋐", "3324.TW": "雙鴻", "3653.TW": "健策",
    "3533.TW": "嘉澤", "3013.TW": "晟銘電", "8210.TW": "勤誠", "7769.TW": "鴻勁",
    "3037.TW": "欣興", "8046.TW": "南電", "3189.TW": "景碩", "2368.TW": "金像電",
    "4958.TW": "臻鼎KY", "2313.TW": "華通", "6274.TWO": "台燿", "2383.TW": "台光電",
    "6213.TW": "聯茂", "3008.TW": "大立光", "3406.TW": "玉晶光", "1519.TW": "華城",
    "1503.TW": "士電", "1513.TW": "中興電", "1504.TW": "東元", "1605.TW": "華新",
    "1101.TW": "台泥", "1102.TW": "亞泥", "2002.TW": "中鋼", "2027.TW": "大成鋼",
    "2014.TW": "中鴻", "2207.TW": "和泰車", "9910.TW": "豐泰", "9921.TW": "巨大",
    "9904.TW": "寶成", "2603.TW": "長榮", "2609.TW": "陽明", "2615.TW": "萬海",
    "2618.TW": "長榮航", "2610.TW": "華航", "2606.TW": "裕民", "3596.TW": "智易",
    "5388.TWO": "中磊", "3380.TW": "明泰", "2345.TW": "智邦", "2881.TW": "富邦金",
    "2882.TW": "國泰金", "2891.TW": "中信金", "2886.TW": "兆豐金", "2884.TW": "玉山金",
    "2892.TW": "第一金", "2880.TW": "華南金", "2885.TW": "元大金", "2890.TW": "永豐金",
    "2883.TW": "開發金", "2887.TW": "台新金", "5880.TW": "合庫金", "8069.TWO": "元太",
    "3293.TWO": "鈊象", "8436.TW": "大江", "8441.TW": "可寧衛", "8390.TWO": "金益鼎",
    "0050.TW": "台50", "0056.TW": "高股息", "00878.TW": "永續", "00919.TW": "精選高息",
    "00929.TW": "復華科技", "00713.TW": "高息低波", "006208.TW": "富邦台50", 
    "6789.TW": "采鈺", "6147.TWO": "頎邦", "3016.TW": "嘉晶", "6805.TW": "富世達"
}
DEFAULT_SECTORS = {
    "2330": "半導體", "2454": "半導體", "3661": "半導體", "3034": "半導體",
    "2317": "AI伺服器", "3231": "AI伺服器", "2382": "AI伺服器", "2356": "AI伺服器",
    "3017": "散熱模組", "3324": "散熱模組", "3653": "散熱模組", "6805": "軸承",
    "2383": "PCB零組件", "2368": "PCB零組件", "3533": "連接器", "3037": "PCB零組件",
    "2308": "電源供應", "2345": "網通", "2603": "航運", "2609": "航運", "2881": "金融"
}

if not os.path.exists(CONFIG_FILE):
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump({"STOCKS_DICT": DEFAULT_STOCKS, "SECTOR_MAP": DEFAULT_SECTORS}, f, ensure_ascii=False, indent=4)
    except Exception as e:
        st.toast(f"建立設定檔失敗: {e}")

try:
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        config_data = json.load(f)
    STOCKS_DICT = config_data.get("STOCKS_DICT", DEFAULT_STOCKS)
    SECTOR_MAP = config_data.get("SECTOR_MAP", DEFAULT_SECTORS)
except Exception as e:
    STOCKS_DICT = DEFAULT_STOCKS
    SECTOR_MAP = DEFAULT_SECTORS
    st.toast(f"讀取設定檔失敗，使用系統預設名單: {e}")

CLEAN_TO_FULL_MAP = {k.split('.')[0]: k for k in STOCKS_DICT.keys()}
MAINTENANCE_LOG_FILE = "trade_maintenance_log.csv"

# === 3. 瀏覽次數統計與交易工單 ===
def get_and_increment_view_count():
    count_file = "page_views.txt"
    if os.path.exists(count_file):
        try:
            with open(count_file, "r") as f:
                count = int(f.read().strip())
        except: count = 0
    else: count = 0
        
    if 'has_viewed' not in st.session_state:
        count += 1
        try:
            with open(count_file, "w") as f: f.write(str(count))
            st.session_state['has_viewed'] = True
        except: pass
    return count

def save_trade_maintenance_log(stock, reason, stop_loss, status):
    new_log = pd.DataFrame([{
        "時間": datetime.datetime.now(datetime.timezone.utc).astimezone(datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y-%m-%d %H:%M"),
        "標的代號": stock, "進場型態與理由": reason, "預計防守價": stop_loss, "當下心理狀態": status
    }])
    if os.path.exists(MAINTENANCE_LOG_FILE):
        try:
            df = pd.read_csv(MAINTENANCE_LOG_FILE)
            df = pd.concat([df, new_log], ignore_index=True)
        except: df = new_log
    else: df = new_log
    df.to_csv(MAINTENANCE_LOG_FILE, index=False)

# === 4. 安全連線防護機制 ===
@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
def safe_get_json(url, headers):
    response = requests.get(url, headers=headers, timeout=15, verify=False)
    response.raise_for_status() 
    return response.json()

def safe_get_json_fallback(url, headers, max_retries=3):
    try: return safe_get_json(url, headers)
    except: return {}

# === 5. YFinance 批次高速下載 ===
@st.cache_data(ttl=900)
def fetch_bulk_yf_data(full_ticker_list, period="1y"):
    if not full_ticker_list: return {}
    valid_tickers = [t for t in full_ticker_list if t]
    tickers_str = " ".join(valid_tickers)
    res_dict = {}
    try:
        data = yf.download(tickers_str, period=period, threads=True, progress=False)
        if len(valid_tickers) == 1:
            df_t = data.dropna(subset=['Close'])
            if not df_t.empty: res_dict[valid_tickers[0]] = df_t
        else:
            for t in valid_tickers:
                try:
                    df_t = pd.DataFrame({
                        'Open': data['Open'][t], 'High': data['High'][t],
                        'Low': data['Low'][t], 'Close': data['Close'][t], 'Volume': data['Volume'][t]
                    }).dropna(subset=['Close'])
                    if not df_t.empty: res_dict[t] = df_t
                except: continue
        return res_dict
    except: return {}

# === 6. 核心指標與大盤風向球 ===
@st.cache_data(ttl=1800)
def get_market_breadth():
    try:
        df = yf.Ticker("^TWII").history(period="3mo")
        if not df.empty:
            df['MA20'] = df['Close'].rolling(20).mean()
            c, m20 = df['Close'].iloc[-1], df['MA20'].iloc[-1]
            status = "🟢 偏多順風 (站上月線，積極操作)" if c > m20 else "🔴 偏空逆風 (跌破月線，縮小部位)"
            return round(c, 2), round(m20, 2), status
    except: pass
    return None, None, "⚪ 系統連線中"

def us_market_brain():
    st.sidebar.markdown("---")
    st.sidebar.subheader("🌐 美股連動觀測")
    us_tickers = {"TSM": "台積電 ADR", "ARM": "安謀 (Arm)", "AAPL": "蘋果 (Apple)", "MSFT": "微軟", "GOOG": "谷歌", "NVDA": "輝達", "META": "Meta", "TSLA": "特斯拉", "SKHY": "SK海力士"}
    for ticker, name in us_tickers.items():
        try:
            df = yf.Ticker(ticker).history(period="1mo")
            if not df.empty and len(df) >= 2:
                close_today, close_yest = df['Close'].iloc[-1], df['Close'].iloc[-2]
                change = ((close_today - close_yest) / close_yest) * 100
                st.sidebar.metric(f"{name} ({ticker})", f"${close_today:.2f}", f"{change:.2f}%", delta_color="normal" if change > 0 else "inverse")
            else: st.sidebar.metric(name, "N/A", "-")
        except: st.sidebar.metric(name, "Error", "-")

def adr_premium_calculator():
    st.sidebar.markdown("---")
    st.sidebar.subheader("⚡ ADR 開盤神算")
    try:
        tsm_adr = yf.Ticker("TSM").history(period="2d")['Close'].iloc[-1]
        twd_us = yf.Ticker("TWD=X").history(period="2d")['Close'].iloc[-1]
        tsmc_tw = yf.Ticker("2330.TW").history(period="2d")['Close'].iloc[-1]
        theo_price = (tsm_adr * twd_us) / 5  
        premium = ((theo_price - tsmc_tw) / tsmc_tw) * 100
        st.sidebar.metric("今日理論開盤價", f"{theo_price:.0f} 元", f"溢價差 {premium:.2f}%")
    except: pass

def ai_voice_report(market_status):
    st.sidebar.markdown("---")
    if st.sidebar.button("📢 生成並播放今日早報", use_container_width=True):
        with st.spinner("專屬 AI 正在整理戰報..."):
            now = datetime.datetime.now(datetime.timezone.utc).astimezone(datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y年%m月%d日")
            try:
                tts = gTTS(text=f"老闆早安，今天是{now}。大盤狀態：{market_status}。祝您操作順利！", lang='zh-tw')
                audio_fp = io.BytesIO()
                tts.write_to_fp(audio_fp)
                st.sidebar.audio(audio_fp, format='audio/mp3')
            except: pass

def line_notify_setting():
    st.sidebar.markdown("---")
    line_token = st.sidebar.text_input("Line Notify Token", type="password")
    if st.sidebar.button("傳送測試訊息") and line_token:
        requests.post("https://notify-api.line.me/api/notify", headers={"Authorization": f"Bearer {line_token}"}, data={'message': '🔧 雷達測試成功！'})

# === 7. 熱門清單與內部排行資料 (僅供背景運算) ===
@st.cache_data(ttl=3600)
def fetch_top15_ranking():
    tse_df, otc_df = pd.DataFrame(), pd.DataFrame()
    def get_tse(date_str=""):
        res = safe_get_json_fallback(f"https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&type=ALLBUT0999&date={date_str}", HEADERS)
        if res and 'tables' in res:
            for t in res['tables']:
                if '證券代號' in t.get('fields', []) and '成交金額' in t.get('fields', []):
                    df = pd.DataFrame(t['data'], columns=t['fields'])
                    df['v'] = pd.to_numeric(df['成交金額'].str.replace(',',''), errors='coerce')
                    if not df.empty and df['v'].sum() > 0:
                        df_sorted = df.sort_values('v', ascending=False).head(30)[['證券代號', '證券名稱', '收盤價', 'v']]
                        df_sorted.columns = ['證券代號', '證券名稱', '收盤價', '成交金額']
                        return df_sorted
        return pd.DataFrame()

    def get_otc(date_str=""):
        res = safe_get_json_fallback(f"https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php?l=zh-tw&o=json&d={date_str}", HEADERS)
        data_otc = res.get('aaData', []) or (res.get('tables', [{}])[0].get('data', []) if 'tables' in res else [])
        if data_otc:
            df = pd.DataFrame(data_otc)
            cv = 9 if df.shape[1] >= 10 else df.shape[1] - 2
            df['v'] = pd.to_numeric(df[cv].astype(str).str.replace(',',''), errors='coerce')
            if not df.empty and df['v'].sum() > 0:
                df_sorted = df.sort_values('v', ascending=False).head(30)[[0, 1, 2, 'v']]
                df_sorted.columns = ['證券代號', '證券名稱', '收盤價', '成交金額']
                return df_sorted
        return pd.DataFrame()

    today = datetime.datetime.now(datetime.timezone.utc).astimezone(datetime.timezone(datetime.timedelta(hours=8)))
    for i in range(7):
        tse_df = get_tse((today - datetime.timedelta(days=i)).strftime('%Y%m%d') if i > 0 else "")
        if not tse_df.empty: break
    for i in range(7):
        otc_df = get_otc((today - datetime.timedelta(days=i)).strftime(f'{today.year - 1911}/%m/%d') if i > 0 else "")
        if not otc_df.empty: break
    return tse_df, otc_df

@st.cache_data(ttl=300)
def get_hot_rank_ids():
    tse_df, otc_df = fetch_top15_ranking()
    hot_ids = set()
    if not tse_df.empty: hot_ids.update(tse_df['證券代號'].tolist())
    if not otc_df.empty: hot_ids.update(otc_df['證券代號'].tolist())
    return hot_ids

# === 8. 技術指標計算 ===
def calculate_kd(df):
    if len(df) < 9: return df
    df['9_min'] = df['Low'].rolling(window=9).min()
    df['9_max'] = df['High'].rolling(window=9).max()
    df['RSV'] = (df['Close'] - df['9_min']) / (df['9_max'] - df['9_min']) * 100
    k_v, d_v, k, d = [], [], 50.0, 50.0
    for rsv in df['RSV']:
        if pd.isna(rsv):
            k_v.append(50.0); d_v.append(50.0)
        else:
            k = (2/3) * k + (1/3) * rsv
            d = (2/3) * d + (1/3) * k
            k_v.append(k); d_v.append(d)
    df['K'], df['D'] = k_v, d_v
    return df

def calculate_macd(df):
    exp1 = df['Close'].ewm(span=12, adjust=False).mean()
    exp2 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp1 - exp2
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['Hist'] = df['MACD'] - df['Signal']
    return df

@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
def fetch_fugle_api(symbol):
    res = requests.get(f"https://api.fugle.tw/marketdata/v1.0/stock/intraday/quote/{symbol}", headers={"X-API-KEY": FUGLE_API_KEY}, timeout=5, verify=False)
    res.raise_for_status()
    return res.json()

def get_fugle_realtime(symbol):
    try:
        data = fetch_fugle_api(symbol)
        return data.get('closePrice'), data.get('total', {}).get('tradeVolume', 0)
    except: return None, None

def fetch_fast_price(symbol):
    fc, _ = get_fugle_realtime(str(symbol))
    if fc: return fc
    try:
        df = yf.Ticker(CLEAN_TO_FULL_MAP.get(str(symbol), f"{symbol}.TW")).history(period="1d")
        if not df.empty: return round(df['Close'].iloc[-1], 2)
    except: pass
    return "---"

def estimate_vwap(symbol, days):
    if days <= 0 or not isinstance(days, int): return "---"
    try:
        df = yf.Ticker(CLEAN_TO_FULL_MAP.get(str(symbol), f"{symbol}.TW")).history(period="1mo")
        if len(df) >= days:
            recent = df.tail(days)
            return round((recent['Close'] * recent['Volume']).sum() / recent['Volume'].sum(), 2)
    except: pass
    return "---"

# === 9. 基本面與新聞 ===
def get_fundamentals_and_news(symbol):
    try:
        tkr = yf.Ticker(CLEAN_TO_FULL_MAP.get(str(symbol), f"{symbol}.TW"))
        info = tkr.info
        eps = info.get('trailingEps', '---')
        pe = info.get('trailingPE', '---')
        rev_growth = info.get('revenueGrowth', None)
        rev_growth_str = f"{rev_growth * 100:.2f} %" if rev_growth is not None else "---"
        news = []
        try:
            name = STOCKS_DICT.get(CLEAN_TO_FULL_MAP.get(str(symbol), f"{symbol}.TW"), "").replace(" ", "")
            res = requests.get(f"https://news.google.com/rss/search?q={symbol}+{name}+股市&hl=zh-TW&gl=TW&ceid=TW:zh-Hant", headers=HEADERS, timeout=5)
            root = ET.fromstring(res.content)
            for item in root.findall('.//item')[:5]:
                news.append({'title': item.find('title').text.rsplit(' - ', 1)[0], 'link': item.find('link').text if item.find('link') is not None else "#"})
        except: pass
        return eps, pe, rev_growth_str, news
    except: return "---", "---", "---", []

def ai_news_sentiment(news_list):
    if not news_list: return "⚪ 尚無近期外電或財經新聞可供分析。"
    score = 0
    formatted_news = []
    for n in news_list:
        formatted_news.append(f"- [{n.get('title', '')}]({n.get('link', '#')})")
        for w in ['增', '漲', '高', '好', '強', '大單', '受惠', '利多', '新高', '突破', '成長', '看好']:
            if w in n.get('title', ''): score += 1
        for w in ['減', '跌', '低', '壞', '差', '弱', '砍單', '衰退', '利空', '破底', '下修', '看壞']:
            if w in n.get('title', ''): score -= 1
    if score >= 2: conclusion = "🟢 **【AI 判定：偏多】** 近期新聞頻釋利多。"
    elif score <= -2: conclusion = "🔴 **【AI 判定：偏空】** 近期新聞出現雜音或利空。"
    else: conclusion = "🟡 **【AI 判定：中性】** 近期新聞無極端多空方向。"
    return f"{conclusion}\n\n**📰 近期熱門新聞標題：**\n" + "\n".join(formatted_news)

@st.cache_data(ttl=3600)
def get_inst_data():
    inst_map = {}
    try:
        r1 = safe_get_json_fallback("https://www.twse.com.tw/fund/T86?response=json&selectType=ALLBUT0999", HEADERS)
        if 'data' in r1:
            for d in r1['data']: inst_map[d[0].strip()] = int(d[2].replace(',', '')) + int(d[10].replace(',', ''))
        r2 = safe_get_json_fallback("https://www.tpex.org.tw/web/stock/fund/T86/T86_result.php?l=zh-tw&o=json", HEADERS)
        if 'aaData' in r2:
            for d in r2['aaData']: inst_map[d[0].strip()] = int(d[8].replace(',', '')) + int(d[10].replace(',', ''))
    except: pass
    return inst_map

@st.cache_data(ttl=3600)
def fetch_co_buying_radar():
    co_buy_list = []
    try:
        res_twse = safe_get_json_fallback("https://www.twse.com.tw/fund/T86?response=json&selectType=ALLBUT0999", HEADERS)
        if 'data' in res_twse and 'fields' in res_twse:
            fields = res_twse['fields']
            idx_code = fields.index("證券代號") if "證券代號" in fields else 0
            idx_name = fields.index("證券名稱") if "證券名稱" in fields else 1
            idx_foreign = next((i for i, f in enumerate(fields) if "外陸資買賣超" in f), 4)
            idx_trust = next((i for i, f in enumerate(fields) if "投信買賣超" in f), 10)
            for d in res_twse['data']:
                try:
                    f_net = int(str(d[idx_foreign]).replace(',', '')) // 1000
                    t_net = int(str(d[idx_trust]).replace(',', '')) // 1000
                    if f_net > 0 and t_net > 0:
                        co_buy_list.append({"代號": d[idx_code].strip(), "名稱": d[idx_name].strip(), "外資買賣超(張)": f_net, "投信買賣超(張)": t_net, "市場": "上市"})
                except: pass

        res_tpex = safe_get_json_fallback("https://www.tpex.org.tw/web/stock/fund/T86/T86_result.php?l=zh-tw&o=json", HEADERS)
        if 'aaData' in res_tpex:
            for d in res_tpex['aaData']:
                try:
                    f_net = int(str(d[4]).replace(',', '')) // 1000
                    t_net = int(str(d[7]).replace(',', '')) // 1000
                    if f_net > 0 and t_net > 0:
                        co_buy_list.append({"代號": d[0].strip(), "名稱": d[1].strip(), "外資買賣超(張)": f_net, "投信買賣超(張)": t_net, "市場": "上櫃"})
                except: pass
    except: pass
    df = pd.DataFrame(co_buy_list)
    if not df.empty:
        df['合計買超(張)'] = df['外資買賣超(張)'] + df['投信買賣超(張)']
        df = df.sort_values(by='合計買超(張)', ascending=False).reset_index(drop=True)
    return df

# === 10. 雷達與各項診斷圖表邏輯 ===
def analyst_three_line_macd_scanner(clean_id, df_ticker, full_id, inst_map, is_bearish=False):
    try:
        df = df_ticker.copy()
        if df.empty or len(df) < 65: return None

        fc, fv = get_fugle_realtime(clean_id)
        if fc:
            df.iloc[-1, df.columns.get_loc('Close')] = fc
            if fv: df.iloc[-1, df.columns.get_loc('Volume')] = fv

        c = df['Close'].iloc[-1]
        v = df['Volume'].iloc[-1]
        v5_avg = df['Volume'].iloc[-6:-1].mean()

        if v5_avg < 500000: return None 

        df['5MA'] = df['Close'].rolling(5).mean()
        df['10MA'] = df['Close'].rolling(10).mean()
        df['20MA'] = df['Close'].rolling(20).mean()

        df['EMA12'] = df['Close'].ewm(span=12, adjust=False).mean()
        df['EMA26'] = df['Close'].ewm(span=26, adjust=False).mean()
        df['DIF'] = df['EMA12'] - df['EMA26']
        df['MACD'] = df['DIF'].ewm(span=9, adjust=False).mean()

        is_three_line_bull = (df['5MA'].iloc[-1] > df['10MA'].iloc[-1] > df['20MA'].iloc[-1])
        is_macd_above_zero = (df['DIF'].iloc[-1] > 0) and (df['MACD'].iloc[-1] > 0)
        is_macd_golden = (df['DIF'].iloc[-1] > df['MACD'].iloc[-1]) 

        if is_three_line_bull and is_macd_above_zero and is_macd_golden:
            if is_bearish and inst_map.get(clean_id, 0) <= 0: return None

            inst_val = inst_map.get(clean_id, 0)
            chip_status = f"🔴 大戶進駐 ({inst_val:,}張)" if inst_val > 0 else "⚪ 散戶/主力盤"
            name = STOCKS_DICT.get(full_id, clean_id)
            chart_url = f"https://tw.stock.yahoo.com/quote/{clean_id}/technical-analysis"

            prev_bull = (df['5MA'].iloc[-2] > df['10MA'].iloc[-2] > df['20MA'].iloc[-2])
            prev_zero = (df['DIF'].iloc[-2] > 0) and (df['MACD'].iloc[-2] > 0)
            is_fresh_start = not (prev_bull and prev_zero)

            return {
                '標的': f"{clean_id} {name}",
                '看盤連結': chart_url,
                '即時收盤價': round(c, 2),
                '引擎型態': "🔥 剛觸發！三線零軸共振" if is_fresh_start else "🌟 三線翻多+雙線零軸上",
                '快線(DIF)': round(df['DIF'].iloc[-1], 2),
                '慢線(MACD)': round(df['MACD'].iloc[-1], 2),
                '籌碼狀態': chip_status,
                '戰鬥評價': "🚀 主升段波段發動點"
            }
    except: return None

def plot_three_line_macd_chart(symbol):
    try:
        full_id = CLEAN_TO_FULL_MAP.get(str(symbol), f"{symbol}.TW")
        df = yf.Ticker(full_id).history(period="6mo")
        if df.empty:
            st.error("找不到該標的資料")
            return

        df['5MA'] = df['Close'].rolling(window=5).mean()
        df['10MA'] = df['Close'].rolling(window=10).mean()
        df['20MA'] = df['Close'].rolling(window=20).mean()

        df['EMA12'] = df['Close'].ewm(span=12, adjust=False).mean()
        df['EMA26'] = df['Close'].ewm(span=26, adjust=False).mean()
        df['DIF'] = df['EMA12'] - df['EMA26']
        df['MACD'] = df['DIF'].ewm(span=9, adjust=False).mean()
        df['OSC'] = df['DIF'] - df['MACD']
        df.dropna(inplace=True)

        fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                            vertical_spacing=0.03, subplot_titles=(f'{symbol} K線與三線多空', 'MACD (零軸指標)'),
                            row_width=[0.3, 0.7])

        fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'],
                                     low=df['Low'], close=df['Close'], name='K線'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['5MA'], mode='lines', name='短線 (5MA)', line=dict(color='orange')), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['10MA'], mode='lines', name='中線 (10MA)', line=dict(color='deepskyblue')), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['20MA'], mode='lines', name='長線 (20MA)', line=dict(color='red')), row=1, col=1)

        fig.add_trace(go.Bar(x=df.index, y=df['OSC'], name='OSC 柱狀圖', marker_color=np.where(df['OSC']>0, '#ff4b4b', '#00cc96')), row=2, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['DIF'], mode='lines', name='DIF (快線)', line=dict(color='orange')), row=2, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['MACD'], mode='lines', name='MACD (慢線)', line=dict(color='deepskyblue')), row=2, col=1)
        fig.add_hline(y=0, line_dash="dash", line_color="white", row=2, col=1)

        fig.update_layout(height=700, template="plotly_dark", xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"繪圖發生錯誤: {e}")

def analyze_stock_score_v2(clean_id, df_ticker, full_id, inst_map, hot_list, is_bearish=False):
    try:
        df = df_ticker.copy()
        if df.empty or len(df) < 65: return None
        fc, fv = get_fugle_realtime(clean_id)
        if fc:
            df.iloc[-1, df.columns.get_loc('Close')] = fc
            if fv: df.iloc[-1, df.columns.get_loc('Volume')] = fv
        
        c = df['Close'].iloc[-1]
        v = df['Volume'].iloc[-1]
        v5 = df['Volume'].iloc[-6:-1].mean()
        if v5 < 1000000: return None
        
        df['MA5'] = df['Close'].rolling(5).mean()
        df['MA20'] = df['Close'].rolling(20).mean()
        df['MA60'] = df['Close'].rolling(60).mean()
        
        if is_bearish:
            if c < df['MA60'].iloc[-1]: return None
            if inst_map.get(clean_id, 0) <= 0: return None
            
        df = calculate_kd(df)
        df = calculate_macd(df)
        
        return_5d = (c / df['Close'].iloc[-6]) - 1 if len(df) >= 6 else 0
        bias_20 = (c / df['MA20'].iloc[-1]) - 1
        is_warning = return_5d > 0.25 or bias_20 > 0.30
        upper_shadow_pct = (df['High'].iloc[-1] / c) - 1
        is_daytrader_trap = (v > v5 * 3) and (upper_shadow_pct > 0.04)
        
        s, tags = 0, []
        if c > df['MA5'].iloc[-1] > df['MA20'].iloc[-1] > df['MA60'].iloc[-1]: s+=1; tags.append("[均線多頭]")
        if df['MA20'].iloc[-1] > df['MA20'].iloc[-2]: s+=1; tags.append("[月線向上]")
        if v > v5 * 1.5: s+=1; tags.append("[爆量攻擊]")
        if df['K'].iloc[-1] > df['D'].iloc[-1] and df['K'].iloc[-2] <= df['D'].iloc[-2]: s+=1; tags.append("[KD金叉]")
        if df['Hist'].iloc[-1] > 0 and df['Hist'].iloc[-1] > df['Hist'].iloc[-2]: s+=1; tags.append("[MACD強勢]")
        if c > df['High'].iloc[-21:-1].max(): s+=1; tags.append("[創20日新高]")
        
        is_higher_low = df['Low'].iloc[-1] >= df['Low'].iloc[-2]
        is_higher_high = df['High'].iloc[-1] > df['High'].iloc[-2]
        if is_higher_low and is_higher_high and c > df['MA20'].iloc[-1]:
            s+=1; tags.append("👑[強勢底底高架構]")
            
        if clean_id in hot_list: tags.append("🔥[排行熱門]")
        inst_val = inst_map.get(clean_id, 0)
        if inst_val > 500: tags.append("🔴[大戶進駐]")
        if is_warning: tags.append("🚨[處置警戒]")
        if is_daytrader_trap: tags.append("🪤[隔日沖倒貨區]")
        
        risk_level = "🚨 高風險 (處置前兆)" if is_warning else ("⚠️ 留意隔日沖砸盤" if is_daytrader_trap else "✅ 安全")
        star_display = ("🌟" * s) + ("⚫" * (7 - s)) if s > 0 else "💤 盤整 (無星)"
        
        return {
            '標的': f"{clean_id} {STOCKS_DICT.get(full_id, clean_id)}", '看盤連結': f"https://tw.stock.yahoo.com/quote/{clean_id}/technical-analysis",
            '星等': star_display, '收盤': round(c,2), '籌碼大戶(張)': f"{inst_val:,}" if inst_val != 0 else "--", 
            '今日量(張)': int(v/1000), '觸發條件': " ".join(tags), '星星數': s, '處置與籌碼風險': risk_level
        }
    except: return None

def bearish_breakdown_scanner(clean_id, df_ticker, full_id, inst_map):
    try:
        df = df_ticker.copy()
        if df.empty or len(df) < 65: return None
        fc, fv = get_fugle_realtime(clean_id)
        if fc:
            df.iloc[-1, df.columns.get_loc('Close')] = fc
            if fv: df.iloc[-1, df.columns.get_loc('Volume')] = fv
            
        c = df['Close'].iloc[-1]
        df['MA20'] = df['Close'].rolling(20).mean()
        df['MA60'] = df['Close'].rolling(60).mean()
        is_bear_trend = (c < df['MA20'].iloc[-1] < df['MA60'].iloc[-1])
        is_ma_going_down = (df['MA20'].iloc[-1] < df['MA20'].iloc[-3])
        
        now_tw = datetime.datetime.now(datetime.timezone.utc).astimezone(datetime.timezone(datetime.timedelta(hours=8)))
        recent_10d_low = df['Low'].iloc[-12:-2].min() if (now_tw.hour < 14 and now_tw.weekday() < 5) else df['Low'].iloc[-11:-1].min()
        is_breaking_down = c < recent_10d_low
        
        inst_val = inst_map.get(clean_id, 0)
        is_inst_dumping = inst_val < -300
        
        if is_bear_trend and is_ma_going_down and is_breaking_down and is_inst_dumping:
            return {
                '標的': f"{clean_id} {STOCKS_DICT.get(full_id, clean_id)}", '看盤連結': f"https://tw.stock.yahoo.com/quote/{clean_id}/technical-analysis",
                '即時收盤價': round(c, 2), '引擎型態': "☠️ 斷頭破底 (均線下彎+破底)", '籌碼狀態': f"🟢 大戶提款 ({inst_val:,}張)", '戰鬥評價': "🚨 強烈建議避開或列入空方觀察"
            }
    except: return None

def ultimate_breakout_scanner(clean_id, df_ticker, full_id, inst_map, is_bearish=False):
    try:
        df = df_ticker.copy()
        if df.empty or len(df) < 65: return None
        fc, fv = get_fugle_realtime(clean_id)
        if fc:
            df.iloc[-1, df.columns.get_loc('Close')] = fc
            if fv: df.iloc[-1, df.columns.get_loc('Volume')] = fv
            
        c = df['Close'].iloc[-1]
        v = df['Volume'].iloc[-1]
        
        now_tw = datetime.datetime.now(datetime.timezone.utc).astimezone(datetime.timezone(datetime.timedelta(hours=8)))
        is_market_closed = now_tw.hour >= 14 or now_tw.weekday() >= 5
        
        if is_market_closed:
            v5_avg = df['Volume'].iloc[-7:-2].mean()
            recent_10d_high = df['High'].iloc[-12:-2].max()
            recent_10d_low = df['Low'].iloc[-12:-2].min()
            is_breaking_high = c >= df['High'].iloc[-22:-2].max()
        else:
            v5_avg = df['Volume'].iloc[-6:-1].mean()
            recent_10d_high = df['High'].iloc[-11:-1].max()
            recent_10d_low = df['Low'].iloc[-11:-1].min()
            is_breaking_high = c >= df['High'].iloc[-21:-1].max()

        if v5_avg < 500000: return None
        df['MA5'] = df['Close'].rolling(5).mean()
        df['MA20'] = df['Close'].rolling(20).mean()
        df['MA60'] = df['Close'].rolling(60).mean()
        
        if is_bearish and inst_map.get(clean_id, 0) <= 0: return None
        is_bull_trend = (df['MA5'].iloc[-1] > df['MA20'].iloc[-1] > df['MA60'].iloc[-1])
        consolidation_pct = (recent_10d_high - recent_10d_low) / recent_10d_low
        is_tight_consolidation = consolidation_pct < 0.08 
        is_volume_explosion = v > (v5_avg * 2.5)
        
        if is_bull_trend and is_tight_consolidation and is_breaking_high and is_volume_explosion:
            inst_val = inst_map.get(clean_id, 0)
            return {
                '標的': f"{clean_id} {STOCKS_DICT.get(full_id, clean_id)}", '看盤連結': f"https://tw.stock.yahoo.com/quote/{clean_id}/technical-analysis", 
                '即時收盤價': round(c, 2), '引擎型態': "⚡ 旱地拔蔥 (壓縮突破)", '今日爆發量(張)': int(v/1000), 
                '均量倍數': f"{v/v5_avg:.1f} 倍", '關鍵數據': f"壓縮震幅 {consolidation_pct*100:.1f}%",
                '籌碼狀態': f"🔴 大戶進場 ({inst_val:,}張)" if inst_val > 200 else "⚪ 偏向純主力/散戶", '戰鬥評價': "🚀 終極起漲點確認"
            }
    except: return None

def short_squeeze_moat_scanner(clean_id, df_ticker, full_id, inst_map, is_bearish=False):
    try:
        df = df_ticker.copy()
        if df.empty or len(df) < 65: return None
        fc, fv = get_fugle_realtime(clean_id)
        if fc:
            df.iloc[-1, df.columns.get_loc('Close')] = fc
            if fv: df.iloc[-1, df.columns.get_loc('Volume')] = fv
            
        c = df['Close'].iloc[-1]
        v = df['Volume'].iloc[-1]
        
        df['MA20'] = df['Close'].rolling(20).mean()
        df['MA60'] = df['Close'].rolling(60).mean()
        df = calculate_kd(df)
        
        if is_bearish and inst_map.get(clean_id, 0) <= 0: return None
        if df['MA20'].iloc[-1] <= df['MA20'].iloc[-3] or df['MA60'].iloc[-1] <= df['MA60'].iloc[-3]: return None
        
        m20 = df['MA20'].iloc[-1]
        deviation_m20 = abs(c - m20) / m20
        is_touching_moat = deviation_m20 <= 0.022
        recent_3d_max_vol = df['Volume'].iloc[-4:-1].max()
        past_attack_max_vol = df['Volume'].iloc[-25:-4].max()
        is_volume_shrinking = recent_3d_max_vol < (past_attack_max_vol * 0.45)
        is_fire_up = v > df['Volume'].iloc[-2] and df['K'].iloc[-1] > df['D'].iloc[-1]
        
        if is_touching_moat and is_volume_shrinking and is_fire_up:
            inst_val = inst_map.get(clean_id, 0)
            return {
                '標的': f"{clean_id} {STOCKS_DICT.get(full_id, clean_id)}", '看盤連結': f"https://tw.stock.yahoo.com/quote/{clean_id}/technical-analysis", 
                '即時收盤價': round(c, 2), '引擎型態': "👑 主升段回踩 (軋空起飛)", '今日爆發量(張)': int(v/1000), 
                '均量倍數': f"量止跌回升 ({v/df['Volume'].iloc[-2]:.1f}倍)", '關鍵數據': f"距月線僅 {deviation_m20*100:.1f}%",
                '籌碼狀態': f"🔴 大戶進場 ({inst_val:,}張)" if inst_val > 300 else "⚪ 主力防守盤", '戰鬥評價': "🔥 鴨頭鎖碼・準備開飆"
            }
    except: return None

def plot_advanced_chart_with_vpvr(symbol, cost_price, period="6mo"):
    full_id = CLEAN_TO_FULL_MAP.get(str(symbol), f"{symbol}.TW")
    df = yf.Ticker(full_id).history(period=period)
    df.dropna(subset=['Close'], inplace=True)
    if not df.empty:
        if len(df) >= 9: df = calculate_kd(df)
        bins = np.linspace(df['Low'].min(), df['High'].max(), num=40)
        df['Price_Bin'] = pd.cut(df['Close'], bins=bins)
        vp = df.groupby('Price_Bin')['Volume'].sum().reset_index()
        vp['Bin_Center'] = vp['Price_Bin'].apply(lambda x: x.mid).astype(float)
        
        fig = make_subplots(rows=2, cols=2, shared_xaxes=True, shared_yaxes=True, row_heights=[0.7, 0.3], column_widths=[0.8, 0.2], horizontal_spacing=0.01, vertical_spacing=0.05)
        fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='K線'), row=1, col=1)
        fig.add_trace(go.Bar(x=vp['Volume'], y=vp['Bin_Center'], orientation='h', name='籌碼密集區', marker_color='rgba(255, 209, 102, 0.5)'), row=1, col=2)
        if 'K' in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df['K'], name='K', line=dict(color='yellow')), row=2, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['D'], name='D', line=dict(color='cyan')), row=2, col=1)
        if cost_price > 0:
            fig.add_hline(y=cost_price, line_dash="dash", line_color="#00cc96", annotation_text=f"防線 {cost_price}", annotation_position="top left", row=1, col=1)
        fig.update_layout(height=700, template="plotly_dark", xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=30, b=10), showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    else: st.error("資料讀取失敗，無法繪製圖表。")

def diagnose_holding(ticker_in):
    try:
        clean = ticker_in.replace('.TW','').replace('.TWO','')
        full_id = CLEAN_TO_FULL_MAP.get(clean, f"{clean}.TW")
        df = yf.Ticker(full_id).history(period="6mo")
        df.dropna(subset=['Close'], inplace=True)
        if df.empty or len(df) < 30: return None
        fc, _ = get_fugle_realtime(clean)
        if fc: df.iloc[-1, df.columns.get_loc('Close')] = fc
        df['MA5'] = df['Close'].rolling(5).mean(); df['MA20'] = df['Close'].rolling(20).mean(); df = calculate_kd(df)
        c, m5, m20 = df['Close'].iloc[-1], df['MA5'].iloc[-1], df['MA20'].iloc[-1]
        k, d = df['K'].iloc[-1], df['D'].iloc[-1]
        v5_lots = int(df['Volume'].iloc[-6:-1].mean() / 1000)
        
        status, action = [], "🟢 續抱 (趨勢健康)"
        if c < m20: status.append("⚠️ 跌破月線"); action = "🛑 建議停損/停利"
        elif c < m5: status.append("⚠️ 跌破5日線"); action = "🟡 建議先減碼一半"
        if k < d and df['K'].iloc[-2] >= df['D'].iloc[-2] and k > 70: status.append("⚠️ KD高檔死叉"); action = "🟡 建議拔檔減碼"
        if not status: status.append("✅ 強勢多頭")
        return {
            "標的": clean, "收盤": round(c,2), "MA5": round(m5,2), "MA20": round(m20,2), 
            "KD": f"K:{round(k,1)}/D:{round(d,1)}", "状况": "、".join(status), "建議": action, "5日均量": max(1, v5_lots)
        }
    except: return None

def analyze_dynamic_moat(symbol, cost_price):
    try:
        clean = symbol.replace('.TW','').replace('.TWO','')
        full_id = CLEAN_TO_FULL_MAP.get(clean, f"{clean}.TW")
        df = yf.Ticker(full_id).history(period="3mo")
        if df.empty or len(df) < 20: return None
        current_price = df['Close'].iloc[-1]
        recent_df = df.tail(20)
        bull_candles = recent_df[recent_df['Close'] > recent_df['Open']]
        if not bull_candles.empty:
            max_vol_idx = bull_candles['Volume'].idxmax()
            key_candle = bull_candles.loc[max_vol_idx]
            support_price = round((key_candle['High'] + key_candle['Low']) / 2, 2)
            date_str = max_vol_idx.strftime('%Y-%m-%d')
        else:
            support_price = round(df['Close'].rolling(20).mean().iloc[-1], 2)
            date_str = "月線 (近期無帶量紅K)"
        return {"current_price": round(current_price, 2), "support_price": support_price, "key_date": date_str, "cost_price": cost_price}
    except: return None

def run_simple_backtest(symbol):
    try:
        clean = symbol.replace('.TW','').replace('.TWO','')
        full_id = CLEAN_TO_FULL_MAP.get(clean, f"{clean}.TW")
        df = yf.Ticker(full_id).history(period="2y")
        if len(df) < 60: return None
        df['MA20'] = df['Close'].rolling(20).mean()
        df = df.dropna()
        df['Signal'] = 0
        df.loc[df['Close'] > df['MA20'], 'Signal'] = 1
        df['Return'] = df['Close'].pct_change()
        df['Strategy_Return'] = df['Signal'].shift(1) * df['Return']
        df['Equity'] = (1 + df['Strategy_Return'].fillna(0)).cumprod() * 100
        win_rate = len(df[df['Strategy_Return'] > 0]) / len(df[df['Strategy_Return'] != 0]) if len(df[df['Strategy_Return'] != 0]) > 0 else 0
        total_return = df['Equity'].iloc[-1] - 100
        return df, win_rate, total_return
    except: return None

# === 11. 經理人籌碼追蹤 ===
def fetch_today_holdings_from_api(etf_code="00981A"):
    today = datetime.datetime.now(datetime.timezone.utc).astimezone(datetime.timezone(datetime.timedelta(hours=8))).strftime('%Y-%m-%d')
    new_data = []
    res = safe_get_json_fallback(f"https://www.twse.com.tw/fund/ETF8?response=json&code={etf_code}", HEADERS)
    if res and 'data' in res and len(res['data']) > 0:
        for row in res['data']:
            new_data.append([today, str(row[0]).strip(), str(row[1]).strip(), int(row[2].replace(',', '')) // 1000])
    return pd.DataFrame(new_data, columns=['日期', '代號', '股票名稱', '持有張數'])

def get_00981a_holdings_history(force_refresh=False):
    db_path = "00981A_holdings_db.csv"
    today_str = datetime.datetime.now(datetime.timezone.utc).astimezone(datetime.timezone(datetime.timedelta(hours=8))).strftime('%Y-%m-%d')
    if os.path.exists(db_path): df_history = pd.read_csv(db_path)
    else: df_history = pd.DataFrame(columns=['日期', '代號', '股票名稱', '持有張數'])
        
    if not df_history.empty and today_str in df_history['日期'].values and not force_refresh: return df_history
    if force_refresh and not df_history.empty: df_history = df_history[df_history['日期'] != today_str]
            
    with st.spinner("🔄 正在從連線獲取經理人今日最新持股..."):
        df_today = fetch_today_holdings_from_api("00981A")
        
    if not df_today.empty:
        df_history = pd.concat([df_history, df_today], ignore_index=True)
        df_history.to_csv(db_path, index=False)
        st.toast("✅ 今日持股資料已更新入庫！", icon="🎉")
    elif df_history.empty:
        dates = [(datetime.datetime.now(datetime.timezone.utc).astimezone(datetime.timezone(datetime.timedelta(hours=8))) - datetime.timedelta(days=i)).strftime('%Y-%m-%d') for i in range(3, -1, -1)]
        mock_scenarios = [
            ("2317", "鴻海", [1000, 1500, 2000, 3000]), ("3231", "緯創", [2000, 2000, 2000, 3500]),
            ("2383", "台光電", [3000, 3000, 3500, 4200]), ("6805", "富世達", [200, 400, 800, 1500]), 
            ("3017", "奇鋐", [800, 800, 1200, 1800]), ("2345", "智邦", [1000, 1200, 1500, 1900]),
            ("3533", "嘉澤", [600, 600, 700, 900]), ("2330", "台積電", [8000, 8000, 8000, 8000]),
            ("2454", "聯發科", [1500, 1500, 1500, 1500]), ("3324", "雙鴻", [500, 500, 500, 500]),
            ("2308", "台達電", [5000, 5200, 5500, 4500]), ("2382", "廣達", [4000, 4000, 3000, 2000]),
            ("3034", "聯詠", [1000, 1000, 800, 500]), ("2603", "長榮", [5000, 4000, 3000, 2000]),
            ("3661", "世芯-KY", [400, 400, 400, 200])
        ]
        dummy_rows = []
        for ticker, name, shares in mock_scenarios:
            for i, d in enumerate(dates): dummy_rows.append([d, ticker, f"{name} (測試)", shares[i]])
        return pd.DataFrame(dummy_rows, columns=['日期', '代號', '股票名稱', '持有張數'])
    return df_history

def analyze_manager_moves(df):
    if df.empty: return pd.DataFrame()
    df = df.sort_values(by=['代號', '日期'])
    df['單日買賣超(張)'] = df.groupby('代號')['持有張數'].diff().fillna(0)
    results = []
    for stock_id, group in df.groupby('代號'):
        group = group.sort_values('日期')
        diffs = group['單日買賣超(張)'].tolist()
        consecutive_buy = sum(1 for d in reversed(diffs) if d > 0) if diffs[-1] > 0 else 0
        consecutive_sell = sum(1 for d in reversed(diffs) if d < 0) if diffs[-1] < 0 else 0
        latest_record = group.iloc[-1]
        
        if consecutive_buy > 0: status, days = "🟢 主力連買", consecutive_buy
        elif consecutive_sell > 0: status, days = "🔴 經理人倒貨", consecutive_sell
        else: status, days = "⚪ 靜止觀望", 0
        
        results.append({
            "代號": stock_id, "股票名稱": latest_record['股票名稱'], 
            "看盤連結": f"https://tw.stock.yahoo.com/quote/{stock_id}/technical-analysis",
            "最新持股張數": int(latest_record['持有張數']),
            "今日買賣超(張)": int(latest_record['單日買賣超(張)']), "動向狀態": status, "連續天數": days,
            "連續天數顯示": f"{days} 天" if days > 0 else "-"
        })
    return pd.DataFrame(results).sort_values(by="今日買賣超(張)", ascending=False)

# === 12. 早盤渦輪截擊雷達 ===
async def fetch_fugle_intraday_async(session, clean_id, prev_vol, full_name, is_test_mode):
    try:
        async with session.get(f"https://api.fugle.tw/marketdata/v1.0/stock/intraday/quote/{clean_id}", headers={"X-API-KEY": FUGLE_API_KEY}, timeout=5, ssl=False) as response:
            if response.status != 200: return None
            data = await response.json()
            open_p, close_p, prev_close = data.get('openPrice'), data.get('closePrice'), data.get('previousClose')
            vol_now = data.get('total', {}).get('tradeVolume', 0)
            
            if not open_p or not prev_close: return None
            gap_pct = ((open_p - prev_close) / prev_close) * 100
            cur_pct = ((close_p - prev_close) / prev_close) * 100
            is_breakout_vol = prev_vol > 0 and vol_now > (prev_vol * 0.15)
                
            if is_test_mode or (gap_pct >= 2.0 and cur_pct >= 2.0):
                is_super_strong = close_p >= open_p
                status = "🔥 點火噴出" if is_super_strong else "⚠️ 留上影線"
                if is_breakout_vol: status += " (🌟預估爆量)"
                elif is_test_mode and not (gap_pct >= 2.0 and cur_pct >= 2.0): status = "⚪ 觀察中 (未達標)"
                
                return {
                    "代號": clean_id, "名稱": full_name, "跳空幅度": gap_pct, "即時漲幅": cur_pct,
                    "跳空顯示": f"{gap_pct:.1f}%", "漲幅顯示": f"{cur_pct:.1f}%",
                    "即時價": close_p, "目前累積量": vol_now, "昨日總量": int(prev_vol), "早盤型態": status
                }
    except: return None

async def run_morning_scan_async(valid_list, bulk_data_dict, test_mode):
    async with aiohttp.ClientSession() as session:
        tasks = []
        for t in valid_list:
            df_hist = bulk_data_dict.get(CLEAN_TO_FULL_MAP.get(t, f"{t}.TW"))
            prev_vol = df_hist['Volume'].iloc[-2] if (df_hist is not None and len(df_hist) >= 2 and datetime.datetime.now(datetime.timezone.utc).astimezone(datetime.timezone(datetime.timedelta(hours=8))).hour < 14) else (df_hist['Volume'].iloc[-1] if df_hist is not None else 0)
            tasks.append(fetch_fugle_intraday_async(session, t, prev_vol, STOCKS_DICT.get(CLEAN_TO_FULL_MAP.get(t, f"{t}.TW"), t), test_mode))
        results = await asyncio.gather(*tasks)
        return [r for r in results if r]

def run_async(coro):
    try: loop = asyncio.get_event_loop()
    except RuntimeError: loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)

# === 13. 側邊欄與大盤風向球 ===
st.sidebar.title("📡 阿綜專屬：軍規操盤台 V13.0")

st.sidebar.markdown("---")
st.sidebar.subheader("🌍 大盤多空風向球")
tw_c, tw_m20, tw_status = get_market_breadth()
is_bearish = "🔴" in tw_status or "偏空" in tw_status

if tw_c is not None:
    st.sidebar.metric("加權指數", f"{tw_c:,.0f}")
    if not is_bearish: st.sidebar.success(tw_status)
    else: st.sidebar.error(tw_status)
else:
    st.sidebar.warning(tw_status)

us_market_brain()
adr_premium_calculator()
ai_voice_report(tw_status if tw_status else "系統連線中")
line_notify_setting()

st.sidebar.markdown("---")

main_page = st.sidebar.radio("跳轉頁面", [
    "🎯 股神六星雷達系統", 
    "📈 股神三線零軸 (宇明流)",
    "📉 弱勢破底雷達 (防禦/空方)", 
    "🌐 全球金融戰情室",
    "🤝 土洋主力共振雷達", 
    "🏢 基本面與 AI 診斷", 
    "🕵️‍♂️ 00981A 經理人跟單雷達",
    "☠️ 隔日沖分點照妖鏡",
    "🚀 早盤渦輪截擊"
])

st.sidebar.subheader("🧼 減法優化濾網")
hide_complex_tech = st.sidebar.toggle("🧼 執行減法哲學 (隱藏進階技術欄位)", value=False)
mobile_mode = st.sidebar.toggle("📱 啟動極簡戰鬥模式", value=False)

if main_page in ["🎯 股神六星雷達系統", "📈 股神三線零軸 (宇明流)", "📉 弱勢破底雷達 (防禦/空方)", "🤝 土洋主力共振雷達", "☠️ 隔日沖分點照妖鏡", "🚀 早盤渦輪截擊"]:
    st.sidebar.subheader("⚙️ 自選股水庫")
    def_tickers = ", ".join([k.split('.')[0] for k in STOCKS_DICT.keys()])
    u_input = st.sidebar.text_area("代號庫：", value=def_tickers, height=150)
    s_list = [t.strip() for t in u_input.replace('，',',').split(',') if t.strip()]

st.sidebar.markdown("---")
if st.sidebar.button("🧹 清除系統快取 (強制重抓)", use_container_width=True):
    st.cache_data.clear()
    st.sidebar.success("快取已清除！請重新掃描。")
    time.sleep(1)
    st.rerun()

st.sidebar.markdown(f"👁️ **累積瀏覽次數：** `{get_and_increment_view_count()}` 次")

# ==========================================
# 分頁 1: 🎯 股神六星雷達系統
# ==========================================
if main_page == "🎯 股神六星雷達系統":
    if is_bearish: st.error("⛔ **【系統防呆斷油機制已觸發】** 當前大盤處於偏空逆風環境。嚴防逆風做多遭倒貨。")
    
    st.markdown("### 🎯 買進策略：共振發動")
    st.info("💡 **【系統操盤核心心法】**\n1. 不預測、一眼定多空。\n2. 均線是保護傘，嚴守停損紀律。")

    if mobile_mode:
        st.title("📱 戰鬥儀表板")
        col_m1, col_m2 = st.columns(2)
        with col_m1: btn_normal = st.button("🚀 六星共振掃描", use_container_width=True)
        with col_m2: btn_ultimate = st.button("🔥 終極飆股掃描", use_container_width=True, type="primary")

        if btn_normal:
            inst_map = get_inst_data(); hot_list = get_hot_rank_ids(); res, danger_res = [], []
            with st.spinner("🚀 啟動引擎下載中..."):
                full_ids = [CLEAN_TO_FULL_MAP.get(t, f"{t}.TW") for t in s_list]
                bulk_data_dict = fetch_bulk_yf_data(full_ids, period="1y")
                with ThreadPoolExecutor(max_workers=5) as ex:
                    futs = [ex.submit(analyze_stock_score_v2, t, bulk_data_dict.get(CLEAN_TO_FULL_MAP.get(t, f"{t}.TW")), CLEAN_TO_FULL_MAP.get(t, f"{t}.TW"), inst_map, hot_list, is_bearish) for t in s_list if CLEAN_TO_FULL_MAP.get(t, f"{t}.TW") in bulk_data_dict]
                    for f in as_completed(futs):
                        r = f.result()
                        if r:
                            if r['星星數'] >= 4: res.append(r)
                            if any(w in r['處置與籌碼風險'] for w in ["風險", "隔日沖", "警戒"]): danger_res.append(r)
            
            st.subheader("🚨 警戒區")
            if danger_res:
                for d in danger_res: st.error(f"**{d['標的']}** | {d['處置與籌碼風險']}")
                
            st.subheader("🔥 今日最強突破 (4星以上)")
            if res:
                df_res = pd.DataFrame(res).sort_values(by=['星星數', '今日量(張)'], ascending=[False, False]).reset_index(drop=True)
                for i, row in df_res.iterrows():
                    st.markdown(f"🏆 **No.{i+1} | {row['標的']}** {row['星等']} (收: {row['收盤']})")

        elif btn_ultimate:
            inst_map = get_inst_data(); breakout_res = []
            with st.spinner("🔥 啟動掃描..."):
                full_ids = [CLEAN_TO_FULL_MAP.get(t, f"{t}.TW") for t in s_list]
                bulk_data_dict = fetch_bulk_yf_data(full_ids, period="1y")
                valid_list = [t for t in s_list if CLEAN_TO_FULL_MAP.get(t, f"{t}.TW") in bulk_data_dict]
                with ThreadPoolExecutor(max_workers=5) as ex:
                    futs = [ex.submit(ultimate_breakout_scanner, t, bulk_data_dict[CLEAN_TO_FULL_MAP.get(t, f"{t}.TW")], CLEAN_TO_FULL_MAP.get(t, f"{t}.TW"), inst_map, is_bearish) for t in valid_list] + \
                           [ex.submit(short_squeeze_moat_scanner, t, bulk_data_dict[CLEAN_TO_FULL_MAP.get(t, f"{t}.TW")], CLEAN_TO_FULL_MAP.get(t, f"{t}.TW"), inst_map, is_bearish) for t in valid_list]
                    for f in as_completed(futs):
                        if f.result(): breakout_res.append(f.result())
            
            st.subheader("🔥 飆股戰報")
            if breakout_res:
                for r in breakout_res: st.markdown(f"🚀 **{r['標的']}** ({r['引擎型態']}) - 收: {r['即時收盤價']}")
    else:
        st.title("📡 阿綜專屬：四維共振終極版")
        t1, t2, t3, t4, t5, t6 = st.tabs(["🎯 六星雷達", "📈 VPVR", "🛡️ 部位診斷", "🚨 處置警戒", "🧪 策略回測", "🚀 終極飆股戰情室"])
        
        with t1:
            if st.button("🚀 啟動即時掃描 (全自動共振分析)", use_container_width=True):
                inst_map = get_inst_data(); hot_list = get_hot_rank_ids(); res, pb = [], st.progress(0)
                with st.spinner("🚀 下載數據中..."):
                    full_ids = [CLEAN_TO_FULL_MAP.get(t, f"{t}.TW") for t in s_list]
                    bulk_data_dict = fetch_bulk_yf_data(full_ids, period="1y")
                    valid_list = [t for t in s_list if CLEAN_TO_FULL_MAP.get(t, f"{t}.TW") in bulk_data_dict]
                    with ThreadPoolExecutor(max_workers=5) as ex:
                        futs = [ex.submit(analyze_stock_score_v2, t, bulk_data_dict[CLEAN_TO_FULL_MAP.get(t, f"{t}.TW")], CLEAN_TO_FULL_MAP.get(t, f"{t}.TW"), inst_map, hot_list, is_bearish) for t in valid_list]
                        for i, f in enumerate(as_completed(futs)):
                            pb.progress((i+1)/len(valid_list))
                            if f.result(): res.append(f.result())
                if res:
                    df = pd.DataFrame(res).sort_values(by=['星星數', '今日量(張)'], ascending=[False, False]).reset_index(drop=True)
                    df.insert(0, '名次', df.index + 1)
                    display_df = df[['名次', '標的', '看盤連結', '星等', '收盤']] if hide_complex_tech else df[['名次', '標的', '看盤連結', '星等', '收盤', '處置與籌碼風險', '籌碼大戶(張)', '今日量(張)', '觸發條件']]
                    st.dataframe(display_df, use_container_width=True, hide_index=True, column_config={"看盤連結": st.column_config.LinkColumn("互動看盤", display_text="📈 點我看圖")})

        with t2:
            st.markdown("### 📈 VPVR 籌碼透視 X 光機")
            col_t2_1, col_t2_2 = st.columns([1, 1])
            with col_t2_1: vpvr_id = st.text_input("🔍 欲透視的股票代號", value="3034", key="vpvr_in")
            with col_t2_2: vpvr_cost = st.number_input("💰 標示您的成本防護線 (輸入 0 則不顯示)", value=0.0, step=1.0)
            if st.button("📈 繪製 VPVR 籌碼透視圖", use_container_width=True): plot_advanced_chart_with_vpvr(vpvr_id, vpvr_cost)

        with t3:
            st.markdown("### 🛡️ 智能部位計算機與波段護城河")
            col_diag, col_calc = st.columns([1, 1])
            with col_diag: d_id = st.text_input("🔍 欲買進標的代號", value="2317", key="diag_in")
            with col_calc:
                capital = st.number_input("💰 本次預計投入總資金 (台幣)", value=500000, step=50000)
                risk_pct = st.slider("⚖️ 單筆可承受最大虧損比例 (%)", 1.0, 5.0, 2.0, 0.5)

            if st.button("🛡️ 執行診斷與資金計算", use_container_width=True):
                r_diag = diagnose_holding(d_id)
                if r_diag:
                    st.markdown(f"### 🎯 {r_diag['標的']} 戰情室")
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("即時價", r_diag['收盤']); c2.metric("5日線", r_diag['MA5']); c3.metric("月線", r_diag['MA20']); c4.metric("KD狀態", r_diag['KD'])
                    if r_diag['收盤'] <= r_diag['MA20']: st.error("⚠️ 目前股價已低於月線，強烈建議不要買進！")
                    else: st.success(f"建議買進張數：{max(1, int((capital * (risk_pct/100)) / ((r_diag['收盤'] - r_diag['MA20']) * 1000)))} 張")
            
            st.markdown("---")
            with st.form("maintenance_log_form"):
                log_stock = st.text_input("🛠️ 工單標的代號", value=d_id)
                log_reason = st.text_input("💡 進場型態與理由", value="")
                log_stop = st.number_input("🛡️ 確定的技術停損防守價", value=0.0, step=0.5)
                log_mood = st.selectbox("🧠 當下進場心理狀態", ["✅ 理智機械化操作", "⚠️ 害怕錯過", "❌ 衝動追高", "💤 試單"])
                if st.form_submit_button("💾 簽收並儲存保養工單") and log_stock and log_reason and log_stop > 0:
                    save_trade_maintenance_log(log_stock, log_reason, log_stop, log_mood)
                    st.toast("🎉 工單已儲存！")
            
            if os.path.exists(MAINTENANCE_LOG_FILE):
                try: st.dataframe(pd.read_csv(MAINTENANCE_LOG_FILE).sort_index(ascending=False), use_container_width=True, hide_index=True)
                except: pass

        with t4:
            st.markdown("### 🚨 處置與隔日沖警戒清單")
            if st.button("⚠️ 掃描全市場過熱標的", use_container_width=True):
                inst_map = get_inst_data(); hot_list = get_hot_rank_ids(); danger_list = []; pb = st.progress(0)
                with st.spinner("掃描中..."):
                    full_ids = [CLEAN_TO_FULL_MAP.get(t, f"{t}.TW") for t in s_list]
                    bulk_data_dict = fetch_bulk_yf_data(full_ids, period="1y")
                    valid_list = [t for t in s_list if CLEAN_TO_FULL_MAP.get(t, f"{t}.TW") in bulk_data_dict]
                    with ThreadPoolExecutor(max_workers=5) as ex:
                        futs = [ex.submit(analyze_stock_score_v2, t, bulk_data_dict[CLEAN_TO_FULL_MAP.get(t, f"{t}.TW")], CLEAN_TO_FULL_MAP.get(t, f"{t}.TW"), inst_map, hot_list, False) for t in valid_list]
                        for i, f in enumerate(as_completed(futs)):
                            pb.progress((i+1)/len(valid_list))
                            res = f.result()
                            if res and ("處置" in res['處置與籌碼風險'] or "隔日沖" in res['處置與籌碼風險']): danger_list.append(res)
                if danger_list: st.dataframe(pd.DataFrame(danger_list)[['標的', '收盤', '處置與籌碼風險', '觸發條件']], use_container_width=True)
                else: st.success("✅ 目前無過熱標的。")

        with t5:
            st.markdown("### 🧪 策略回測實驗室 (2年期)")
            bt_id = st.text_input("🔍 欲回測標的代號", value="2317", key="bt_in")
            if st.button("🧪 執行歷史回測", use_container_width=True):
                res = run_simple_backtest(bt_id)
                if res:
                    df_bt, win_rate, total_ret = res
                    c1, c2 = st.columns(2)
                    c1.metric("策略歷史勝率", f"{win_rate*100:.1f} %"); c2.metric("2年期累積報酬率", f"{total_ret:.1f} %")
                    fig = px.line(df_bt, x=df_bt.index, y='Equity', title=f"{bt_id} 波段策略權益曲線")
                    fig.update_layout(template="plotly_dark")
                    st.plotly_chart(fig, use_container_width=True)

        with t6:
            st.markdown("### 🚀 V13 雙核心飆股戰情室")
            if st.button("🔥 啟動雙核心大飆股獵殺掃描", use_container_width=True, type="primary"):
                inst_map = get_inst_data(); breakout_res = []; pb = st.progress(0)
                with st.spinner("掃描中..."):
                    full_ids = [CLEAN_TO_FULL_MAP.get(t, f"{t}.TW") for t in s_list]
                    bulk_data_dict = fetch_bulk_yf_data(full_ids, period="1y")
                    valid_list = [t for t in s_list if CLEAN_TO_FULL_MAP.get(t, f"{t}.TW") in bulk_data_dict]
                    with ThreadPoolExecutor(max_workers=5) as ex:
                        futs = [ex.submit(ultimate_breakout_scanner, t, bulk_data_dict[CLEAN_TO_FULL_MAP.get(t, f"{t}.TW")], CLEAN_TO_FULL_MAP.get(t, f"{t}.TW"), inst_map, is_bearish) for t in valid_list] + \
                               [ex.submit(short_squeeze_moat_scanner, t, bulk_data_dict[CLEAN_TO_FULL_MAP.get(t, f"{t}.TW")], CLEAN_TO_FULL_MAP.get(t, f"{t}.TW"), inst_map, is_bearish) for t in valid_list]
                        for i, f in enumerate(as_completed(futs)):
                            pb.progress((i+1)/(len(valid_list)*2))
                            if f.result(): breakout_res.append(f.result())
                if breakout_res:
                    st.success(f"🎯 鎖定完成！共抓到 {len(breakout_res)} 檔")
                    df_breakout = pd.DataFrame(breakout_res)
                    display_df = df_breakout[['標的', '看盤連結', '即時收盤價', '引擎型態']] if hide_complex_tech else df_breakout
                    st.dataframe(display_df, use_container_width=True, hide_index=True, column_config={"看盤連結": st.column_config.LinkColumn("互動看盤", display_text="📈 點我看圖")})
                else: st.warning("👀 無符合飆股型態標的。")

# ==========================================
# 分頁 1.5: 📈 股神三線零軸 (新增：宇明流專屬雷達)
# ==========================================
elif main_page == "📈 股神三線零軸 (宇明流)":
    st.title("📈 股神三線零軸雷達 (宇明流還原版)")
    st.info("💡 **核心邏輯**：還原分析師「三線翻多 (5MA>10MA>20MA)」搭配「MACD 雙線站上零軸」的多方波段發動訊號。")

    st.subheader("📊 個股專屬三線零軸 X光機")
    c1, c2 = st.columns([1, 1])
    with c1: chart_id = st.text_input("🔍 輸入標的代號繪製專屬趨勢圖", value="2330", key="ym_chart")
    if st.button("📈 繪製技術圖表", use_container_width=True):
        plot_three_line_macd_chart(chart_id)

    st.divider()

    st.subheader("🚀 全市場三線零軸共振掃描")
    if st.button("🎯 啟動雷達掃描", type="primary", use_container_width=True):
        inst_map = get_inst_data()
        ym_res = []
        pb = st.progress(0)
        
        with st.spinner("🚀 下載自選庫歷史數據中..."):
            full_ids = [CLEAN_TO_FULL_MAP.get(t, f"{t}.TW") for t in s_list]
            bulk_data_dict = fetch_bulk_yf_data(full_ids, period="1y")
            
        with st.spinner("🧠 三線與零軸引擎交叉比對中..."):
            valid_list = [t for t in s_list if CLEAN_TO_FULL_MAP.get(t, f"{t}.TW") in bulk_data_dict]
            with ThreadPoolExecutor(max_workers=5) as ex:
                futs = [ex.submit(analyst_three_line_macd_scanner, t, bulk_data_dict[CLEAN_TO_FULL_MAP.get(t, f"{t}.TW")], CLEAN_TO_FULL_MAP.get(t, f"{t}.TW"), inst_map, is_bearish) for t in valid_list]
                for i, f in enumerate(as_completed(futs)):
                    pb.progress((i+1)/len(valid_list))
                    res = f.result()
                    if res: ym_res.append(res)
                    
        if ym_res:
            df_ym = pd.DataFrame(ym_res).sort_values(by='引擎型態', ascending=True)
            st.success(f"🎯 掃描完成！共抓出 {len(df_ym)} 檔符合三線零軸共振標的！")
            
            def highlight_ym(val):
                if isinstance(val, str):
                    if '剛觸發' in val or '🔥' in val: return 'color: #ff4b4b; font-weight: bold'
                    if '大戶進駐' in val or '🔴' in val: return 'color: #00cc96; font-weight: bold' 
                return ''
                
            st.dataframe(
                df_ym.style.map(highlight_ym, subset=['引擎型態', '籌碼狀態']), 
                use_container_width=True, hide_index=True,
                column_config={"看盤連結": st.column_config.LinkColumn("互動看盤", display_text="📈 點我看圖")}
            )
        else:
            st.warning("✅ 目前盤面自選庫沒有符合「三線多頭且 MACD 站上零軸」的標的。")

# ==========================================
# 分頁 2: 📉 弱勢破底雷達 (防禦/空方)
# ==========================================
elif main_page == "📉 弱勢破底雷達 (防禦/空方)":
    st.title("📉 弱勢破底雷達 (斷頭空方引擎)")
    st.error("⚠️ **【空方防護網】** 尋找「均線下彎、型態破底、法人倒貨」的弱勢標的。")
    if st.button("☠️ 啟動空方破底掃描", use_container_width=True):
        inst_map = get_inst_data(); bearish_res = []; pb = st.progress(0)
        with st.spinner("掃描中..."):
            full_ids = [CLEAN_TO_FULL_MAP.get(t, f"{t}.TW") for t in s_list]
            bulk_data_dict = fetch_bulk_yf_data(full_ids, period="1y")
            valid_list = [t for t in s_list if CLEAN_TO_FULL_MAP.get(t, f"{t}.TW") in bulk_data_dict]
            with ThreadPoolExecutor(max_workers=5) as ex:
                futs = [ex.submit(bearish_breakdown_scanner, t, bulk_data_dict[CLEAN_TO_FULL_MAP.get(t, f"{t}.TW")], CLEAN_TO_FULL_MAP.get(t, f"{t}.TW"), inst_map) for t in valid_list]
                for i, f in enumerate(as_completed(futs)):
                    pb.progress((i+1)/len(valid_list))
                    if f.result(): bearish_res.append(f.result())
        if bearish_res: st.dataframe(pd.DataFrame(bearish_res), use_container_width=True, hide_index=True, column_config={"看盤連結": st.column_config.LinkColumn("互動看盤", display_text="📈 點我看圖")})
        else: st.success("✅ 目前無斷頭破底標的。")

# ==========================================
# 分頁 3: 🌐 全球金融戰情室
# ==========================================
elif main_page == "🌐 全球金融戰情室":
    st.title("🌐 阿綜專屬：全球金融戰情室 (AI旗艦版)")
    tabs = st.tabs(["💀 AI 戰情", "🇹🇼 台股戰略", "🚀 風險雷達", "💎 半導體雷達", "🔄 輪動策略", "🌐 資產配置", "📈 趨勢圖", "🫧 AI 泡沫觀測"])

    with tabs[0]:
        st.subheader("💀 AI 資金掃描雷達")
        col_left, col_right = st.columns([1, 2])
        with col_left:
            st.error("⚠️ 警報：全面翻負")
            st.metric(label="Tech 平均離差", value="-6.55%", delta="-6.55", delta_color="inverse")
        with col_right:
            data = {"名稱": ["納斯達克", "費城半導體", "台灣加權", "半導體ETF", "輝達"], "狀態": ["🟢 弱勢", "🟢 弱勢", "🟢 弱勢", "🟢 弱勢", "🟢 弱勢"], "乖離率(%)": [-4.97, -9.03, -4.57, -7.65, -6.56], "現價": [22078.05, 6352.07, 26434.94, 325.10, 180.64]}
            st.dataframe(pd.DataFrame(data), hide_index=True, use_container_width=True)

    with tabs[1]:
        st.subheader("🇹🇼 台股四大領先指標")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("半導體 (SOXX)", "268.1", "-9.32%", delta_color="inverse")
        col2.metric("內資 (櫃買)", "252.95", "-2.41%", delta_color="inverse")
        col3.metric("美元 (源頭)", "100.11", "0.5%", delta_color="inverse")
        col4.metric("美債 (利率)", "4.11%", "0.37%", delta_color="inverse")

    with tabs[2]:
        st.subheader("🚀 總經與市場風險監控")
        c1, c2, c3 = st.columns(3)
        c1.metric("VIX 恐慌指數", "18.5", "1.2", delta_color="inverse")
        c2.metric("台幣匯率", "32.45", "-0.15", delta_color="inverse")
        c3.metric("Put/Call Ratio", "112.4%", "5.2%", delta_color="normal")

    with tabs[3]:
        st.subheader("💎 核心半導體產業鏈")
        @st.cache_data(ttl=300) 
        def fetch_real_semi_data():
            semi_tickers = {"2330.TW": "2330 台積電", "2454.TW": "2454 聯發科", "NVDA": "NVDA 輝達", "ASML": "ASML 艾司摩爾", "TSM": "台積電 ADR"}
            results = []
            for tk, name in semi_tickers.items():
                try:
                    df = yf.Ticker(tk).history(period="1mo")
                    if not df.empty and len(df) >= 20:
                        df['MA20'] = df['Close'].rolling(20).mean()
                        c, m20 = round(df['Close'].iloc[-1], 2), df['MA20'].iloc[-1]
                        bias = ((c - m20) / m20) * 100
                        results.append({"標的": name, "最新收盤價": c, "月線防守 (20MA)": "✅ 站上" if c > m20 else "⚠️ 跌破", "月線乖離率(%)": round(bias, 2)})
                except: pass
            return pd.DataFrame(results)
        st.dataframe(fetch_real_semi_data(), hide_index=True, use_container_width=True)

    with tabs[4]:
        st.subheader("🔄 市場熱錢流向與輪動")
        tse_df, otc_df = fetch_top15_ranking()
        if not tse_df.empty or not otc_df.empty:
            combined_top = pd.concat([tse_df, otc_df], ignore_index=True)
            combined_top['產業族群'] = combined_top['證券代號'].astype(str).str.strip().map(SECTOR_MAP).fillna("🔥 活躍熱門股")
            combined_top['成交億'] = (combined_top['成交金額'] / 100000000).round(1)
            sector_flow = combined_top.groupby('產業族群')['成交億'].sum().sort_values(ascending=False)
            st.bar_chart(sector_flow, color="#ffd166")

    with tabs[5]:
        st.subheader("🌐 當前建議資產水位")
        st.progress(60, text="📈 股票部位：60%")
        st.progress(30, text="💵 現金部位：30%")

    with tabs[6]:
        st.subheader("📈 台灣加權指數 (^TWII)")
        twii_df = yf.Ticker("^TWII").history(period="4mo")
        if not twii_df.empty:
            twii_df['MA20'] = twii_df['Close'].rolling(20).mean()
            fig = make_subplots(rows=1, cols=1)
            fig.add_trace(go.Candlestick(x=twii_df.index, open=twii_df['Open'], high=twii_df['High'], low=twii_df['Low'], close=twii_df['Close']))
            fig.add_trace(go.Scatter(x=twii_df.index, y=twii_df['MA20'], line=dict(color='orange')))
            fig.update_layout(template="plotly_dark", xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)

    with tabs[7]:
        st.subheader("🫧 AI 產業泡沫觀測 (即時財報源頭連線)")
        @st.cache_data(ttl=86400)
        def fetch_real_fundamental_comparison():
            ai_tickers = {"NVDA": "輝達", "TSM": "台積電"}
            consumer_tickers = {"AAPL": "蘋果", "INTC": "英特爾"}
            data = []
            for tk, name in ai_tickers.items():
                try: data.append({"板塊": "🔥 AI 核心軍火商", "公司": name, "營收年增率(%)": yf.Ticker(tk).info.get('revenueGrowth', 0) * 100})
                except: pass
            for tk, name in consumer_tickers.items():
                try: data.append({"板塊": "📱 傳統消費電子", "公司": name, "營收年增率(%)": yf.Ticker(tk).info.get('revenueGrowth', 0) * 100})
                except: pass
            return pd.DataFrame(data)
        fund_df = fetch_real_fundamental_comparison()
        if not fund_df.empty:
            fig_rev = px.bar(fund_df, x="公司", y="營收年增率(%)", color="板塊", color_discrete_map={"🔥 AI 核心軍火商": "#ff4b4b", "📱 傳統消費電子": "#00cc96"})
            fig_rev.update_layout(template="plotly_dark", height=350)
            st.plotly_chart(fig_rev, use_container_width=True)

# ==========================================
# 分頁 4: 🤝 土洋主力共振雷達
# ==========================================
elif main_page == "🤝 土洋主力共振雷達":
    st.title("🤝 土洋主力共振雷達 (籌碼深度追蹤)")
    if is_bearish: st.error("⛔ **【防呆限制】大盤目前環境風險極高**。")
    if st.button("🚀 啟動全市場土洋籌碼共振掃描", type="primary", use_container_width=True):
        with st.spinner("📡 解析中..."):
            co_buy_df = fetch_co_buying_radar()
            if not co_buy_df.empty:
                hot_ids = set(co_buy_df['代號'].tolist())
                full_ids = [f"{t}.TW" if len(t)==4 else f"{t}.TWO" for t in hot_ids]
                bulk_data = fetch_bulk_yf_data(full_ids, period="3mo")
                inst_map, tech_results = get_inst_data(), {}
                with ThreadPoolExecutor(max_workers=5) as ex:
                    futs = {ex.submit(analyze_stock_score_v2, t, bulk_data[f"{t}.TW" if len(t)==4 else f"{t}.TWO"], f"{t}.TW" if len(t)==4 else f"{t}.TWO", inst_map, hot_ids, is_bearish): t for t in hot_ids if (f"{t}.TW" if len(t)==4 else f"{t}.TWO") in bulk_data}
                    for f in as_completed(futs):
                        if f.result(): tech_results[futs[f]] = f.result()['星等']
                
                co_buy_df['技術面星等'] = co_buy_df['代號'].map(tech_results).fillna("💤 無資料")
                co_buy_df.insert(0, '名次', co_buy_df.index + 1)
                display_df = co_buy_df[['名次', '代號', '名稱', '合計買超(張)', '技術面星等']] if hide_complex_tech else co_buy_df[['名次', '代號', '名稱', '外資買賣超(張)', '投信買賣超(張)', '合計買超(張)', '技術面星等', '市場']]
                st.dataframe(display_df, use_container_width=True, hide_index=True)

# ==========================================
# 分頁 5: 🏢 基本面與 AI 診斷
# ==========================================
elif main_page == "🏢 基本面與 AI 診斷":
    st.title("🏢 基本面濾網與 AI 財報新聞分析")
    f_id = st.text_input("🔍 欲查探基本面的標的代號", value="2317")
    if st.button("🧠 啟動 AI 智能診斷", use_container_width=True):
        eps, pe, rev, news_list = get_fundamentals_and_news(f_id)
        st.markdown(f"#### 📊 {f_id} 核心基本面數據")
        c1, c2, c3 = st.columns(3)
        c1.metric("近四季 EPS", eps); c2.metric("本益比", pe); c3.metric("營收年增率", rev)
        st.info(ai_news_sentiment(news_list))

# ==========================================
# 分頁 6: 🕵️‍♂️ 00981A 經理人跟單雷達
# ==========================================
elif main_page == "🕵️‍♂️ 00981A 經理人跟單雷達":
    st.title("🕵️‍♂️ 00981A 經理人跟單雷達")
    force_refresh = st.button("🔄 強制重新抓取今日籌碼")
    analyzed_df = analyze_manager_moves(get_00981a_holdings_history(force_refresh=force_refresh))
    if not analyzed_df.empty:
        with st.spinner("⚡ 正在獲取最新股價..."):
            inst_map, hot_list, star_dict, price_dict = get_inst_data(), get_hot_rank_ids(), {}, {}
            bulk_data_dict = fetch_bulk_yf_data([CLEAN_TO_FULL_MAP.get(str(row['代號']), f"{row['代號']}.TW") for _, row in analyzed_df.iterrows()], period="1y")
            with ThreadPoolExecutor(max_workers=8) as ex:
                futs = {ex.submit(analyze_stock_score_v2, str(row['代號']), bulk_data_dict.get(CLEAN_TO_FULL_MAP.get(str(row['代號']), f"{row['代號']}.TW")), CLEAN_TO_FULL_MAP.get(str(row['代號']), f"{row['代號']}.TW"), inst_map, hot_list, is_bearish): str(row['代號']) for _, row in analyzed_df.iterrows() if CLEAN_TO_FULL_MAP.get(str(row['代號']), f"{row['代號']}.TW") in bulk_data_dict}
                for f in as_completed(futs):
                    t, res = futs[f], f.result()
                    if res: star_dict[t], price_dict[t] = res['星等'], res['收盤']
                    else: star_dict[t], price_dict[t] = "💤 盤整", fetch_fast_price(t)
            
            analyzed_df.insert(2, '最新收盤價', analyzed_df['代號'].map(price_dict))
            analyzed_df.insert(3, '六星技術評等', analyzed_df['代號'].map(star_dict))
            st.dataframe(analyzed_df[['代號', '股票名稱', '最新收盤價', '今日買賣超(張)', '動向狀態', '六星技術評等']], use_container_width=True, hide_index=True)

# ==========================================
# 分頁 7: ☠️ 隔日沖分點照妖鏡
# ==========================================
elif main_page == "☠️ 隔日沖分點照妖鏡":
    st.title("☠️ 隔日沖分點照妖鏡")
    target_id = st.text_input("🔍 輸入懷疑有隔日沖介入的股票代號", value="3034")
    if st.button("🕵️‍♂️ 啟動分點 X 光機掃描", use_container_width=True):
        st.warning("⚠️ 找不到本地真實資料庫，切換至模擬展示模式。")
        st.dataframe(pd.DataFrame({"券商分點": ["凱基-台北", "台灣匯立", "摩根大通", "美林", "元大-土城永寧"], "買進張數": [4500, 3200, 2800, 2100, 1800], "賣出張數": [100, 50, 200, 500, 0]}), use_container_width=True, hide_index=True)

# ==========================================
# 分頁 8: 🚀 早盤渦輪截擊
# ==========================================
elif main_page == "🚀 早盤渦輪截擊":
    st.title("🚀 早盤渦輪截擊雷達 (9:00-9:30 專用)")
    if is_bearish: st.error("⛔ **【系統防呆斷油機制已觸發】** 大盤處於偏空逆風。早盤追高極易遭拉高出貨。")

    col_t1, col_t2 = st.columns(2)
    with col_t1: test_mode = st.toggle("🔧 開啟寬鬆測試模式 (無跳空限制)", value=False)
    with col_t2:
        if st_autorefresh is not None:
            auto_refresh_on = st.toggle("🔄 開啟自動巡航 (每 30 秒刷新)", value=False)
            if auto_refresh_on: st_autorefresh(interval=30 * 1000, key="morning_autorefresh")
        else: auto_refresh_on = False; st.warning("請先安裝 streamlit-autorefresh")
            
    if auto_refresh_on or st.button("🚨 啟動早盤極速點火掃描", use_container_width=True):
        with st.spinner("🚀 預載數據中..."):
            full_ids = [CLEAN_TO_FULL_MAP.get(t, f"{t}.TW") for t in s_list]
            bulk_data_dict = fetch_bulk_yf_data(full_ids, period="5d")
            valid_list = [t for t in s_list if CLEAN_TO_FULL_MAP.get(t, f"{t}.TW") in bulk_data_dict]
            runners = run_async(run_morning_scan_async(valid_list, bulk_data_dict, test_mode)) if aiohttp else []
            
            if runners:
                df_run = pd.DataFrame(runners).sort_values(by="即時漲幅", ascending=False).reset_index(drop=True)
                df_run.insert(0, '🔥 排名', df_run.index + 1)
                st.dataframe(df_run[['🔥 排名', '代號', '名稱', '即時價', '漲幅顯示']] if hide_complex_tech else df_run[['🔥 排名', '代號', '名稱', '即時價', '跳空顯示', '漲幅顯示', '早盤型態', '目前累積量', '昨日總量']], use_container_width=True, hide_index=True)
            else: st.warning("👀 目前盤面沒有符合起漲點火的強勢標的。")
