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

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
HEADERS = {"User-Agent": UA}

# === 2. 核心計算函數 ===
def calculate_kd(df):
    if len(df) < 9: return df [cite: 1]
    df['9_min'] = df['Low'].rolling(window=9).min() [cite: 1]
    df['9_max'] = df['High'].rolling(window=9).max() [cite: 1]
    df['RSV'] = (df['Close'] - df['9_min']) / (df['9_max'] - df['9_min']) * 100 [cite: 1]
    k_v, d_v = [], []
    k, d = 50.0, 50.0 [cite: 2]
    for rsv in df['RSV']:
        if pd.isna(rsv):
            k_v.append(k); d_v.append(d) [cite: 2, 3]
        else:
            k = (2/3) * k + (1/3) * rsv [cite: 3]
            d = (2/3) * d + (1/3) * k [cite: 3]
            k_v.append(k); d_v.append(d) [cite: 3, 4]
    df['K'], df['D'] = k_v, d_v [cite: 4]
    return df

def analyze_stock_score(ticker, name):
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="2y")
        if df.empty or len(df) < 60: return None [cite: 4]
        close = df['Close'].iloc[-1]
        vol_5d = df['Volume'].tail(5).mean()
        if vol_5d < 1000000: return None [cite: 4]
        
        score, tags = 0, [] [cite: 5]
        ma20 = df['Close'].rolling(20).mean().iloc[-1]
        if close > ma20: 
            score += 20; tags.append("[站上月線]") [cite: 5, 6]
        
        df = calculate_kd(df.copy())
        dk, dd = df['K'].iloc[-1], df['D'].iloc[-1] [cite: 6]
        dyk, dyd = df['K'].iloc[-2], df['D'].iloc[-2] [cite: 6]
        if (dk > dd) and (dyk <= dyd): 
            score += 40; tags.append("[日剛金叉]") [cite: 6, 7]
        elif dk > dd: 
            score += 20; tags.append("[日線偏多]") [cite: 7, 8]
        
        df_w = df.resample('W-FRI').agg({'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'}).dropna() [cite: 8]
        df_w = calculate_kd(df_w.copy())
        wk = df_w['K'].iloc[-1] [cite: 8]
        if wk > df_w['D'].iloc[-1]: 
            score += 40; tags.append("[周線偏多]") [cite: 9]
        
        tid = ticker.replace('.TW', '').replace('.TWO', '')
        return {'標的': f"{tid} {name}", '評分': f"{score}分", '收盤': round(close, 2), '狀態': " + ".join(tags) if tags else "休息", '日K': round(dk, 1), '周K': round(wk, 1), '5日均量': int(vol_5d/1000), 'Sort_Score': score}
    except: return None

# === 3. 成交排行與籌碼數據 ===
@st.cache_data(ttl=300)
def get_rank(m_type):
    try:
        if m_type == "TWSE":
            u = "https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&type=ALLBUT0999"
            res = requests.get(u, headers=HEADERS, verify=False, timeout=10).json() [cite: 10]
            stock_data, fields = None, None
            if 'tables' in res:
                for table in res['tables']:
                    if 'fields' in table and '證券代號' in table['fields']:
                        fields, stock_data = table['fields'], table['data']
                        break
            df = pd.DataFrame(stock_data, columns=fields) [cite: 10]
            df = df[['證券代號', '證券名稱', '成交金額']] [cite: 10]
        else:
            u = "https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php?l=zh-tw&o=json"
            res = requests.get(u, headers=HEADERS, verify=False, timeout=10).json() [cite: 11]
            df = pd.DataFrame(res.get('aaData', [])) [cite: 11]
            df_n = df.apply(pd.to_numeric, errors='coerce').fillna(0)
            v_col = df_n.sum().idxmax()
            df = df[[0, 1, v_col]]
            df.columns = ['證券代號', '證券名稱', '成交金額']
        df['值'] = pd.to_numeric(df['成交金額'].astype(str).str.replace(',',''), errors='coerce').fillna(0) [cite: 11]
        return df.sort_values('值', ascending=False)
    except: return None

@st.cache_data(ttl=3600)
def get_chip_data():
    try:
        u = "https://www.twse.com.tw/fund/T86?response=json&selectType=ALLBUT0999"
        res = requests.get(u, headers=HEADERS, verify=False, timeout=10).json()
        if 'data' in res:
            df = pd.DataFrame(res['data'])
            df = df.iloc[:, [0, 1, 2, 10, 11]]
            df.columns = ['代號', '名稱', '外資', '投信', '自營']
            for col in ['外資', '投信', '自營']:
                df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
            df['法人合計'] = df['外資'] + df['投信'] + df['自營']
            return df
    except: return None

