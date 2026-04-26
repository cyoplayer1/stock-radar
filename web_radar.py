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

def analyze_stock_score(ticker, stock_name):
    try:
        stock = yf.Ticker(ticker)
        df_daily = stock.history(period="2y")
        df_daily.dropna(subset=['Close', 'Volume'], inplace=True)
        if df_daily.empty or len(df_daily) < 60: return None
        close_price = df_daily['Close'].iloc[-1]
        avg_vol_5d = df_daily['Volume'].tail(5).mean()
        if avg_vol_5d < 1000000: return None
        score, status_tags = 0, []
        df_daily['20MA'] = df_daily['Close'].rolling(window=20).mean()
        if close_price > df_daily['20MA'].iloc[-1]:
            score += 20; status_tags.append("[站上月線]")
        df_daily = calculate_kd(df_daily.copy())
        d_k, d_d = df_daily['K'].iloc[-1], df_daily['D'].iloc[-1]
        d_yest_k, d_yest_d = df_daily['K'].iloc[-2], df_daily['D'].iloc[-2]
        if (d_k > d_d) and (d_yest_k <= d_yest_d):
            score += 40; status_tags.append("[日剛金叉]")
        elif d_k > d_d:
            score += 20; status_tags.append("[日線偏多]")
        df_w = df_daily.resample('W-FRI').agg({'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}).dropna()
        df_w = calculate_kd(df_w.copy())
        if df_w['K'].iloc[-1] > df_w['D'].iloc[-1]:
            score += 40; status_tags.append("[周線偏多]")
        tid = ticker.replace('.TW', '').replace('.TWO', '')
        return {'標的名稱': f"{tid} {stock_name}", '評分': f"{score}分", '收盤價': round(close_price, 2), '技術面狀態': " + ".join(status_tags) if status_tags else "休息", '日K': round(d_k, 1), '周K': round(df_w['K'].iloc[-1], 1), '5日均量(張)': int(avg_vol_5d/1000), 'Sort_Score': score}
    except: return None

@st.cache_data(ttl=300)
def get_rank(m_type):
    try:
        if m_type == "TWSE":
            url = "https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&type=ALLBUT0999"
            res = requests.get(url, headers=HEADERS, verify=False, timeout=10).json()
            raw_data = res['tables'][8]['data']
            df = pd.DataFrame(raw_data)
            # 上市固定取 0, 1, 9 (代號, 名稱, 成交值)
            df = df.iloc[:, [0, 1, 9]]
        else:
            url = "https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php?l=zh-tw&o=json"
            res = requests.get(url, headers=HEADERS, verify=False, timeout=10).json()
            raw_data = res.get('aaData', [])
            if not raw_data: return None
            df = pd.DataFrame(raw_data)
            # 上櫃比較亂，我們抓第 0, 1 欄，以及金額通常在第 8 或 9 欄
            # 這裡強化邏輯：選取前兩欄加上數值最大的那一欄（通常就是成交金額）
            for col in range(df.shape[1]):
                df[col] = df[col].astype(str).str.replace(',', '')
            
            # 嘗試找尋成交金額欄位 (上櫃通常在索引 8 或 10)
            df_numeric = df.apply(pd.to_numeric, errors='coerce').fillna(0)
            val_col = df_numeric.sum().idxmax() # 找出總和最大的欄位
            df = df.iloc[:, [0, 1, val_col]]

        df.columns = ['代號','名稱','金額Raw']
        df['值'] = pd.to_numeric(df['金額Raw'].astype(str).str.replace(',',''), errors='coerce').fillna(0)
        df = df.sort_values('值', ascending=False).head(15)
        df['成交金額'] = df['值'].apply(lambda x: f"{int(x/100000000):,} 億")
        return df[['代號','名稱','成交金額']].reset_index(drop=True)
    except Exception as e:
        return pd.DataFrame([{"代號": "錯誤", "名稱": str(e), "成交金額": "0"}])

# === 3. 名單 ===
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
    "4958.TW": "臻鼎KY", "2313.TW": "華通", "6274.TWO": "台燿", "2383.TW": "台光電",
    "6213.TW": "聯茂", "3008.TW": "大立光", "3406.TW": "玉晶光",
    "1519.TW": "華城", "1503.TW": "士電", "1513.TW": "中興電", "1504.TW": "東元",
    "1605.TW": "華新", "1101.TW": "台泥", "1102.TW": "亞泥", "2002.TW": "中鋼",
    "2027.TW": "大成鋼", "2014.TW": "中鴻", "2207.TW": "和泰車", "9910.TW": "豐泰",
    "2603.TW": "長榮", "2609.TW": "陽明", "2618.TW": "長榮航", "2881.TW": "富邦金",
    "2882.TW": "國泰金", "0050.TW": "台50", "0056.TW": "高股息", "00878.TW": "永續",
    "00919.TW": "精選高息", "00929.TW": "科技優息", "8441.TW": "可寧衛", "8390.TWO": "金益鼎"
}

# === 4. 介面 ===
st.title("📡 股神系統雷達 V5.0")
tabs = st.tabs(["🎯 股神雷達", "💰 成交排行", "📈 互動看盤", "🚀 波段掃描", "🔥 量能監控"])

with tabs[0]:
    if st.button("🚀 啟動掃描", use_container_width=True):
        res = []
        pb = st.progress(0); txt = st.empty()
        with ThreadPoolExecutor(max_workers=5) as ex:
            futs = [ex.submit(analyze_stock_score, t, n) for t, n in STOCKS.items()]
            for i, f in enumerate(as_completed(futs)):
                pb.progress((i+1)/len(STOCKS))
                txt.text(f"掃描中... {i+1}/{len(STOCKS)}")
                if f.result(): res.append(f.result())
        pb.empty(); txt.empty()
        if res:
            df = pd.DataFrame(res).sort_values(by=['Sort_Score','日K'], ascending=False)
            st.session_state['df'] = df.drop(columns=['Sort_Score']).head(30)
    if 'df' in st.session_state: st.dataframe(st.session_state['df'], use_container_width=True)

with tabs[1]:
    if st.button("🔄 刷新排行"): st.cache_data.clear()
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("📈 上市成交值")
        df_twse = get_rank("TWSE")
        st.table(df_twse)
    with c2:
        st.subheader("📉 上櫃成交值")
        df_tpex = get_rank("TPEx")
        if df_tpex is not None:
            st.table(df_tpex)
        else:
            st.error("暫時抓不到上櫃資料，請稍後再試")

with tabs[2]:
    sid = st.text_input("🔍 輸入代號 (如 2330)",
