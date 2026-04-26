import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import warnings
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib3

# === 1. 系統基礎設定 ===
warnings.filterwarnings("ignore")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
st.set_page_config(page_title="股神系統雷達", page_icon="📡", layout="wide")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
HEADERS = {"User-Agent": UA}

# === 2. 核心計算函數 ===
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
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="2y")
        if df.empty or len(df) < 60: return None
        close = df['Close'].iloc[-1]
        vol_5d = df['Volume'].tail(5).mean()
        if vol_5d < 1000000: return None # 1000張門檻
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
        if df_w['K'].iloc[-1] > df_w['D'].iloc[-1]: score += 40; tags.append("[周線偏多]")
        tid = ticker.replace('.TW', '').replace('.TWO', '')
        return {'標的': f"{tid} {name}", '評分': f"{score}分", '收盤': round(close, 2), '狀態': " + ".join(tags) if tags else "休息", '日K': round(dk, 1), '周K': round(df_w['K'].iloc[-1], 1), '5日均量': int(vol_5d/1000), 'Sort_Score': score}
    except: return None

# === 3. 成交排行 (整合自 web_top15 並優化) ===
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
            df_n = df.apply(pd.to_numeric, errors='coerce').fillna(0)
            v_col = df_n.sum().idxmax()
            df = df[[0, 1, v_col]]
            df.columns = ['證券代號', '證券名稱', '成交金額']
        df['值'] = pd.to_numeric(df['成交金額'].astype(str).str.replace(',',''), errors='coerce').fillna(0)
        df = df.sort_values('值', ascending=False).head(15)
        df['金額'] = df['值'].apply(lambda x: f"{int(x/100000000):,} 億")
        return df[['證券代號','證券名稱','金額']].reset_index(drop=True)
    except: return None

# === 4. 完整名單 ===
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
    "4958.TW": "臻鼎KY", "1519.TW": "華城", "1503.TW": "士電", "1513.TW": "中興電",
    "2603.TW": "長榮", "2609.TW": "陽明", "2618.TW": "長榮航", "2881.TW": "富邦金",
    "2882.TW": "國泰金", "8441.TW": "可寧衛", "8390.TWO": "金益鼎", "0050.TW": "台50",
    "0056.TW": "高股息", "00878.TW": "永續", "00919.TW": "精選高息", "00929.TW": "科技優息",
    "6789.TW": "采鈺", "6147.TWO": "頎邦"
}

# === 5. 網頁介面 ===
st.title("📡 股神系統整合旗艦版 V5.0")
t1, t2, t3, t4, t5 = st.tabs(["🎯 股神雷達", "💰 成交排行", "📈 互動看盤", "🚀 波段掃描", "🔥 及時爆量"])

with t1:
    if st.button("🚀 啟動完整雷達掃描", use_container_width=True):
        start_t = time.time()
        res, processed = [], 0
        pb, txt = st.progress(0), st.empty()
        with ThreadPoolExecutor(max_workers=5) as ex:
            futs = [ex.submit(analyze_stock_score, t, n) for t, n in STOCKS.items()]
            for f in as_completed(futs):
                processed += 1
                pb.progress(processed / len(STOCKS))
                txt.text(f"🔄 掃描中: {processed}/{len(SL)} ...")
                if f.result(): res.append(f.result())
        pb.empty(); txt.empty()
        st.success(f"✅ 完成！耗時 {round(time.time() - start_t, 1)} 秒。")
        if res:
            df = pd.DataFrame(res).sort_values(by=['Sort_Score','日K'], ascending=False)
            st.session_state['df_radar'] = df.drop(columns=['Sort_Score']).head(35)
    if 'df_radar' in st.session_state: st.dataframe(st.session_state['df_radar'], use_container_width=True)

with t5:
    st.subheader("🔥 盤中及時爆量監控 (預估量對比)")
    if st.button("🔎 掃描及時爆量標的", use_container_width=True):
        alerts = []
        pb2 = st.progress(0)
        # 計算盤中經過的時間比例 (簡單估算)
        now = datetime.now()
        market_open = now.replace(hour=9, minute=0, second=0)
        if now.hour >= 13 and now.minute >= 30:
            time_ratio = 1.0
        elif now.hour < 9:
            time_ratio = 0.01
        else:
            diff = (now - market_open).total_seconds() / 60
            time_ratio = max(0.01, min(1.0, diff / 270)) # 盤中 270 分鐘
            
        for i, (t, n) in enumerate(STOCKS.items()):
            pb2.progress((i + 1) / len(STOCKS))
            try:
                df = yf.Ticker(t).history(period="5d")
                if df.empty or len(df) < 2: continue
                v_now = df['Volume'].iloc[-1]
                v_avg = df['Volume'].iloc[:-1].mean()
                
                # 預估全天量 = 當前量 / 時間比例
                est_vol = v_now / time_ratio
                vol_ratio = est_vol / v_avg if v_avg > 0 else 0
                
                if vol_ratio > 2.0: # 預估量超過均量 2 倍
                    alerts.append({
                        '標的': f"{t} {n}",
                        '目前成交量': int(v_now/1000),
                        '預估今日倍數': f"🔥 {round(vol_ratio, 1)} 倍",
                        '狀態': '及時爆量' if time_ratio < 0.9 else '今日爆量'
                    })
            except: continue
        pb2.empty()
        if alerts:
            st.dataframe(pd.DataFrame(alerts).sort_values(by='預估今日倍數', ascending=False), use_container_width=True)
        else:
            st.info("目前無明顯爆量標的。")

# 其餘分頁保持原本排行與看盤邏輯即可
