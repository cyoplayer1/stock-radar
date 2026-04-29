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

# === 3. 名單字典 ===
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

# === 4. 核心邏輯 ===
def analyze_stock_score(t_in):
    try:
        c_id = t_in.replace('.TW','').replace('.TWO','')
        tid = c_id + ".TW"; df = yf.Ticker(tid).history(period="1y")
        df.dropna(subset=['Close'], inplace=True)
        if df.empty:
            tid = c_id + ".TWO"; df = yf.Ticker(tid).history(period="1y")
            df.dropna(subset=['Close'], inplace=True)
        if df.empty or len(df) < 65: return None
        fc, fv = get_fugle_realtime(c_id)
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
        return {'標的': f"{c_id} {STOCKS_DICT.get(tid, c_id)}", '星等': "⭐"*s if s>0 else "休息", '收盤': round(c,2), '觸發條件': "+".join(tags), '今日量(張)': int(v/1000), '星星數': s}
    except: return None

def diagnose_holding(t_in):
    try:
        c_id = t_in.replace('.TW','').replace('.TWO','')
        tid = c_id + ".TW"; df = yf.Ticker(tid).history(period="6mo")
        df.dropna(subset=['Close'], inplace=True)
        if df.empty:
            tid = c_id + ".TWO"; df = yf.Ticker(tid).history(period="6mo")
            df.dropna(subset=['Close'], inplace=True)
        if df.empty or len(df) < 30: return None
        fc, _ = get_fugle_realtime(c_id)
        if fc: df.iloc[-1, df.columns.get_loc('Close')] = fc
        df['MA5'] = df['Close'].rolling(5).mean(); df['MA20'] = df['Close'].rolling(20).mean(); df = calculate_kd(df)
        c, m5, m20 = df['Close'].iloc[-1], df['MA5'].iloc[-1], df['MA20'].iloc[-1]
        k, d = df['K'].iloc[-1], df['D'].iloc[-1]
        stt, act = [], "🟢 續抱 (趨勢健康，繼續鎖定獲利)"
        if c < m20: stt.append("⚠️ 跌破月線"); act = "🛑 建議停損/停利"
        elif c < m5: stt.append("⚠️ 跌破5日線"); act = "🟡 建議先減碼一半"
        if k < d and df['K'].iloc[-2] >= df['D'].iloc[-2] and k > 70: stt.append("⚠️ KD高檔死叉"); act = "🟡 建議拔檔減碼"
        if not stt: stt.append("✅ 均線與動能維持強勢多頭")
        return {"標的": c_id, "收盤": round(c,2), "MA5": round(m5,2), "MA20": round(m20,2), "KD": f"K:{round(k,1)}/D:{round(d,1)}", "狀況": "、".join(stt), "建議": act}
    except: return None

# === 5. 排行獲取 (強化版：相容新舊格式) ===
@st.cache_data(ttl=300)
def get_rank(m_type):
    try:
        if m_type == "TWSE":
            u = "https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&type=ALLBUT0999"
            res = requests.get(u, headers=HEADERS, verify=False, timeout=10).json()
            stock_data, fields = None, None
            if 'tables' in res: # 新版格式
                for table in res['tables']:
                    if 'fields' in table and '證券代號' in table['fields']:
                        fields, stock_data = table['fields'], table['data']
                        break
            if not stock_data: # 舊版備用
                for i in range(1, 10):
                    if f'data{i}' in res and '成交金額' in str(res.get(f'fields{i}', '')):
                        fields, stock_data = res[f'fields{i}'], res[f'data{i}']
                        break
            if not stock_data: return None
            df = pd.DataFrame(stock_data, columns=fields)
            df = df[['證券代號', '證券名稱', '成交金額']]
        else:
            u = "https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php?l=zh-tw&o=json"
            res = requests.get(u, headers=HEADERS, verify=False, timeout=10).json()
            stock_data = []
            if 'aaData' in res: # 傳統格式
                stock_data = res['aaData']
            elif 'tables' in res: # 新版結構
                for table in res['tables']:
                    if 'data' in table and len(table['data']) > 0:
                        stock_data = table['data']
                        break
            if not stock_data: return None
            df = pd.DataFrame(stock_data)
            col_v = 9 if df.shape[1] >= 10 else df.shape[1] - 2
            df = df[[0, 1, col_v]]
            df.columns = ['證券代號', '證券名稱', '成交金額']
        df['值'] = pd.to_numeric(df['成交金額'].astype(str).str.replace(',',''), errors='coerce').fillna(0)
        return df.sort_values('值', ascending=False)
    except: return None

# === 6. 介面與導覽 ===
st.sidebar.title("📡 導覽選單")
main_p = st.sidebar.radio("跳轉頁面", ["🎯 股神六星雷達系統", "💰 專業成交排行 (15名)"])
st.sidebar.markdown("---")
st.sidebar.subheader("⚙️ 自選股水庫")
def_t = ", ".join([k.split('.')[0] for k in STOCKS_DICT.keys()])
u_in = st.sidebar.text_area("代號庫：", value=def_t, height=200)
s_list = [t.strip() for t in u_in.replace('，',',').split(',') if t.strip()]

