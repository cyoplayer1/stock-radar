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
import os
import json
import numpy as np

# === 升級套件：斷線重連避震器 ===
try:
    from tenacity import retry, wait_exponential, stop_after_attempt
except ImportError:
    st.error("⚠️ 缺少 tenacity 套件！")
    st.info("💡 解法：本機請執行 `pip install tenacity`；若是部署在 Streamlit Cloud，請確認 requirements.txt 內有加入 `tenacity`。")
    st.stop()  # 加上這行，強制停止畫面渲染，避免後續程式碼找不到 retry 而大當機

# === 1. 系統環境設定與版面美化 ===
warnings.filterwarnings("ignore")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
st.set_page_config(page_title="阿綜專屬：極簡智能雷達", page_icon="📈", layout="wide", initial_sidebar_state="expanded")

# 🎨 注入客製化 CSS (淺色質感模式 + 台股紅綠配色)
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
DEFAULT_SECTORS = {"2330": "半導體", "2317": "AI伺服器", "3017": "散熱模組", "2603": "航運", "2881": "金融"}

STOCKS_DICT = DEFAULT_STOCKS.copy()
CLEAN_TO_FULL_MAP = {k.split('.')[0]: k for k in STOCKS_DICT.keys()}
SECTOR_MAP = DEFAULT_SECTORS.copy()

# === 3. 基礎函數 (網路、資料獲取) ===
@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
def safe_get_json(url, headers):
    res = requests.get(url, headers=headers, timeout=10, verify=False)
    res.raise_for_status() 
    return res.json()

def safe_get_json_fallback(url, headers):
    try: return safe_get_json(url, headers)
    except: return {}

@st.cache_data(ttl=86400, show_spinner=False)
def get_all_tw_stock_data():
    full_ids = []
    stock_dict = {}
    try:
        tse = safe_get_json_fallback("https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&type=ALLBUT0999", HEADERS)
        if tse and 'tables' in tse:
            for t in tse['tables']:
                if '證券代號' in t.get('fields', []) and '證券名稱' in t.get('fields', []):
                    idx_c = t['fields'].index('證券代號')
                    idx_n = t['fields'].index('證券名稱')
                    for row in t['data']:
                        code = row[idx_c].strip()
                        name = row[idx_n].strip()
                        if len(code) == 4 and code.isdigit():
                            full_ids.append(f"{code}.TW")
                            stock_dict[f"{code}.TW"] = name
                            stock_dict[code] = name
    except: pass
    try:
        otc = safe_get_json_fallback("https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php?l=zh-tw&o=json", HEADERS)
        data_otc = otc.get('aaData', []) or (otc.get('tables', [{}])[0].get('data', []) if 'tables' in otc else [])
        for row in data_otc:
            code = str(row[0]).strip()
            name = str(row[1]).strip()
            if len(code) == 4 and code.isdigit():
                full_ids.append(f"{code}.TWO")
                stock_dict[f"{code}.TWO"] = name
                stock_dict[code] = name
    except: pass
    
    if not full_ids:
        return list(DEFAULT_STOCKS.keys()), DEFAULT_STOCKS.copy()
    return full_ids, stock_dict

@st.cache_data(ttl=900, show_spinner=False)
def fetch_bulk_yf_data(full_ticker_list, period="1y"):
    valid_tickers = [t for t in full_ticker_list if t]
    if not valid_tickers: return {}
    res_dict = {}
    chunk_size = 400 
    for i in range(0, len(valid_tickers), chunk_size):
        chunk = valid_tickers[i:i+chunk_size]
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

# 🌟 KD 與 MACD 指標運算 🌟
def calculate_kd(df):
    if len(df) < 9: return df
    df['9_min'] = df['Low'].rolling(window=9).min()
    df['9_max'] = df['High'].rolling(window=9).max()
    df['RSV'] = (df['Close'] - df['9_min']) / (df['9_max'] - df['9_min']) * 100
    k_v, d_v, k, d = [], [], 50.0, 50.0
    for rsv in df['RSV']:
        if pd.isna(rsv): k_v.append(50.0); d_v.append(50.0)
        else: k = (2/3)*k + (1/3)*rsv; d = (2/3)*d + (1/3)*k; k_v.append(k); d_v.append(d)
    df['K'], df['D'] = k_v, d_v
    return df

