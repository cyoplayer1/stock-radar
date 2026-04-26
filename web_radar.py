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

UA_S = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
UA_S += "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
HEADERS = {"User-Agent": UA_S}

# === 2. 核心計算函數 (繼承自你的股神系統雷達.py) ===
def calculate_kd(df):
    if len(df) < 9: return df
    df['9_min'] = df['Low'].rolling(window=9).min()
    df['9_max'] = df['High'].rolling(window=9).max()
    df['RSV'] = (df['Close'] - df['9_min']) / (df['9_max'] - df['9_min']) * 100
    k, d, k_vals, d_vals = 50.0, 50.0, [], []
    for rsv in df['RSV']:
        if pd.isna(rsv):
            k_vals.append(50.0); d_vals.append(50.0)
        else:
            k = (2/3) * k + (1/3) * rsv
            d = (2/3) * d + (1/3) * k
            k_vals.append(k); d_vals.append(d)
    df['K'], df['D'] = k_vals, d_vals
    return df

def analyze_stock_score(ticker, stock_name):
    try:
        stock = yf.Ticker(ticker)
        df_daily = stock.history(period="2y")
        df_daily.dropna(subset=['Close', 'Volume'], inplace=True)
        if df_daily.empty or len(df_daily) < 60: return None
        
        close_p = df_daily['Close'].iloc[-1]
        v_5d = df_daily['Volume'].tail(5).mean()
        if v_5d < 1000000: return None # 門檻 1000張
            
        score, tags = 0, []
        # 月線 (20分)
        df_daily['20MA'] = df_daily['Close'].rolling(window=20).mean()
        if close_p > df_daily['20MA'].iloc[-1]:
            score += 20; tags.append("[站上月線]")
            
        # 日KD (金叉40, 偏多20)
        df_daily = calculate_kd(df_daily.copy())
        dk, dd = df_daily['K'].iloc[-1], df_daily['D'].iloc[-1]
        dyk, dyd = df_daily['K'].iloc[-2], df_daily['D'].iloc[-2]
        if (dk > dd) and (dyk <= dyd):
            score += 40; tags.append("[日剛金叉]")
        elif dk > dd:
            score += 20; tags.append("[日線偏多]")
            
        # 周KD (40分)
        df_w = df_daily.resample('W-FRI').agg({
            'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'
        }).dropna()
        df_w = calculate_kd(df_w.copy())
        wk = df_w['K'].iloc[-1]
        if wk > df_w['D'].iloc[-1]:
            score += 40; tags.append("[周線偏多]")
            
        tid = ticker.replace('.TW', '').replace('.TWO', '')
        return {
            '標的名稱': f"{tid} {stock_name}", '評分': f"{score}分",
            '收盤價': round(close_p, 2), '技術面狀態': " + ".join(tags) if tags else "休息",
            '日K': round(dk, 1), '周K': round(wk, 1),
            '5日均量(張)': int(v_5d/1000), 'Sort_Score': score
        }
    except: return None

# === 3. 成交排行函數 (繼承自你的 web_top15.py.py) ===
@st.cache_data(ttl=300)
def get_twse_top_15():
    url = "https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&type=ALLBUT0999"
    try:
        res = requests.get(url, headers=HEADERS, verify=False, timeout=10).json()
        raw = res['tables'][8]['data']
        cols = res['tables'][8]['fields']
        df = pd.DataFrame(raw, columns=cols)[['證券代號', '證券名稱', '成交金額']]
        df['值'] = pd.to_numeric(df['成交金額'].str.replace(',',''), errors='coerce').fillna(0)
        df = df.sort_values('值', ascending=False).head(15)
        df['成交金額(元)'] = df['值'].apply(lambda x: f"{int(x):,}")
        return df[['證券代號', '證券名稱', '成交金額(元)']].reset_index(drop=True)
    except: return None

@st.cache_data(ttl=300)
def get_tpex_top_15():
    url = "https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php?l=zh-tw&o=json"
    try:
        res = requests.get(url, headers=HEADERS, verify=False, timeout=10).json()
        df = pd.DataFrame(res['aaData'])
        # 0:代號, 1:名稱, 9:成交金額
        df = df[[0, 1, 9]]
        df.columns = ['證券代號', '證券名稱', '成交金額']
        df['值'] = pd.to_numeric(df['成交金額'].str.replace(',',''), errors='coerce').fillna(0)
        df = df.sort_values('值', ascending=False).head(15)
        df['成交金額(元)'] = df['值'].apply(lambda x: f"{int(x):,}")
        return df[['證券代號', '證券名稱', '成交金額(元)']].reset_index(drop=True)
    except: return None

