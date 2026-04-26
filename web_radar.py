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

# === 系統設定與警告停用 ===
warnings.filterwarnings("ignore")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 設定網頁標題與版面寬度
st.set_page_config(page_title="綜合投資分析站", page_icon="📡", layout="wide")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# ================= 核心計算函數 =================
def calculate_kd(df):
    if len(df) < 9: 
        return df
    df['9_min'] = df['Low'].rolling(window=9).min()
    df['9_max'] = df['High'].rolling(window=9).max()
    df['RSV'] = (df['Close'] - df['9_min']) / (df['9_max'] - df['9_min']) * 100
    
    k_values, d_values = [], []
    k, d = 50.0, 50.0
    for rsv in df['RSV']:
        if pd.isna(rsv):
            k_values.append(50.0)
            d_values.append(50.0)
        else:
            k = (2/3) * k + (1/3) * rsv
            d = (2/3) * d + (1/3) * k
            k_values.append(k)
            d_values.append(d)
    df['K'], df['D'] = k_values, d_values
    return df

def calculate_bollinger(df):
    df['20MA'] = df['Close'].rolling(window=20).mean()
    df['STD'] = df['Close'].rolling(window=20).std()
    df['UPPER'] = df['20MA'] + (2 * df['STD'])
    df['LOWER'] = df['20MA'] - (2 * df['STD'])
    return df

def analyze_stock_score(ticker, stock_name):
    """第一分頁：技術面評分系統"""
    try:
        stock = yf.Ticker(ticker)
        df_daily = stock.history(period="1y")
        df_daily.dropna(subset=['Close', 'Volume'], inplace=True)
        if df_daily.empty or len(df_daily) < 60: 
            return None
        
        close_price = df_daily['Close'].iloc[-1]
        avg_vol_5d = df_daily['Volume'].tail(5).mean()
        if avg_vol_5d < 1000000: 
            return None
            
        score = 0
        tags = []
        df_daily['20MA'] = df_daily['Close'].rolling(window=20).mean()
        if close_price > df_daily['20MA'].iloc[-1]:
            score += 20
            tags.append("[站上月線]")
            
        df_daily = calculate_kd(df_daily.copy())
        k, d = df_daily['K'].iloc[-1], df_daily['D'].iloc[-1]
        yk, yd = df_daily['K'].iloc[-2], df_daily['D'].iloc[-2]
        
        if k > d and yk <= yd:
            score += 40
            tags.append("[日剛金叉]")
        elif k > d:
            score += 20
            tags.append("[日線偏多]")
            
        clean_ticker = ticker.replace('.TW', '').replace('.TWO', '')
        return {
            '標的名稱': f"{clean_ticker} {stock_name}", 
            '評分': score,
            '收盤價': round(close_price, 2),
            '技術面狀態': " + ".join(tags) if tags else "空頭休息",
            '日K': round(k, 1), 
            '5日均量(張)': int(avg_vol_5d / 1000), 
            'ticker': ticker
        }
    except Exception: 
        return None

def analyze_bollinger_breakout(ticker, stock_name):
    """第四分頁：布林通道爆發策略"""
    try:
        df = yf.Ticker(ticker).history(period="6mo")
        df.dropna(subset=['Close'], inplace=True)
        if len(df) < 20: 
            return None
        
        df = calculate_bollinger(df)
        close = df['Close'].iloc[-1]
        upper = df['UPPER'].iloc[-1]
        ma20 = df['20MA'].iloc[-1]
        
        is_breakout = close > upper
        bandwidth = ((upper - df['LOWER'].iloc[-1]) / ma20) * 100
        
        if is_breakout:
            clean_ticker = ticker.replace('.TW', '').replace('.TWO', '')
            return {
                '標的名稱': f"{clean_ticker} {stock_name}", 
                '收盤價': round(close, 2),
                '上軌價位': round(upper, 2), 
                '通道寬度(%)': round(bandwidth, 1),
                '狀態': '🔥 突破上軌 (強勢爆發)'
            }
        return None
    except Exception: 
        return None

def analyze_etf_yield(ticker, name):
    """第四分頁：高息ETF乖離率計算"""
    try:
        df = yf.Ticker(ticker).history(period="3mo")
        df.dropna(subset=['Close'], inplace=True)
        if len(df) < 20: 
            return None
        
        close = df['Close'].iloc[-1]
        ma20 = df['Close'].rolling(window=2
