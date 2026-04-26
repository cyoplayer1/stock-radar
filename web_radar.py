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
        ma20 = df['Close'].rolling(window=20).mean().iloc[-1]
        bias = ((close - ma20) / ma20) * 100
        
        status = "🟢 折價 (適合分批建倉)" if bias < 0 else "🔴 溢價 (建議觀望)"
        return {
            "ETF名稱": name, 
            "收盤價": round(close, 2), 
            "月線(20MA)": round(ma20, 2),
            "乖離率(%)": round(bias, 2),
            "進場判定": status
        }
    except Exception: 
        return None

def analyze_volume_breakout(ticker, stock_name):
    """第五分頁：異常爆量買賣監控"""
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="1mo")
        df.dropna(subset=['Close', 'Volume'], inplace=True)
        if len(df) < 6: 
            return None

        vol_today = df['Volume'].iloc[-1]
        vol_5ma = df['Volume'].iloc[-6:-1].mean() 
        close_today = df['Close'].iloc[-1]
        open_today = df['Open'].iloc[-1]
        close_yest = df['Close'].iloc[-2]

        if vol_5ma < 500000: 
            return None

        vol_ratio = vol_today / vol_5ma if vol_5ma > 0 else 0

        if vol_ratio > 1.5:
            status = ""
            if close_today > open_today and close_today > close_yest:
                status = "🔥 爆量上漲 (買盤湧入)"
            elif close_today < open_today and close_today < close_yest:
                status = "🩸 爆量下跌 (賣壓出籠)"
            else:
                status = "⚠️ 爆量震盪 (多空交戰)"

            clean_ticker = ticker.replace('.TW', '').replace('.TWO', '')
            return {
                '標的名稱': f"{clean_ticker} {stock_name}",
                '收盤價': round(close_today, 2),
                '今日成交量(張)': int(vol_today / 1000),
                '5日均量(張)': int(vol_5ma / 1000),
                '爆量倍數': round(vol_ratio, 1),
                '異動狀態': status
            }
        return None
    except Exception: 
        return None

# ================= 股市排行系統 函數 =================
@st.cache_data(ttl=300)
def get_twse_top_15():
    try:
        res = requests.get("https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&type=ALLBUT0999", headers=HEADERS, verify=False, timeout=10)
        data = res.json()
        stock_data, fields = None, None
        if 'tables' in data:
            for table in data['tables']:
                if 'fields' in table and 'data' in table:
                    if '證券代號' in table['fields'] and '成交金額' in table['fields']:
                        fields, stock_data = table['fields'], table['data']
                        break
        if not stock_data:
            for key, val in data.items():
                if key.startswith('fields') and isinstance(val, list):
                    if '證券代號' in val and '成交金額' in val:
                        data_key = key.replace('fields', 'data')
                        if data_key in data:
                            fields, stock_data = val, data[data_key]
                            break
        if not stock_data: 
            return None, data.get('stat', '找不到上市資料')
            
        df = pd.DataFrame(stock_data, columns=fields)[['證券代號', '證券名稱', '成交金額']]
        df['成交金額'] = pd.to_numeric(df['成交金額'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
        df_sorted = df.sort_values(by='成交金額', ascending=False).head(15)
        df_sorted['成交金額(元)'] = df_sorted['成交金額'].apply(lambda x: f"{int(x):,}")
        df_sorted.index = range(1, 16)
        return df_sorted.drop(columns=['成交金額']), "OK"
    except Exception as e: 
        return None, f"上市錯誤: {e}"

@st.cache_data(ttl=300)
def get_tpex_top_15():
    try:
        res = requests.get("https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php?l=zh-tw&o=json", headers=HEADERS, verify=False, timeout=10)
        data = res.json()
        stock_data = []
        if 'aaData' in data and data['aaData']: 
            stock_data = data['aaData']
        elif 'tables' in data:
            for table in data['tables']:
                if 'data' in table and len(table['data']) > 0:
                    stock_data = table['data']
                    break
        if not stock_data: 
            return None, "找不到上櫃資料"
            
        df = pd.DataFrame(stock_data)
        col_val = 9 if df.shape[1] >= 10 else df.shape[1] - 2
        df = df[[0, 1, col_val]]
        df.columns = ['證券代號', '證券名稱', '成交金額']
        df['成交金額'] = pd.to_numeric(df['成交金額'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
        df_sorted = df.sort_values(by='成交金額', ascending=False).head(15)
        df_sorted['成交金額(元)'] = df_sorted['成交金額'].apply(lambda x: f"{int(x):,}")
        df_sorted.index = range(1, 16)
        return df_sorted.drop(columns=['成交金額']), "OK"
    except Exception as e: 
        return None, f"上櫃錯誤: {e}"

# ================= 名單設定 =================
STOCKS = {
    "2330.TW": "台積電", "2317.TW": "鴻海", "2454.TW": "聯發科", "2308.TW": "台達電", "2303.TW": "聯電", "3711.TW": "日月光", "2408.TW": "南亞科", "2344.TW": "華邦電
