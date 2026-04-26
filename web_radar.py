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
    if len(df) < 9: return df
    df['9_min'] = df['Low'].rolling(window=9).min()
    df['9_max'] = df['High'].rolling(window=9).max()
    df['RSV'] = (df['Close'] - df['9_min']) / (df['9_max'] - df['9_min']) * 100
    k_v, d_v = [], []
    k, d = 50.0, 50.0
    for rsv in df['RSV']:
        if pd.isna(rsv):
            k_v.append(50.0); d_v.append(50.0)
        else:
            k = (2/3) * k + (1/3) * rsv
            d = (2/3) * d + (1/3) * k
            k_v.append(k); d_v.append(d)
    df['K'], df['D'] = k_v, d_v
    return df

@st.cache_data(ttl=300)
def get_rank_v2(m_type):
    """採用最新動態掃描邏輯抓取排行 (修復不顯示問題)"""
    try:
        if m_type == "TWSE":
            url = "https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&type=ALLBUT0999"
            res = requests.get(url, headers=HEADERS, verify=False, timeout=10).json()
            stock_data, fields = None, None
            # 🌟 掃描 TWSE 所有的 tables 格式
            if 'tables' in res:
                for table in res['tables']:
                    if 'fields' in table and '證券代號' in table['fields'] and '成交金額' in table['fields']:
                        fields, stock_data = table['fields'], table['data']
                        break
            if not stock_data: return pd.DataFrame()
            df = pd.DataFrame(stock_data, columns=fields)
            df = df[['證券代號', '證券名稱', '成交金額']]
        else:
            url = "https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php?l=zh-tw&o=json"
            res = requests.get(url, headers=HEADERS, verify=False, timeout=10).json()
            # 🌟 掃描 TPEx 所有的 tables 或 aaData
            stock_data = res.get('aaData', [])
            if not stock_data and 'tables' in res:
                for table in res['tables']:
                    if 'data' in table and len(table['data']) > 0 and len(table['data'][0]) > 5:
                        stock_data = table['data']; break
            if not stock_data: return pd.DataFrame()
            df = pd.DataFrame(stock_data)
            # 櫃買中心成交值通常在位置 9 或最後幾欄
            col_idx = 9 if df.shape[1] >= 10 else df.shape[1] - 2
            df = df[[0, 1, col_idx]]
            df.columns = ['證券代號', '證券名稱', '成交金額']
        
        # 數值清洗
        df['金額數值'] = pd.to_numeric(df['成交金額'].astype(str).str.replace(',',''), errors='coerce').fillna(0)
        df_sorted = df.sort_values('金額數值', ascending=False).head(20)
        return df_sorted
    except: return pd.DataFrame()

# === 3. 名單與其餘功能保持不變 ===
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

st.title("📡 股神系統旗艦整合版")
tabs = st.tabs(["🎯 股神雷達", "💰 成交排行", "📈 互動看盤", "🚀 波段掃描", "🔥 量能監控", "🔍 全台股低檔快篩"])

with tabs[1]:
    if st.button("🔄 刷新即時排行"): st.cache_data.clear()
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("📈 上市排行 (TWSE)")
        df1 = get_rank_v2("TWSE")
        if not df1.empty:
            df1['金額'] = df1['金額數值'].apply(lambda x: f"{int(x/100000000):,} 億")
            st.table(df1[['證券代號','證券名稱','金額']].reset_index(drop=True).head(15))
        else: st.error("上市資料抓取失敗，請確認網路或 API 狀態")
    with c2:
        st.subheader("📉 上櫃排行 (TPEx)")
        df2 = get_rank_v2("TPEx")
        if not df2.empty:
            df2['金額'] = df2['金額數值'].apply(lambda x: f"{int(x/100000000):,} 億")
            st.table(df2[['證券代號','證券名稱','金額']].reset_index(drop=True).head(15))
        else: st.error("上櫃資料抓取失敗，請確認網路或 API 狀態")

# 其餘分頁代碼依照旗艦版邏輯保持不變...
with tabs[5]:
    st.subheader("🔍 全台股：低檔爆量強勢股偵測")
    st.info("💡 **邏輯說明：** 1. 位階 < 25% (半年底部) 2. 今日成交量 > 5日均量 1.8 倍 3. 排除無量股。")
    if st.button("🚀 開始全市場大掃描", use_container_width=True):
        st_t = time.time()
        with st.spinner("掃描熱門標的中..."):
            pool = []
            df1 = get_rank_v2("TWSE"); df2 = get_rank_v2("TPEx")
            if not df1.empty:
                for _, r in df1.head(150).iterrows(): pool.append((r['證券代號'] + ".TW", r['證券名稱']))
            if not df2.empty:
                for _, r in df2.head(100).iterrows(): pool.append((r['證券代號'] + ".TWO", r['證券名稱']))
            
            # ... 此處接續 ThreadPoolExecutor 掃描邏輯 (與 V23 版相同) ...