# === 4. 快篩邏輯與 112 檔名單 ===
def check_low_breakout(ticker, name):
    try:
        df = yf.Ticker(ticker).history(period="6mo")
        if df.empty or len(df) < 40: return None [cite: 12]
        v_now, v_avg = df['Volume'].iloc[-1], df['Volume'].iloc[-6:-1].mean() [cite: 12]
        if v_now < v_avg * 1.8: return None [cite: 12]
        low_p, high_p = df['Low'].min(), df['High'].max() [cite: 12]
        curr_p = df['Close'].iloc[-1]
        pos = (curr_p - low_p) / (high_p - low_p) if high_p != low_p else 1 [cite: 13]
        if pos < 0.25:
            return {'代號名稱': f"{ticker.split('.')[0]} {name}", '收盤價': round(curr_p, 2), '量能倍數': round(v_now/v_avg, 2), '今日張數': int(v_now/1000)} [cite: 13]
    except: return None

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
    "00929.TW": "復華科技", "00713.TW": "高息低波", "006208.TW": "富邦台50", 
    "6789.TW": "采鈺", "6147.TWO": "頎邦"
}

# === 5. 介面佈局 ===
tabs = st.tabs(["🎯 股神雷達", "💰 成交排行", "📈 互動看盤", "🚀 波段掃描", "🔥 量能監控", "🔍 低檔快篩", "💎 籌碼大數據", "📺 多圖連動"])

with tabs[0]:
    if st.button("🚀 啟動完整雷達掃描", use_container_width=True):
        res, prc = [], 0
        pb, txt = st.progress(0), st.empty() [cite: 17]
        with ThreadPoolExecutor(max_workers=5) as ex:
            futs = [ex.submit(analyze_stock_score, t, n) for t, n in STOCKS.items()]
            for f in as_completed(futs):
                prc += 1
                pb.progress(prc / len(STOCKS)) [cite: 17]
                txt.text(f"🔄 掃描中: {prc}/{len(STOCKS)} ...") [cite: 18]
                if f.result(): res.append(f.result())
        pb.empty(); txt.empty() [cite: 19]
        if res:
            df = pd.DataFrame(res).sort_values(by=['Sort_Score','日K'], ascending=False)
            st.session_state['df_radar'] = df.drop(columns=['Sort_Score']).head(35)
    
    if 'df_radar' in st.session_state:
        st.dataframe(st.session_state['df_radar'], use_container_width=True)

with tabs[1]:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("📈 上市排行")
        df1 = get_rank("TWSE") [cite: 20]
        if df1 is not None:
            df1_disp = df1.head(15).copy()
            df1_disp['金額'] = df1_disp['值'].apply(lambda x: f"{int(x/100000000):,} 億")
            st.table(df1_disp[['證券代號','證券名稱','金額']].reset_index(drop=True)) [cite: 20]
    with c2:
        st.subheader("📉 上櫃排行")
        df2 = get_rank("TPEx") [cite: 20]
        if df2 is not None:
            df2_disp = df2.head(15).copy()
            df2_disp['金額'] = df2_disp['值'].apply(lambda x: f"{int(x/100000000):,} 億")
            st.table(df2_disp[['證券代號','證券名稱','金額']].reset_index(drop=True)) [cite: 21]

with tabs[2]:
    sid3 = st.text_input("🔍 代號查詢", value="2330", key="t3_sid")
    if sid3:
        tid3 = sid3 + ".TW" if "." not in sid3 else sid3 [cite: 22]
        d3 = yf.Ticker(tid3).history(period="1y") [cite: 22]
        if not d3.empty:
            d3 = calculate_kd(d3)
            fig3 = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3]) [cite: 22]
            fig3.add_trace(go.Candlestick(x=d3.index, open=d3['Open'], high=d3['High'], low=d3['Low'], close=d3['Close'], name='K線'), row=1, col=1) [cite: 22]
            fig3.add_trace(go.Scatter(x=d3.index, y=d3['K'], name='K', line=dict(color='yellow')), row=2, col=1) [cite: 23]
            fig3.add_trace(go.Scatter(x=d3.index, y=d3['D'], name='D', line=dict(color='cyan')), row=2, col=1) [cite: 23]
            fig3.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False) [cite: 23]
            st.plotly_chart(fig3, use_container_width=True)

with tabs[3]:
    if st.button("啟動波段掃描"):
        brs = []
        for t, n in STOCKS.items():
            df = yf.Ticker(t).history(period="3mo") [cite: 24]
            if len(df) < 20: continue [cite: 24]
            df['UP'] = df['Close'].rolling(20).mean() + (2 * df['Close'].rolling(20).std()) [cite: 24]
            if df['Close'].iloc[-1] > df['UP'].iloc[-1]:
                brs.append({'標的':f"{t} {n}",'價':round(df['Close'].iloc[-1],2)}) [cite: 24]
        if brs: st.dataframe(pd.DataFrame(brs), use_container_width=True)

