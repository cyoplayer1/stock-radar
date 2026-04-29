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
st.set_page_config(page_title="老盧股神系統雷達", page_icon="📡", layout="wide")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
HEADERS = {"User-Agent": UA}
FUGLE_API_KEY = "54f80721-6cad-4ec9-9679-c5a315e7b00b"

# === 2. 籌碼引擎：抓取法人買賣超 ===
@st.cache_data(ttl=3600)
def get_inst_data():
    """抓取今日(或昨日)外資投信買賣超合計"""
    inst_map = {}
    try:
        # 1. 上市法人 (外資+投信)
        url_twse = "https://www.twse.com.tw/fund/T86?response=json&selectType=ALLBUT0999"
        res = requests.get(url_twse, headers=HEADERS, timeout=10).json()
        if 'data' in res:
            for d in res['data']:
                sid = d[0].strip()
                # 外資(d[2]) + 投信(d[10]) 的合計買賣超
                foreign = int(d[2].replace(',', ''))
                trust = int(d[10].replace(',', ''))
                inst_map[sid] = foreign + trust
        
        # 2. 上櫃法人 (外資+投信)
        url_tpex = "https://www.tpex.org.tw/web/stock/fund/T86/T86_result.php?l=zh-tw&o=json"
        res_otc = requests.get(url_tpex, headers=HEADERS, timeout=10).json()
        if 'aaData' in res_otc:
            for d in res_otc['aaData']:
                sid = d[0].strip()
                # 外資(d[8]) + 投信(d[10])
                foreign = int(d[8].replace(',', ''))
                trust = int(d[10].replace(',', ''))
                inst_map[sid] = foreign + trust
    except:
        pass
    return inst_map

# === 3. 核心計算 ===
def calculate_kd(df):
    if len(df) < 9: return df
    df['9_min'] = df['Low'].rolling(window=9).min()
    df['9_max'] = df['High'].rolling(window=9).max()
    df['RSV'] = (df['Close'] - df['9_min']) / (df['9_max'] - df['9_min']) * 100
    k_v, d_v, k, d = [], [], 50.0, 50.0
    for rsv in df['RSV']:
        if pd.isna(rsv):
            k_v.append(50.0); d_v.append(50.0)
        else:
            k = (2/3) * k + (1/3) * rsv
            d = (2/3) * d + (1/3) * k
            k_v.append(k); d_v.append(d)
    df['K'], df['D'] = k_v, d_v
    return df

def calculate_macd(df):
    exp1 = df['Close'].ewm(span=12, adjust=False).mean()
    exp2 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp1 - exp2
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['Hist'] = df['MACD'] - df['Signal']
    return df

def get_fugle_realtime(symbol):
    try:
        url = f"https://api.fugle.tw/marketdata/v1.0/stock/intraday/quote/{symbol}"
        res = requests.get(url, headers={"X-API-KEY": FUGLE_API_KEY}, timeout=5)
        if res.status_code == 200:
            data = res.json()
            return data.get('closePrice'), data.get('total', {}).get('tradeVolume', 0)
    except: pass
    return None, None