def calculate_macd(df):
    df['EMA12'] = df['Close'].ewm(span=12, adjust=False).mean()
    df['EMA26'] = df['Close'].ewm(span=26, adjust=False).mean()
    df['DIF'] = df['EMA12'] - df['EMA26']
    df['MACD'] = df['DIF'].ewm(span=9, adjust=False).mean()
    df['Hist'] = df['DIF'] - df['MACD']
    return df

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
            for d in r1['data']: inst_map[d[0].strip()] = int(d[2].replace(',', '')) + int(d[10].replace(',', ''))
        r2 = safe_get_json_fallback("https://www.tpex.org.tw/web/stock/fund/T86/T86_result.php?l=zh-tw&o=json", HEADERS)
        if 'aaData' in r2:
            for d in r2['aaData']: inst_map[d[0].strip()] = int(d[8].replace(',', '')) + int(d[10].replace(',', ''))
    except: pass
    return inst_map

# === 4. 雷達分析核心引擎 ===

def analyze_stock_score_v2(clean_id, df_ticker, full_id, inst_map, hot_list, is_bearish=False):
    try:
        df = df_ticker.copy()
        if df.empty or len(df) < 65: return None
        c, v = df['Close'].iloc[-1], df['Volume'].iloc[-1]
        v5 = df['Volume'].iloc[-6:-1].mean()
        if v5 < 500000: return None
        
        df['MA5'] = df['Close'].rolling(5).mean()
        df['MA20'] = df['Close'].rolling(20).mean()
        df['MA60'] = df['Close'].rolling(60).mean()
        
        if is_bearish and (c < df['MA60'].iloc[-1] or inst_map.get(clean_id, 0) <= 0): return None
            
        df = calculate_kd(df)
        df = calculate_macd(df)
        
        s, tags = 0, []
        
        upper_shadow = df['High'].iloc[-1] - max(df['Open'].iloc[-1], c)
        body = abs(c - df['Open'].iloc[-1])
        is_false_breakout = (upper_shadow > body * 1.5) and ((df['High'].iloc[-1] - c) / c > 0.02)
        if is_false_breakout:
            tags.append("🚨[假突破警戒]")
            
        if c > df['MA5'].iloc[-1] > df['MA20'].iloc[-1] > df['MA60'].iloc[-1]: s+=1; tags.append("[均線多頭]")
        if df['MA20'].iloc[-1] > df['MA20'].iloc[-2]: s+=1; tags.append("[月線向上]")
        if v > v5 * 1.5: s+=1; tags.append("[爆量攻擊]")
        if df['K'].iloc[-1] > df['D'].iloc[-1] and df['K'].iloc[-2] <= df['D'].iloc[-2]: s+=1; tags.append("[KD金叉]")
        if df['Hist'].iloc[-1] > 0 and df['Hist'].iloc[-1] > df['Hist'].iloc[-2]: s+=1; tags.append("[MACD強勢]")
        if c > df['High'].iloc[-21:-1].max(): s+=1; tags.append("[創20日新高]")
        
        is_higher_low = df['Low'].iloc[-1] >= df['Low'].iloc[-2]
        is_higher_high = df['High'].iloc[-1] > df['High'].iloc[-2]
        if is_higher_low and is_higher_high and c > df['MA20'].iloc[-1]:
            s+=1; tags.append("👑[底底高架構]")
            
        if clean_id in hot_list: tags.append("🔥[熱門股]")
        inst_val = inst_map.get(clean_id, 0)
        
        star_display = ("🌟" * s) + ("⚫" * (7 - s)) if s > 0 else "💤 盤整"
        
        if s >= 4: 
            return {
                '代號': clean_id, '名稱': STOCKS_DICT.get(full_id, clean_id), 
                '星等': star_display, '收盤價': round(c, 2), 
                '法人買賣超(張)': inst_val, '觸發條件': " ".join(tags)
            }
    except: return None

