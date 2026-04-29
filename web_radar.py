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

# === 2. 核心技術指標計算 ===
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

def calculate_macd(df):
    exp1 = df['Close'].ewm(span=12, adjust=False).mean()
    exp2 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp1 - exp2
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['Hist'] = df['MACD'] - df['Signal']
    return df

# === 3. 六星雷達核心邏輯 ===
def analyze_stock_score(ticker, name):
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="1y")
        # 🛡️ 濾除幽靈空值
        df.dropna(subset=['Close'], inplace=True)
        if df.empty or len(df) < 65: return None
        
        close = df['Close'].iloc[-1]
        vol_today = df['Volume'].iloc[-1]
        vol_5d = df['Volume'].iloc[-6:-1].mean()
        
        if vol_5d < 1000000: return None
        
        df['MA5'] = df['Close'].rolling(5).mean()
        df['MA20'] = df['Close'].rolling(20).mean()
        df['MA60'] = df['Close'].rolling(60).mean()
        
        df = calculate_kd(df)
        df = calculate_macd(df)
        
        stars = 0
        tags = []
        
        if close > df['MA5'].iloc[-1] > df['MA20'].iloc[-1] > df['MA60'].iloc[-1]:
            stars += 1; tags.append("[均線多頭]")
        if df['MA20'].iloc[-1] > df['MA20'].iloc[-2]:
            stars += 1; tags.append("[月線向上]")
        if vol_today > vol_5d * 1.5:
            stars += 1; tags.append("[爆量攻擊]")
            
        dk, dd = df['K'].iloc[-1], df['D'].iloc[-1]
        dyk, dyd = df['K'].iloc[-2], df['D'].iloc[-2]
        if (dk > dd) and (dyk <= dyd):
            stars += 1; tags.append("[KD金叉]")
            
        hist, hist_y = df['Hist'].iloc[-1], df['Hist'].iloc[-2]
        if hist > 0 and hist > hist_y:
            stars += 1; tags.append("[MACD強勢]")
            
        high_20 = df['High'].iloc[-21:-1].max()
        if close > high_20:
            stars += 1; tags.append("[創20日新高]")
            
        star_display = "⭐" * stars if stars > 0 else "休息中"
        tid = ticker.replace('.TW', '').replace('.TWO', '')
        return {
            '標的': f"{tid} {name}", '星等': star_display, '收盤': round(close, 2), 
            '觸發條件': " + ".join(tags) if tags else "無", '今日量(張)': int(vol_today/1000), '星星數': stars 
        }
    except: return None

# === 4. 持股出場診斷邏輯 (防空值 + 上櫃自動偵測) ===
def diagnose_holding(ticker_input):
    try:
        # 自動判斷是否為上櫃股票
        tid = ticker_input + ".TW" if "." not in ticker_input else ticker_input
        df = yf.Ticker(tid).history(period="6mo")
        df.dropna(subset=['Close'], inplace=True) # 🛡️ 濾除幽靈空值
        
        # 如果上市找不到，自動去上櫃找
        if df.empty and "." not in ticker_input:
            tid = ticker_input + ".TWO"
            df = yf.Ticker(tid).history(period="6mo")
            df.dropna(subset=['Close'], inplace=True)
            
        if df.empty or len(df) < 30: return None

        df['MA5'] = df['Close'].rolling(5).mean()
        df['MA20'] = df['Close'].rolling(20).mean()
        df = calculate_kd(df)

        close = df['Close'].iloc[-1]
        ma5 = df['MA5'].iloc[-1]
        ma20 = df['MA20'].iloc[-1]
        k, d = df['K'].iloc[-1], df['D'].iloc[-1]
        k_y, d_y = df['K'].iloc[-2], df['D'].iloc[-2]

        status = []
        action = "🟢 續抱 (趨勢健康，繼續鎖定獲利)"

        if close < ma20:
            status.append("⚠️ 跌破 20 日月線 (波段趨勢轉弱)")
            action = "🛑 建議停損/停利出場，保留現金"
        elif close < ma5:
            status.append("⚠️ 跌破 5 日線 (短線攻擊熄火)")
            action = "🟡 建議先減碼一半，收回部分資金"

        if k < d and k_y >= d_y and k_y > 70:
            status.append("⚠️ KD 高檔死亡交叉 (上漲動能衰退)")
            action = "🟡 建議拔檔減碼，提防主力出貨"

        if not status:
            status.append("✅ 均線與動能皆維持強勢多頭")

        return {
            "標的代號": tid, "收盤價": round(close, 2), "5日線": round(ma5, 2), "月線": round(ma20, 2),
            "KD狀態": f"K: {round(k,1)} / D: {round(d,1)}",
            "技術面診斷": "、".join(status), "系統建議": action
        }
    except: return None

