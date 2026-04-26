import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests, warnings, time, urllib3
from concurrent.futures import ThreadPoolExecutor, as_completed

# === 1. 系統設定 ===
warnings.filterwarnings("ignore")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
st.set_page_config(page_title="股神雷達", page_icon="📡", layout="wide")
HEADERS = {"User-Agent": "Mozilla/5.0"}

# === 2. 數據清洗與計算 ===
def clean_it(df):
    if df is None or df.empty: return None
    df = df.copy()
    if hasattr(df.columns, 'nlevels') and df.columns.nlevels > 1:
        df.columns = df.columns.get_level_values(0)
    for c in ['Open', 'High', 'Low', 'Close', 'Volume']:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce')
    if 'Close' not in df.columns: return None
    return df.dropna(subset=['Close'])

def calculate_kd(df):
    df = clean_it(df)
    if df is None or len(df) < 9: return df
    l9, h9 = df['Low'].rolling(9).min(), df['High'].rolling(9).max()
    rsv = (df['Close'] - l9) / (h9 - l9) * 100
    k, d, kl, dl = 50.0, 50.0, [], []
    for v in rsv:
        if pd.isna(v): kl.append(k); dl.append(d)
        else:
            k = (2/3)*k + (1/3)*v
            d = (2/3)*d + (1/3)*k
            kl.append(k); dl.append(d)
    df['K'], df['D'] = kl, dl
    return df

@st.cache_data(ttl=300)
def get_rk():
    res = {"TWSE": pd.DataFrame(), "TPEx": pd.DataFrame()}
    try:
        u1 = "https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&type=ALLBUT0999"
        r1 = requests.get(u1, headers=HEADERS, timeout=10).json()
        d1 = pd.DataFrame(r1['tables'][8]['data']).iloc[:, [0, 1, 4]]
        d1.columns = ['代號', '名稱', '金額']
        d1['v'] = pd.to_numeric(d1['金額'].str.replace(',',''), errors='coerce')
        res["TWSE"] = d1.sort_values('v', ascending=False).head(15).copy()
        u2 = "https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php?l=zh-tw&o=json"
        r2 = requests.get(u2, headers=HEADERS, timeout=10).json()
        d2 = pd.DataFrame(r2['aaData']).iloc[:, [0, 1, 9]]
        d2.columns = ['代號', '名稱', '金額']
        d2['v'] = pd.to_numeric(d2['金額'].str.replace(',',''), errors='coerce')
        res["TPEx"] = d2.sort_values('v', ascending=False).head(15).copy()
    except: pass
    return res

# === 3. 核心 112 檔名單 ===
SL = {
    "2330.TW": "台積電", "2317.TW": "鴻海", "2454.TW": "聯發科", 
    "2308.TW": "台達電", "2303.TW": "聯電", "3711.TW": "日月光", 
    "2408.TW": "南亞科", "2344.TW": "華邦電", "2337.TW": "旺宏", 
    "3443.TW": "創意", "3661.TW": "世芯KY", "3034.TW": "聯詠",
    "2379.TW": "瑞昱", "4966.TW": "譜瑞KY", "6415.TW": "矽力KY", 
    "3529.TW": "力旺", "6488.TWO": "環球晶", "5483.TWO": "中美晶", 
    "3105.TWO": "穩懋", "8299.TWO": "群聯", "2382.TW": "廣達", 
    "3231.TW": "緯創", "6669.TW": "緯穎", "2356.TW": "英業達",
    "2324.TW": "仁寶", "2353.TW": "宏碁", "2357.TW": "華碩", 
    "2376.TW": "技嘉", "2377.TW": "微星", "3017.TW": "奇鋐", 
    "3324.TW": "雙鴻", "3653.TW": "健策", "3533.TW": "嘉澤", 
    "3013.TW": "晟銘電", "8210.TW": "勤誠", "7769.TW": "鴻勁",
    "3037.TW": "欣興", "8046.TW": "南電", "3189.TW": "景碩", 
    "2368.TW": "金像電", "4958.TW": "臻鼎KY", "2313.TW": "華通", 
    "6274.TWO": "台燿", "2383.TW": "台光電", "6213.TW": "聯茂",
    "3008.TW": "大立光", "3406.TW": "玉晶光", "1519.TW": "華城",