def analyst_three_line_macd_scanner(clean_id, df_ticker, full_id, inst_map, is_bearish=False):
    try:
        df = df_ticker.copy()
        if df.empty or len(df) < 60: return None
        c, v = df['Close'].iloc[-1], df['Volume'].iloc[-1]
        v5_avg = df['Volume'].iloc[-6:-1].mean()
        if v5_avg < 500000: return None 

        df['5MA'] = df['Close'].rolling(5).mean()
        df['10MA'] = df['Close'].rolling(10).mean()
        df['20MA'] = df['Close'].rolling(20).mean()
        df = calculate_macd(df)

        is_three_line_bull = (df['5MA'].iloc[-1] > df['10MA'].iloc[-1] > df['20MA'].iloc[-1])
        is_macd_above_zero = (df['DIF'].iloc[-1] > 0) and (df['MACD'].iloc[-1] > 0)
        is_macd_golden = (df['DIF'].iloc[-1] > df['MACD'].iloc[-1]) 

        upper_shadow = df['High'].iloc[-1] - max(df['Open'].iloc[-1], c)
        body = abs(c - df['Open'].iloc[-1])
        is_false_breakout = (upper_shadow > body * 1.5) and ((df['High'].iloc[-1] - c) / c > 0.02)

        if is_three_line_bull and is_macd_above_zero and is_macd_golden:
            if is_bearish and inst_map.get(clean_id, 0) <= 0: return None
            if is_false_breakout: return None
            
            prev_bull = (df['5MA'].iloc[-2] > df['10MA'].iloc[-2] > df['20MA'].iloc[-2])
            prev_zero = (df['DIF'].iloc[-2] > 0) and (df['MACD'].iloc[-2] > 0)
            is_fresh = not (prev_bull and prev_zero)

            return {
                '代號': clean_id, '名稱': STOCKS_DICT.get(full_id, clean_id), 
                '星等': "🚀 剛觸發三線零軸" if is_fresh else "🌟 續強中",
                '收盤價': round(c, 2), 
                '法人買賣超(張)': inst_map.get(clean_id, 0),
                '觸發條件': "三線多頭 + MACD 零軸之上"
            }
    except: return None

def ultimate_breakout_scanner(clean_id, df_ticker, full_id, inst_map, is_bearish=False):
    try:
        df = df_ticker.copy()
        if df.empty or len(df) < 60: return None
        c, v = df['Close'].iloc[-1], df['Volume'].iloc[-1]
        v5_avg = df['Volume'].iloc[-6:-1].mean()
        if v5_avg < 500000: return None
        
        recent_10d_high = df['High'].iloc[-11:-1].max()
        recent_10d_low = df['Low'].iloc[-11:-1].min()
        is_breaking_high = c >= df['High'].iloc[-21:-1].max()
        
        df['MA5'] = df['Close'].rolling(5).mean()
        df['MA20'] = df['Close'].rolling(20).mean()
        
        is_bull_trend = (df['MA5'].iloc[-1] > df['MA20'].iloc[-1])
        consolidation_pct = (recent_10d_high - recent_10d_low) / recent_10d_low
        is_tight = consolidation_pct < 0.08 
        is_vol_boom = v > (v5_avg * 2.0)
        
        upper_shadow = df['High'].iloc[-1] - max(df['Open'].iloc[-1], c)
        body = abs(c - df['Open'].iloc[-1])
        is_false_breakout = (upper_shadow > body * 1.5) and ((df['High'].iloc[-1] - c) / c > 0.02)

        if is_bull_trend and is_tight and is_breaking_high and is_vol_boom:
            if is_bearish and inst_map.get(clean_id, 0) <= 0: return None
            if is_false_breakout: return None

            return {
                '代號': clean_id, '名稱': STOCKS_DICT.get(full_id, clean_id), 
                '星等': "⚡ 壓縮突破",
                '收盤價': round(c, 2), 
                '法人買賣超(張)': inst_map.get(clean_id, 0),
                '觸發條件': f"爆量 {v/v5_avg:.1f}倍 + 創高"
            }
    except: return None

def bearish_breakdown_scanner(clean_id, df_ticker, full_id, inst_map):
    try:
        df = df_ticker.copy()
        if df.empty or len(df) < 60: return None
        c = df['Close'].iloc[-1]
        df['MA20'] = df['Close'].rolling(20).mean()
        
        is_ma_going_down = (df['MA20'].iloc[-1] < df['MA20'].iloc[-3])
        recent_10d_low = df['Low'].iloc[-11:-1].min()
        is_breaking_down = c < recent_10d_low
        inst_val = inst_map.get(clean_id, 0)
        
        if c < df['MA20'].iloc[-1] and is_ma_going_down and is_breaking_down and inst_val < -200:
            return {
                '代號': clean_id, '名稱': STOCKS_DICT.get(full_id, clean_id), 
                '收盤價': round(c, 2), '型態': "☠️ 均線下彎+破底", 
                '法人買賣超(張)': inst_val
            }
    except: return None

