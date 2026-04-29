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

# === 系統環境設定 ===
warnings.filterwarnings("ignore")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
st.set_page_config(page_title="老盧股神系統", page_icon="📡", layout="wide")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
HEADERS = {"User-Agent": UA}

# === 核心清單與功能 (從 source 1 繼承) ===
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
    "6789.TW": "采鈺", "6147.TWO": "頎邦", "3016.TW": "嘉晶"
}

# === 功能函數 ===
def calculate_kd(df):
    if len(df) < 9: return df
    df['9_min'] = df['Low'].rolling(window=9).min()
    df['9_max'] = df['High'].rolling(window=9).max()
    df['RSV'] = (df['Close'] - df['9_min']) / (df['9_max'] - df['9_min']) * 100
    k, d = 50.0, 50.0
    k_v, d_v = [], []
    for rsv in df['RSV']:
        if pd.isna(rsv):
            k_v.append(50.0); d_v.append(50.0)
        else:
            k = (2/3) * k + (1/3) * rsv
            d = (2/3) * d + (1/3) * k
            k_v.append(k); d_v.append(d)
    df['K'], df['D'] = k_v, d_v
    return df

@st.cache_data(ttl=600)
def get_rank_data(m_type):
    """整合 source 1 與 source 2 的抓取邏輯"""
    try:
        if m_type == "TWSE":
            url = "https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&type=ALLBUT0999"
            res = requests.get(url, headers=HEADERS, verify=False, timeout=10).json()
            stock_data, fields = None, None
            if 'tables' in res:
                for table in res['tables']:
                    if 'fields' in table and '證券代號' in table['fields'] and '成交金額' in table['fields']:
                        fields, stock_data = table['fields'], table['data']
                        break
            if not stock_data: return None
            df = pd.DataFrame(stock_data, columns=fields)
            df = df[['證券代號', '證券名稱', '成交金額']]
        else:
            url = "https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php?l=zh-tw&o=json"
            res = requests.get(url, headers=HEADERS, verify=False, timeout=10).json()
            stock_data = res.get('aaData', [])
            if not stock_data: return None
            df = pd.DataFrame(stock_data)
            col_val = 9 if df.shape[1] >= 10 else df.shape[1] - 2
            df = df[[0, 1, col_val]]
            df.columns = ['證券代號', '證券名稱', '成交金額']
        
        df['值'] = pd.to_numeric(df['成交金額'].astype(str).str.replace(',',''), errors='coerce').fillna(0)
        return df.sort_values('值', ascending=False)
    except: return None

# === 側邊欄導覽 ===
st.sidebar.title("🏮 選單")
page = st.sidebar.radio("跳轉頁面", ["🎯 股神雷達系統", "💰 成交值排行 TOP 15"])

# === 第一頁：股神雷達系統 ===
if page == "🎯 股神雷達系統":
    st.title("📡 股神雷達系統旗艦版")
    tabs = st.tabs(["🎯 自動雷達", "📈 互動看盤", "🔍 低檔快篩"])
    
    with tabs[0]:
        if st.button("🚀 啟動完整雷達掃描", use_container_width=True):
            # ... 此處保留您 source 1 內的 analyze_stock_score 運作邏輯 ...
            st.info("執行中...")
            
    with tabs[1]:
        sid = st.text_input("🔍 輸入代號 (如 2330)", value="2330")
        if sid:
            tid = sid + ".TW" if "." not in sid else sid
            try:
                d = yf.Ticker(tid).history(period="1y")
                if not d.empty:
                    d = calculate_kd(d)
                    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3])
                    fig.add_trace(go.Candlestick(x=d.index, open=d['Open'], high=d['High'], low=d['Low'], close=d['Close'], name='K線'), row=1, col=1)
                    fig.add_trace(go.Scatter(x=d.index, y=d['K'], name='K', line=dict(color='yellow')), row=2, col=1)
                    fig.add_trace(go.Scatter(x=d.index, y=d['D'], name='D', line=dict(color='cyan')), row=2, col=1)
                    fig.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False)
                    st.plotly_chart(fig, use_container_width=True)
            except: st.error("查無資料")

# === 第二頁：成交值排行 (整合自 source 2) ===
elif page == "💰 成交值排行 TOP 15":
    st.title("💰 股市成交值排行榜")
    if st.button("🔄 刷新即時排行"): st.cache_data.clear()
    
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("📈 上市排行 (TWSE)")
        df1 = get_rank_data("TWSE")
        if df1 is not None:
            df1_disp = df1.head(15).copy()
            df1_disp['成交金額(億)'] = df1_disp['值'].apply(lambda x: f"{round(x/100000000, 2)} 億")
            st.dataframe(df1_disp[['證券代號','證券名稱','成交金額(億)']].reset_index(drop=True), use_container_width=True)
            
    with c2:
        st.subheader("📉 上櫃排行 (TPEx)")
        df2 = get_rank_data("TPEx")
        if df2 is not None:
            df2_disp = df2.head(15).copy()
            df2_disp['成交金額(億)'] = df2_disp['值'].apply(lambda x: f"{round(x/100000000, 2)} 億")
            st.dataframe(df2_disp[['證券代號','證券名稱','成交金額(億)']].reset_index(drop=True), use_container_width=True)