# === 4. 完整的百大標的名單 (一檔都不漏) ===
SL = {"2330.TW":"台積電","2317.TW":"鴻海","2454.TW":"聯發科","2308.TW":"台達電","2303.TW":"聯電"}
SL.update({"3711.TW":"日月光","2408.TW":"南亞科","2344.TW":"華邦電","2337.TW":"旺宏","3443.TW":"創意"})
SL.update({"3661.TW":"世芯KY","3034.TW":"聯詠","2379.TW":"瑞昱","4966.TW":"譜瑞KY","6415.TW":"矽力KY"})
SL.update({"3529.TW":"力旺","6488.TWO":"環球晶","5483.TWO":"中美晶","3105.TWO":"穩懋","8299.TWO":"群聯"})
SL.update({"2382.TW":"廣達","3231.TW":"緯創","6669.TW":"緯穎","2356.TW":"英業達","2324.TW":"仁寶"})
SL.update({"2353.TW":"宏碁","2357.TW":"華碩","2376.TW":"技嘉","2377.TW":"微星","3017.TW":"奇鋐"})
SL.update({"3324.TW":"雙鴻","3653.TW":"健策","3533.TW":"嘉澤","3013.TW":"晟銘電","8210.TW":"勤誠"})
SL.update({"7769.TW":"鴻勁","3037.TW":"欣興","8046.TW":"南電","3189.TW":"景碩","2368.TW":"金像電"})
SL.update({"4958.TW":"臻鼎KY","2313.TW":"華通","6274.TWO":"台燿","2383.TW":"台光電","6213.TW":"聯茂"})
SL.update({"3008.TW":"大立光","3406.TW":"玉晶光","1519.TW":"華城","1503.TW":"士電","1513.TW":"中興電"})
SL.update({"1504.TW":"東元","1605.TW":"華新","1101.TW":"台泥","1102.TW":"亞泥","2002.TW":"中鋼"})
SL.update({"2027.TW":"大成鋼","2014.TW":"中鴻","2207.TW":"和泰車","9910.TW":"豐泰","9921.TW":"巨大"})
SL.update({"9904.TW":"寶成","2603.TW":"長榮","2609.TW":"陽明","2615.TW":"萬海","2618.TW":"長榮航"})
SL.update({"2610.TW":"華航","2606.TW":"裕民","3596.TW":"智易","5388.TWO":"中磊","3380.TW":"明泰"})
SL.update({"2345.TW":"智邦","2881.TW":"富邦金","2882.TW":"國泰金","2891.TW":"中信金","2886.TW":"兆豐金"})
SL.update({"2884.TW":"玉山金","2892.TW":"第一金","2880.TW":"華南金","2885.TW":"元大金","2890.TW":"永豐金"})
SL.update({"2883.TW":"開發金","2887.TW":"台新金","5880.TW":"合庫金","8069.TWO":"元太","3293.TWO":"鈊象"})
SL.update({"8436.TW":"大江","8441.TW":"可寧衛","0050.TW":"台灣50","0056.TW":"高股息","00878.TW":"國泰永續"})
SL.update({"00919.TW":"群益高息","00929.TW":"復華科技","00713.TW":"高息低波","006208.TW":"富邦台50"})
SL.update({"6789.TW":"采鈺","6147.TWO":"頎邦"})
STOCKS = SL

# === 5. 網頁介面 ===
st.title("📡 股神旗艦綜合投資分析站 V5.0")
tabs = st.tabs(["🎯 股神雷達", "💰 成交排行", "📈 互動看盤", "🚀 波段掃描", "🔥 量能監控"])

with tabs[0]:
    if st.button("🚀 啟動完整雷達掃描", use_container_width=True):
        res, processed = [], 0
        pb, txt = st.progress(0), st.empty()
        with ThreadPoolExecutor(max_workers=5) as ex:
            futs = [ex.submit(analyze_stock_score, t, n) for t, n in STOCKS.items()]
            for f in as_completed(futs):
                processed += 1
                pb.progress(processed / len(STOCKS))
                txt.text(f"🔄 掃描中: {processed}/{len(STOCKS)} ...")
                if f.result(): res.append(f.result())
        pb.empty(); txt.empty()
        if res:
            df = pd.DataFrame(res).sort_values(by=['Sort_Score','日K'], ascending=False)
            st.session_state['main_df'] = df.drop(columns=['Sort_Score']).head(40)
    if 'main_df' in st.session_state:
        st.dataframe(st.session_state['main_df'], use_container_width=True)

with tabs[1]:
    if st.button("🔄 刷新排行"): st.cache_data.clear()
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("📈 上市排行 (TWSE)")
        df1 = get_twse_top_15()
        if df1 is not None: st.table(df1)
    with c2:
        st.subheader("📉 上櫃排行 (TPEx)")
        df2 = get_tpex_top_15()
        if df2 is not None: st.table(df2)

with tabs[2]:
    sid = st.text_input("🔍 輸入代號 (如 2330)", value="2330")
    if sid:
        tid = sid + ".TW" if "." not in sid else sid
        d = yf.Ticker(tid).history(period="1y")
        if not d.empty:
            d = calculate_kd(d)
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3])
            fig.add_trace(go.Candlestick(x=d.index, open=d['Open'], high=d['High'], low=d['Low'], close=d['Close'], name='K線'), row=1, col=1)
            fig.add_trace(go.Scatter(x=d.index, y=d['K'], name='K', line=dict(color='yellow')), row=2, col=1)
            fig.add_trace(go
