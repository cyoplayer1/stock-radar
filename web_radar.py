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

# === 2. 核心計算函數 (保留原始邏輯) ===
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
    """整合老盧原始檔案的評分邏輯 (日KD+周KD+月線)"""
    try:
        stock = yf.Ticker(ticker)
        df_daily = stock.history(period="2y")
        df_daily.dropna(subset=['Close', 'Volume'], inplace=True)
        if df_daily.empty or len(df_daily) < 60: return None
        
        close_p = df_daily['Close'].iloc[-1]
        v_5d = df_daily['Volume'].tail(5).mean()
        if v_5d < 1000000: return None # 照原本 1000張門檻
            
        score, tags = 0, []
        # 月線評分 (20分)
        ma20 = df_daily['Close'].rolling(window=20).mean().iloc[-1]
        if close_p > ma20:
            score += 20; tags.append("[站上月線]")
            
        # 日KD評分 (金叉40, 偏多20)
        df_daily = calculate_kd(df_daily.copy())
        dk, dd = df_daily['K'].iloc[-1], df_daily['D'].iloc[-1]
        dyk, dyd = df_daily['K'].iloc[-2], df_daily['D'].iloc[-2]
        if (dk > dd) and (dyk <= dyd):
            score += 40; tags.append("[日剛金叉]")
        elif dk > dd:
            score += 20; tags.append("[日線偏多]")
            
        # 周KD評分 (40分)
        df_w = df_daily.resample('W-FRI').agg({
            'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'
        }).dropna()
        df_w = calculate_kd(df_w.copy())
        wk, wd = df_w['K'].iloc[-1], df_w['D'].iloc[-1]
        if wk > wd:
            score += 40; tags.append("[周線偏多]")
            
        tid = ticker.replace('.TW', '').replace('.TWO', '')
        return {
            '標的名稱': f"{tid} {stock_name}",
            '評分': f"{score}分",
            '收盤價': round(close_p, 2),
            '技術面狀態': " + ".join(tags) if tags else "空頭休息",
            '日K': round(dk, 1),
            '周K': round(wk, 1),
            '5日均量(張)': int(v_5d/1000),
            'Sort_Score': score
        }
    except: return None

@st.cache_data(ttl=300)
def get_rank_data(m_type):
    """抓取即時成交排行，修復上櫃欄位問題"""
    try:
        if m_type == "TWSE":
            u = "https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&type=ALLBUT0999"
            res = requests.get(u, headers=HEADERS, verify=False, timeout=10).json()
            df = pd.DataFrame(res['tables'][8]['data']).iloc[:, [0, 1, 9]]
        else:
            u = "https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php?l=zh-tw&o=json"
            res = requests.get(u, headers=HEADERS, verify=False, timeout=10).json()
            raw = res.get('aaData', [])
            if not raw: return None
            df = pd.DataFrame(raw)
            # 上櫃金額解析強化：自動找數值最大的那欄
            df_n = df.apply(pd.to_numeric, errors='coerce').fillna(0)
            v_col = df_n.sum().idxmax()
            df = df.iloc[:, [0, 1, v_col]]
            
        df.columns = ['代號','名稱','成交金額']
        df['值'] = pd.to_numeric(df['成交金額'].astype(str).str.replace(',',''), errors='coerce').fillna(0)
        df = df.sort_values('值', ascending=False).head(15)
        df['成交金額'] = df['值'].apply(lambda x: f"{int(x/100000000):,} 億")
        return df[['代號','名稱','成交金額']].reset_index(drop=True)
    except: return None

# === 3. 百大名單 (完整保留) ===
STOCKS = {
    "2330.TW":"台積電","2317.TW":"鴻海","2454.TW":"聯發科","2308.TW":"台達電","2303.TW":"聯電",
    "3711.TW":"日月光","2408.TW":"南亞科","2344.TW":"華邦電","2337.TW":"旺宏","3443.TW":"創意",
    "3661.TW":"世芯KY","3034.TW":"聯詠","2379.TW":"瑞昱","4966.TW":"譜瑞KY","6415.TW":"矽力KY",
    "3529.TW":"力旺","6488.TWO":"環球晶","5483.TWO":"中美晶","3105.TWO":"穩懋","8299.TWO":"群聯",
    "2382.TW":"廣達","3231.TW":"緯創","6669.TW":"緯穎","2356.TW":"英業達","2324.TW":"仁寶",
    "2353.TW":"宏碁","2357.TW":"華碩","2376.TW":"技嘉","2377.TW":"微星","3017.TW":"奇鋐",
    "3324.TW":"雙鴻","3653.TW":"健策","3533.TW":"嘉澤","3013.TW":"晟銘電","8210.TW":"勤誠","7769.TW":"鴻勁",
    "3037.TW":"欣興","8046.TW":"南電","3189.TW":"景碩","2368.TW":"金像電","4958.TW":"臻鼎KY",
    "2313.TW":"華通","6274.TWO":"台燿","2383.TW":"台光電","6213.TW":"聯茂",
    "1519.TW":"華城","1503.TW":"士電","1513.TW":"中興電","1504.TW":"東元","1605.TW":"華新",
    "2603.TW":"長榮","2609.TW":"陽明","2615.TW":"萬海","2618.TW":"長榮航","2610.TW":"華航",
    "2881.TW":"富邦金","2882.TW":"國泰金","2891.TW":"中信金","2886.TW":"兆豐金","2884.TW":"玉山金",
    "8069.TWO":"元太","3293.TWO":"鈊象","8436.TW":"大江","8441.TW":"可寧衛",
    "0050.TW":"台50","0056.TW":"高股息","00878.TW":"國泰永續","00919.TW":"群益高息",
    "00929.TW":"復華科技","00713.TW":"高息低波","006208.TW":"富邦台50","6789.TW":"采鈺","6147.TWO":"頎邦"
}

