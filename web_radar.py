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

# === 1. 基礎設定 ===
warnings.filterwarnings("ignore")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
st.set_page_config(page_title="股神系統雷達", page_icon="📡", layout="wide")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# === 2. 核心計算 (保留原始檔案邏輯) ===
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
        df.dropna(subset=['Close', 'Volume'], inplace=True)
        if len(df) < 60: return None
        
        close = df['Close'].iloc[-1]
        vol_5d = df['Volume'].tail(5).mean()
        if vol_5d < 1000000: return None
            
        score, tags = 0, []
        ma20 = df['Close'].rolling(20).mean().iloc[-1]
        if close > ma20:
            score += 20; tags.append("[站上月線]")
            
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
            '日K': round(dk, 1), '周K