with tabs[4]:
    if st.button("啟動量能監控"):
        vls = [] [cite: 25]
        for t, n in STOCKS.items():
            df = yf.Ticker(t).history(period="1mo") [cite: 25]
            if len(df) < 6: continue [cite: 25]
            v_now, v_avg = df['Volume'].iloc[-1], df['Volume'].iloc[-6:-1].mean() [cite: 25]
            if v_now > v_avg * 1.8:
                vls.append({'標的':f"{t} {n}",'倍數':round(v_now/v_avg,1)}) [cite: 25]
        if vls: st.dataframe(pd.DataFrame(vls).sort_values(by='倍數', ascending=False), use_container_width=True) [cite: 26]

with tabs[5]:
    if st.button("🚀 開始全市場大掃篩選", use_container_width=True):
        pool, results = [], []
        df_twse, df_tpex = get_rank("TWSE"), get_rank("TPEx") [cite: 27, 28]
        if df_twse is not None:
            for _, r in df_twse.head(150).iterrows(): pool.append((r['證券代號'] + ".TW", r['證券名稱'])) [cite: 27]
        if df_tpex is not None:
            for _, r in df_tpex.head(100).iterrows(): pool.append((r['證券代號'] + ".TWO", r['證券名稱'])) [cite: 28]
        with ThreadPoolExecutor(max_workers=10) as executor:
            f_to_s = {executor.submit(check_low_breakout, t, n): t for t, n in pool} [cite: 29]
            for f in as_completed(f_to_s):
                if f.result(): results.append(f.result())
        if results: st.dataframe(pd.DataFrame(results).sort_values('今日張數', ascending=False), use_container_width=True) [cite: 30]

with tabs[6]:
    st.subheader("💎 三大法人昨日買賣超排行榜")
    chip_df = get_chip_data()
    if chip_df is not None:
        ca, cb = st.columns(2)
        with ca:
            st.write("🔥 **法人合買 Top 20**")
            st.dataframe(chip_df.sort_values('法人合計', ascending=False).head(20).reset_index(drop=True), use_container_width=True)
        with cb:
            st.write("❄️ **法人合賣 Top 20**")
            st.dataframe(chip_df.sort_values('法人合計', ascending=True).head(20).reset_index(drop=True), use_container_width=True)

with tabs[7]:
    col_l, col_r = st.columns([1, 4])
    with col_l:
        sid8 = st.text_input("🔍 代號", value="2330", key="t8_sid")
        ind8 = st.radio("副指標切換", ["KD", "成交量", "RSI"])
    
    if sid8:
        tid8 = sid8 + ".TW" if "." not in sid8 else sid8
        try:
            d8 = yf.Ticker(tid8).history(period="1y")
            if not d8.empty:
                d8 = calculate_kd(d8)
                fig8 = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.6, 0.4], vertical_spacing=0.03)
                fig8.add_trace(go.Candlestick(x=d8.index, open=d8['Open'], high=d8['High'], low=d8['Low'], close=d8['Close'], name='K線'), row=1, col=1)
                for m in [5, 20, 60]:
                    d8[f'MA{m}'] = d8['Close'].rolling(m).mean()
                    fig8.add_trace(go.Scatter(x=d8.index, y=d8[f'MA{m}'], name=f'MA{m}', line=dict(width=1)), row=1, col=1)
                
                if ind8 == "KD":
                    fig8.add_trace(go.Scatter(x=d8.index, y=d8['K'], name='K', line=dict(color='yellow')), row=2, col=1)
                    fig8.add_trace(go.Scatter(x=d8.index, y=d8['D'], name='D', line=dict(color='cyan')), row=2, col=1)
                elif ind8 == "成交量":
                    colors = ['red' if c >= o else 'green' for o, c in zip(d8['Open'], d8['Close'])]
                    fig8.add_trace(go.Bar(x=d8.index, y=d8['Volume'], marker_color=colors, name='量'), row=2, col=1)
                elif ind8 == "RSI":
                    delta = d8['Close'].diff()
                    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                    rsi = 100 - (100 / (1 + (gain/loss)))
                    fig8.add_trace(go.Scatter(x=d8.index, y=rsi, name='RSI', line=dict(color='orange')), row=2, col=1)
                
                fig8.update_layout(height=700, template="plotly_dark", xaxis_rangeslider_visible=False, hovermode='x unified')
                st.plotly_chart(fig8, use_container_width=True)
        except Exception as e:
            st.error(f"圖表顯示失敗: {e}")
