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

# === 1. 系統設定 ===
warnings.filterwarnings("ignore")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
st.set_page_config(page_title="股神系統雷達", page_icon="📡", layout="wide")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
HEADERS = {"User-Agent": UA}

# === 2. 原始檔案核心邏輯 ===
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
        close_p = df_daily['Close'].iloc[-1]
        v_5d = df_daily['Volume'].tail(5).mean()
        if v_5d < 1000000: return None
        score, tags = 0, []
        df_daily['20MA'] = df_daily['Close'].rolling(window=20).mean()
        if close_p > df_daily['20MA'].iloc[-1]:
            score += 20; tags.append("[站上月線]")
        df_daily = calculate_kd(df_daily.copy())
        dk, dd = df_daily['K'].iloc[-1], df_daily['D'].iloc[-1]
        dyk, dyd = df_daily['K'].iloc[-2], df_daily['D'].iloc[-2]
        if (dk > dd) and (dyk <= dyd):
            score += 40; tags.append("[日剛金叉]")
        elif dk > dd:
            score += 20; tags.append("[日線偏多]")
        df_w = df_daily.resample('W-FRI').agg({'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}).dropna()
        df_w = calculate_kd(df_w.copy())
        if df_w['K'].iloc[-1] > df_w['D'].iloc[-1]:
            score += 40; tags.append("[周線偏多]")
        tid = ticker.replace('.TW', '').replace('.TWO', '')
        return {'標的名稱': f"{tid} {stock_name}", '評分': f"{score}分", '收盤價': round(close_p, 2), '技術面狀態': " + ".join(tags) if tags else "休息", '日K': round(dk, 1), '周K': round(df_w['K'].iloc[-1], 1), '5日均量(張)': int(v_5d/1000), 'Sort_Score': score}
    except: return None

@st.cache_data(ttl=300)
def get_rank(m_type):
    try:
        if m_type == "TWSE":
            u = "https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&type=ALLBUT0999"
            res = requests.get(u, headers=HEADERS, verify=False, timeout=10).json()
            df = pd.DataFrame(res['tables'][8]['data']).iloc[:, [0, 1, 9]]
        else:
            u = "https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php?l=zh-tw&o=json"
            res = requests.get(u, headers=HEADERS, verify=False, timeout=10).json()
            data = res.get('aaData', [])
            if not data: return pd.DataFrame(columns=['代號','名稱','成交金額'])
            df = pd.DataFrame(data).iloc[:, [0, 1, 8]] # 上櫃通常 0:代號, 1:名稱, 8:成交金額
        df.columns = ['代號','名稱','金額Raw']
        df['值'] = pd.to_numeric(df['金額Raw'].astype(str).str.replace(',',''), errors='coerce').fillna(0)
        df = df.sort_values('值', ascending=False).head(15)
        df['成交金額'] = df['值'].apply(lambda x: f"{int(x/100000000):,} 億")
        return df[['代號','名稱','成交金額']].reset_index(drop=True)
    except:
        return pd.DataFrame([{"代號":"--","名稱":"抓取失敗","成交金額":"--"}] * 5)

# === 3. 完整名單 ===
STOCKS = {
    "2330.TW":"台積電","2317.TW":"鴻海","2454.TW":"聯發科","2308.TW":"台達電","2303.TW":"聯電",
    "3711.TW":"日月光","2408.TW":"南亞科","2344.TW":"華邦電","2337.TW":"旺宏","3443.TW":"創意",
    "3661.TW":"世芯KY","3034.TW":"聯詠","2379.TW":"瑞昱","4966.TW":"譜瑞KY","6415.TW":"矽力KY",
    "6488.TWO":"環球晶","5483.TWO":"中美晶","3105.TWO":"穩懋","8299.TWO":"群聯","2382.TW":"廣達",
    "3231.TW":"緯創","6669.TW":"緯穎","2356.TW":"英業達","2324.TW":"仁寶","2353.TW":"宏碁",
    "2357.TW":"華碩","2376.TW":"技嘉","2377.TW":"微星","3017.TW":"奇鋐","3324.TW":"雙鴻",
    "3653.TW":"健策","3533.TW":"嘉澤","3013.TW":"晟銘電","8210.TW":"勤誠","7769.TW":"鴻勁",
    "3037.TW":"欣興","8046.TW":"南電","3189.TW":"景碩","2368.TW":"金像電","4958.TW":"臻鼎KY",
    "1519.TW":"華城","1503.TW":"士電","1513.TW":"中興電","1504.TW":"東元","1605.TW":"華新",
    "2603.TW":"長榮","2609.TW":"陽明","2618.TW":"長榮航","2881.TW":"富邦金","2882.TW":"國泰金",
    "8069.TWO":"元太","3293.TWO":"鈊象","6147.TWO":"頎邦","6789.TW":"采鈺","0050.TW":"台50",
    "0056.TW":"高股息","00878.TW":"永續","00919.TW":"群益高息","00929.TW":"科技優息"
}

# === 4. 網頁介面 ===
st.title("📡 股神旗艦雷達 V5.5")
tabs = st.tabs(["🎯 股神雷達", "💰 成交排行", "📈 互動看盤", "🚀 波段掃描", "🔥 量能監控"])

with tabs[0]:
    if st.button("🚀 啟動掃描", use_container_width=True):
        res, pb, txt = [], st.progress(0), st.empty()
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
        st.table(get_rank("TWSE"))
    with c2:
        st.subheader("📉 上櫃成交值")
        st.table(get_rank("TPEx"))

with tabs[2]:
    sid = st.text_input("🔍 輸入代號", value="2330")
    if sid:
        tid = sid + ".TW" if "." not in sid else sid
        d = yf.Ticker(tid).history(period="1y")
        if not d.empty:
            d = calculate_kd(d)
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3])
            fig.add_trace(go.Candlestick(x=d.index, open=d['Open'], high=d['High'], low=d['Low'], close=d['Close'], name='K線'), row=1, col=1)
            fig.add_trace(go.Scatter(x=d.index, y=d['K'], name='K', line=dict(color='yellow')), row=2, col=1)
            fig.add_trace(go.Scatter(x=d.index, y=d['D'], name='D', line=dict(color='cyan')), row=2, col=1)
            fig.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)

with tabs[3]:
    if st.button("啟動布林掃描"):
        brks = []
        for t, n in STOCKS.items():
            df = yf.Ticker(t).history(period="3mo")
            if len(df) < 20: continue
            ma, std = df['Close'].rolling(20).mean(), df['Close'].rolling(20).std()
            if df['Close'].iloc[-1] > (ma.iloc[-1] + 2*std):
                brks.append({'標的':f"{t} {n}",'價':round(df['Close'].iloc[-1],2)})
        if brks: st.dataframe(pd.DataFrame(brks), use_container_width=True)

with tabs[4]:
    if st.button("啟動量能監控"):
        vls = []
        for t, n in STOCKS.items():
            df = yf.Ticker(t).history(period="1mo")
            if len(df) < 6: continue
            v_now, v_avg = df['Volume'].iloc[-1], df['Volume'].iloc[-6:-1].mean()
            if v_now > v_avg * 1.8: vls.append({'標的':f"{t} {n}",'倍數':round(v_now/v_avg,1)})
        if vls: st.dataframe(pd.DataFrame(vls).sort_values(by='倍數', ascending=False), use_container_width=True)
