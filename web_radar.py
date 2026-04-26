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

# === 1. 系統環境設定 ===
warnings.filterwarnings("ignore")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
st.set_page_config(page_title="股神系統雷達", page_icon="📡", layout="wide")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
UA += "AppleWebKit/537.36 (KHTML, like Gecko) "
UA += "Chrome/120.0.0.0 Safari/537.36"
HEADERS = {"User-Agent": UA}

# === 2. 核心計算函數 ===
def calculate_kd(df):
    if len(df) < 9: return df
    df['9_min'] = df['Low'].rolling(window=9).min()
    df['9_max'] = df['High'].rolling(window=9).max()
    df['RSV'] = (df['Close'] - df['9_min']) / (df['9_max'] - df['9_min']) * 100
    k_v, d_v = [], []
    k, d = 50.0, 50.0
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
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="2y")
        if df.empty or len(df) < 60: return None
        close = df['Close'].iloc[-1]
        vol_5d = df['Volume'].tail(5).mean()
        if vol_5d < 1000000: return None
        
        score, tags = 0, []
        ma20 = df['Close'].rolling(20).mean().iloc[-1]
        if close > ma20: score += 20; tags.append("[站上月線]")
        
        df = calculate_kd(df.copy())
        dk, dd = df['K'].iloc[-1], df['D'].iloc[-1]
        dyk, dyd = df['K'].iloc[-2], df['D'].iloc[-2]
        if (dk > dd) and (dyk <= dyd): 
            score += 40; tags.append("[日剛金叉]")
        elif dk > dd: 
            score += 20; tags.append("[日線偏多]")
            
        df_w = df.resample('W-FRI').agg({'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}).dropna()
        df_w = calculate_kd(df_w.copy())
        wk = df_w['K'].iloc[-1]
        if wk > df_w['D'].iloc[-1]: 
            score += 40; tags.append("[周線偏多]")
            
        tid = ticker.replace('.TW', '').replace('.TWO', '')
        return {
            '標的': f"{tid} {name}", '評分': f"{score}分", 
            '收盤': round(close, 2), '狀態': " + ".join(tags) if tags else "休息", 
            '日K': round(dk, 1), '周K': round(wk, 1), 
            '5日均量': int(vol_5d/1000), 'Sort_Score': score
        }
    except: return None

# === 3. 成交排行獲取 ===
@st.cache_data(ttl=300)
def get_rank(m_type):
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
            df_n = df.apply(pd.to_numeric, errors='coerce').fillna(0)
            v_col = df_n.sum().idxmax()
            df = df[[0, 1, v_col]]
            df.columns = ['證券代號', '證券名稱', '成交金額']
        df['值'] = pd.to_numeric(df['成交金額'].astype(str).str.replace(',',''), errors='coerce').fillna(0)
        df = df.sort_values('值', ascending=False).head(15)
        df['金額'] = df['值'].apply(lambda x: f"{int(x/100000000):,} 億")
        return df[['證券代號','證券名稱','金額']].reset_index(drop=True)
    except: return None

# === 4. 全台股低檔快篩邏輯 ===
def check_low_breakout(ticker, name):
    """檢查全台股標的是否符合低檔爆量條件"""
    try:
        df = yf.Ticker(ticker).history(period="6mo")
        if df.empty or len(df) < 40: return None
        v_now = df['Volume'].iloc[-1]
        v_avg = df['Volume'].iloc[-6:-1].mean()
        # 條件 1：量能倍數 > 1.8
        if v_now < v_avg * 1.8: return None
        
        # 條件 2：判斷低檔 (價格在半年區間的 25% 以下)
        low_p = df['Low'].min()
        high_p = df['High'].max()
        curr_p = df['Close'].iloc[-1]
        price_range = high_p - low_p
        if price_range == 0: return None
        pos = (curr_p - low_p) / price_range
        
        if pos < 0.25: # 符合低檔爆量
            return {
                '代號名稱': f"{ticker.split('.')[0]} {name}",
                '收盤價': round(curr_p, 2),
                '量能倍數': round(v_now / v_avg, 2),
