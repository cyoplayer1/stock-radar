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
from gtts import gTTS
import io
import asyncio
import aiohttp

# === 升級套件：斷線重連避震器 ===
try:
    from tenacity import retry, wait_exponential, stop_after_attempt
except ImportError:
    st.error("⚠️ 缺少 tenacity 套件，請執行: pip install tenacity")

try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:
    st_autorefresh = None

# === 1. 系統環境設定與版面美化 ===
warnings.filterwarnings("ignore")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
st.set_page_config(page_title="阿綜專屬：極簡智能雷達", page_icon="📈", layout="wide", initial_sidebar_state="expanded")

# 🎨 注入客製化 CSS (提升精緻度)
st.markdown("""
<style>
    /* 調整主標題風格 */
    h1 { color: #FFD166; font-weight: 800; font-family: 'Helvetica Neue', sans-serif; text-shadow: 1px 1px 2px rgba(0,0,0,0.5); }
    h2, h3 { color: #00CC96; }
    /* 數據卡片 (Metric) 美化 */
    div[data-testid="stMetricValue"] { font-size: 1.8rem; font-weight: 700; color: #FFFFFF; }
    div[data-testid="stMetricDelta"] { font-size: 1rem; }
    /* 按鈕圓角與懸停動效 */
    .stButton>button { border-radius: 8px; font-weight: 600; transition: all 0.3s ease; border: 1px solid #444; }
    .stButton>button:hover { transform: translateY(-2px); box-shadow: 0 5px 15px rgba(255, 209, 102, 0.3); border-color: #FFD166; color: #FFD166; }
    /* 主要按鈕特化 */
    .stButton>button[kind="primary"] { background: linear-gradient(90deg, #FF4B4B, #FF7B7B); color: white; border: none; }
    .stButton>button[kind="primary"]:hover { background: linear-gradient(90deg, #FF7B7B, #FF4B4B); box-shadow: 0 5px 15px rgba(255, 75, 75, 0.5); color: white; }
    /* 側邊欄優化 */
    section[data-testid="stSidebar"] { background-color: #16181c; border-right: 1px solid #333; }
    /* 隱藏預設的主選單與 footer */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
HEADERS = {"User-Agent": UA}

try:
    FUGLE_API_KEY = st.secrets["FUGLE_API_KEY"]
except (FileNotFoundError, KeyError):
    FUGLE_API_KEY = "54f80721-6cad-4ec9-9679-c5a315e7b00b"

# === 2. 外部設定檔掛載 ===
CONFIG_FILE = "system_config.json"
DEFAULT_STOCKS = {
    "2330.TW": "台積電", "2317.TW": "鴻海", "2454.TW": "聯發科", "2308.TW": "台達電",
    "3661.TW": "世芯KY", "3034.TW": "聯詠", "2382.TW": "廣達", "3231.TW": "緯創", 
    "3017.TW": "奇鋐", "3324.TW": "雙鴻", "2603.TW": "長榮", "2881.TW": "富邦金"
}
DEFAULT_SECTORS = {"2330": "半導體", "2317": "AI伺服器", "3017": "散熱模組", "2603": "航運", "2881": "金融"}

try:
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        config_data = json.load(f)
    STOCKS_DICT = config_data.get("STOCKS_DICT", DEFAULT_STOCKS)
    SECTOR_MAP = config_data.get("SECTOR_MAP", DEFAULT_SECTORS)
except:
    STOCKS_DICT = DEFAULT_STOCKS
    SECTOR_MAP = DEFAULT_SECTORS

CLEAN_TO_FULL_MAP = {k.split('.')[0]: k for k in STOCKS_DICT.keys()}
MAINTENANCE_LOG_FILE = "trade_maintenance_log.csv"

# === 3. 基礎函數 (網路、資料獲取、技術指標) ===
@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
def safe_get_json(url, headers):
    res = requests.get(url, headers=headers, timeout=10, verify=False)
    res.raise_for_status() 
    return res.json()

def safe_get_json_fallback(url, headers):
    try: return safe_get_json(url, headers)
    except: return {}

@st.cache_data(ttl=900, show_spinner=False)
def fetch_bulk_yf_data(full_ticker_list, period="1y"):
    valid_tickers = [t for t in full_ticker_list if t]
    if not valid_tickers: return {}
    try:
        data = yf.download(" ".join(valid_tickers), period=period, threads=True, progress=False)
        res_dict = {}
        if len(valid_tickers) == 1:
            df_t = data.dropna(subset=['Close'])
            if not df_t.empty: res_dict[valid_tickers[0]] = df_t
        else:
            for t in valid_tickers:
                df_t = pd.DataFrame({'Open': data['Open'][t], 'High': data['High'][t], 'Low': data['Low'][t], 'Close': data['Close'][t], 'Volume': data['Volume'][t]}).dropna(subset=['Close'])
                if not df_t.empty: res_dict[t] = df_t
        return res_dict
    except: return {}

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
            status = "🟢 偏多環境 (積極操作)" if c > m20 else "🔴 偏空環境 (嚴格控管)"
            return round(c, 2), round(m20, 2), status
    except: pass
    return None, None, "⚪ 系統連線中"

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
def analyst_three_line_macd_scanner(clean_id, df_ticker, full_id, inst_map, is_bearish=False):
    try:
        df = df_ticker.copy()
        if df.empty or len(df) < 60: return None
        c, v = df['Close'].iloc[-1], df['Volume'].iloc[-1]
        v5_avg = df['Volume'].iloc[-6:-1].mean()
        if v5_avg < 1000000: return None # 排除成交量太小的

        df['5MA'] = df['Close'].rolling(5).mean()
        df['10MA'] = df['Close'].rolling(10).mean()
        df['20MA'] = df['Close'].rolling(20).mean()
        df = calculate_macd(df)

        is_three_line_bull = (df['5MA'].iloc[-1] > df['10MA'].iloc[-1] > df['20MA'].iloc[-1])
        is_macd_above_zero = (df['DIF'].iloc[-1] > 0) and (df['MACD'].iloc[-1] > 0)
        is_macd_golden = (df['DIF'].iloc[-1] > df['MACD'].iloc[-1]) 

        if is_three_line_bull and is_macd_above_zero and is_macd_golden:
            if is_bearish and inst_map.get(clean_id, 0) <= 0: return None
            
            prev_bull = (df['5MA'].iloc[-2] > df['10MA'].iloc[-2] > df['20MA'].iloc[-2])
            prev_zero = (df['DIF'].iloc[-2] > 0) and (df['MACD'].iloc[-2] > 0)
            is_fresh = not (prev_bull and prev_zero)

            return {
                '代號': clean_id, '名稱': STOCKS_DICT.get(full_id, clean_id), 
                '收盤價': round(c, 2), '型態': "🔥 剛觸發：三線+零軸" if is_fresh else "🌟 續強：三線+零軸",
                '法人買超': inst_map.get(clean_id, 0)
            }
    except: return None

def ultimate_breakout_scanner(clean_id, df_ticker, full_id, inst_map, is_bearish=False):
    try:
        df = df_ticker.copy()
        if df.empty or len(df) < 60: return None
        c, v = df['Close'].iloc[-1], df['Volume'].iloc[-1]
        v5_avg = df['Volume'].iloc[-6:-1].mean()
        if v5_avg < 1000000: return None
        
        recent_10d_high = df['High'].iloc[-11:-1].max()
        recent_10d_low = df['Low'].iloc[-11:-1].min()
        is_breaking_high = c >= df['High'].iloc[-21:-1].max()
        
        df['MA5'] = df['Close'].rolling(5).mean()
        df['MA20'] = df['Close'].rolling(20).mean()
        
        is_bull_trend = (df['MA5'].iloc[-1] > df['MA20'].iloc[-1])
        consolidation_pct = (recent_10d_high - recent_10d_low) / recent_10d_low
        is_tight = consolidation_pct < 0.08 
        is_vol_boom = v > (v5_avg * 2.0)
        
        if is_bull_trend and is_tight and is_breaking_high and is_vol_boom:
            if is_bearish and inst_map.get(clean_id, 0) <= 0: return None
            return {
                '代號': clean_id, '名稱': STOCKS_DICT.get(full_id, clean_id), 
                '收盤價': round(c, 2), '型態': "🚀 壓縮突破 (旱地拔蔥)", 
                '法人買超': inst_map.get(clean_id, 0)
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
                '法人買超': inst_val
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

        fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                            vertical_spacing=0.03, row_width=[0.3, 0.7])

        # K線與均線
        fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='K線', increasing_line_color='#FF4B4B', decreasing_line_color='#00CC96'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['5MA'], mode='lines', name='5MA', line=dict(color='#FFD166', width=1.5)), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['10MA'], mode='lines', name='10MA', line=dict(color='#118AB2', width=1.5)), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['20MA'], mode='lines', name='20MA', line=dict(color='#EF476F', width=2)), row=1, col=1)

        # MACD 副圖
        colors = np.where(df['Hist'] > 0, '#FF4B4B', '#00CC96')
        fig.add_trace(go.Bar(x=df.index, y=df['Hist'], name='MACD柱', marker_color=colors), row=2, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['DIF'], mode='lines', name='DIF', line=dict(color='#FFD166')), row=2, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['MACD'], mode='lines', name='MACD', line=dict(color='#118AB2')), row=2, col=1)
        fig.add_hline(y=0, line_dash="dash", line_color="white", opacity=0.5, row=2, col=1)

        fig.update_layout(height=650, template="plotly_dark", xaxis_rangeslider_visible=False, 
                          margin=dict(l=0, r=0, t=10, b=0), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"繪圖發生錯誤: {e}")

# === 6. 側邊欄 (Sidebar) UI ===
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/10061/10061803.png", width=60) # 裝飾用圖標
    st.markdown("## 📡 智能軍規雷達")
    st.caption("版本：V13 UI 優化版")
    st.divider()

    # 收納導覽選單
    main_page = st.radio("導航選單", [
        "🎯 多頭獵殺 (突破/起漲)", 
        "📉 斷頭防護 (空方破底)", 
        "📊 股神專屬看盤室",
        "🌐 全球戰情與總經",
        "⚙️ 自選庫與設定"
    ])

    st.divider()
    
    # 資訊區塊 (使用 expander 收納以保持清爽)
    tw_c, tw_m20, tw_status = get_market_breadth()
    is_bearish = "🔴" in tw_status
    
    with st.expander("🌍 大盤即時風向", expanded=True):
        if tw_c:
            st.metric("加權指數", f"{tw_c:,.0f}", delta=f"{tw_c - tw_m20:,.0f} (距月線)")
            st.markdown(f"**狀態：** {tw_status}")
        else:
            st.warning("大盤連線中...")

    with st.expander("🌐 美股連動指標", expanded=False):
        us_market_brain()

# === 7. 處理全域變數與自選名單 ===
if 'watch_list' not in st.session_state:
    st.session_state.watch_list = list(CLEAN_TO_FULL_MAP.keys())
s_list = st.session_state.watch_list

# ==========================================
# 分頁 1: 🎯 多頭獵殺 (將六星雷達、飆股結合)
# ==========================================
if main_page == "🎯 多頭獵殺 (突破/起漲)":
    st.title("🎯 多方飆股獵殺雷達")
    st.info("💡 **白話文說明**：這裡專抓「正準備發動」的強勢股。按下方按鈕，系統會自動幫你掃描自選名單，找出均線多頭、剛帶量突破，或是 MACD 翻紅的好學生。")
    
    if is_bearish: 
        st.error("⚠️ **風險警告**：目前大盤跌破月線，操作多單勝率較低，請務必縮小資金部位，切勿盲目追高。")

    col1, col2 = st.columns(2)
    with col1: btn_breakout = st.button("🚀 掃描：旱地拔蔥 (壓縮突破)", use_container_width=True, type="primary")
    with col2: btn_ym = st.button("🌟 掃描：三線零軸 (穩定波段)", use_container_width=True)

    if btn_breakout or btn_ym:
        inst_map = get_inst_data()
        results = []
        progress_bar = st.progress(0, text="📡 正在從雲端載入數據...")
        
        full_ids = [CLEAN_TO_FULL_MAP.get(t, f"{t}.TW") for t in s_list]
        bulk_data_dict = fetch_bulk_yf_data(full_ids, period="1y")
        valid_list = [t for t in s_list if CLEAN_TO_FULL_MAP.get(t, f"{t}.TW") in bulk_data_dict]
        
        progress_bar.progress(30, text="🧠 啟動 AI 演算法交叉比對中...")
        
        with ThreadPoolExecutor(max_workers=5) as ex:
            if btn_breakout:
                futs = [ex.submit(ultimate_breakout_scanner, t, bulk_data_dict[CLEAN_TO_FULL_MAP.get(t, f"{t}.TW")], CLEAN_TO_FULL_MAP.get(t, f"{t}.TW"), inst_map, is_bearish) for t in valid_list]
            else:
                futs = [ex.submit(analyst_three_line_macd_scanner, t, bulk_data_dict[CLEAN_TO_FULL_MAP.get(t, f"{t}.TW")], CLEAN_TO_FULL_MAP.get(t, f"{t}.TW"), inst_map, is_bearish) for t in valid_list]
            
            for i, f in enumerate(as_completed(futs)):
                progress_bar.progress(30 + int(70 * (i+1)/len(valid_list)))
                if f.result(): results.append(f.result())
                
        progress_bar.empty()
        
        if results:
            st.success(f"🎯 漂亮！成功為你捕捉到 **{len(results)}** 檔強勢標的。")
            df_res = pd.DataFrame(results).sort_values(by='法人買超', ascending=False)
            
            # 建立精美的 DataFrame 欄位設定
            st.dataframe(
                df_res, 
                use_container_width=True, 
                hide_index=True,
                column_config={
                    "代號": st.column_config.TextColumn("代號", width="small"),
                    "名稱": st.column_config.TextColumn("名稱", width="medium"),
                    "收盤價": st.column_config.NumberColumn("收盤價", format="%.2f", width="small"),
                    "法人買超": st.column_config.NumberColumn("大戶籌碼 (張)", help="外資與投信單日買賣超合計"),
                }
            )
            st.toast("雷達掃描完畢！", icon="✅")
            st.balloons() # 增加成就感
        else:
            st.warning("👀 目前盤面靜悄悄，沒有符合嚴格過濾條件的標的。請保持耐心，空手也是一種操作。")

# ==========================================
# 分頁 2: 📉 斷頭防護 (空方破底)
# ==========================================
elif main_page == "📉 斷頭防護 (空方破底)":
    st.title("📉 弱勢避雷針 (空方引擎)")
    st.info("💡 **白話文說明**：小心駛得萬年船！這裡幫你揪出「均線下彎、跌破近期低點，而且法人還在瘋狂倒貨」的危險股。手上有這些股票請考慮停損；若是放空高手，這裡就是你的標的池。")

    if st.button("☠️ 啟動地雷股掃描", use_container_width=True, type="primary"):
        inst_map = get_inst_data()
        results = []
        progress_text = "📡 搜尋全市場地雷中..."
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
            df_res = pd.DataFrame(results).sort_values(by='法人買超', ascending=True)
            st.dataframe(
                df_res, 
                use_container_width=True, 
                hide_index=True,
                column_config={
                    "法人買超": st.column_config.NumberColumn("法人大逃亡 (張)", format="%d"),
                }
            )
        else:
            st.success("✅ 太棒了！你的自選名單中目前沒有岌岌可危的斷頭股。")

# ==========================================
# 分頁 3: 📊 股神專屬看盤室 (視覺化圖表)
# ==========================================
elif main_page == "📊 股神專屬看盤室":
    st.title("📊 專家級無干擾看盤室")
    st.info("💡 **白話文說明**：輸入股票代號，一鍵生成擁有「多重均線」與「MACD 紅綠柱體」的高級技術分析圖表。")

    col1, col2 = st.columns([1, 3])
    with col1:
        chart_id = st.text_input("🔍 輸入標的代號 (例如: 2330)", value="2317")
        btn_draw = st.button("📈 繪製高解析度圖表", use_container_width=True, type="primary")
        
        st.markdown("---")
        st.caption("📚 **判讀小秘訣**：\n* **均線多頭**：黃線(5) > 藍線(10) > 紅線(20)\n* **零軸起飛**：下方柱狀圖由綠轉紅，且兩條線爬上白色虛線。")
        
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
        fig.add_trace(go.Candlestick(x=twii_df.index, open=twii_df['Open'], high=twii_df['High'], low=twii_df['Low'], close=twii_df['Close'], name="大盤"))
        fig.add_trace(go.Scatter(x=twii_df.index, y=twii_df['MA20'], line=dict(color='#FFD166'), name="月線"))
        fig.update_layout(template="plotly_dark", xaxis_rangeslider_visible=False, margin=dict(l=0,r=0,t=0,b=0), height=400)
        st.plotly_chart(fig, use_container_width=True)
    except:
        st.warning("無法載入大盤走勢圖。")

# ==========================================
# 分頁 5: ⚙️ 自選庫與設定
# ==========================================
elif main_page == "⚙️ 自選庫與設定":
    st.title("⚙️ 系統設定與自選名單管理")
    st.info("💡 **白話文說明**：雷達系統會掃描這裡的股票清單。你可以隨時增加或刪除你要關注的股票代號，記得用半形逗號 `,` 隔開。")
    
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
