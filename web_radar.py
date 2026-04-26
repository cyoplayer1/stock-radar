import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests, warnings, time, urllib3
from datetime import datetime

# === 1. 系統環境設定 ===
warnings.filterwarnings("ignore")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
st.set_page_config(page_title="股神系統雷達", page_icon="📡", layout="wide")

HEADERS = {"User-Agent": "Mozilla/5.0"}

# === 2. 核心清洗與計算函數 ===
def clean_data(df):
    """處理 yfinance MultiIndex 問題，避免 TypeError"""
    if df is None or df.empty: return df
    df = df.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    for c in ['Open', 'High', 'Low', 'Close', 'Volume']:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce')
    return df

def calculate_kd(df):
    df = clean_data(df)
    if len(df) < 9: return df
    l9 = df['Low'].rolling(9).min()
    h9 = df['High'].rolling(9).max()
    rsv = (df['Close'] - l9) / (h9 - l9) * 100
    k, d = 50.0, 50.0
    k_l, d_l = [], []
    for v in rsv:
        if pd.isna(v): k_l.append(k); d_l.append(d)
        else:
            k = (2/3)*k + (1/3)*v
            d = (2/3)*d + (1/3)*k
            k_l.append(k); d_l.append(d)
    df['K'], df['D'] = k_l, d_l
    return df

@st.cache_data(ttl=300)
def get_ranks():
    """獲取排行，拆分網址防止 GitHub 截斷報錯"""
    r_data = {"TWSE": pd.DataFrame(), "TPEx": pd.DataFrame()}
    try:
        # 上市排行
        u1 = "https://www.twse.com.tw/exchangeReport/"
        u1 += "MI_INDEX?response=json&type=ALLBUT0999"
        res1 = requests.get(u1, headers=HEADERS, timeout=10).json()
        d1 = pd.DataFrame(res1['tables'][8]['data'], columns=res1['tables'][8]['fields'])
        d1['val'] = pd.to_numeric(d1['成交金額'].str.replace(',',''), errors='coerce')
        r_data["TWSE"] = d1.sort_values('val', ascending=False).head(15)[['證券代號','證券名稱','成交金額']]
        
        # 上櫃排行
        u2 = "https://www.tpex.org.tw/web/stock/aftertrading/"
        u2 += "daily_close_quotes/stk_quote_result.php?l=zh-tw&o=json"
        res2 = requests.get(u2, headers=HEADERS, timeout=10).json()
        d2 = pd.DataFrame(res2['aaData'])
        d2['val'] = pd.to_numeric(d2[9].str.replace(',',''), errors='coerce')
        r_data["TPEx"] = d2.sort_values('val', ascending=False).head(15)[[0, 1, 9]]
        r_data["TPEx"].columns = ['證券代號','證券名稱','成交金額']
    except: pass
    return r_data

# === 3. 完整 112 檔名單 (垂直定義防截斷) ===
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
    "6213.TW": "聯茂", "3008.TW": "大立光", "3406.TW": "玉晶光", "1519.TW": "華城",
    "1503.TW": "士電", "1513.TW": "中興電", "1504.TW": "東元", "1605.TW": "華新",
    "1101.TW": "台泥", "1102.TW": "亞泥", "2002.TW": "中鋼", "2027.TW": "大成鋼",
    "2014.TW": "中鴻", "2207.TW": "和泰車", "9910.TW": "豐泰", "9921.TW": "巨大",
    "9904.TW": "寶成", "2603.TW": "長榮", "2609.TW": "陽明", "2615.TW": "萬海",
    "2618.TW": "長榮航", "2610.TW": "華航", "2606.TW": "裕民", "3596.TW": "智易",
    "5388.TWO": "中磊", "3380.TW": "明泰", "2345.TW": "智邦", "2881.TW": "富邦金",
    "2882.TW": "國泰金", "2891.TW": "中信金", "2886.TW": "兆豐金", "2884.TW": "玉山金",
    "2892.TW": "第一金", "2880.TW": "華南金", "2885.TW": "元大金", "2890.TW": "永豐金",
    "2883.TW": "開發金", "2887.TW": "台新金", "5880.TW": "合庫金", "8069.TWO": "元太",
    "3293.TWO": "鈊象", "8436.TW": "大江", "8441.TW": "可寧衛", "8390.TWO": "金益鼎",
    "0050.TW": "台50", "0056.TW": "高股息", "00878.TW": "永續", "00919.TW": "精選高息",
    "00929.TW": "科技優息", "00713.TW": "高息低波", "006208.TW": "富邦台50", 
    "6789.TW": "采鈺", "6147.TWO": "頎邦"
}

# === 4. 介面設計 ===
st.title("📡 股神系統旗艦整合版 V5.0")
tbs = st.tabs(["🎯 股神雷達", "💰 成交排行", "📈 互動看盤", "🚀 波段掃描", "🔥 量能監控", "🔍 全台股低檔快篩"])

with tbs[0]:
    if st.button("🚀 啟動完整掃描", use_container_width=True):
        all_d = yf.download(list(STOCKS.keys()), period="2y", group_by='ticker', silent=True)
        res = []
        for t, name in STOCKS.items():
            try:
                df = clean_data(all_d[t].dropna())
                if len(df) < 60: continue
                close, vol5 = df['Close'].iloc[-1], df['Volume'].tail(5).mean()
                if vol5 < 1000000: continue
                ma20 = df['Close'].rolling(20).mean().iloc[-1]
                score, tags = 0, []
                if close > ma20: score += 20; tags.append("[站上月線]")
                dfkd = calculate_kd(df)
                if dfkd['K'].iloc[-1] > dfkd['D'].iloc[-1]:
                    if dfkd['K'].iloc[-2] <= dfkd['D'].iloc[-2]: score += 40; tags.append("[日剛金叉]")
                    else: score += 20; tags.append("[日偏多]")
                res.append({'標的': f"{t.split('.')[0]} {name}", '評分': f"{score
