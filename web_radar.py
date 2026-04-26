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
st.set_page_config(page_title="股神系統雷達", page_icon="📡", layout="wide")

UA_S = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
UA_S += "AppleWebKit/537.36 (KHTML, like Gecko) "
UA_S += "Chrome/120.0.0.0 Safari/537.36"
HEADERS = {"User-Agent": UA_S}

# === 2. 核心計算函數 (繼承老盧原始檔案邏輯) ===
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
    """日KD+周KD+月線評分邏輯"""
    try:
        stock = yf.Ticker(ticker)
        df_daily = stock.history(period="2y")
        df_daily.dropna(subset=['Close', 'Volume'], inplace=True)
        if df_daily.empty or len(df_daily) < 60: return None
        
        close_p = df_daily['Close'].iloc[-1]
        v_5d = df_daily['Volume'].tail(5).mean()
        if v_5d < 1000000: return None # 門檻 1000張
            
        score, tags = 0, []
        ma20 = df_daily['Close'].rolling(window=20).mean().iloc[-1]
        if close_p > ma20:
            score += 20; tags.append("[站上月線]")
            
        df_daily = calculate_kd(df_daily.copy())
        dk, dd = df_daily['K'].iloc[-1], df_daily['D'].iloc[-1]
        dyk, dyd = df_daily['K'].iloc[-2], df_daily['D'].iloc[-2]
        if (dk > dd) and (dyk <= dyd):
            score += 40; tags.append("[日剛金叉]")
        elif dk > dd:
            score += 20; tags.append("[日線偏多]")
            
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

# === 3. 成交排行函數 (解決上櫃跑不出來問題) ===
@st.cache_data(ttl=300)
def get_rank_data(market_type):
    try:
        if market_type == "TWSE":
            u = "https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&type=ALLBUT0999"
            res = requests.get(u, headers=HEADERS, verify=False, timeout=10).json()
            df = pd.DataFrame(res['tables'][8]['data'])
            df.columns = res['tables'][8]['fields']
            df = df[['證券代號', '證券名稱', '成交金額']]
        else:
            u = "https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php?l=zh-tw&o=json"
            res = requests.get(u, headers=HEADERS, verify=False, timeout=10).json()
            df = pd.DataFrame(res.get('aaData', []))
            # ★上櫃排行修正：自動尋找金額最大的欄位★
            df_n = df.apply(pd.to_numeric, errors='coerce').fillna(0)
            v_col = df_n.sum().idxmax()
            df = df[[0, 1, v_col]]
            df.columns = ['證券代號', '證券名稱', '成交金額']
            
        df['值'] = pd.to_numeric(df['成交金額'].astype(str).str.replace(',',''), errors='coerce').fillna(0)
        df = df.sort_values('值', ascending=False).head(15)
        df['金額'] = df['值'].apply(lambda x: f"{int(x/100000000):,} 億")
        return df[['證券代號','證券名稱','金額']].reset_index(drop=True)
    except: return None

# === 4. 完整的百大名單 (超短行定義防止裁斷) ===
SL = {
    "2330.TW": "台積電", "2317.TW": "鴻海", "2454.TW": "聯發科", 
    "2308.TW": "台達電", "2303.TW": "聯電", "3711.TW": "日月光",
    "2408.TW": "南亞科", "2344.TW": "華邦電", "2337.TW": "旺宏",
    "3443.TW": "創意", "3661.TW": "世芯KY", "3034.TW": "聯詠",
    "2379.TW": "瑞昱", "4966.TW": "譜瑞KY", "6415.TW": "矽力KY",
    "3529.TW": "力旺", "6488.TWO": "環球晶", "5483.TWO": "中美晶",
    "3105.TWO": "穩懋", "8299.TWO": "群聯", "2382.TW": "廣達",
    "3231.TW": "緯創", "6669.TW": "緯穎", "2356.TW": "英業達",
    "2324.TW": "仁寶", "2353.TW": "宏碁", "2357.TW": "華碩",
    "2376.TW": "技嘉", "2377.TW": "微星", "3017.TW": "奇鋐",
    "3324.TW": "雙鴻", "3653.TW": "健策", "3533.TW": "嘉澤",
    "3013.TW": "晟銘電", "8210.TW": "勤誠", "7769.TW": "鴻勁",
    "3037.TW": "欣興", "8046.TW": "南電", "3189.TW": "景碩",
    "2368.TW": "金像電", "4958.TW": "臻鼎KY", "2313.TW": "華通",
    "6274.TWO": "台燿", "2383.TW": "台光電", "6213.TW": "聯茂",
    "3008.TW": "大立光", "3406.TW": "玉晶光", "1519.TW": "華城",
    "1503.TW": "士電", "1513.TW": "中興電", "1504.TW": "東元",
    "1605.TW": "華新", "1101.TW": "台泥", "1102.TW": "亞泥",
    "2002.TW": "中鋼", "2027.TW": "大成鋼", "2014.TW": "中鴻",
    "2207.TW": "和泰車", "9910.TW": "豐泰", "9921.TW": "巨大",
    "9904.TW": "寶成", "2603.TW": "長榮", "2609.TW": "陽明",
    "2615.TW": "萬海", "2618.TW": "長榮航", "2610.TW": "華航",
    "2606.TW": "裕民", "3596.TW": "智易", "5388.TWO": "中磊",
    "3380.TW": "明泰", "2345.TW": "智邦", "2881.TW": "富邦金",
    "2882.TW": "國泰金", "2891.TW": "中信金", "2886.TW": "兆豐金",
    "2884.TW": "玉山金", "2892.TW": "第一金", "2880.TW": "華南金",
    "2885.TW": "元大金", "2890.TW": "永豐金", "2883.TW": "開發金",
    "2887.TW": "台新金", "5880.TW": "合庫金", "8069.TWO": "元太",
    "3293.TWO": "鈊象", "8436.TW": "大江", "8441.TW": "可寧衛",
    "0050.TW": "台50", "0056.TW": "高股息", "00878.TW": "永續",
    "00919.TW": "精選高息", "00929.TW": "科技優息", "00713.TW": "高息低波",
    "006208.TW": "富邦台50", "6789.TW": "采鈺", "6147.TWO": "頎邦"
}

