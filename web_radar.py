import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests, warnings, time, urllib3

# === 1. 系統設定 ===
warnings.filterwarnings("ignore")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
st.set_page_config(page_title="股神系統雷達", page_icon="📡", layout="wide")

HEADERS = {"User-Agent": "Mozilla/5.0"}

# === 2. 數據清洗與計算 (解決 TypeError 關鍵) ===
def clean_data(df):
    """徹底處理 MultiIndex 並強制轉為純數值型態"""
    if df is None or df.empty: return df
    df = df.copy()
    # 剝離多層索引 (yfinance 3.14 環境常見問題)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    # 強制數值轉化
    for c in ['Open', 'High', 'Low', 'Close', 'Volume']:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce')
    return df.dropna()

def calculate_kd(df):
    df = clean_data(df)
    if len(df) < 9: return df
    low_9 = df['Low'].rolling(9).min()
    high_9 = df['High'].rolling(9).max()
    rsv = (df['Close'] - low_9) / (high_9 - low_9) * 100
    k, d, kl, dl = 50.0, 50.0, [], []
    for v in rsv:
        if pd.isna(v): kl.append(k); dl.append(d)
        else:
            k = (2/3)*k + (1/3)*v
            d = (2/3)*d + (1/3)*k
            kl.append(k); dl.append(d)
    df['K'], df['D'] = kl, dl
    return df

@st.cache_data(ttl=300)
def get_ranks():
    rd = {"TWSE": pd.DataFrame(), "TPEx": pd.DataFrame()}
    try:
        u1 = "https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&type=ALLBUT0999"
        r1 = requests.get(u1, headers=HEADERS, timeout=10).json()
        d1 = pd.DataFrame(r1['tables'][8]['data'], columns=r1['tables'][8]['fields'])
        d1['val'] = pd.to_numeric(d1['成交金額'].str.replace(',',''), errors='coerce')
        rd["TWSE"] = d1.sort_values('val', ascending=False).head(15)[['證券代號','證券名稱','成交金額']]
        
        u2 = "https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php?l=zh-tw&o=json"
        r2 = requests.get(u2, headers=HEADERS, timeout=10).json()
        d2 = pd.DataFrame(r2['aaData'])
        d2['val'] = pd.to_numeric(d2[9].str.replace(',',''), errors='coerce')
        rd["TPEx"] = d2.sort_values('val', ascending=False).head(15)[[0, 1, 9]]
        rd["TPEx"].columns = ['證券代號','證券名稱','成交金額']
    except: pass
    return rd

# === 3. 完整 112 檔名單 ===
SL = {
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
st.title("📡 股神系統旗艦整合版 V6.1")
tbs = st.tabs(["🎯 雷達評分", "💰 成交排行", "📈 互動看盤", "🚀 波段掃描", "🔥 量能監控", "🔍 市場快篩"])

with tbs[0]:
    if st.button("🚀 啟動掃描", use_container_width=True):
        raw = yf.download(list(SL.keys()), period="2y", group_by='ticker', silent=True)
        rl = []
        for t, name in SL.items():
            try:
                df = clean_data(raw[t])
                if len(df) < 60: continue
                cl, v5 = df['Close'].iloc[-1], df['Volume'].tail(5).mean()
                if v5 < 1000000: continue
                sc, tags = 0, []
                ma20 = df['Close'].rolling(20).mean().iloc[-1]
                if cl > ma20: sc += 20; tags.append("[站上月線]")
                dkd = calculate_kd(df)
                if dkd['K'].iloc[-1] > dkd['D'].iloc[-1]:
                    if dkd['K'].iloc[-2] <= dkd['D'].iloc[-2]: sc += 40; tags.append("[日金叉]")
                    else: sc += 20; tags.append("[日偏多]")
                rl.append({'標的': f"{t.split('.')[0]} {name}", '評分': f"{sc}分", '收盤': round(float(cl), 2), '狀態': " + ".join(tags) if tags else "休息", 'Sort': sc})
            except: continue
        if rl: st.dataframe(pd.DataFrame(rl).sort_values('Sort', ascending=False).drop(columns='Sort'), use_container_width=True)

with tbs[1]:
    rk = get_ranks()
    c1, c2 = st.columns(2)
    with c1: st.subheader("📈 上市排行"); st.table(rk["TWSE"])
    with c2: st.subheader("📉 上櫃排行"); st.table(rk["TPEx"])

with tbs[2]:
    sid = st.text_input("🔍 代號", value="2330")
    if sid:
        tid = sid + (".TWO" if sid[0] in '34568' else ".TW")
        # 下載單檔時強制定向清洗
        d = yf.download(tid, period="1y", silent=True)
        d = clean_data(d)
        if not d.empty:
            d = calculate_kd(d)
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3])
            fig.add_trace(go.Candlestick(x=d.index, open=d['Open'], high=d['High'], low=d['Low'], close=d['Close'], name='K線'), row=1, col=1)
            fig.add_trace(go.Scatter(x=d.index, y=d['K'], name='K', line=dict(color='yellow')), row=2, col=1)
            fig.add_trace(go.Scatter(x=d.index, y=d['D'], name='D', line=dict(color='cyan')), row=2, col=1)
            fig.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)

with tbs[5]:
    st.subheader("🔍 全台股：低檔爆量強勢股快篩")
    if st.button("🚀 開始全市場掃描"):
        with st.spinner("正在掃描市場熱門標的..."):
            rk = get_ranks()
            cands = list(rk["TWSE"]['證券代號'] + ".TW") + list(rk["TPEx"]['證券代號'] + ".TWO")
            raw_m = yf.download(cands, period="6mo", group_by='ticker', silent=True)
            res_l = []
            for t in cands:
                try:
                    df = clean_data(raw_m[t])
                    vn, va = df['Volume'].iloc[-1], df['Volume'].iloc[-6:-1].mean()
                    lp, hp, cp = df['Low'].min(), df['High'].max(), df['Close'].iloc[-1]
                    pos = (cp - lp) / (hp - lp) if hp != lp else 1
                    if vn > va * 1.8 and pos < 0.25:
                        res_l.append({'代號':t, '收盤':round(float(cp),2), '倍數':round(float(vn/va),2), '位置':f"{round(float(pos*100),1)}%"})
                except: continue
            if res_l: st.dataframe(pd.DataFrame(res_l).sort_values('倍數', ascending=False), use_container_width=True)