# === 5. 繪圖與圖表函數 ===
def plot_beautiful_chart(symbol):
    try:
        full_id = CLEAN_TO_FULL_MAP.get(str(symbol), f"{symbol}.TW")
        df = yf.Ticker(full_id).history(period="6mo")
        if df.empty:
            st.error("找不到該標的資料")
            return

        df['5MA'] = df['Close'].rolling(window=5).mean()
        df['10MA'] = df['Close'].rolling(window=10).mean()
        df['20MA'] = df['Close'].rolling(window=20).mean()
        df = calculate_macd(df)
        df.dropna(inplace=True)

        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_width=[0.3, 0.7])

        fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='K線', 
                                     increasing_line_color='#FF4B4B', decreasing_line_color='#00CC96'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['5MA'], mode='lines', name='5MA', line=dict(color='#F59E0B', width=1.5)), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['10MA'], mode='lines', name='10MA', line=dict(color='#3B82F6', width=1.5)), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['20MA'], mode='lines', name='20MA', line=dict(color='#8B5CF6', width=2)), row=1, col=1)

        colors = np.where(df['Hist'] > 0, '#FF4B4B', '#00CC96')
        fig.add_trace(go.Bar(x=df.index, y=df['Hist'], name='MACD柱', marker_color=colors), row=2, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['DIF'], mode='lines', name='DIF', line=dict(color='#F59E0B')), row=2, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['MACD'], mode='lines', name='MACD', line=dict(color='#3B82F6')), row=2, col=1)
        fig.add_hline(y=0, line_dash="dash", line_color="#E5E7EB", opacity=0.8, row=2, col=1)

        fig.update_layout(height=650, template="plotly_white", xaxis_rangeslider_visible=False, 
                          margin=dict(l=0, r=0, t=10, b=0), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"繪圖發生錯誤: {e}")

# === 6. 美股與市場關聯函數 ===
def us_market_brain():
    us_tickers = {
        "TSM": "台積電 ADR", "ARM": "安謀", "AAPL": "蘋果", 
        "MSFT": "微軟", "GOOG": "谷歌", "NVDA": "輝達", 
        "META": "Meta", "TSLA": "特斯拉", "SKHY": "SK海力士"
    }
    for ticker, name in us_tickers.items():
        try:
            df = yf.Ticker(ticker).history(period="5d")
            if not df.empty and len(df) >= 2:
                close_today = df['Close'].iloc[-1]
                close_yest = df['Close'].iloc[-2]
                change = ((close_today - close_yest) / close_yest) * 100
                st.metric(f"{name} ({ticker})", f"${close_today:.2f}", f"{change:.2f}%", delta_color="inverse")
            else: 
                st.metric(name, "N/A", "-")
        except: 
            st.metric(name, "Error", "-")


# === 7. 側邊欄 (Sidebar) UI ===
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/10061/10061803.png", width=60)
    st.markdown("## 📡 智能軍規雷達")
    st.caption("版本：V14.0 雙劍合璧版")
    st.divider()

    st.subheader("🎯 掃描範圍設定")
    scan_mode = st.radio("雷達引擎掃描目標：", ["自選監控庫 (快速)", "全市場上市櫃 (約1700檔)"], help="全市場掃描約需 1-2 分鐘，請耐心等候。")
    st.divider()

    main_page = st.radio("導航選單", [
        "🎯 多頭獵殺 (突破/起漲)",
        "🔥 全市場金流榜",  
        "📉 斷頭防護 (空方破底)", 
        "📊 股神專屬看盤室",
        "🌐 全球戰情與總經",
        "⚙️ 自選庫與設定"
    ])

    st.divider()
    
    tw_c, tw_m20, tw_status = get_market_breadth()
    is_bearish = "🟩" in tw_status
    
    with st.expander("🌍 大盤即時風向", expanded=True):
        if tw_c:
            st.metric("加權指數", f"{tw_c:,.0f}", delta=f"{tw_c - tw_m20:,.0f} (距月線)", delta_color="inverse")
            st.markdown(f"**狀態：** {tw_status}")
        else:
            st.warning("大盤連線中...")

    with st.expander("🌐 美股連動指標", expanded=False):
        us_market_brain()