# === 5. 網頁介面 ===
st.title("📡 股神系統雷達 - 旗艦大滿貫整合版")
t1, t2, t3, t4, t5 = st.tabs(["🎯 股神雷達", "💰 成交排行", "📈 互動看盤", "🚀 波段掃描", "🔥 量能監控"])

with t1:
    st.markdown("### 操盤室級別：【技術面熱力雷達評分系統 - 完整版】")
    if st.button("🚀 啟動完整雷達掃描", use_container_width=True):
        # ★修復 NameError: start_time 必須先定義★
        start_t = time.time()
        res, prc = [], 0
        pb, txt = st.progress(0), st.empty()
        with ThreadPoolExecutor(max_workers=5) as ex:
            futs = [ex.submit(analyze_stock_score, t, n) for t, n in SL.items()]
            for f in as_completed(futs):
                prc += 1
                pb.progress(prc / len(SL))
                txt.text(f"🔄 掃描中: {prc}/{len(SL)} ...")
                if f.result(): res.append(f.result())
        pb.empty(); txt.empty()
        st.success(f"✅ 掃描完成！總耗時 {round(time.time() - start_t, 1)} 秒。")
        if res:
            df = pd.DataFrame(res).sort_values(by=['Sort_Score','日K'], ascending=False)
            st.session_state['main_df'] = df.drop(columns=['Sort_Score']).head(35)
    if 'main_df' in st.session_state:
        st.dataframe(st.session_state['main_df'], use_container_width=True)

with t2:
    if st.button("🔄 刷新即時排行"): st.cache_data.clear()
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("📈 上市排行 (TWSE)")
        df1 = get_rank_data("TWSE")
        if df1 is not None: st.table(df1)
    with c2:
        st.subheader("📉 上櫃排行 (TPEx)")
        df2 = get_rank_data("TPEx")
        if df2 is not None: st.table(df2)
        else: st.error("目前抓不到上櫃資料")

with t3:
    sid = st.text_input("🔍 代號 (如 2330)", value="2330")
    if sid:
        tid = sid + ".TW" if "." not in sid else sid
        try:
            d = yf.Ticker(tid).history(period="1y")
            if not d.empty:
                d = calculate_kd(d)
                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3])
                k_trace = go.Candlestick(x=d.index, open=d['Open'], high=d['High'], 
                                         low=d['Low'], close=d['Close'], name='K線')
                fig.add_trace(k_trace, row=1, col=1)
                fig.add_trace(go.Scatter(x=d.index, y=d['K'], name='K', line=dict(color='yellow')), row=2, col=1)
                fig.add_trace(go.Scatter(x=d.index, y=d['D'], name='D', line=dict(color='cyan')), row=2, col=1)
                fig.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True)
        except: st.error("查無資料")

with t4:
    if st.button("啟動波段突破掃描"):
        brs = []
        for t, n in SL.items():
            df = yf.Ticker(t).history(period="3mo")
            if len(df) < 20: continue
            ma, std = df['Close'].rolling(20).mean(), df['Close'].rolling(20).std()
            if df['Close'].iloc[-1] > (ma.iloc[-1] + 2*std):
                brs.append({'標的':f"{t} {n}",'價':round(df['Close'].iloc[-1],2),'狀態':'🔥突破'})
        if brs: st.dataframe(pd.DataFrame(brs), use_container_width=True)

with t5:
    if st.button("啟動量能監控"):
        vls = []
        for t, n in SL.items():
            df = yf.Ticker(t).history(period="1mo")
            if len(df) < 6: continue
            v_now, v_avg = df['Volume'].iloc[-1], df['Volume'].iloc[-6:-1].mean()
            if v_now > v_avg * 1.8:
                vls.append({'標的':f"{t} {n}",'量能倍數':round(v_now/v_avg,1)})
        if vls: st.dataframe(pd.DataFrame(vls).sort_values(by='量能倍數', ascending=False), use_container_width=True)