if main_p == "🎯 股神六星雷達系統":
    st.title("📡 老盧股神系統：終極即時版")
    t1, t2, t3, t4 = st.tabs(["🎯 六星雷達", "💰 成交排行", "📈 互動看盤", "🛡️ 持股診斷"])
    with t1:
        if st.button("🚀 啟動掃描", use_container_width=True):
            res, pb = [], st.progress(0)
            with ThreadPoolExecutor(max_workers=5) as ex:
                futs = [ex.submit(analyze_stock_score, t) for t in s_list]
                for i, f in enumerate(as_completed(futs)):
                    pb.progress((i+1)/len(s_list))
                    if f.result(): res.append(f.result())
            if res:
                df = pd.DataFrame(res).sort_values(by='星星數', ascending=False)
                st.dataframe(df.drop(columns=['星星數']), use_container_width=True)
    with t2:
        if st.button("🔄 刷新排行"): st.cache_data.clear()
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("📈 上市排行")
            df1 = get_rank("TWSE")
            if df1 is not None:
                df1_d = df1.head(15).copy()
                df1_d['金額'] = df1_d['值'].apply(lambda x: f"{int(x/100000000):,} 億")
                st.table(df1_d[['證券代號','證券名稱','金額']].reset_index(drop=True))
            else: st.warning("⚠️ 暫無資料 (凌晨維護中)")
        with c2:
            st.subheader("📉 上櫃排行")
            df2 = get_rank("TPEx")
            if df2 is not None:
                df2_d = df2.head(15).copy()
                df2_d['金額'] = df2_d['值'].apply(lambda x: f"{int(x/100000000):,} 億")
                st.table(df2_d[['證券代號','證券名稱','金額']].reset_index(drop=True))
            else: st.warning("⚠️ 暫無資料 (凌晨維護中)")
    with t3:
        sid = st.text_input("🔍 輸入代號", value="2330", key="chart_in")
        if st.button("📈 繪圖", use_container_width=True):
            tid = sid + ".TW" if "." not in sid else sid
            df = yf.Ticker(tid).history(period="1y")
            df.dropna(subset=['Close'], inplace=True)
            if df.empty and "." not in sid:
                tid = sid + ".TWO"; df = yf.Ticker(tid).history(period="1y")
            if not df.empty:
                d = calculate_kd(df)
                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3])
                fig.add_trace(go.Candlestick(x=d.index, open=d['Open'], high=d['High'], low=d['Low'], close=d['Close'], name=tid), row=1, col=1)
                fig.add_trace(go.Scatter(x=d.index, y=d['K'], name='K', line=dict(color='yellow')), row=2, col=1)
                fig.add_trace(go.Scatter(x=d.index, y=d['D'], name='D', line=dict(color='cyan')), row=2, col=1)
                fig.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True)
            else: st.error("⚠️ 查無資料")
    with t4:
        st.subheader("🛡️ 持股即時診斷")
        d_id = st.text_input("🔍 診斷代號", value="2330", key="diag_in")
        if st.button("🛡️ 執行診斷", use_container_width=True):
            r = diagnose_holding(d_id)
            if r:
                st.markdown(f"### 🎯 {r['標的']} 戰情室")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("即時價", r['收盤']); c2.metric("5日線", r['MA5'])
                c3.metric("月線", r['MA20']); c4.metric("KD狀態", r['KD'])
                st.warning(f"**狀況：** {r['狀況']}")
                if "續抱" in r['建議']: st.success(f"**建議：** {r['建議']}")
                elif "減碼" in r['建議']: st.warning(f"**建議：** {r['建議']}")
                else: st.error(f"**建議：** {r['建議']}")
            else: st.error("⚠️ 資料擷取失敗")
else:
    st.title("💰 專業成交排行 TOP 15")
    if st.button("🔄 刷新資料"): st.cache_data.clear()
    c_a, c_b = st.columns(2)
    df_a = get_rank("TWSE")
    if df_a is not None:
        c_a.header("🏢 上市熱門")
        d15 = df_a.head(15).copy()
        d15['成交金額(元)'] = d15['值'].apply(lambda x: f"{int(x):,}")
        c_a.dataframe(d15[['證券代號', '證券名稱', '成交金額(元)']], use_container_width=True)
    df_b = get_rank("TPEx")
    if df_b is not None:
        c_b.header("🏪 上櫃熱門")
        d15b = df_b.head(15).copy()
        d15b['成交金額(元)'] = d15b['值'].apply(lambda x: f"{int(x):,}")
        c_b.dataframe(d15b[['證券代號', '證券名稱', '成交金額(元)']], use_container_width=True)
