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
st.set_page_config(page_title="老盧股神系統", page_icon="📡", layout="wide")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
HEADERS = {"User-Agent": UA}
# 🔑 老盧專屬富果 API 金鑰
FUGLE_API_KEY = "54f80721-6cad-4ec9-9679-c5a315e7b00b"

# === 2. 核心計算函數 ===

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

def get_fugle_realtime(symbol):
    try:
        url = f"https://api.fugle.tw/marketdata/v1.0/stock/intraday/quote/{symbol}"
        res = requests.get(url, headers={"X-API-KEY": FUGLE_API_KEY}, timeout=5, verify=False)
        if res.status_code == 200:
            data = res.json()
            return data.get('closePrice'), data.get('total', {}).get('tradeVolume', 0)
    except: pass
    return None, None

@st.cache_data(ttl=3600)
def get_inst_data():
    """抓取今日法人買賣超合計 (外資+投信)"""
    inst_map = {}
    try:
        u1 = "https://www.twse.com.tw/fund/T86?response=json&selectType=ALLBUT0999"
        r1 = requests.get(u1, headers=HEADERS, timeout=10, verify=False).json()
        if 'data' in r1:
            for d in r1['data']: inst_map[d[0].strip()] = int(d[2].replace(',', '')) + int(d[10].replace(',', ''))
        u2 = "https://www.tpex.org.tw/web/stock/fund/T86/T86_result.php?l=zh-tw&o=json"
        r2 = requests.get(u2, headers=HEADERS, timeout=10, verify=False).json()
        if 'aaData' in r2:
            for d in r2['aaData']: inst_map[d[0].strip()] = int(d[8].replace(',', '')) + int(d[10].replace(',', ''))
    except: pass
    return inst_map

@st.cache_data(ttl=300)
def get_hot_rank_ids():
    """抓取全市場成交金額前 15 名的代號清單"""
    hot_ids = set()
    try:
        u1 = "https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&type=ALLBUT0999"
        res1 = requests.get(u1, headers=HEADERS, timeout=10, verify=False).json()
        if 'tables' in res1:
            for t in res1['tables']:
                if '證券代號' in t.get('fields', []):
                    df_t = pd.DataFrame(t['data'], columns=t['fields'])
                    df_t['val'] = pd.to_numeric(df_t['成交金額'].str.replace(',',''), errors='coerce')
                    hot_ids.update(df_t.sort_values('val', ascending=False).head(15)['證券代號'].tolist())
                    break
        u2 = "https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php?l=zh-tw&o=json"
        res2 = requests.get(u2, headers=HEADERS, timeout=10, verify=False).json()
        dt = res2.get('aaData', []) or (res2.get('tables', [{}])[0].get('data', []) if 'tables' in res2 else [])
        if dt:
            df_otc = pd.DataFrame(dt)
            idx = 9 if df_otc.shape[1] >= 10 else df_otc.shape[1] - 2
            df_otc['val'] = pd.to_numeric(df_otc[idx].astype(str).str.replace(',',''), errors='coerce')
            hot_ids.update(df_otc.sort_values('val', ascending=False).head(15)[0].tolist())
    except: pass
    return hot_ids

def get_rank_full(m_type):
    """獲取完整排行數據供分頁顯示"""
    try:
        if m_type == "TWSE":
            u = "https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&type=ALLBUT0999"
            r = requests.get(u, headers=HEADERS, timeout=10, verify=False).json()
            if 'tables' in r:
                for t in r['tables']:
                    if '證券代號' in t.get('fields', []):
                        df = pd.DataFrame(t['data'], columns=t['fields'])
                        df['值'] = pd.to_numeric(df['成交金額'].str.replace(',',''), errors='coerce')
                        return df.sort_values('值', ascending=False)
        else:
            u = "https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php?l=zh-tw&o=json"
            r = requests.get(u, headers=HEADERS, timeout=10, verify=False).json()
            dt = r.get('aaData', []) or (r.get('tables', [{}])[0].get('data', []) if 'tables' in r else [])
            if dt:
                df = pd.DataFrame(dt)
                idx = 9 if df.shape[1] >= 10 else df.shape[1] - 2
                df['值'] = pd.to_numeric(df[idx].astype(str).str.replace(',',''), errors='coerce')
                return df.sort_values('值', ascending=False)
    except: pass
    return None

# === 3. 112 檔精選名單字典 ===
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

# === 4. 雷達掃描與診斷邏輯 ===

