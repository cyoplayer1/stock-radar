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

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
HEADERS = {"User-Agent": UA}

# === 2. 核心計算函數 (技術指標) ===
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

# === 3. 籌碼面抓取函數 (三大法人) ===
@st.cache_data(ttl=3600)
def get_twse_chip():
    """抓取上市三大法人買賣超排行"""
    try:
        url = "https://www.twse.com.tw/fund/T86?response=json&selectType=ALLBUT0999"
        res = requests.get(url, headers=HEADERS, verify=False, timeout=10).json()
        if 'data' in res:
            df = pd.DataFrame(res['data'], columns=res['fields'])
            # 欄位：0代號, 1名稱, 2外資買賣, 10投信買賣, 11自營商買賣
            df = df.iloc[:, [0, 1, 2, 10, 11]]
            df.columns = ['代號', '名稱', '外資', '投信', '自營']
            for col in ['外資', '投信', '自營']:
                df[col] = pd.to_numeric(df[col].str.replace(',', ''), errors='coerce').fillna(0)
            df['法人合計'] = df['外資'] + df['投信'] + df['自營']
            return df.sort_values('法人合計', ascending=False)
    except: return None

# === 介面設計 ===
st.title("📡 股神系統旗艦整合版 V3.0")
tabs = st.tabs(["🎯 股神雷達", "💰 成交排行", "📈 基礎看盤", "🚀 波段掃描", "🔥 量能監控", "🔍 低檔快篩", "💎 籌碼分析", "📺 多圖連動"])

# (前 6 個 Tab 的邏輯保持不變，此處省略以節省空間，請沿用之前提供的修正版代碼)

# === 第七個分頁：籌碼面分析 ===
with tabs[6]:
    st.subheader("💎 三大法人：現貨買賣超追蹤")
    if st.button("🔄 刷新今日法人數據", key="refresh_chip"):
        st.cache_data.clear()
    
    chip_df = get_twse_chip()
    if chip_df is not None:
        c1, c2 = st.columns(2)
        with c1:
            st.write("🔥 **法人合計買超 Top 20**")
            st.dataframe(chip_df.head(20).reset_index(drop=True), use_container_width=True)
        with c2:
            st.write("❄️ **法人合計賣超 Top 20**")
            st.dataframe(chip_df.tail(20).sort_values('法人合計').reset_index(drop=True), use_container_width=True)
        
        st.info("💡 註：數據包含外資、投信、自營商（避險+自行買賣），單位為「張」。")
    else:
        st.warning("目前尚未產生法人數據，或證交所 API 連線逾時。")

# === 第八個分頁：多圖連動看盤 (進階版) ===
with tabs[7]:
    col_l, col_r = st.columns([1, 4])
    with col_l:
        st.markdown("### 📺 顯示設定")
        sid_8 = st.text_input("🔍 輸入代號", value="2330", key="tab8_sid")
        p_8 = st.selectbox("時間範圍", ["6mo", "1y", "2y"], index=1)
        ind_8 = st.radio("指標切換", ["KD", "RSI", "成交量"], index=0)
    
    if sid_8:
        tid_8 = sid_8 + ".TW" if "." not in sid_8 else sid_8
        try:
            d = yf.Ticker(tid_8).history(period=p_8)
            if not d.empty:
                d = calculate_kd(d)
                
                # 建立多圖連動結構 (K線 + 指標)
                fig = make_subplots(
                    rows=2, cols=1, 
                    shared_xaxes=True, 
                    vertical_spacing=0.03,
                    row_heights=[0.65, 0.35]
                )

                # --- 上圖：K線與均線 ---
                fig.add_trace(go.Candlestick(
                    x=d.index, open=d['Open'], high=d['High'], 
                    low=d['Low'], close=d['Close'], name='K線'
                ), row=1, col=1)
                
                for ma, color in zip([5, 20, 60], ['#FFFFFF', '#FFFF00', '#FF00FF']):
                    d[f'MA{ma}'] = d['Close'].rolling(ma).mean()
                    fig.add_trace(go.Scatter(x=d.index, y=d[f'MA{ma}'], name=f'MA{ma}', line=dict(color=color, width=1)), row=1, col=1)

                # --- 下圖：動態指標 ---
                if ind_8 == "KD":
                    fig.add_trace(go.Scatter(x=d.index, y=d['K'], name='K線', line=dict(color='#FFFF00')), row=2, col=1)
                    fig.add_trace(go.Scatter(x=d.index, y=d['D'], name='D線', line=dict(color='#00FFFF')), row=2, col=1)
                elif ind_8 == "成交量":
                    colors = ['#FF0000' if c >= o else '#00FF00' for o, c in zip(d['Open'], d['Close'])]
                    fig.add_trace(go.Bar(x=d.index, y=d['Volume'], name='成交量', marker_color=colors), row=2, col=1)
                elif ind_8 == "RSI":
                    delta = d['Close'].diff(); gain = (delta.where(delta > 0, 0)).rolling(14).mean(); loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                    rsi = 100 - (100 / (1 + (gain/loss)))
                    fig.add_trace(go.Scatter(x=d.index, y=rsi, name='RSI', line=dict(color='#FFA500')), row=2, col=1)

                fig.update_layout(height=750, template="plotly_dark", xaxis_rangeslider_visible=False, hovermode='x unified')
                st.plotly_chart(fig, use_container_width=True)
                
                # 下方數據儀表板
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("收盤價", f"{d['Close'].iloc[-1]:.2f}", f"{(d['Close'].iloc[-1]-d['Close'].iloc[-2]):.2f}")
                m2.metric("日K值", f"{d['K'].iloc[-1]:.1f}", f"{(d['K'].iloc[-1]-d['K'].iloc[-2]):.1f}")
                m3.metric("5日均量", f"{int(d['Volume'].tail(5).mean()/1000):,} 張")
                m4.metric("半年位階", f"{round(((d['Close'].iloc[-1]-d['Low'].min())/(d['High'].max()-d['Low'].min()))*100, 1)}%")
        except: st.error("查無此代號，請檢查輸入是否正確。")
