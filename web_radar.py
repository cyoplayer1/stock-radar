import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import warnings
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib3

# === 1. 系統設定 (防截斷 UA) ===
warnings.filterwarnings("ignore")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
st.set_page_config(page_title="股神系統雷達", page_icon="📡", layout="wide")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
UA += "AppleWebKit/537.36 (KHTML, like Gecko) "
UA += "Chrome/120.0.0.0 Safari/537.36"
HEADERS = {"User-Agent": UA}

# === 2. 核心計算函數 (繼承自股神系統雷達.py) ===
def calculate_kd(df):
    if len(df) < 9: return df
    df['9_min'] = df['Low'].rolling(window=9).min()
    df['9_max'] = df['High'].rolling(window=9).max()
    df['RSV'] = (df['Close'] - df['9_min']) / (df['9_max'] - df['9_min']) * 100
    k, d, k_v, d_v = 50.0, 50.0, [], []
    for rsv in df['RSV']:
        if pd.isna(rsv):
            k_v.append(50.0); d_v.append(50.0)
        else:
            k = (2/3) * k + (1/3) * rsv
            d = (2/3) * d + (1/3) * k
            k_v.append(k); d_v.append(d)
    df['K'], df['D'] = k_v, d_v
    return df

def analyze_stock_score(ticker, name):
    """老盧原始 100 分制評分邏輯"""
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="2y")
        df.dropna(subset=['Close', 'Volume'], inplace=True)
        if len(df) < 60: return None
        close = df['Close'].iloc[-1]
        v_5d = df['Volume'].tail(5).mean()
        if v_5d < 1000000: return None 
        score, tags = 0, []
        ma20 = df['Close'].rolling(20).mean().iloc[-1]
        if close > ma20: score += 20; tags.append("[站上月線]")
        df = calculate_kd(df.copy())
        dk, dd = df['K'].iloc[-1], df['D'].iloc[-1]
        dyk, dyd = df['K'].iloc[-2], df['D'].iloc[-2]
        if (dk > dd) and (dyk <= dyd): score += 40; tags.append("[日剛金叉]")
        elif dk > dd: score += 20; tags.append("[日線偏多]")
        df_w = df.resample('W-FRI').agg({'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}).dropna()
        df_w = calculate_kd(df_w.copy())
        wk = df_w['K'].iloc[-1]
        if wk > df_w['D'].iloc[-1]: score += 40; tags.append("[周線偏多]")
        tid = ticker.replace('.TW', '').replace('.TWO', '')
        return {'標的': f"{tid} {name}", '評分': f"{score}分", '收盤': round(close, 2), '狀態': " + ".join(tags) if tags else "休息", '日K': round(dk, 1), '周K': round(wk, 1), '5日均量(張)': int(v_5d/1000), 'Sort_Score': score}
    except: return None

# === 3. 排行函數 (繼承自 web_top15.py 並強化上櫃偵測) ===
@st.cache_data(ttl=300)
def get_rank_data(m_type):
    try:
        if m_type == "TWSE":
            u = "https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&type=ALLBUT0999"
            res = requests.get(u, headers=HEADERS, verify=False, timeout=10).json()
            df = pd.DataFrame(res['tables'][8]['data'])
            df.columns = res['tables'][8]['fields']
            df = df[['證券代號', '證券名稱', '成交金額']]
        else:
            u = "https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php?l=zh-tw&o=json"
            res = requests.get(u, headers=HEADERS, verify=False, timeout=10).json()
            df = pd.DataFrame(res.get('aaData', []))
            # 動態偵測金額欄位 (通常是 8 或 9)
            df_n = df.apply(pd.to_numeric, errors='coerce').fillna(0)
            v_col = df_n.sum().idxmax()
            df = df[[0, 1, v_col]]
            df.columns = ['證券代號', '證券名稱', '成交金額']
        df['值'] = pd.to_numeric(df['成交金額'].astype(str).str.replace(',',''), errors='coerce').fillna(0)
        df_sorted = df.sort_values('值', ascending=False).head(15)
        df_sorted['金額'] = df_sorted['值'].apply(lambda x: f"{int(x/100000000):,} 億")
        return df_sorted[['證券代號','證券名稱','金額']].reset_index(drop=True)
    except: return None

# === 4. 完整的 112 檔名單 (垂直定義防截斷) ===
STOCKS = {
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
    "2892.TW": "第一金", "
