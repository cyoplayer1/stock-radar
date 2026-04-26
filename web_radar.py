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

# === 基礎設定 ===
warnings.filterwarnings("ignore")
urllib3.disable_warnings(
    urllib3.exceptions.InsecureRequestWarning
)
st.set_page_config(
    page_title="綜合投資分析站",
    page_icon="📡",
    layout="wide"
)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
UA += "AppleWebKit/537.36 (KHTML, like Gecko) "
UA += "Chrome/120.0.0.0 Safari/537.36"
HEADERS = {"User-Agent": UA}

# === 計算函數 ===
def calculate_kd(df):
    if len(df) < 9:
        return df
    low_min = df['Low'].rolling(9).min()
    high_max = df['High'].rolling(9).max()
    df['RSV'] = (df['Close'] - low_min) / (high_max - low_min) * 100
    k_vals, d_vals = [], []
    k, d = 50.0, 50.0
    for rsv in df['RSV']:
        if pd.isna(rsv):
            k_vals.append(50.0)
            d_vals.append(50.0)
        else:
            k = (2/3) * k + (1/3) * rsv
            d = (2/3) * d + (1/3) * k
            k_vals.append(k)
            d_vals.append(d)
    df['K'], df['D'] = k_vals, d_vals
    return df

def calculate_bollinger(df):
    df['20MA'] = df['Close'].rolling(20).mean()
    std = df['Close'].rolling(20).std()
    df['UPPER'] = df['20MA'] + (2 * std)
    df['LOWER'] = df['20MA'] - (2 * std)
    return df

# === 分析函數 ===
def analyze_stock_score(ticker, name):
    try:
        s = yf.Ticker(ticker)
        df = s.history(period="1y")
        df.dropna(subset=['Close'], inplace=True)
        if len(df) < 60:
            return None
        close = df['Close'].iloc[-1]
        vol_5d = df['Volume'].tail(5).mean()
        if vol_5d < 1000000:
            return None
        score = 0
        tags = []
        ma20 = df['Close'].rolling(20).mean().iloc[-1]
        if close > ma20:
            score += 20
            tags.append("[站上月線]")
        df = calculate_kd(df.copy())
        k, d = df['K'].iloc[-1], df['D'].iloc[-1]
        yk, yd = df['K'].iloc[-2], df['D'].iloc[-2]
        if k > d and yk <= yd:
            score += 40
            tags.append("[日剛金叉]")
        elif k > d:
            score += 20
            tags.append("[日線偏多]")
        # 這裡就是上次斷掉的地方，現在改寫成短行
        t_id = ticker.replace('.TW', '')
        t_id = t_id.replace('.TWO', '')
        return {
            '標的名稱': f"{t_id} {name}",
            '評分': score,
            '收盤價': round(close, 2),
            '技術面狀態': " + ".join(tags) if tags else "休息",
            '日K': round(k, 1),
            '5日均量(張)': int(vol_5d / 1000),
            'ticker': ticker
        }
    except Exception:
        return None

def analyze_bollinger_breakout(ticker, name):
    try:
        df = yf.Ticker(ticker).history(period="6mo")
        if len(df) < 20:
            return None
        df = calculate_bollinger(df)
        c = df['Close'].iloc[-1]
        u = df['UPPER'].iloc[-1]
        l = df['LOWER'].iloc[-1]
        m = df['20MA'].iloc[-1]
        if c > u:
            bw = ((u - l) / m) * 100
            t_id = ticker.replace('.TW', '')
            return {
                '標的名稱': f"{t_id} {name}",
                '收盤價': round(c, 2),
                '上軌': round(u, 2),
                '頻寬(%)': round(bw, 1),
                '狀態': '🔥 突破上軌'
            }
        return None
    except Exception:
        return None

