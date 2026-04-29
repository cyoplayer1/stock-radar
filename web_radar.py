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
st.set_page_config(page_title="老盧股神系統", page_icon="📡", layout="wide")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
HEADERS = {"User-Agent": UA}
FUGLE_API_KEY = "54f80721-6cad-4ec9-9679-c5a315e7b00b"

# === 2. 核心計算函數 ===

def calculate_kd(df):
    if len(df) < 9: return df
    df['9_min'] = df['Low'].rolling(window=9).min()
    df['9_max'] = df['High'].rolling(window=9).max()
    df['RSV'] = (df['Close'] - df['9_min']) / (df['9_max'] - df['9_min']) * 100
    k_v, d_v, k, d = [], [], 50.0, 50.0
    for rsv in df['RSV']:
        if pd.isna(rsv):
            k_v.append(50.0); d_v.append(50.0)
        else:
            k = (2/3) * k + (1/3) * rsv
            d = (2/3) * d + (1/3) * k
            k_v.append(k); d_v.append(d)
    df['K'], df['D'] = k_v, d_v
    return df

def get_fugle_realtime(symbol):
    try:
        url = f"https://api.fugle.tw/marketdata/v1.0/stock/intraday/quote/{symbol}"
        res = requests.get(url, headers={"X-API-KEY": FUGLE_API_KEY}, timeout=5, verify=False)
        if res.status_code == 200:
            data = res.json()
            return data.get('closePrice'), data.get('total', {}).get('tradeVolume', 0)
    except: pass
    return None, None

@st.cache_data(ttl=3600)
def get_inst_data():
    inst_map = {}
    try:
        u1 = "https://www.twse.com.tw/fund/T86?response=json&selectType=ALLBUT0999"
        r1 = requests.get(u1, headers=HEADERS, timeout=10, verify=False).json()
        if 'data' in r1:
            for d in r1['data']: inst_map[d[0].strip()] = int(d[2].replace(',', '')) + int(d[10].replace(',', ''))
        u2 = "https://www.tpex.org.tw/web/stock/fund/T86/T86_result.php?l=zh-tw&o=json"
        r2 = requests.get(u2, headers=HEADERS, timeout=10, verify=False).json()
        if 'aaData' in r2:
            for d in r2['aaData']: inst_map[d[0].strip()] = int(d[8].replace(',', '')) + int(d[10].replace(',', ''))
    except: pass
    return inst_map

@st.cache_data(ttl=300)
def get_hot_rank_ids():
    hot_ids = set()
    try:
        u1 = "https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&type=ALLBUT0999"
        res1 = requests.get(u1, headers=HEADERS, timeout=10, verify=False).json()
        if 'tables' in res1:
            for t in res1['tables']:
                if '證券代號' in t.get('fields', []):
                    df_t = pd.DataFrame(t['data'], columns=t['fields'])
                    df_t['val'] = pd.to_numeric(df_t['成交金額'].str.replace(',',''), errors='coerce')
                    hot_ids.update(df_t.sort_values('val', ascending=False).head(15)['證券代號'].tolist())
                    break
        u2 = "https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php?l=zh-tw&o=json"
        res2 = requests.get(u2, headers=HEADERS, timeout=10, verify=False).json()
        dt = res2.get('aaData', []) or (res2.get('tables', [{}])[0].get('data', []) if 'tables' in res2 else [])
        if dt:
            df_otc = pd.DataFrame(dt)
            idx = 9 if df_otc.shape[1] >= 10 else df_otc.shape[1] - 2
            df_otc['val'] = pd.to_numeric(df_otc[idx].astype(str).str.replace(',',''), errors='coerce')
            hot_ids.update(df_otc.sort_values('val', ascending=False).head(15)[0].tolist())
    except: pass
    return hot_ids