# === 5. 成交排行獲取 (新舊格式通吃) ===
@st.cache_data(ttl=300)
def get_rank(m_type):
    try:
        if m_type == "TWSE":
            u = "https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&type=ALLBUT0999"
            res = requests.get(u, headers=HEADERS, verify=False, timeout=10).json()
            stock_data, fields = None, None
            if 'tables' in res:
                for table in res['tables']:
                    if 'fields' in table and '證券代號' in table['fields'] and '成交金額' in table['fields']:
                        fields, stock_data = table['fields'], table['data']
                        break
            if not stock_data:
                for key, val in res.items():
                    if key.startswith('fields') and isinstance(val, list):
                        if '證券代號' in val and '成交金額' in val:
                            data_key = key.replace('fields', 'data')
                            if data_key in res:
                                fields, stock_data = val, res[data_key]
                                break
            if not stock_data: return None
            df = pd.DataFrame(stock_data, columns=fields)
            df = df[['證券代號', '證券名稱', '成交金額']]
        else:
            u = "https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php?l=zh-tw&o=json"
            res = requests.get(u, headers=HEADERS, verify=False, timeout=10).json()
            stock_data = []
            if 'aaData' in res and res['aaData']:
                stock_data = res['aaData']
            elif 'tables' in res:
                for table in res['tables']:
                    if 'data' in table and len(table['data']) > 0 and len(table['data'][0]) > 5:
                        stock_data = table['data']
                        break
            if not stock_data: return None
            df = pd.DataFrame(stock_data)
            col_val = 9 if df.shape[1] >= 10 else df.shape[1] - 2
            df = df[[0, 1, col_val]]
            df.columns = ['證券代號', '證券名稱', '成交金額']
    
        df['值'] = pd.to_numeric(df['成交金額'].astype(str).str.replace(',',''), errors='coerce').fillna(0)
        return df.sort_values('值', ascending=False)
    except: return None

# === 6. 112 檔精選名單 ===
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

# === 7. 側邊欄與分頁介面 ===
st.sidebar.title("📡 導覽選單")
main_page = st.sidebar.radio("跳轉頁面", ["🎯 股神六星雷達系統", "💰 專業成交排行 (15名)"])