def analyze_stock_score(ticker_in, inst_map, hot_list):
    try:
        clean = ticker_in.replace('.TW','').replace('.TWO','')
        tid = clean + (".TWO" if ticker_in.endswith(".TWO") else ".TW")
        df = yf.Ticker(tid).history(period="1y")
        if df.empty and not ticker_in.endswith((".TW", ".TWO")):
            tid = clean + ".TWO"; df = yf.Ticker(tid).history(period="1y")
        if df.empty or len(df) < 65: return None
        
        fc, fv = get_fugle_realtime(clean)
        if fc: df.iloc[-1, df.columns.get_loc('Close')] = fc
        if fv: df.iloc[-1, df.columns.get_loc('Volume')] = fv
        
        c = df['Close'].iloc[-1]; v = df['Volume'].iloc[-1]; v5 = df['Volume'].iloc[-6:-1].mean()
        df['MA5'] = df['Close'].rolling(5).mean(); df['MA20'] = df['Close'].rolling(20).mean(); df['MA60'] = df['Close'].rolling(60).mean()
        df = calculate_kd(df)
        
        s, tags = 0, []
        if c > df['MA5'].iloc[-1] > df['MA20'].iloc[-1] > df['MA60'].iloc[-1]: s+=1; tags.append("[均線多頭]")
        if df['MA20'].iloc[-1] > df['MA20'].iloc[-2]: s+=1; tags.append("[月線向上]")
        if v > v5 * 1.5: s+=1; tags.append("[爆量攻擊]")
        if df['K'].iloc[-1] > df['D'].iloc[-1] and df['K'].iloc[-2] <= df['D'].iloc[-2]: s+=1; tags.append("[KD金叉]")
        if c > df['High'].iloc[-21:-1].max(): s+=1; tags.append("[創20日新高]")
        
        if clean in hot_list: tags.append("🔥[排行熱門]")
        inst_val = inst_map.get(clean, 0)
        if inst_val > 500: tags.append("🔴[大戶進駐]")
        
        return {'代號': clean, '標的': f"{clean} {STOCKS_DICT.get(tid, '')}", '星等': "⭐"*s if s>0 else "休息", '收盤': round(c,2), '籌碼大戶(張)': f"{inst_val:,}" if inst_val!=0 else "--", '今日量(張)': int(v/1000), '觸發條件': " ".join(tags), '星星數': s}
    except: return None

def diagnose_and_linkage(clean_id):
    """一鍵聯動：自動生成圖表、診斷與煞車計算"""
    tid = clean_id + ".TW"; df = yf.Ticker(tid).history(period="1y")
    if df.empty: tid = clean_id + ".TWO"; df = yf.Ticker(tid).history(period="1y")
    if df.empty: return st.error("⚠️ 查無此代號資料")

    # 即時價格補正
    fc, _ = get_fugle_realtime(clean_id)
    if fc: df.iloc[-1, df.columns.get_loc('Close')] = fc

    df['MA5'] = df['Close'].rolling(5).mean(); df['MA20'] = df['Close'].rolling(20).mean(); df = calculate_kd(df)
    c, m5, m20, k, d = df['Close'].iloc[-1], df['MA5'].iloc[-1], df['MA20'].iloc[-1], df['K'].iloc[-1], df['D'].iloc[-1]

    col_chart, col_tool = st.columns([2, 1])
    with col_chart:
        d_plot = df.tail(100)
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3])
        fig.add_trace(go.Candlestick(x=d_plot.index, open=d_plot['Open'], high=d_plot['High'], low=d_plot['Low'], close=d_plot['Close'], name='K線'), row=1, col=1)
        fig.add_trace(go.Scatter(x=d_plot.index, y=d_plot['K'], name='K', line=dict(color='yellow')), row=2, col=1)
        fig.add_trace(go.Scatter(x=d_plot.index, y=d_plot['D'], name='D', line=dict(color='cyan')), row=2, col=1)
        fig.update_layout(height=500, template="plotly_dark", xaxis_rangeslider_visible=False, margin=dict(t=10, b=10, l=10, r=10))
        st.plotly_chart(fig, use_container_width=True)

    with col_tool:
        st.subheader(f"🛡️ {clean_id} 即時診斷")
        st.metric("即時價", f"{round(c, 2)}", delta=f"月線乖離 {round(c-m20, 2)}")
        
        # 診斷邏輯
        stt, act = [], "🟢 續抱 (趨勢健康)"
        if c < m20: stt.append("⚠️ 跌破月線"); act = "🛑 建議停損/停利"
        elif c < m5: stt.append("⚠️ 跌破5日線"); act = "🟡 建議先減碼一半"
        if k < d and k > 70: stt.append("⚠️ KD高檔死叉"); act = "🟡 建議拔檔減碼"
        if not stt: stt.append("✅ 強勢多頭趨勢")
        
        st.write(f"**技術狀況：** {'、'.join(stt)}")
        if "續抱" in act: st.success(f"**系統建議：** {act}")
        else: st.warning(f"**系統建議：** {act}")

        st.divider()
        st.subheader("⚖️ 煞車計算器")
        risk_money = st.number_input("本筆交易願意賠多少？(元)", value=20000, step=1000)
        stop_price = st.number_input("預計停損價 (破月線停損)", value=round(m20 * 0.98, 1))
        
        if c > stop_price:
            suggest_shares = risk_money / (c - stop_price)
            st.success(f"⚖️ 建議買進：**{round(suggest_shares/1000, 2)}** 張")
            st.info(f"💡 賠率公式：$20,000 / ({c} - {stop_price}) = {int(suggest_shares)} 股$")
        else: st.error("⚠️ 停損價需低於目前價格")