# === 3. 名單字典 (已修正格式) ===
STOCKS_DICT = {
    "2330.TW": "台積電", "2317.TW": "鴻海", "2454.TW": "聯發科", "2308.TW": "台達電",
    "2303.TW": "聯電", "3711.TW": "日月光", "2382.TW": "廣達", "3231.TW": "緯創",
    "6669.TW": "緯穎", "2356.TW": "英業達", "3017.TW": "奇鋐", "3324.TW": "雙鴻",
    "3653.TW": "健策", "7769.TW": "鴻勁", "2603.TW": "長榮", "1519.TW": "華城",
    "3016.TW": "嘉晶", "6147.TW": "頎邦", "2376.TW": "技嘉", "2377.TW": "微星"
}

# === 4. 聯動核心函數 ===

def analyze_stock_score(ticker_in, inst_map, hot_list):
    try:
        clean = ticker_in.replace('.TW','').replace('.TWO','')
        tid = clean + (".TWO" if ticker_in.endswith(".TWO") else ".TW")
        df = yf.Ticker(tid).history(period="1y")
        if df.empty:
            tid = clean + ".TWO"; df = yf.Ticker(tid).history(period="1y")
        if df.empty or len(df) < 65: return None
        
        fc, fv = get_fugle_realtime(clean)
        if fc: df.iloc[-1, df.columns.get_loc('Close')] = fc
        
        c = df['Close'].iloc[-1]; v = df['Volume'].iloc[-1]; v5 = df['Volume'].iloc[-6:-1].mean()
        df['MA5'] = df['Close'].rolling(5).mean(); df['MA20'] = df['Close'].rolling(20).mean(); df['MA60'] = df['Close'].rolling(60).mean()
        df = calculate_kd(df)
        
        s, tags = 0, []
        if c > df['MA5'].iloc[-1] > df['MA20'].iloc[-1] > df['MA60'].iloc[-1]: s+=1; tags.append("[均線多頭]")
        if df['MA20'].iloc[-1] > df['MA20'].iloc[-2]: s+=1; tags.append("[月線向上]")
        if v > v5 * 1.5: s+=1; tags.append("[爆量攻擊]")
        if df['K'].iloc[-1] > df['D'].iloc[-1] and df['K'].iloc[-2] <= df['D'].iloc[-2]: s+=1; tags.append("[KD金叉]")
        if c > df['High'].iloc[-21:-1].max(): s+=1; tags.append("[創20日新高]")
        if clean in hot_list: tags.append("🔥[排行熱門]")
        inst_val = inst_map.get(clean, 0)
        if inst_val > 500: tags.append("🔴[大戶進駐]")
        
        return {'代號': clean, '標的': f"{clean} {STOCKS_DICT.get(tid, '')}", '星等': "⭐"*s if s>0 else "休息", '收盤': round(c,2), '大戶(張)': f"{inst_val:,}", '星星數': s, '觸發條件': " ".join(tags)}
    except: return None