# === 8. 動態切換掃描全域變數 ===
if 'watch_list' not in st.session_state:
    st.session_state.watch_list = [k.split('.')[0] for k in DEFAULT_STOCKS.keys()]

if scan_mode == "全市場上市櫃 (約1700檔)":
    all_ids, all_dict = get_all_tw_stock_data()
    STOCKS_DICT.update(all_dict)
    for k in all_ids:
        CLEAN_TO_FULL_MAP[k.split('.')[0]] = k
    s_list = [k.split('.')[0] for k in all_ids]
else:
    s_list = st.session_state.watch_list


# ==========================================
# 分頁 1: 🎯 多頭獵殺
# ==========================================
if main_page == "🎯 多頭獵殺 (突破/起漲)":
    st.title(f"🎯 多方飆股獵殺雷達 ({scan_mode})")
    st.info("💡 **防禦與進攻升級**：內建防禦假突破。點擊「雙劍合璧」，系統將為你找出『同時符合六星強勢與三線零軸』的極致無敵好股！")
    
    if is_bearish: 
        st.error("⚠️ **大盤環境警告**：目前大盤跌破月線，操作多單勝率極低！假突破機率大增，請務必縮小資金部位，切勿盲目追高。")

    col1, col2 = st.columns(2)
    with col1: btn_star = st.button("🌟 六星雷達 (經典大滿配)", use_container_width=True)
    with col2: btn_ym = st.button("📈 三線零軸 (宇明流)", use_container_width=True)
    
    col3, col4 = st.columns(2)
    with col3: btn_breakout = st.button("🚀 旱地拔蔥 (壓縮起漲)", use_container_width=True)
    # 🔥 新增：雙劍合璧按鈕
    with col4: btn_overlap = st.button("⚔️ 雙劍合璧 (六星 + 宇明流重疊)", use_container_width=True, type="primary")

    if btn_star or btn_breakout or btn_ym or btn_overlap:
        inst_map = get_inst_data()
        hot_list = get_hot_rank_ids()
        results = []
        progress_bar = st.progress(0, text=f"📡 正在從雲端載入 {len(s_list)} 檔標的數據 (全市場掃描較久請耐心等候)...")
        
        full_ids = [CLEAN_TO_FULL_MAP.get(t, f"{t}.TW") for t in s_list]
        bulk_data_dict = fetch_bulk_yf_data(full_ids, period="1y")
        valid_list = [t for t in s_list if CLEAN_TO_FULL_MAP.get(t, f"{t}.TW") in bulk_data_dict]
        
        progress_bar.progress(50, text="🧠 啟動 AI 演算法交叉比對中 (假突破濾網已開啟)...")
        
        with ThreadPoolExecutor(max_workers=5) as ex:
            if btn_overlap:
                # 雙劍合璧：同時跑兩套演算法
                futs_star = {ex.submit(analyze_stock_score_v2, t, bulk_data_dict[CLEAN_TO_FULL_MAP.get(t, f"{t}.TW")], CLEAN_TO_FULL_MAP.get(t, f"{t}.TW"), inst_map, hot_list, is_bearish): t for t in valid_list}
                futs_ym = {ex.submit(analyst_three_line_macd_scanner, t, bulk_data_dict[CLEAN_TO_FULL_MAP.get(t, f"{t}.TW")], CLEAN_TO_FULL_MAP.get(t, f"{t}.TW"), inst_map, is_bearish): t for t in valid_list}
                
                res_star_list, res_ym_list = [], []
                total_tasks = len(futs_star) + len(futs_ym)
                
                for i, f in enumerate(as_completed(list(futs_star.keys()) + list(futs_ym.keys()))):
                    progress_bar.progress(50 + int(50 * (i+1)/total_tasks))
                    res = f.result()
                    if res:
                        if f in futs_star: res_star_list.append(res)
                        else: res_ym_list.append(res)
                
                # 尋找重疊的交集
                star_dict = {r['代號']: r for r in res_star_list}
                ym_dict = {r['代號']: r for r in res_ym_list}
                overlap_ids = set(star_dict.keys()).intersection(set(ym_dict.keys()))
                
                for cid in overlap_ids:
                    s_info = star_dict[cid]
                    y_info = ym_dict[cid]
                    results.append({
                        '代號': cid,
                        '名稱': s_info['名稱'],
                        '六星評等': s_info['星等'],
                        '宇明型態': y_info['星等'], # 宇明掃描器回傳在 '星等' 欄位
                        '收盤價': s_info['收盤價'],
                        '法人買賣超(張)': s_info['法人買賣超(張)'],
                        '綜合觸發條件': f"{s_info['觸發條件']} ➕ {y_info['觸發條件']}"
                    })
            else:
                # 單一雷達掃描
                if btn_star:
                    futs = [ex.submit(analyze_stock_score_v2, t, bulk_data_dict[CLEAN_TO_FULL_MAP.get(t, f"{t}.TW")], CLEAN_TO_FULL_MAP.get(t, f"{t}.TW"), inst_map, hot_list, is_bearish) for t in valid_list]
                elif btn_breakout:
                    futs = [ex.submit(ultimate_breakout_scanner, t, bulk_data_dict[CLEAN_TO_FULL_MAP.get(t, f"{t}.TW")], CLEAN_TO_FULL_MAP.get(t, f"{t}.TW"), inst_map, is_bearish) for t in valid_list]
                else:
                    futs = [ex.submit(analyst_three_line_macd_scanner, t, bulk_data_dict[CLEAN_TO_FULL_MAP.get(t, f"{t}.TW")], CLEAN_TO_FULL_MAP.get(t, f"{t}.TW"), inst_map, is_bearish) for t in valid_list]
                
                for i, f in enumerate(as_completed(futs)):
                    progress_bar.progress(50 + int(50 * (i+1)/len(valid_list)))
                    if f.result(): results.append(f.result())
                
        progress_bar.empty()
        
        if results:
            st.success(f"🎯 漂亮！成功為你捕捉到 **{len(results)}** 檔通過嚴格過濾的標的。")
            df_res = pd.DataFrame(results).sort_values(by='法人買賣超(張)', ascending=False)
            
            def style_dataframe(val):
                if isinstance(val, str) and '🚨' in val:
                    return 'color: #FF4B4B; font-weight: bold; background-color: #FFE5E5;'
                if isinstance(val, (int, float)):
                    if val > 0: return 'color: #FF4B4B; font-weight: bold;'
                    elif val < 0: return 'color: #00CC96; font-weight: bold;'
                return ''

            if btn_overlap:
                styled_df = df_res.style.map(style_dataframe, subset=['法人買賣超(張)', '綜合觸發條件'])
                st.dataframe(
                    styled_df, use_container_width=True, hide_index=True,
                    column_config={
                        "代號": st.column_config.TextColumn("代號", width="small"),
                        "名稱": st.column_config.TextColumn("名稱", width="small"),
                        "六星評等": st.column_config.TextColumn("六星狀態", width="medium"),
                        "宇明型態": st.column_config.TextColumn("宇明流狀態", width="medium"),
                        "收盤價": st.column_config.NumberColumn("收盤價", format="%.2f", width="small"),
                        "法人買賣超(張)": st.column_config.NumberColumn("大戶籌碼", help="單日買賣超"),
                        "綜合觸發條件": st.column_config.TextColumn("雙重條件", width="large")
                    }
                )
            else:
                styled_df = df_res.style.map(style_dataframe, subset=['法人買賣超(張)', '觸發條件'])
                st.dataframe(
                    styled_df, use_container_width=True, hide_index=True,
                    column_config={
                        "代號": st.column_config.TextColumn("代號", width="small"),
                        "名稱": st.column_config.TextColumn("名稱", width="small"),
                        "星等": st.column_config.TextColumn("型態評估", width="medium"),
                        "收盤價": st.column_config.NumberColumn("收盤價", format="%.2f", width="small"),
                        "法人買賣超(張)": st.column_config.NumberColumn("大戶籌碼", help="單日買賣超"),
                        "觸發條件": st.column_config.TextColumn("觸發條件", width="large")
                    }
                )
            st.toast("雷達掃描完畢！", icon="🛡️")
            st.balloons()
        else:
            st.warning("👀 此刻沒有任何一檔股票能通過這般嚴苛的測試。保持空手，不賠就是賺！")