# === 4. 網頁介面 ===
st.title("📡 股神旗艦綜合投資分析站")
tabs = st.tabs(["🎯 股神雷達", "💰 成交排行", "📈 互動看盤", "🚀 波段掃描", "🔥 量能監控"])

with tabs[0]:
    st.markdown("### 操盤室級別：【技術面熱力雷達評分系統 - 百大旗艦版】")
    if st.button("🚀 啟動雷達掃描", use_container_width=True):
        start_time = time.time()
        scored, processed = [], 0
        pb, txt = st.progress(0), st.empty()
        with ThreadPoolExecutor(max_workers=5) as ex:
            futs = [ex.submit(analyze_stock_score, t, n) for t, n in STOCKS.items()]
            for f in as_completed(futs):
                processed += 1
                pb.progress(processed / len(STOCKS))
                txt.text(f"🔄 雷達掃描中: {processed}/{len(STOCKS)} 檔標的...")
                if f.result(): scored.append(f.result())
        pb.empty(); txt.empty()
        st.success(f"✅ 掃描完成！總耗時 {round(time.time() - start_time, 1)} 秒。")
        if scored:
            df = pd.DataFrame(scored).sort_values(by=['Sort_Score','日K'], ascending=False)
            st.session_state['df_radar'] = df.drop(columns=['Sort_Score']).head(30)
    if 'df_radar' in st.session_state:
        st.subheader("🔥 目前大盤最強的 30 檔標的")
        st.dataframe(st.session_state['df_radar'], use_container_width=True)

with tabs[1]:
    if st.button("🔄 刷新即時排行"): st.cache_data.clear()
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("📈 上市成交值前 15 (TWSE)")
        df1 = get_rank_data("TWSE")
        if df1 is not None: st.table(df1)
    with c2:
        st.subheader("📉 上櫃成交值前 15 (TPEx)")
        df2 = get_rank_data("TPEx")
        if df2 is not None: st.table(df2)

with tabs[2]:
    sid = st.text_input("🔍 輸入台股代號 (如 2330)", value="2330")
    if sid:
        tid = sid + ".TW" if "." not in sid else sid
        d = yf.Ticker(tid).history(period="1y")
        if not d.empty:
            d = calculate_kd(d)
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.7, 0.3])
            fig.add_trace(go.Candlestick(x=d.index, open=d['Open'], high=d['High'], low=d['Low'], close=d['Close'], name='K線'), row=1, col=1)
            fig.add_trace(go.Scatter(x=d.index, y=d['K'], name='K', line=dict(color='yellow')), row=2, col=1)
            fig.add_trace(go.Scatter(x=d.index, y=d['D'], name='D', line=dict(color='cyan')), row=2, col=1)
            fig.update_layout(height=650, template="plotly_dark", xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)

with tabs[3]:
    if st.button("啟動波段突破掃描"):
        brks = []
        with st.spinner("掃描中..."):
            for t, n in STOCKS.items():
                df = yf.Ticker(t).history(period="3mo")
                if len(df) < 20: continue
                ma = df['Close'].rolling(20).mean(); std = df['Close'].rolling(20).std()
                if df['Close'].iloc[-1] > (ma.iloc[-1] + 2*std):
                    brks.append({'標的':f"{t} {n}",'收盤':round(df['Close'].iloc[-1],2),'狀態':'🔥 突破上軌'})
        if brks: st.dataframe(pd.DataFrame(brks), use_container_width=True)

with tabs[4]:
    if st.button("啟動盤中爆量監控"):
        vls = []
        with st.spinner("監控中..."):
            for t, n in STOCKS.items():
                df = yf.Ticker(t).history(period="1mo")
                if len(df) < 6: continue
                v_now, v_avg = df['Volume'].iloc[-1], df['Volume'].iloc[-6:-1].mean()
                if v_now > v_avg * 1.8:
                    vls.append({'標的':f"{t} {n}",'倍數':round(v_now/v_avg,1),'今日成交(張)':int(v_now/1000)})
        if vls: st.dataframe(pd.DataFrame(vls).sort_values(by='倍數', ascending=False), use_container_width=True)