# === 5. 側邊欄與導覽 ===

st.sidebar.title("📡 老盧中控台")
ticker_list_str = ", ".join([k.split('.')[0] for k in STOCKS_DICT.keys()])
user_input = st.sidebar.text_area("自選股水庫：", value=ticker_list_str, height=200)
s_list = list(set([t.strip() for t in user_input.replace('，',',').split(',') if t.strip()]))

# === 6. 主畫面顯示 ===

st.title("📡 老盧股神系統：全自動聯動版")

t_radar, t_rank = st.tabs(["🎯 六星共振雷達", "💰 成交排行 (15名)"])

with t_radar:
    st.markdown("""
    ### 🎯 買進策略：共振發動
    * **核心指標：** 5顆星以上股票。
    * **黃金組合：** [KD金叉] + [爆量攻擊] + 🔥[排行熱門] + 🔴[大戶進駐]。
    * **便利功能：** 掃描完後直接在下方「選取標的」，自動聯動圖表與煞車計算。
    ---
    """)
    if st.button("🚀 啟動即時全方位掃描", use_container_width=True):
        inst_map = get_inst_data()
        hot_list = get_hot_rank_ids()
        res, pb = [], st.progress(0)
        with ThreadPoolExecutor(max_workers=5) as ex:
            futs = [ex.submit(analyze_stock_score, t, inst_map, hot_list) for t in s_list]
            for i, f in enumerate(as_completed(futs)):
                pb.progress((i+1)/len(s_list))
                if f.result(): res.append(f.result())
        if res:
            df_res = pd.DataFrame(res).sort_values(by='星星數', ascending=False)
            st.session_state['scan_res'] = df_res
        else: st.error("⚠️ 無法獲取資料，請檢查 API 或網路連線。")

    if 'scan_res' in st.session_state:
        # 顯示雷達表格
        st.dataframe(st.session_state['scan_res'][['標的', '星等', '收盤', '籌碼大戶(張)', '觸發條件']], use_container_width=True)
        
        st.divider()
        st.markdown("### 🔍 智慧聯動：選取標的進入戰情分析")
        option_list = st.session_state['scan_res']['代號'].tolist()
        selected_sid = st.selectbox("🎯 請選擇剛才掃描出的標的：", options=option_list)
        
        if selected_sid:
            diagnose_and_linkage(selected_sid)

with t_rank:
    st.markdown("### 💰 市場最熱：主力資金足跡")
    if st.button("🔄 刷新即時排行表"): st.cache_data.clear()
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🏢 上市熱門 TOP 15")
        df_twse = get_rank_full("TWSE")
        if df_twse is not None:
            d15 = df_twse.head(15).copy()
            d15['金額'] = d15['值'].apply(lambda x: f"{int(x/100000000):,} 億")
            st.table(d15[['證券代號','證券名稱','金額']].reset_index(drop=True))
    with c2:
        st.subheader("📉 上櫃熱門 TOP 15")
        df_otc = get_rank_full("TPEx")
        if df_otc is not None:
            d15b = df_otc.head(15).copy()
            d15b['金額'] = d15b['值'].apply(lambda x: f"{int(x/100000000):,} 億")
            # 上櫃 API 欄位處理
            st.table(d15b.iloc[:, [0, 1, -1]].rename(columns={0:'代號', 1:'名稱'}).reset_index(drop=True))