# === 4. 名單字典 ===
STOCKS_DICT = {
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

# === 5. 核心邏輯 (加入法人數據) ===
def analyze_stock_score(ticker_in, inst_map):
    try:
        clean = ticker_in.replace('.TW','').replace('.TWO','')
        tid = clean + ".TW"; df = yf.Ticker(tid).history(period="1y")
        df.dropna(subset=['Close'], inplace=True)
        if df.empty:
            tid = clean + ".TWO"; df = yf.Ticker(tid).history(period="1y")
            df.dropna(subset=['Close'], inplace=True)
        if df.empty or len(df) < 65: return None
        
        # ⚡ 富果即時報價
        fc, fv = get_fugle_realtime(clean)
        if fc:
            df.iloc[-1, df.columns.get_loc('Close')] = fc
            if fv: df.iloc[-1, df.columns.get_loc('Volume')] = fv
        
        c = df['Close'].iloc[-1]; v = df['Volume'].iloc[-1]; v5 = df['Volume'].iloc[-6:-1].mean()
        if v5 < 1000000: return None
        
        df['MA5'] = df['Close'].rolling(5).mean(); df['MA20'] = df['Close'].rolling(20).mean(); df['MA60'] = df['Close'].rolling(60).mean()
        df = calculate_kd(df); df = calculate_macd(df)
        
        s, tags = 0, []
        if c > df['MA5'].iloc[-1] > df['MA20'].iloc[-1] > df['MA60'].iloc[-1]: s+=1; tags.append("[均線多頭]")
        if df['MA20'].iloc[-1] > df['MA20'].iloc[-2]: s+=1; tags.append("[月線向上]")
        if v > v5 * 1.5: s+=1; tags.append("[爆量攻擊]")
        if df['K'].iloc[-1] > df['D'].iloc[-1] and df['K'].iloc[-2] <= df['D'].iloc[-2]: s+=1; tags.append("[KD金叉]")
        if df['Hist'].iloc[-1] > 0 and df['Hist'].iloc[-1] > df['Hist'].iloc[-2]: s+=1; tags.append("[MACD強勢]")
        if c > df['High'].iloc[-21:-1].max(): s+=1; tags.append("[創20日新高]")
        
        # 💎 獲取法人合計數據
        inst_val = inst_map.get(clean, 0)
        inst_display = f"{inst_val:,}" if inst_val != 0 else "--"
        
        name = STOCKS_DICT.get(tid, clean)
        return {
            '標的': f"{clean} {name}", '星等': "⭐"*s if s>0 else "休息", '收盤': round(c,2), 
            '外投買賣(張)': inst_display, '觸發條件': "+".join(tags), '今日量(張)': int(v/1000), '星星數': s
        }
    except: return None

# === 6. 介面與導覽 ===
st.sidebar.title("📡 導覽選單")
main_page = st.sidebar.radio("跳轉頁面", ["🎯 股神六星雷達系統", "💰 專業成交排行 (15名)"])
st.sidebar.markdown("---")
st.sidebar.subheader("⚙️ 自選股水庫")
def_t = ", ".join([k.split('.')[0] for k in STOCKS_DICT.keys()])
u_in = st.sidebar.text_area("代號庫：", value=def_t, height=200)
s_list = [t.strip() for t in u_in.replace('，',',').split(',') if t.strip()]

if main_page == "🎯 股神六星雷達系統":
    st.title("📡 老盧股神系統：籌碼強化版")
    t1, t2, t3, t4 = st.tabs(["🎯 六星雷達", "💰 成交排行", "📈 互動看盤", "🛡️ 持股診斷"])
    
    with t1:
        st.markdown("""
        ### 🎯 高勝率組合：5星以上 + [爆量攻擊] + 外投買超
        * **外投買賣(張)：** 外資與投信今日買賣超合計。
        * **加分題：** 如果星星多，且法人也站在買方，這台車馬力更足！
        ---
        """)
        if st.button("🚀 啟動即時掃描 (含籌碼分析)", use_container_width=True):
            # 先抓法人總表
            inst_data = get_inst_data()
            res, pb = [], st.progress(0)
            with ThreadPoolExecutor(max_workers=5) as ex:
                futs = [ex.submit(analyze_stock_score, t, inst_data) for t in s_list]
                for i, f in enumerate(as_completed(futs)):
                    pb.progress((i+1)/len(s_list))
                    if f.result(): res.append(f.result())
            if res:
                df = pd.DataFrame(res).sort_values(by='星星數', ascending=False)
                # 重新排序顯示欄位
                disp_cols = ['標的', '星等', '收盤', '外投買賣(張)', '今日量(張)', '觸發條件']
                st.dataframe(df[disp_cols], use_container_width=True)
            else: st.warning("⚠️ 水庫資料抓取異常。")

    # (其餘分頁 t2, t3, t4 保持原樣)
    with t2:
        if st.button("🔄 刷新排行"): st.cache_data.clear()
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("📈 上市排行")
            df1 = get_rank("TWSE")
            if df1 is not None:
                d15 = df1.head(15).copy()
                d15['金額'] = d15['值'].apply(lambda x: f"{int(x/100000000):,} 億")
                st.table(d15[['證券代號','證券名稱','金額']].reset_index(drop=True))
        with c2:
            st.subheader("📉 上櫃排行")
            df2 = get_rank("TPEx")
            if df2 is not None:
                d15b = df2.head(15).copy()
                d15b['金額'] = d15b['值'].apply(lambda x: f"{int(x/100000000):,} 億")
                st.table(d15b[['證券代號','證券名稱','金額']].reset_index(drop=True))

    with t3:
        sid = st.text_input("🔍 輸入代號", value="2330", key="chart_in")
        if st.button("📈 繪圖", use_container_width=True):
            tid = sid + ".TW" if "." not in sid else sid
            df = yf.Ticker(tid).history(period="1y")
            df.dropna(subset=['Close'], inplace=True)
            if not df.empty:
                d = calculate_kd(df)
                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3])
                fig.add_trace(go.Candlestick(x=d.index, open=d['Open'], high=d['High'], low=d['Low'], close=d['Close'], name=tid), row=1, col=1)
                fig.add_trace(go.Scatter(x=d.index, y=d['K'], name='K', line=dict(color='yellow')), row=2, col=1)
                fig.add_trace(go.Scatter(x=d.index, y=d['D'], name='D', line=dict(color='cyan')), row=2, col=1)
                fig.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True)

    with t4:
        st.subheader("🛡️ 持股即時診斷")
        d_id = st.text_input("🔍 診斷代號", value="2330", key="diag_in")
        if st.button("🛡️ 執行診斷", use_container_width=True):
            # (診斷函數內容保持不變，可參考上一版本)
            from web_radar import diagnose_holding 
            r = diagnose_holding(d_id)
            if r:
                st.markdown(f"### 🎯 {r['標的']} 戰情室")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("即時價", r['收盤']); c2.metric("5日線", r['MA5'])
                c3.metric("月線", r['MA20']); c4.metric("KD狀態", r['KD'])
                st.warning(f"**狀況：** {r['狀況']}")
                if "續抱" in r['建議']: st.success(f"**建議：** {r['建議']}")
                else: st.error(f"**建議：** {r['建議']}")