def diagnose_and_show(clean_id):
    """【聯動核心】負責畫圖、診斷與煞車計算"""
    tid = clean_id + ".TW"; df = yf.Ticker(tid).history(period="1y")
    if df.empty: tid = clean_id + ".TWO"; df = yf.Ticker(tid).history(period="1y")
    if df.empty: return st.error(f"⚠️ 找不到 {clean_id} 的資料")

    fc, _ = get_fugle_realtime(clean_id)
    if fc: df.iloc[-1, df.columns.get_loc('Close')] = fc

    df['MA5'] = df['Close'].rolling(5).mean(); df['MA20'] = df['Close'].rolling(20).mean(); df = calculate_kd(df)
    c, m5, m20, k, d = df['Close'].iloc[-1], df['MA5'].iloc[-1], df['MA20'].iloc[-1], df['K'].iloc[-1], df['D'].iloc[-1]

    col_l, col_r = st.columns([2, 1])
    with col_l:
        d_p = df.tail(80)
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3])
        fig.add_trace(go.Candlestick(x=d_p.index, open=d_p['Open'], high=d_p['High'], low=d_p['Low'], close=d_p['Close'], name='K線'), row=1, col=1)
        fig.add_trace(go.Scatter(x=d_p.index, y=d_p['K'], name='K', line=dict(color='yellow')), row=2, col=1)
        fig.add_trace(go.Scatter(x=d_p.index, y=d_p['D'], name='D', line=dict(color='cyan')), row=2, col=1)
        fig.update_layout(height=450, template="plotly_dark", xaxis_rangeslider_visible=False, margin=dict(t=10, b=10, l=10, r=10))
        st.plotly_chart(fig, use_container_width=True)

    with col_r:
        st.subheader(f"🛡️ {clean_id} 戰情診斷")
        st.metric("即時價", f"{round(c, 2)}", delta=f"離月線 {round(c-m20, 2)}")
        
        status, action = [], "🟢 續抱"
        if c < m20: status.append("⚠️ 跌破月線"); action = "🛑 停損"
        elif c < m5: status.append("⚠️ 跌破5日線"); action = "🟡 建議減碼"
        if k < d and k > 75: status.append("⚠️ KD高檔死叉"); action = "🟡 鎖利"
        if not status: status.append("✅ 趨勢強勢")
        
        st.write(f"**狀況：** {'、'.join(status)}")
        if "續抱" in action: st.success(f"**建議：** {action}")
        else: st.warning(f"**建議：** {action}")

        st.divider()
        st.subheader("⚖️ 煞車計算")
        fund = st.number_input("本金 (元)", value=1000000, step=10000)
        risk = st.slider("願意賠 %", 1.0, 3.0, 2.0)
        stop_p = st.number_input("停損點位", value=round(m20 * 0.98, 1))
        if c > stop_p:
            sh = (fund * (risk / 100)) / (c - stop_p)
            st.success(f"建議買進：**{round(sh / 1000, 2)}** 張")
        else: st.error("停損價設定過高")

# === 6. 介面執行 ===

st.sidebar.title("📡 老盧智慧中控")
u_input = st.sidebar.text_area("代號水庫：", value="2330, 2317, 2454, 7769, 3016, 3653, 3231, 2382, 6147, 1519", height=150)
s_list = list(set([t.strip() for t in u_input.replace('，',',').split(',') if t.strip()]))

st.title("📡 老盧股神系統：一鍵聯動雷達")

# 1. 掃描
st.markdown("### 🎯 1. 啟動六星掃描 (技術+籌碼+熱度)")
if st.button("🚀 執行全自動掃描", use_container_width=True):
    with st.spinner('引擎調校中...'):
        inst_map = get_inst_data(); hot_list = get_hot_rank_ids()
        res, pb = [], st.progress(0)
        with ThreadPoolExecutor(max_workers=5) as ex:
            futs = [ex.submit(analyze_stock_score, t, inst_map, hot_list) for t in s_list]
            for i, f in enumerate(as_completed(futs)):
                pb.progress((i+1)/len(s_list))
                if f.result(): res.append(f.result())
        if res:
            # 存入 Session State 確保選單切換時資料不會不見
            st.session_state['radar_data'] = pd.DataFrame(res).sort_values(by='星星數', ascending=False)
        else: st.error("掃描無結果，請檢查代號")

# 2. 顯示與聯動
if 'radar_data' in st.session_state:
    st.dataframe(st.session_state['radar_data'][['標的', '星等', '收盤', '大戶(張)', '觸發條件']], use_container_width=True)
    
    st.divider()
    st.markdown("### 🔍 2. 智慧聯動戰情室")
    # 從掃描結果中提取代號清單
    sel_options = st.session_state['radar_data']['代號'].tolist()
    
    # 這裡就是聯動的開關！
    target_sid = st.selectbox("🎯 選取標的，下方圖表與診斷將自動同步：", options=sel_options)
    
    if target_sid:
        # 只要下拉選單一動，這行就會重新跑一次，達成聯動
        diagnose_and_show(target_sid)