# ==========================================
# 分頁 1.5: 🔥 全市場金流榜
# ==========================================
elif main_page == "🔥 全市場金流榜":
    st.title("🔥 全市場資金流向與類股權重")
    st.info("💡 **白話文說明**：這裡顯示全台股市場「當日成交金額最大」的標的，並自動歸類成產業族群，讓你一眼看出市場的熱錢都往哪裡塞！跟著熱錢走，勝率大增。")
    
    with st.spinner("🚀 計算資金板塊熱力中..."):
        tse_df, otc_df = fetch_top15_ranking()
        if not tse_df.empty or not otc_df.empty:
            combined_top = pd.concat([tse_df, otc_df], ignore_index=True)
            combined_top['代號乾淨'] = combined_top['證券代號'].astype(str).str.strip()
            combined_top['產業族群'] = combined_top['代號乾淨'].map(SECTOR_MAP).fillna("🔥 活躍熱門股")
            combined_top['成交億'] = (combined_top['成交金額'] / 100000000).round(1)
            
            col_chart1, col_chart2 = st.columns([4, 6])
            with col_chart1:
                st.subheader("🎯 類股資金佔比")
                sector_summary = combined_top.groupby('產業族群')['成交億'].sum().reset_index().sort_values(by='成交億', ascending=False)
                fig_pie = px.pie(sector_summary, values='成交億', names='產業族群', hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
                fig_pie.update_traces(textposition='inside', textinfo='percent+label')
                fig_pie.update_layout(template="plotly_white", showlegend=False, margin=dict(t=10, l=10, r=10, b=10), height=350)
                st.plotly_chart(fig_pie, use_container_width=True)
                
            with col_chart2:
                st.subheader("🗺️ 資金板塊熱力圖")
                fig_heat = px.treemap(combined_top, path=[px.Constant("全市場"), '產業族群', '證券名稱'], values='成交億', color='成交億', color_continuous_scale=['#E5E7EB', '#F59E0B', '#FF4B4B'])
                fig_heat.update_traces(textinfo="label+value")
                fig_heat.update_layout(template="plotly_white", margin=dict(t=10, l=10, r=10, b=10), height=350)
                st.plotly_chart(fig_heat, use_container_width=True)
                
            st.divider()
            st.subheader("💰 熱門金流個股排行 (前30大)")
            display_top = combined_top[['證券代號', '證券名稱', '產業族群', '收盤價', '成交億']].sort_values(by='成交億', ascending=False).reset_index(drop=True)
            display_top.insert(0, '名次', display_top.index + 1)
            
            st.dataframe(
                display_top, 
                use_container_width=True, 
                hide_index=True,
                column_config={
                    "成交億": st.column_config.NumberColumn("成交金額 (億元)", format="%.1f")
                }
            )
        else:
            st.warning("⚠️ 系統連線中或目前盤後暫無排行資料。")


# ==========================================
# 分頁 2: 📉 斷頭防護
# ==========================================
elif main_page == "📉 斷頭防護 (空方破底)":
    st.title(f"📉 弱勢避雷針 (空方引擎) - {scan_mode}")
    st.info("💡 **白話文說明**：小心駛得萬年船！這裡幫你揪出「均線下彎、跌破近期低點，而且法人還在瘋狂倒貨」的危險股。手上有這些股票請考慮停損；若是放空高手，這裡就是你的標的池。")

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
            st.error(f"🚨 警告！發現 **{len(results)}** 檔具備高下市/崩跌風險的股票！")
            df_res = pd.DataFrame(results).sort_values(by='法人買賣超(張)', ascending=True)
            
            def color_negative_green(val):
                if isinstance(val, (int, float)) and val < 0:
                    return 'color: #00CC96; font-weight: bold;'
                return ''

            st.dataframe(
                df_res.style.map(color_negative_green, subset=['法人買賣超(張)']), 
                use_container_width=True, 
                hide_index=True,
                column_config={
                    "法人買賣超(張)": st.column_config.NumberColumn("法人大逃亡 (張)", format="%d"),
                }
            )
        else:
            st.success("✅ 太棒了！你的掃描名單中目前沒有岌岌可危的斷頭股。")

# ==========================================
# 分頁 3: 📊 股神專屬看盤室
# ==========================================
elif main_page == "📊 股神專屬看盤室":
    st.title("📊 專家級無干擾看盤室")
    st.info("💡 **白話文說明**：輸入股票代號，一鍵生成擁有「多重均線」與「MACD 紅綠柱體」的高級技術分析圖表。")

    col1, col2 = st.columns([1, 3])
    with col1:
        chart_id = st.text_input("🔍 輸入標的代號 (例如: 2330)", value="2317")
        btn_draw = st.button("📈 繪製高解析度圖表", use_container_width=True, type="primary")
        
        st.markdown("---")
        st.caption("📚 **判讀小秘訣**：\n* **均線多頭**：黃線(5) > 藍線(10) > 紫線(20)\n* **零軸起飛**：下方柱狀圖由綠轉紅(上漲紅)，且兩條線爬上水平線。")
        
    with col2:
        if btn_draw:
            with st.spinner("繪製中..."):
                plot_beautiful_chart(chart_id)

# ==========================================
# 分頁 4: 🌐 全球戰情與總經
# ==========================================
elif main_page == "🌐 全球戰情與總經":
    st.title("🌐 總體經濟與大盤戰情")
    st.info("💡 **白話文說明**：股市不是只看個股。這裡幫你把台股大盤、匯率、美股動向等「大環境」數據整合在一起，大風向對了，賺錢才輕鬆。")

    col1, col2, col3 = st.columns(3)
    col1.metric("台幣匯率 (貶值不利台股)", "32.45", "-0.15", delta_color="inverse", help="匯率貶值通常代表外資將錢匯出台灣。")
    col2.metric("VIX 恐慌指數", "18.5", "1.2", delta_color="inverse", help="超過 20 代表市場開始恐慌。")
    col3.metric("美債殖利率", "4.11%", "0.05%", delta_color="inverse", help="無風險利率上升，對科技股估值有壓抑作用。")

    st.markdown("### 📈 加權指數 (^TWII) 真實走勢")
    try:
        twii_df = yf.Ticker("^TWII").history(period="3mo")
        twii_df['MA20'] = twii_df['Close'].rolling(20).mean()
        fig = make_subplots(rows=1, cols=1)
        fig.add_trace(go.Candlestick(x=twii_df.index, open=twii_df['Open'], high=twii_df['High'], low=twii_df['Low'], close=twii_df['Close'], name="大盤",
                                     increasing_line_color='#FF4B4B', decreasing_line_color='#00CC96'))
        fig.add_trace(go.Scatter(x=twii_df.index, y=twii_df['MA20'], line=dict(color='#3B82F6'), name="月線"))
        fig.update_layout(template="plotly_white", xaxis_rangeslider_visible=False, margin=dict(l=0,r=0,t=0,b=0), height=400)
        st.plotly_chart(fig, use_container_width=True)
    except:
        st.warning("無法載入大盤走勢圖。")

# ==========================================
# 分頁 5: ⚙️ 自選庫與設定
# ==========================================
elif main_page == "⚙️ 自選庫與設定":
    st.title("⚙️ 系統設定與自選名單管理")
    st.info("💡 **白話文說明**：當雷達設定為【自選監控庫】時，會掃描這裡的股票清單。你可以隨時增加或刪除你要關注的股票代號，記得用半形逗號 `,` 隔開。")
    
    def_tickers = ", ".join(st.session_state.watch_list)
    new_input = st.text_area("📝 您的監控代號庫：", value=def_tickers, height=150)
    
    if st.button("💾 儲存並更新名單", type="primary"):
        new_list = [t.strip() for t in new_input.replace('，',',').split(',') if t.strip()]
        st.session_state.watch_list = new_list
        st.success(f"✅ 更新成功！目前共監控 {len(new_list)} 檔股票。")
        time.sleep(1)
        st.rerun()

    st.divider()
    st.subheader("🧹 系統優化")
    if st.button("清除系統快取 (排除資料不同步問題)", use_container_width=False):
        st.cache_data.clear()
        st.toast("快取已清除！", icon="🧹")
