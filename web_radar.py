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
import numpy as np

# === 升級套件：斷線重連避震器 ===
try:
    from tenacity import retry, wait_exponential, stop_after_attempt
except ImportError:
    st.error("⚠️ 缺少 tenacity 套件！")
    st.info("💡 解法：本機請執行 `pip install tenacity`；若是部署在 Streamlit Cloud，請確認 requirements.txt 內有加入 `tenacity`。")
    st.stop()

# === 1. 系統環境設定與版面美化 ===
warnings.filterwarnings("ignore")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
st.set_page_config(page_title="阿綜專屬：極簡智能雷達", page_icon="📈", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    h1 { color: #1E3A8A; font-weight: 800; font-family: 'Helvetica Neue', sans-serif; text-shadow: 1px 1px 2px rgba(0,0,0,0.1); }
    h2, h3 { color: #009688; }
    div[data-testid="stMetricValue"] { font-size: 1.8rem; font-weight: 700; color: #333333; }
    div[data-testid="stMetricDelta"] { font-size: 1rem; font-weight: bold; }
    .stButton>button { border-radius: 8px; font-weight: 600; transition: all 0.3s ease; border: 1px solid #ccc; background-color: #f8f9fa; color: #333;}
    .stButton>button:hover { transform: translateY(-2px); box-shadow: 0 5px 15px rgba(0, 0, 0, 0.1); border-color: #009688; color: #009688; }
    .stButton>button[kind="primary"] { background: linear-gradient(90deg, #FF4B4B, #FF7B7B); color: white; border: none; }
    .stButton>button[kind="primary"]:hover { background: linear-gradient(90deg, #FF7B7B, #FF4B4B); box-shadow: 0 5px 15px rgba(255, 75, 75, 0.3); color: white; }
    section[data-testid="stSidebar"] { background-color: #f1f3f5; border-right: 1px solid #e0e0e0; }
    section[data-testid="stSidebar"] * { color: #333333 !important; }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
HEADERS = {"User-Agent": UA}

# === 2. 外部設定檔掛載 ===
DEFAULT_STOCKS = {
    "2330.TW": "台積電", "2317.TW": "鴻海", "2454.TW": "聯發科", "2308.TW": "台達電",
    "3661.TW": "世芯KY", "3034.TW": "聯詠", "2382.TW": "廣達", "3231.TW": "緯創", 
    "3017.TW": "奇鋐", "3324.TW": "雙鴻", "2603.TW": "長榮", "2881.TW": "富邦金"
}
DEFAULT_SECTORS = {"2330": "半導體業", "2317": "電腦及週邊設備業", "3017": "電腦及週邊設備業", "2603": "航運業", "2881": "金融保險業"}
STOCKS_DICT = DEFAULT_STOCKS.copy()
CLEAN_TO_FULL_MAP = {k.split('.')[0]: k for k in STOCKS_DICT.keys()}

# === 3. 基礎函數 (網路、資料獲取) ===
@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
def safe_get_json(url, headers=None):
    res = requests.get(url, headers=headers, timeout=10, verify=False)
    res.raise_for_status() 
    return res.json()

def safe_get_json_fallback(url, headers=None):
    try: return safe_get_json(url, headers)
    except: return {}

def get_fugle_quote(clean_id, api_key):
    try:
        url = f"https://api.fugle.tw/marketdata/v1.0/stock/intraday/quote/{clean_id}"
        headers = {"X-API-KEY": api_key}
        res = requests.get(url, headers=headers, timeout=2).json()
        if 'quote' not in res: return None
        
        c = res['quote'].get('trade', {}).get('price')
        if not c: return None
        
        o = res['quote'].get('priceOpen', {}).get('price', c)
        h = res['quote'].get('priceHigh', {}).get('price', c)
        l = res['quote'].get('priceLow', {}).get('price', c)
        v = res['quote'].get('total', {}).get('tradeVolume', 0)
        return {'Open': o, 'High': h, 'Low': l, 'Close': c, 'Volume': v}
    except: return None

@st.cache_data(ttl=86400*7, show_spinner=False)
def get_all_sector_map():
    sector_map = DEFAULT_SECTORS.copy()
    try:
        res_twse = safe_get_json_fallback("https://openapi.twse.com.tw/v1/opendata/t187ap03_L")
        if res_twse and isinstance(res_twse, list):
            for item in res_twse: sector_map[item.get('公司代號', '').strip()] = item.get('產業別', '未分類')
    except: pass
    try:
        res_tpex = safe_get_json_fallback("https://openapi.tpex.org.tw/v1/web/regular_emerging/t187ap03_O")
        if res_tpex and isinstance(res_tpex, list):
            for item in res_tpex: sector_map[item.get('公司代號', '').strip()] = item.get('產業別', '未分類')
    except: pass
    return sector_map

GLOBAL_SECTOR_MAP = get_all_sector_map()

@st.cache_data(ttl=86400, show_spinner=False)
def get_all_tw_stock_data():
    full_ids = []
    stock_dict = {}
    try:
        tse = safe_get_json_fallback("https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&type=ALLBUT0999", HEADERS)
        if tse and 'tables' in tse:
            for t in tse['tables']:
                if '證券代號' in t.get('fields', []) and '證券名稱' in t.get('fields', []):
                    idx_c, idx_n = t['fields'].index('證券代號'), t['fields'].index('證券名稱')
                    for row in t['data']:
                        code, name = row[idx_c].strip(), row[idx_n].strip()
                        if len(code) == 4 and code.isdigit():
                            full_ids.append(f"{code}.TW"); stock_dict[f"{code}.TW"] = name; stock_dict[code] = name
    except: pass
    try:
        otc = safe_get_json_fallback("https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php?l=zh-tw&o=json", HEADERS)
        data_otc = otc.get('aaData', []) or (otc.get('tables', [{}])[0].get('data', []) if 'tables' in otc else [])
        for row in data_otc:
            code, name = str(row[0]).strip(), str(row[1]).strip()
            if len(code) == 4 and code.isdigit():
                full_ids.append(f"{code}.TWO"); stock_dict[f"{code}.TWO"] = name; stock_dict[code] = name
    except: pass
    if not full_ids: return list(DEFAULT_STOCKS.keys()), DEFAULT_STOCKS.copy()
    return full_ids, stock_dict

@st.cache_data(ttl=900, show_spinner=False)
def fetch_bulk_yf_data(full_ticker_list, period="1y"):
    valid_tickers = [t for t in full_ticker_list if t]
    if not valid_tickers: return {}
    res_dict = {}
    for i in range(0, len(valid_tickers), 400):
        chunk = valid_tickers[i:i+400]
        try:
            data = yf.download(" ".join(chunk), period=period, threads=True, progress=False)
            if len(chunk) == 1:
                df_t = data.dropna(subset=['Close'])
                if not df_t.empty: res_dict[chunk[0]] = df_t
            else:
                for t in chunk:
                    try:
                        df_t = pd.DataFrame({'Open': data['Open'][t], 'High': data['High'][t], 'Low': data['Low'][t], 'Close': data['Close'][t], 'Volume': data['Volume'][t]}).dropna(subset=['Close'])
                        if not df_t.empty: res_dict[t] = df_t
                    except: pass
        except: pass
    return res_dict

@st.cache_data(ttl=10800, show_spinner=False)
def fetch_high_yield_stocks():
    res_list = []
    try:
        res = safe_get_json_fallback("https://www.twse.com.tw/exchangeReport/BWIBBU_d?response=json&selectType=ALL", HEADERS)
        if 'data' in res:
            for row in res['data']:
                code, name = row[0].strip(), row[1].strip()
                try:
                    yld = float(row[2].replace(',', ''))
                    pe = float(row[4].replace(',', '')) if row[4] != '-' else 0.0
                    pb = float(row[5].replace(',', '')) if row[5] != '-' else 0.0
                    if 5.0 <= yld <= 8.5:
                        res_list.append({'代號': code, '名稱': name, '產業族群': GLOBAL_SECTOR_MAP.get(code, '未分類'), '殖利率(%)': yld, '本益比': pe, '股價淨值比': pb})
                except: pass
    except: pass
    return pd.DataFrame(res_list)

@st.cache_data(ttl=1800, show_spinner=False)
def get_macro_data_dynamic():
    tickers = {"TWD=X": "台幣匯率", "^VIX": "VIX 恐慌指數", "^TNX": "美債殖利率"}
    results = {}
    for t, name in tickers.items():
        try:
            df = yf.Ticker(t).history(period="5d")
            if not df.empty and len(df) >= 2:
                c_today, c_yest = df['Close'].iloc[-1], df['Close'].iloc[-2]
                results[name] = {'val': round(c_today, 2), 'diff': round(c_today - c_yest, 2), 'pct': round(((c_today - c_yest) / c_yest) * 100, 2)}
        except: results[name] = {'val': 'N/A', 'diff': 0, 'pct': 0}
    return results

@st.cache_data(ttl=1800, show_spinner=False)
def get_market_breadth():
    try:
        df = yf.Ticker("^TWII").history(period="3mo")
        if not df.empty:
            df['MA20'] = df['Close'].rolling(20).mean()
            c, m20 = df['Close'].iloc[-1], df['MA20'].iloc[-1]
            status = "🟥 偏多環境 (站上月線，積極操作)" if c > m20 else "🟩 偏空環境 (跌破月線，嚴格控管)"
            return round(c, 2), round(m20, 2), status
    except: pass
    return None, None, "⚪ 系統連線中"

# 🌟 技術指標運算 🌟
def calculate_kd(df):
    if len(df) < 9: return df
    df['9_min'], df['9_max'] = df['Low'].rolling(window=9).min(), df['High'].rolling(window=9).max()
    df['RSV'] = (df['Close'] - df['9_min']) / (df['9_max'] - df['9_min']) * 100
    k_v, d_v, k, d = [], [], 50.0, 50.0
    for rsv in df['RSV']:
        if pd.isna(rsv): k_v.append(50.0); d_v.append(50.0)
        else: k = (2/3)*k + (1/3)*rsv; d = (2/3)*d + (1/3)*k; k_v.append(k); d_v.append(d)
    df['K'], df['D'] = k_v, d_v
    return df

def calculate_macd(df):
    df['EMA12'], df['EMA26'] = df['Close'].ewm(span=12, adjust=False).mean(), df['Close'].ewm(span=26, adjust=False).mean()
    df['DIF'] = df['EMA12'] - df['EMA26']
    df['MACD'] = df['DIF'].ewm(span=9, adjust=False).mean()
    df['Hist'] = df['DIF'] - df['MACD']
    return df

def calculate_bb_bias(df):
    df['MA20'], df['STD20'] = df['Close'].rolling(20).mean(), df['Close'].rolling(20).std()
    df['BB_UPPER'] = df['MA20'] + 2 * df['STD20']
    df['BIAS20'] = (df['Close'] - df['MA20']) / df['MA20'] * 100
    return df

@st.cache_data(ttl=3600, show_spinner=False)
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

@st.cache_data(ttl=300, show_spinner=False)
def get_hot_rank_ids():
    tse_df, otc_df = fetch_top15_ranking()
    hot_ids = set()
    if not tse_df.empty: hot_ids.update(tse_df['證券代號'].tolist())
    if not otc_df.empty: hot_ids.update(otc_df['證券代號'].tolist())
    return hot_ids

@st.cache_data(ttl=3600, show_spinner=False)
def get_inst_data():
    inst_map = {}
    try:
        r1 = safe_get_json_fallback("https://www.twse.com.tw/fund/T86?response=json&selectType=ALLBUT0999", HEADERS)
        if 'data' in r1:
            fields = r1.get('fields', [])
            fk_idx = fields.index("外陸資買賣超股數(不含外資自營商)") if "外陸資買賣超股數(不含外資自營商)" in fields else 4
            it_idx = fields.index("投信買賣超股數") if "投信買賣超股數" in fields else 10
            for d in r1['data']:
                inst_map[d[0].strip()] = {'外資': int(d[fk_idx].replace(',', '')) // 1000, '投信': int(d[it_idx].replace(',', '')) // 1000}
                
        r2 = safe_get_json_fallback("https://www.tpex.org.tw/web/stock/fund/T86/T86_result.php?l=zh-tw&o=json", HEADERS)
        if 'aaData' in r2:
            for d in r2['aaData']:
                inst_map[d[0].strip()] = {'外資': int(d[10].replace(',', '')) // 1000, '投信': int(d[13].replace(',', '')) // 1000}
    except: pass
    return inst_map

# === 4. 雷達分析核心引擎 ===
def analyze_stock_score_v2(clean_id, df_ticker, full_id, inst_map, hot_list, is_bearish=False, fugle_key=""):
    try:
        df = df_ticker.copy()
        if df.empty or len(df) < 65: return None
        
        fugle_active = False
        if fugle_key:
            rt = get_fugle_quote(clean_id, fugle_key)
            if rt:
                df.iloc[-1, df.columns.get_loc('Close')] = rt['Close']
                df.iloc[-1, df.columns.get_loc('Open')] = rt['Open']
                df.iloc[-1, df.columns.get_loc('High')] = max(df.iloc[-1]['High'], rt['High'])
                df.iloc[-1, df.columns.get_loc('Low')] = min(df.iloc[-1]['Low'], rt['Low'])
                df.iloc[-1, df.columns.get_loc('Volume')] = max(df.iloc[-1]['Volume'], rt['Volume'])
                fugle_active = True

        c, v = df['Close'].iloc[-1], df['Volume'].iloc[-1]
        v5 = df['Volume'].iloc[-6:-1].mean()
        if v5 < 500000: return None
        
        df = calculate_bb_bias(df)
        df['MA5'], df['MA60'] = df['Close'].rolling(5).mean(), df['Close'].rolling(60).mean()
        
        inst_data = inst_map.get(clean_id, {'外資': 0, '投信': 0})
        fk_val, it_val = inst_data['外資'], inst_data['投信']
        total_inst = fk_val + it_val

        if is_bearish and (c < df['MA60'].iloc[-1] or total_inst <= 0): return None
        if pd.notna(df['BIAS20'].iloc[-1]):
            if df['BIAS20'].iloc[-1] > 15 or c > df['BB_UPPER'].iloc[-1] * 1.03: return None
            
        df = calculate_kd(df)
        df = calculate_macd(df)
        s, tags = 0, []
        
        if fugle_active: tags.append("⚡[極速即時]")
        sector = GLOBAL_SECTOR_MAP.get(clean_id, '未分類')
        if pd.notna(df['BIAS20'].iloc[-1]) and df['BIAS20'].iloc[-1] > 10: tags.append("🥵[乖離偏高]")
        upper_shadow = df['High'].iloc[-1] - max(df['Open'].iloc[-1], c)
        body = abs(c - df['Open'].iloc[-1])
        if (upper_shadow > body * 1.5) and ((df['High'].iloc[-1] - c) / c > 0.02): tags.append("🚨[假突破警戒]")
            
        if c > df['MA5'].iloc[-1] > df['MA20'].iloc[-1] > df['MA60'].iloc[-1]: s+=1; tags.append("[均線多頭]")
        if df['MA20'].iloc[-1] > df['MA20'].iloc[-2]: s+=1; tags.append("[月線向上]")
        if v > v5 * 1.5: s+=1; tags.append("[爆量攻擊]")
        if df['K'].iloc[-1] > df['D'].iloc[-1] and df['K'].iloc[-2] <= df['D'].iloc[-2]: s+=1; tags.append("[KD金叉]")
        if df['Hist'].iloc[-1] > 0 and df['Hist'].iloc[-1] > df['Hist'].iloc[-2]: s+=1; tags.append("[MACD強勢]")
        if c > df['High'].iloc[-21:-1].max(): s+=1; tags.append("[創20日新高]")
        if df['Low'].iloc[-1] >= df['Low'].iloc[-2] and df['High'].iloc[-1] > df['High'].iloc[-2] and c > df['MA20'].iloc[-1]: s+=1; tags.append("👑[底底高架構]")
        if clean_id in hot_list: tags.append("🔥[熱門股]")
        
        if fk_val > 500: tags.append("💰[外資大買]")
        if it_val > 200: tags.append("🏦[投信認養]")
        if fk_val > 0 and it_val > 0: tags.append("🤝[土洋合作]")

        star_display = ("🌟" * s) + ("⚫" * (7 - s)) if s > 0 else "💤 盤整"
        if s >= 4: 
            return {'代號': clean_id, '名稱': STOCKS_DICT.get(full_id, clean_id), '產業族群': sector, '星等': star_display, 
                    '收盤價': round(c, 2), '外資(張)': fk_val, '投信(張)': it_val, '法人買賣超(張)': total_inst, '觸發條件': " ".join(tags)}
    except: return None

def analyst_three_line_macd_scanner(clean_id, df_ticker, full_id, inst_map, is_bearish=False, fugle_key=""):
    try:
        df = df_ticker.copy()
        if df.empty or len(df) < 60: return None
        
        fugle_active = False
        if fugle_key:
            rt = get_fugle_quote(clean_id, fugle_key)
            if rt:
                df.iloc[-1, df.columns.get_loc('Close')] = rt['Close']
                df.iloc[-1, df.columns.get_loc('Open')] = rt['Open']
                df.iloc[-1, df.columns.get_loc('High')] = max(df.iloc[-1]['High'], rt['High'])
                df.iloc[-1, df.columns.get_loc('Low')] = min(df.iloc[-1]['Low'], rt['Low'])
                df.iloc[-1, df.columns.get_loc('Volume')] = max(df.iloc[-1]['Volume'], rt['Volume'])
                fugle_active = True

        c, v = df['Close'].iloc[-1], df['Volume'].iloc[-1]
        if df['Volume'].iloc[-6:-1].mean() < 500000: return None 

        df = calculate_bb_bias(df)
        df['5MA'], df['10MA'] = df['Close'].rolling(5).mean(), df['Close'].rolling(10).mean()
        df = calculate_macd(df)
        sector = GLOBAL_SECTOR_MAP.get(clean_id, '未分類')
        inst_data = inst_map.get(clean_id, {'外資': 0, '投信': 0})
        fk_val, it_val = inst_data['外資'], inst_data['投信']
        total_inst = fk_val + it_val

        if pd.notna(df['BIAS20'].iloc[-1]) and (df['BIAS20'].iloc[-1] > 15 or c > df['BB_UPPER'].iloc[-1] * 1.03): return None

        if (df['5MA'].iloc[-1] > df['10MA'].iloc[-1] > df['MA20'].iloc[-1]) and (df['DIF'].iloc[-1] > 0) and (df['MACD'].iloc[-1] > 0) and (df['DIF'].iloc[-1] > df['MACD'].iloc[-1]):
            if is_bearish and total_inst <= 0: return None
            upper_shadow = df['High'].iloc[-1] - max(df['Open'].iloc[-1], c)
            body = abs(c - df['Open'].iloc[-1])
            if (upper_shadow > body * 1.5) and ((df['High'].iloc[-1] - c) / c > 0.02): return None
            
            is_fresh = not ((df['5MA'].iloc[-2] > df['10MA'].iloc[-2] > df['MA20'].iloc[-2]) and (df['DIF'].iloc[-2] > 0) and (df['MACD'].iloc[-2] > 0))
            tags = ["三線多頭 + MACD 零軸之上"]
            if fugle_active: tags.append("⚡[極速即時]")
            if pd.notna(df['BIAS20'].iloc[-1]) and df['BIAS20'].iloc[-1] > 10: tags.append("🥵[乖離偏高]")
            if fk_val > 500: tags.append("💰[外資大買]")
            if it_val > 200: tags.append("🏦[投信認養]")
            if fk_val > 0 and it_val > 0: tags.append("🤝[土洋合作]")

            return {'代號': clean_id, '名稱': STOCKS_DICT.get(full_id, clean_id), '產業族群': sector, '星等': "🚀 剛觸發三線零軸" if is_fresh else "🌟 續強中", 
                    '收盤價': round(c, 2), '外資(張)': fk_val, '投信(張)': it_val, '法人買賣超(張)': total_inst, '觸發條件': " ".join(tags)}
    except: return None

def ultimate_breakout_scanner(clean_id, df_ticker, full_id, inst_map, is_bearish=False, fugle_key=""):
    try:
        df = df_ticker.copy()
        if df.empty or len(df) < 60: return None
        
        fugle_active = False
        if fugle_key:
            rt = get_fugle_quote(clean_id, fugle_key)
            if rt:
                df.iloc[-1, df.columns.get_loc('Close')] = rt['Close']
                df.iloc[-1, df.columns.get_loc('Open')] = rt['Open']
                df.iloc[-1, df.columns.get_loc('High')] = max(df.iloc[-1]['High'], rt['High'])
                df.iloc[-1, df.columns.get_loc('Low')] = min(df.iloc[-1]['Low'], rt['Low'])
                df.iloc[-1, df.columns.get_loc('Volume')] = max(df.iloc[-1]['Volume'], rt['Volume'])
                fugle_active = True

        c, v = df['Close'].iloc[-1], df['Volume'].iloc[-1]
        v5_avg = df['Volume'].iloc[-6:-1].mean()
        if v5_avg < 500000: return None
        
        df = calculate_bb_bias(df)
        df['MA5'] = df['Close'].rolling(5).mean()
        sector = GLOBAL_SECTOR_MAP.get(clean_id, '未分類')
        inst_data = inst_map.get(clean_id, {'外資': 0, '投信': 0})
        fk_val, it_val = inst_data['外資'], inst_data['投信']
        total_inst = fk_val + it_val

        if pd.notna(df['BIAS20'].iloc[-1]) and (df['BIAS20'].iloc[-1] > 15 or c > df['BB_UPPER'].iloc[-1] * 1.03): return None

        recent_10d_high, recent_10d_low = df['High'].iloc[-11:-1].max(), df['Low'].iloc[-11:-1].min()
        if (df['MA5'].iloc[-1] > df['MA20'].iloc[-1]) and ((recent_10d_high - recent_10d_low) / recent_10d_low < 0.08) and (c >= df['High'].iloc[-21:-1].max()) and (v > v5_avg * 2.0):
            if is_bearish and total_inst <= 0: return None
            upper_shadow = df['High'].iloc[-1] - max(df['Open'].iloc[-1], c)
            body = abs(c - df['Open'].iloc[-1])
            if (upper_shadow > body * 1.5) and ((df['High'].iloc[-1] - c) / c > 0.02): return None
            
            tags_str = f"爆量 {v/v5_avg:.1f}倍 + 創高"
            if fugle_active: tags_str += " ⚡[極速即時]"

            return {'代號': clean_id, '名稱': STOCKS_DICT.get(full_id, clean_id), '產業族群': sector, '星等': "⚡ 壓縮突破",
                    '收盤價': round(c, 2), '外資(張)': fk_val, '投信(張)': it_val, '法人買賣超(張)': total_inst, '觸發條件': tags_str}
    except: return None

def bearish_breakdown_scanner(clean_id, df_ticker, full_id, inst_map):
    try:
        df = df_ticker.copy()
        if df.empty or len(df) < 60: return None
        c = df['Close'].iloc[-1]
        df['MA20'] = df['Close'].rolling(20).mean()
        inst_data = inst_map.get(clean_id, {'外資': 0, '投信': 0})
        total_inst = inst_data['外資'] + inst_data['投信']
        
        if c < df['MA20'].iloc[-1] and (df['MA20'].iloc[-1] < df['MA20'].iloc[-3]) and (c < df['Low'].iloc[-11:-1].min()) and total_inst < -200:
            return {'代號': clean_id, '名稱': STOCKS_DICT.get(full_id, clean_id), '產業族群': GLOBAL_SECTOR_MAP.get(clean_id, '未分類'),
                    '收盤價': round(c, 2), '型態': "☠️ 均線下彎+破底", '外資(張)': inst_data['外資'], '投信(張)': inst_data['投信'], '法人買賣超(張)': total_inst}
    except: return None

# === 5. 繪圖與圖表函數 ===
def plot_beautiful_chart(symbol, cost_price=None):
    try:
        full_id = CLEAN_TO_FULL_MAP.get(str(symbol), f"{symbol}.TW")
        df = yf.Ticker(full_id).history(period="6mo")
        if df.empty:
            st.error("找不到該標的資料")
            return
        df['5MA'], df['10MA'], df['20MA'] = df['Close'].rolling(5).mean(), df['Close'].rolling(10).mean(), df['Close'].rolling(20).mean()
        df = calculate_macd(df)
        df = calculate_bb_bias(df)
        df.dropna(inplace=True)

        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_width=[0.3, 0.7])
        fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='K線', increasing_line_color='#FF4B4B', decreasing_line_color='#00CC96'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['5MA'], mode='lines', name='5MA', line=dict(color='#F59E0B', width=1.5)), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['10MA'], mode='lines', name='10MA', line=dict(color='#3B82F6', width=1.5)), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['20MA'], mode='lines', name='20MA', line=dict(color='#8B5CF6', width=2)), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['BB_UPPER'], mode='lines', name='布林上軌', line=dict(color='#9CA3AF', width=1, dash='dot')), row=1, col=1)
        if cost_price and cost_price > 0:
            fig.add_hline(y=cost_price, line_dash="solid", line_color="#E11D48", line_width=2, annotation_text=f"持股成本: {cost_price}", annotation_position="top left", annotation_font_color="#E11D48", row=1, col=1)
        colors = np.where(df['Hist'] > 0, '#FF4B4B', '#00CC96')
        fig.add_trace(go.Bar(x=df.index, y=df['Hist'], name='MACD柱', marker_color=colors), row=2, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['DIF'], mode='lines', name='DIF', line=dict(color='#F59E0B')), row=2, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['MACD'], mode='lines', name='MACD', line=dict(color='#3B82F6')), row=2, col=1)
        fig.add_hline(y=0, line_dash="dash", line_color="#E5E7EB", opacity=0.8, row=2, col=1)
        fig.update_layout(height=650, template="plotly_white", xaxis_rangeslider_visible=False, margin=dict(l=0, r=0, t=10, b=0), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        st.plotly_chart(fig, use_container_width=True)
    except: st.error("繪圖發生錯誤")

# === 6. 美股與市場關聯函數 ===
def us_market_brain():
    us_tickers = {"TSM": "台積電 ADR", "ARM": "安謀", "AAPL": "蘋果", "MSFT": "微軟", "NVDA": "輝達", "TSLA": "特斯拉"}
    for ticker, name in us_tickers.items():
        try:
            df = yf.Ticker(ticker).history(period="5d")
            if not df.empty and len(df) >= 2:
                c_t, c_y = df['Close'].iloc[-1], df['Close'].iloc[-2]
                st.metric(f"{name} ({ticker})", f"${c_t:.2f}", f"{((c_t - c_y) / c_y) * 100:.2f}%", delta_color="inverse")
            else: st.metric(name, "N/A", "-")
        except: st.metric(name, "Error", "-")


# === 7. 全域狀態管理與設定 (預設 API Key) ===
FUGLE_API_KEY = "54f80721-6cad-4ec9-9679-c5a315e7b00b"
if 'fugle_api_key' not in st.session_state: st.session_state.fugle_api_key = FUGLE_API_KEY
if 'watch_list' not in st.session_state: st.session_state.watch_list = [k.split('.')[0] for k in DEFAULT_STOCKS.keys()]

# === 8. 側邊欄 (Sidebar) UI ===
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/10061/10061803.png", width=60)
    st.markdown("## 📡 智能軍規雷達")
    st.caption("版本：V19.2 紀律作戰版")
    st.divider()

    st.subheader("🎯 掃描範圍設定")
    scan_mode = st.radio("雷達引擎掃描目標：", ["自選監控庫 (毫秒即時)", "全市場上市櫃 (約1700檔)"])
    st.divider()

    main_page = st.radio("導航選單", [
        "🎯 多頭獵殺 (突破/起漲)",
        "💰 高股息與 ETF 尋寶",  
        "🔥 全市場金流榜",  
        "📉 斷頭防護 (空方破底)", 
        "📊 股神專屬看盤室",
        "🌐 全球戰情與總經",
        "🧮 資金與風險控管",
        "⚙️ 自選庫與設定"
    ])
    st.divider()
    
    tw_c, tw_m20, tw_status = get_market_breadth()
    is_bearish = "🟩" in tw_status
    with st.expander("🌍 大盤即時風向", expanded=True):
        if tw_c:
            st.metric("加權指數", f"{tw_c:,.0f}", delta=f"{tw_c - tw_m20:,.0f} (距月線)", delta_color="inverse")
            st.markdown(f"**狀態：** {tw_status}")

    with st.expander("🌐 美股連動指標", expanded=False): us_market_brain()

if scan_mode == "全市場上市櫃 (約1700檔)":
    all_ids, all_dict = get_all_tw_stock_data()
    STOCKS_DICT.update(all_dict)
    for k in all_ids: CLEAN_TO_FULL_MAP[k.split('.')[0]] = k
    s_list = [k.split('.')[0] for k in all_ids]
else:
    s_list = st.session_state.watch_list


# ==========================================
# 分頁 1: 🎯 多頭獵殺 (V19.2 紀律作戰版)
# ==========================================
if main_page == "🎯 多頭獵殺 (突破/起漲)":
    st.title(f"🎯 多方飆股獵殺雷達 ({scan_mode})")
    
    active_fugle_key = st.session_state.fugle_api_key if (st.session_state.fugle_api_key and len(s_list) <= 150) else ""
    
    # 🌟 嚴格紀律風格的系統提示
    if active_fugle_key:
        st.success("⚡ **極速戰術連線已啟動**：系統強制擷取毫秒級即時報價覆寫 K 線，確保突破判定零誤差。請堅守交易紀律，伺機而動。")
    else:
        st.info("💡 **系統提示**：目前為大範圍掃描模式。系統依紀律退回標準延遲報價 (約 15-20 分鐘)，避免資料過載。請耐心等候訊號。")
    
    if is_bearish: st.error("⚠️ **大盤環境警告**：目前大盤跌破月線，操作多單勝率極低！請嚴格控制資金部位。")

    col1, col2, col3, col4 = st.columns(4)
    with col1: btn_star = st.button("🌟 六星雷達", use_container_width=True)
    with col2: btn_ym = st.button("📈 三線零軸", use_container_width=True)
    with col3: btn_breakout = st.button("🚀 旱地拔蔥", use_container_width=True)
    with col4: btn_overlap = st.button("⚔️ 雙劍合璧", use_container_width=True, type="primary")

    if btn_star or btn_breakout or btn_ym or btn_overlap:
        inst_map = get_inst_data()
        hot_list = get_hot_rank_ids()
        results = []
        progress_bar = st.progress(0, text=f"📡 正在從雲端載入 {len(s_list)} 檔標的數據...")
        
        full_ids = [CLEAN_TO_FULL_MAP.get(t, f"{t}.TW") for t in s_list]
        bulk_data_dict = fetch_bulk_yf_data(full_ids, period="1y")
        valid_list = [t for t in s_list if CLEAN_TO_FULL_MAP.get(t, f"{t}.TW") in bulk_data_dict]
        
        progress_bar.progress(50, text="🧠 啟動 AI 演算法交叉比對中...")
        with ThreadPoolExecutor(max_workers=5) as ex:
            if btn_overlap:
                futs_star = {ex.submit(analyze_stock_score_v2, t, bulk_data_dict[CLEAN_TO_FULL_MAP.get(t, f"{t}.TW")], CLEAN_TO_FULL_MAP.get(t, f"{t}.TW"), inst_map, hot_list, is_bearish, active_fugle_key): t for t in valid_list}
                futs_ym = {ex.submit(analyst_three_line_macd_scanner, t, bulk_data_dict[CLEAN_TO_FULL_MAP.get(t, f"{t}.TW")], CLEAN_TO_FULL_MAP.get(t, f"{t}.TW"), inst_map, is_bearish, active_fugle_key): t for t in valid_list}
                res_star_list, res_ym_list = [], []
                for i, f in enumerate(as_completed(list(futs_star.keys()) + list(futs_ym.keys()))):
                    progress_bar.progress(50 + int(50 * (i+1)/(len(futs_star)+len(futs_ym))))
                    res = f.result()
                    if res:
                        if f in futs_star: res_star_list.append(res)
                        else: res_ym_list.append(res)
                
                star_dict = {r['代號']: r for r in res_star_list}
                ym_dict = {r['代號']: r for r in res_ym_list}
                for cid in set(star_dict.keys()).intersection(set(ym_dict.keys())):
                    results.append({
                        '代號': cid, '名稱': star_dict[cid]['名稱'], '產業族群': star_dict[cid]['產業族群'], 
                        '六星評等': star_dict[cid]['星等'], '宇明型態': ym_dict[cid]['星等'],
                        '收盤價': star_dict[cid]['收盤價'], '外資(張)': star_dict[cid]['外資(張)'], '投信(張)': star_dict[cid]['投信(張)'],
                        '法人買賣超(張)': star_dict[cid]['法人買賣超(張)'], '綜合觸發條件': f"{star_dict[cid]['觸發條件']} ➕ {ym_dict[cid]['觸發條件']}"
                    })
            else:
                if btn_star: futs = [ex.submit(analyze_stock_score_v2, t, bulk_data_dict[CLEAN_TO_FULL_MAP.get(t, f"{t}.TW")], CLEAN_TO_FULL_MAP.get(t, f"{t}.TW"), inst_map, hot_list, is_bearish, active_fugle_key) for t in valid_list]
                elif btn_ym: futs = [ex.submit(analyst_three_line_macd_scanner, t, bulk_data_dict[CLEAN_TO_FULL_MAP.get(t, f"{t}.TW")], CLEAN_TO_FULL_MAP.get(t, f"{t}.TW"), inst_map, is_bearish, active_fugle_key) for t in valid_list]
                elif btn_breakout: futs = [ex.submit(ultimate_breakout_scanner, t, bulk_data_dict[CLEAN_TO_FULL_MAP.get(t, f"{t}.TW")], CLEAN_TO_FULL_MAP.get(t, f"{t}.TW"), inst_map, is_bearish, active_fugle_key) for t in valid_list]
                for i, f in enumerate(as_completed(futs)):
                    progress_bar.progress(50 + int(50 * (i+1)/len(valid_list)))
                    if f.result(): results.append(f.result())
                
        progress_bar.empty()
        
        if results:
            st.success(f"🎯 成功捕捉到 **{len(results)}** 檔通過過濾的標的！")
            df_res = pd.DataFrame(results).sort_values(by='法人買賣超(張)', ascending=False)
            
            st.subheader("📊 今日飆股族群分佈 (資金風向球)")
            sector_counts = df_res['產業族群'].value_counts().reset_index()
            sector_counts.columns = ['產業族群', '檔數']
            fig_pie = px.pie(sector_counts, values='檔數', names='產業族群', hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
            fig_pie.update_traces(textposition='inside', textinfo='percent+label')
            fig_pie.update_layout(height=350, margin=dict(t=20, b=20, l=20, r=20), showlegend=False)
            st.plotly_chart(fig_pie, use_container_width=True)
            
            st.divider()
            def style_dataframe(val):
                if isinstance(val, str) and '🚨' in val: return 'color: #FF4B4B; font-weight: bold; background-color: #FFE5E5;'
                if isinstance(val, str) and ('🥵' in val or '⚡' in val): return 'color: #F59E0B; font-weight: bold;'
                if isinstance(val, str) and ('💰' in val or '🏦' in val or '🤝' in val): return 'color: #FF4B4B; font-weight: bold;'
                if isinstance(val, (int, float)):
                    if val > 0: return 'color: #FF4B4B; font-weight: bold;'
                    elif val < 0: return 'color: #00CC96; font-weight: bold;'
                return ''

            col_subset = ['外資(張)', '投信(張)', '法人買賣超(張)', '綜合觸發條件'] if btn_overlap else ['外資(張)', '投信(張)', '法人買賣超(張)', '觸發條件']
            st.dataframe(df_res.style.map(style_dataframe, subset=col_subset), use_container_width=True, hide_index=True)
            st.balloons()
            
            with st.expander("🤖 生成 AI 盤後戰略報告提示詞 (Prompt)", expanded=False):
                top_stocks_str = ""
                for idx, row in df_res.head(5).iterrows():
                    cond = row.get('綜合觸發條件', row.get('觸發條件', ''))
                    top_stocks_str += f"- {row['名稱']}({row['代號']}) [{row['產業族群']}] / 收盤價:{row['收盤價']} / 法人買超:{row['法人買賣超(張)']}張 / 觸發: {cond}\n"
                macro_data = get_macro_data_dynamic()
                ai_prompt = f"""你是一位擁有20年經驗的量化交易員。請根據以下我今天透過「極簡智能雷達」掃描出的數據，撰寫【明日交易戰略報告】。
【大環境狀態】
- 大盤狀態：{tw_status}
- VIX恐慌指數：{macro_data.get("VIX 恐慌指數", {}).get('val', 'N/A')}
- 台幣匯率：{macro_data.get("台幣匯率", {}).get('val', 'N/A')}

【今日雷達嚴選強勢股 (前5大)】
{top_stocks_str}

請依照以下架構回覆：
1. 總體與板塊解讀：結合大盤與上述強勢股的「產業族群」，分析目前的市場資金風向。
2. 個股戰略點評：挑選出2檔最具潛力的標的，說明籌碼與技術面優勢。
3. 嚴格風險控管：提醒追高乖離風險與具體的停損策略。"""
                st.code(ai_prompt, language="markdown")
                
        else: st.warning("👀 此刻沒有任何股票通過嚴格測試。請堅守紀律，保持空手！")

# ==========================================
# 分頁 8: ⚙️ 自選庫與設定 
# ==========================================
elif main_page == "⚙️ 自選庫與設定":
    st.title("⚙️ 系統設定與自選名單管理")
    
    st.subheader("📝 您的自選監控代號庫")
    st.info("💡 確保代號使用半形逗號 `,` 隔開。為了保護 API 連線品質與系統穩定，極速即時報價僅支援自選庫總數低於 150 檔時啟動。")
    def_tickers = ", ".join(st.session_state.watch_list)
    new_input = st.text_area("", value=def_tickers, height=150)
    
    if st.button("💾 儲存自選名單", type="primary"):
        new_list = [t.strip() for t in new_input.replace('，',',').split(',') if t.strip()]
        st.session_state.watch_list = new_list
        st.success(f"✅ 更新成功！共監控 {len(new_list)} 檔。")
        time.sleep(1)
        st.rerun()

    st.divider()
    st.subheader("🧹 系統優化")
    if st.button("清除系統快取 (排除資料不同步問題)", use_container_width=False):
        st.cache_data.clear()
        st.toast("快取已清除！", icon="🧹")

# ==========================================
# 其餘分頁 (高股息/金流榜/斷頭防護/看盤室/總經/風險) 
# ==========================================
elif main_page == "💰 高股息與 ETF 尋寶":
    st.title("💰 穩健防禦：高股息/ETF 尋寶雷達")
    with st.spinner("🔍 正在從證交所撈取最新本益比與殖利率數據..."):
        df_yield = fetch_high_yield_stocks()
        if not df_yield.empty:
            df_yield = df_yield.sort_values(by='殖利率(%)', ascending=False).reset_index(drop=True)
            st.dataframe(df_yield, use_container_width=True, hide_index=True)
        else: st.warning("⚠️ 目前抓取不到資料。")

elif main_page == "🔥 全市場金流榜":
    st.title("🔥 全市場資金流向與類股權重")
    with st.spinner("🚀 計算資金板塊熱力中..."):
        tse_df, otc_df = fetch_top15_ranking()
        if not tse_df.empty or not otc_df.empty:
            combined_top = pd.concat([tse_df, otc_df], ignore_index=True)
            combined_top['產業族群'] = combined_top['證券代號'].astype(str).str.strip().map(GLOBAL_SECTOR_MAP).fillna("🔥 活躍熱門股")
            combined_top['成交億'] = (combined_top['成交金額'] / 100000000).round(1)
            col_chart1, col_chart2 = st.columns([4, 6])
            with col_chart1:
                sector_summary = combined_top.groupby('產業族群')['成交億'].sum().reset_index()
                fig_pie = px.pie(sector_summary, values='成交億', names='產業族群', hole=0.4)
                fig_pie.update_layout(template="plotly_white", showlegend=False, margin=dict(t=10, l=10, r=10, b=10))
                st.plotly_chart(fig_pie, use_container_width=True)
            with col_chart2:
                fig_heat = px.treemap(combined_top, path=[px.Constant("全市場"), '產業族群', '證券名稱'], values='成交億', color='成交億', color_continuous_scale=['#E5E7EB', '#F59E0B', '#FF4B4B'])
                fig_heat.update_layout(template="plotly_white", margin=dict(t=10, l=10, r=10, b=10))
                st.plotly_chart(fig_heat, use_container_width=True)

elif main_page == "📉 斷頭防護 (空方破底)":
    st.title(f"📉 弱勢避雷針 (空方引擎) - {scan_mode}")
    if st.button("☠️ 啟動地雷股掃描", use_container_width=True, type="primary"):
        inst_map = get_inst_data()
        results = []
        progress_text = f"📡 搜尋全市場地雷中 ({len(s_list)} 檔)..."
        my_bar = st.progress(0, text=progress_text)
        full_ids = [CLEAN_TO_FULL_MAP.get(t, f"{t}.TW") for t in s_list]
        bulk_data_dict = fetch_bulk_yf_data(full_ids, period="6mo")
        valid_list = [t for t in s_list if CLEAN_TO_FULL_MAP.get(t, f"{t}.TW") in bulk_data_dict]
        with ThreadPoolExecutor(max_workers=5) as ex:
            futs = [ex.submit(bearish_breakdown_scanner, t, bulk_data_dict[CLEAN_TO_FULL_MAP.get(t, f"{t}.TW")], CLEAN_TO_FULL_MAP.get(t, f"{t}.TW"), inst_map) for t in valid_list]
            for i, f in enumerate(as_completed(futs)):
                my_bar.progress((i+1)/len(valid_list), text=progress_text)
                if f.result(): results.append(f.result())
        my_bar.empty()
        if results:
            df_res = pd.DataFrame(results).sort_values(by='法人買賣超(張)', ascending=True)
            st.dataframe(df_res, use_container_width=True, hide_index=True)
        else: st.success("✅ 目前沒有岌岌可危的斷頭股。")

elif main_page == "📊 股神專屬看盤室":
    st.title("📊 專家級無干擾看盤室")
    col1, col2 = st.columns([1, 3])
    with col1:
        chart_id = st.text_input("🔍 輸入標的代號 (例如: 3034)", value="3034")
        cost_price = st.number_input("💰 您的持股成本 (0代表不顯示)", value=431.0, step=1.0)
        btn_draw = st.button("📈 繪製圖表", use_container_width=True, type="primary")
    with col2:
        if btn_draw:
            with st.spinner("繪製中..."): plot_beautiful_chart(chart_id, cost_price if cost_price > 0 else None)

elif main_page == "🌐 全球戰情與總經":
    st.title("🌐 總體經濟與大盤戰情")
    macro_data = get_macro_data_dynamic()
    col1, col2, col3 = st.columns(3)
    twd = macro_data.get("台幣匯率", {})
    col1.metric("台幣匯率", f"{twd.get('val', 'N/A')}", f"{twd.get('diff', 0)} ({twd.get('pct', 0)}%)", delta_color="inverse")
    vix = macro_data.get("VIX 恐慌指數", {})
    col2.metric("VIX 恐慌指數", f"{vix.get('val', 'N/A')}", f"{vix.get('diff', 0)} ({vix.get('pct', 0)}%)", delta_color="inverse")
    tnx = macro_data.get("美債殖利率", {})
    col3.metric("10年期美債殖利率", f"{tnx.get('val', 'N/A')}%", f"{tnx.get('diff', 0)}%", delta_color="inverse")
    try:
        twii_df = yf.Ticker("^TWII").history(period="3mo")
        twii_df['MA20'] = twii_df['Close'].rolling(20).mean()
        fig = make_subplots(rows=1, cols=1)
        fig.add_trace(go.Candlestick(x=twii_df.index, open=twii_df['Open'], high=twii_df['High'], low=twii_df['Low'], close=twii_df['Close'], name="大盤", increasing_line_color='#FF4B4B', decreasing_line_color='#00CC96'))
        fig.add_trace(go.Scatter(x=twii_df.index, y=twii_df['MA20'], line=dict(color='#3B82F6'), name="月線"))
        fig.update_layout(template="plotly_white", xaxis_rangeslider_visible=False, margin=dict(l=0,r=0,t=0,b=0), height=400)
        st.plotly_chart(fig, use_container_width=True)
    except: st.warning("無法載入大盤走勢圖。")

elif main_page == "🧮 資金與風險控管":
    st.title("🧮 資金部位計算機 (固定風險模型)")
    col1, col2 = st.columns([1, 1])
    with col1:
        st.subheader("1. 設定交易參數")
        total_capital = st.number_input("💰 總交易本金 (元)", min_value=10000, value=1000000, step=10000)
        risk_pct = st.slider("🛡️ 單筆最大虧損承受度 (%)", min_value=0.5, max_value=5.0, value=2.0, step=0.1)
        entry_price = st.number_input("📈 預計進場價 (元)", min_value=1.0, value=100.0, step=0.5)
        stop_loss_price = st.number_input("🛑 嚴格停損價 (元)", min_value=1.0, value=90.0, step=0.5)
    with col2:
        st.subheader("2. 系統運算結果")
        if entry_price <= stop_loss_price: st.error("⚠️ 停損價必須低於進場價。")
        else:
            max_loss = total_capital * (risk_pct / 100)
            max_shares = max_loss // (entry_price - stop_loss_price)
            total_cost = max_shares * entry_price
            st.metric("最大允許虧損", f"NT$ {max_loss:,.0f}")
            st.markdown(f"### 👉 建議購買： **{max_shares:,.0f} 股** ({max_shares / 1000:.1f} 張)")
            if total_cost > total_capital: st.warning(f"⚠️ 花費 NT$ {total_cost:,.0f}，已超出總本金！")
            else: st.success(f"✅ 總花費 NT$ {total_cost:,.0f}，佔總資金 {(total_cost/total_capital)*100:.1f}%。")