if main_page == "🎯 股神六星雷達系統":
    st.title("📡 股神系統：多頭六星飆股雷達")
    
    t1, t2, t3, t4 = st.tabs(["🎯 六星雷達掃描", "💰 成交排行", "📈 互動看盤", "🛡️ 持股出場診斷"])

    with t1:
        st.info("💡 評分條件：均線多頭、月線向上、成交爆量、KD金叉、MACD強勢、創20日高。")
        if st.button("🚀 啟動六星雷達掃描", use_container_width=True):
            start_t = time.time()
            res, prc = [], 0
            pb, txt = st.progress(0), st.empty()
            with ThreadPoolExecutor(max_workers=5) as ex:
                futs = [ex.submit(analyze_stock_score, t, n) for t, n in STOCKS.items()]
                for f in as_completed(futs):
                    prc += 1
                    pb.progress(prc / len(STOCKS))
                    txt.text(f"🔄 掃描引擎運轉中: {prc}/{len(STOCKS)} ...")
                    if f.result(): res.append(f.result())
            pb.empty(); txt.empty()
            st.success(f"✅ 掃描完成！耗時 {round(time.time() - start_t, 1)} 秒。")
            if res:
                df = pd.DataFrame(res).sort_values(by='星星數', ascending=False)
                st.session_state['df_radar'] = df.drop(columns=['星星數'])
        
        if 'df_radar' in st.session_state:
            st.dataframe(st.session_state['df_radar'], use_container_width=True)

    with t2:
        if st.button("🔄 刷新即時排行"): st.cache_data.clear()
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("📈 上市排行 (TWSE)")
            df1 = get_rank("TWSE")
            if df1 is not None:
                df1_disp = df1.head(15).copy()
                df1_disp['金額'] = df1_disp['值'].apply(lambda x: f"{int(x/100000000):,} 億")
                st.table(df1_disp[['證券代號','證券名稱','金額']].reset_index(drop=True))
            else:
                st.warning("⚠️ 暫時抓不到上市資料，可能因非交易時段。")
                
        with c2:
            st.subheader("📉 上櫃排行 (TPEx)")
            df2 = get_rank("TPEx")
            if df2 is not None:
                df2_disp = df2.head(15).copy()
                df2_disp['金額'] = df2_disp['值'].apply(lambda x: f"{int(x/100000000):,} 億")
                st.table(df2_disp[['證券代號','證券名稱','金額']].reset_index(drop=True))
            else:
                st.warning("⚠️ 暫時抓不到上櫃資料，可能因非交易時段。")

    with t3:
        st.subheader("📈 個股 K 線與動能分析")
        col_input, col_btn = st.columns([3, 1])
        with col_input:
            sid = st.text_input("🔍 輸入股票代號 (直接輸入代號即可)", value="2330", key="chart_input")
        with col_btn:
            st.write("") # 為了排版對齊
            st.write("")
            chart_submitted = st.button("📈 繪製 K 線圖", use_container_width=True)

        # 加入按鈕控制，點擊按鈕後才執行繪圖
        if chart_submitted and sid:
            with st.spinner("讀取圖表中..."):
                tid = sid + ".TW" if "." not in sid else sid
                try:
                    df = yf.Ticker(tid).history(period="1y")
                    df.dropna(subset=['Close'], inplace=True) # 🛡️ 濾除空值
                    
                    # 上櫃自動切換
                    if df.empty and "." not in sid:
                        tid = sid + ".TWO"
                        df = yf.Ticker(tid).history(period="1y")
                        df.dropna(subset=['Close'], inplace=True)

                    if not df.empty:
                        d = calculate_kd(df)
                        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3])
                        fig.add_trace(go.Candlestick(x=d.index, open=d['Open'], high=d['High'], low=d['Low'], close=d['Close'], name=tid), row=1, col=1)
                        fig.add_trace(go.Scatter(x=d.index, y=d['K'], name='K', line=dict(color='yellow')), row=2, col=1)
                        fig.add_trace(go.Scatter(x=d.index, y=d['D'], name='D', line=dict(color='cyan')), row=2, col=1)
                        fig.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False, title_text=f"{tid} 行情圖")
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.error("⚠️ 查無此股票資料。")
                except: st.error("⚠️ 資料讀取失敗。")

    with t4:
        st.subheader("🛡️ 智慧出場與持股診斷")
        st.write("輸入持股代號，系統將幫你檢查目前的均線支撐與動能，判斷是否該獲利了結或停損。")
        
        col_diag_input, col_diag_btn = st.columns([3, 1])
        with col_diag_input:
            diag_sid = st.text_input("🔍 輸入持股代號 (直接輸入代號即可)", value="2330", key="diag_input")
        with col_diag_btn:
            st.write("") # 為了排版對齊
            st.write("")
            diag_submitted = st.button("🛡️ 執行診斷", use_container_width=True)
        
        # 加入按鈕控制，點擊按鈕後才執行診斷
        if diag_submitted and diag_sid:
            with st.spinner('機密診斷中...'):
                result = diagnose_holding(diag_sid)
                if result:
                    st.markdown(f"### 🎯 {result['標的代號']} 診斷結果")
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("收盤價", result['收盤價'])
                    c2.metric("5日線 (極短線支撐)", result['5日線'])
                    c3.metric("月線 (波段防守線)", result['月線'])
                    c4.metric("KD 動能", result['KD狀態'])
                    
                    st.warning(f"**技術面狀況：** {result['技術面診斷']}")
                    
                    if "續抱" in result['系統建議']:
                        st.success(f"**行動建議：** {result['系統建議']}")
                    elif "減碼" in result['系統建議']:
                        st.info(f"**行動建議：** {result['系統建議']}")
                    else:
                        st.error(f"**行動建議：** {result['系統建議']}")
                else:
                    st.error("⚠️ 查無此股票資料，或資料筆數不足以進行診斷。")

else:
    st.title("💰 專業成交值排行榜 TOP 15")
    if st.button("🔄 刷新資料"): st.cache_data.clear()
    
    col_a, col_b = st.columns(2)
    with col_a:
        st.header("🏢 上市成交 TOP 15")
        df_a = get_rank("TWSE")
        if df_a is not None:
            df_a_15 = df_a.head(15).copy()
            df_a_15['成交金額(元)'] = df_a_15['值'].apply(lambda x: f"{int(x):,}")
            df_a_15.index = range(1, 16)
            st.dataframe(df_a_15[['證券代號', '證券名稱', '成交金額(元)']], use_container_width=True)
        else:
            st.error("⚠️ 無法讀取上市資料，可能因非交易時段。")

    with col_b:
        st.header("🏪 上櫃成交 TOP 15")
        df_b = get_rank("TPEx")
        if df_b is not None:
            df_b_15 = df_b.head(15).copy()
            df_b_15['成交金額(元)'] = df_b_15['值'].apply(lambda x: f"{int(x):,}")
            df_b_15.index = range(1, 16)
            st.dataframe(df_b_15[['證券代號', '證券名稱', '成交金額(元)']], use_container_width=True)
        else:
            st.error("⚠️ 無法讀取上櫃資料，可能因非交易時段。")