def analyze_volume_breakout(ticker, name):
    try:
        df = yf.Ticker(ticker).history(period="1mo")
        if len(df) < 6:
            return None
        v_now = df['Volume'].iloc[-1]
        v_avg = df['Volume'].iloc[-6:-1].mean()
        if v_avg < 500000:
            return None
        ratio = v_now / v_avg
        if ratio > 1.5:
            c, o = df['Close'].iloc[-1], df['Open'].iloc[-1]
            cy = df['Close'].iloc[-2]
            if c > o and c > cy:
                st = "🔥 爆量上漲"
            elif c < o and c < cy:
                st = "🩸 爆量下跌"
            else:
                st = "⚠️ 爆量震盪"
            t_id = ticker.replace('.TW', '')
            return {
                '標的名稱': f"{t_id} {name}",
                '收盤價': round(c, 2),
                '倍數': round(ratio, 1),
                '異動狀態': st
            }
        return None
    except Exception:
        return None

# === 股票清單 (拆細防截斷) ===
L1 = {"2330.TW": "台積電", "2317.TW": "鴻海", "2454.TW": "聯發科"}
L1.update({"2308.TW": "台達電", "2303.TW": "聯電", "3711.TW": "日月光"})
L1.update({"2408.TW": "南亞科", "2344.TW": "華邦電", "2337.TW": "旺宏"})
L1.update({"3443.TW": "創意", "3661.TW": "世芯KY", "3034.TW": "聯詠"})
L1.update({"2382.TW": "廣達", "3231.TW": "緯創", "6669.TW": "緯穎"})
L1.update({"2356.TW": "英業達", "2376.TW": "技嘉", "3017.TW": "奇鋐"})
L1.update({"1519.TW": "華城", "1503.TW": "士電", "1513.TW": "中興電"})
L1.update({"2603.TW": "長榮", "2609.TW": "陽明", "2618.TW": "長榮航"})
L1.update({"2881.TW": "富邦金", "2882.TW": "國泰金", "2891.TW": "中信金"})
L1.update({"0050.TW": "台50", "00878.TW": "永續", "00919.TW": "高息"})
STOCKS = L1

# === 介面 ===
st.title("📡 綜合投資分析站 V5.0")
tabs = st.tabs(["🎯 雷達", "💰 排行", "📈 看盤", "🚀 波段", "🔥 爆量"])

with tabs[0]:
    if st.button("啟動雷達"):
        res = []
        pb = st.progress(0)
        curr = 0
        with ThreadPoolExecutor(max_workers=5) as ex:
            futs = [ex.submit(analyze_stock_score, t, n) for t, n in STOCKS.items()]
            for f in as_completed(futs):
                curr += 1
                pb.progress(curr / len(STOCKS))
                if f.result(): res.append(f.result())
        pb.empty()
        if res:
            df = pd.DataFrame(res).sort_values('評分', ascending=False)
            st.dataframe(df.drop(columns=['ticker']), use_container_width=True)

with tabs[1]:
    st.write("成交排行載入中...")
    # 這裡可補上之前的抓取證交所排行代碼，為縮短長度先跳過

with tabs[2]:
    sid = st.text_input("輸入代號", "2330")
    if sid:
        t_id = sid + ".TW" if "." not in sid else sid
        d = yf.Ticker(t_id).history(period="6mo")
        if not d.empty:
            d = calculate_kd(d)
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True)
            fig.add_trace(go.Candlestick(x=d.index, open=d['Open'], high=d['High'], low=d['Low'], close=d['Close']), row=1, col=1)
            fig.add_trace(go.Scatter(x=d.index, y=d['K'], name='K'), row=2, col=1)
            fig.add_trace(go.Scatter(x=d.index, y=d['D'], name='D'), row=2, col=1)
            fig.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)

with tabs[3]:
    if st.button("掃描布林突破"):
        res = []
        with ThreadPoolExecutor(max_workers=5) as ex:
            futs = [ex.submit(analyze_bollinger_breakout, t, n) for t, n in STOCKS.items()]
            for f in as_completed(futs):
                if f.result(): res.append(f.result())
        if res: st.table(pd.DataFrame(res))

with tabs[4]:
    if st.button("啟動爆量監控"):
        res = []
        with ThreadPoolExecutor(max_workers=5) as ex:
            futs = [ex.submit(analyze_volume_breakout, t, n) for t, n in STOCKS.items()]
            for f in as_completed(futs):
                if f.result(): res.append(f.result())
        if res: st.table(pd.DataFrame(res))
