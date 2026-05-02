import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import warnings
import time
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib3
from requests.exceptions import ChunkedEncodingError, ConnectionError, ReadTimeout
import os

# === 1. 系統環境設定 ===
warnings.filterwarnings("ignore")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
st.set_page_config(page_title="稀有的股神系統雷達", page_icon="📡", layout="wide")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
HEADERS = {"User-Agent": UA}
FUGLE_API_KEY = "54f80721-6cad-4ec9-9679-c5a315e7b00b"

# === 2. 🛡️ 安全連線防護機制 (修正快取衝突版) ===
def safe_get_json(url, headers, max_retries=3):
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=15, verify=False)
            response.raise_for_status() 
            return response.json()
        except (ChunkedEncodingError, ConnectionError, ReadTimeout) as e:
            # 🛑 已移除 st.toast，避免引發 Streamlit 的 CacheReplayClosureError 崩潰
            time.sleep(2)
        except ValueError:
            break
        except Exception as e:
            break
    return {}

# === 3. 核心計算函數 ===
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
        res = requests.get(url, headers={"X-API-KEY": FUGLE_API_KEY}, timeout=5, verify=False)
        if res.status_code == 200:
            data = res.json()
            return data.get('closePrice'), data.get('total', {}).get('tradeVolume', 0)
    except: pass
    return None, None

@st.cache_data(ttl=3600)
def get_inst_data():
    inst_map = {}
    try:
        u1 = "https://www.twse.com.tw/fund/T86?response=json&selectType=ALLBUT0999"
        r1 = safe_get_json(u1, HEADERS)
        if 'data' in r1:
            for d in r1['data']: inst_map[d[0].strip()] = int(d[2].replace(',', '')) + int(d[10].replace(',', ''))
            
        u2 = "https://www.tpex.org.tw/web/stock/fund/T86/T86_result.php?l=zh-tw&o=json"
        r2 = safe_get_json(u2, HEADERS)
        if 'aaData' in r2:
            for d in r2['aaData']: inst_map[d[0].strip()] = int(d[8].replace(',', '')) + int(d[10].replace(',', ''))
    except: pass
    return inst_map

@st.cache_data(ttl=300)
def get_hot_rank_ids():
    hot_ids = set()
    try:
        u1 = "https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&type=ALLBUT0999"
        res1 = safe_get_json(u1, HEADERS)
        if 'tables' in res1:
            for t in res1['tables']:
                if '證券代號' in t.get('fields', []):
                    df_tmp = pd.DataFrame(t['data'], columns=t['fields'])
                    df_tmp['val'] = pd.to_numeric(df_tmp['成交金額'].str.replace(',',''), errors='coerce')
                    hot_ids.update(df_tmp.sort_values('val', ascending=False).head(15)['證券代號'].tolist())
                    break
                    
        u2 = "https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php?l=zh-tw&o=json"
        res2 = safe_get_json(u2, HEADERS)
        data_otc = res2.get('aaData', []) or (res2.get('tables', [{}])[0].get('data', []) if 'tables' in res2 else [])
        if data_otc:
            df_otc = pd.DataFrame(data_otc)
            cv = 9 if df_otc.shape[1] >= 10 else df_otc.shape[1] - 2
            df_otc['val'] = pd.to_numeric(df_otc[cv].astype(str).str.replace(',',''), errors='coerce')
            hot_ids.update(df_otc.sort_values('val', ascending=False).head(15)[0].tolist())
    except: pass
    return hot_ids

# === 4. 名單字典 (112 檔精選) ===
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

# === 5. 雷達掃描與診斷邏輯 ===
def analyze_stock_score(ticker_in, inst_map, hot_list):
    try:
        clean = ticker_in.replace('.TW','').replace('.TWO','')
        tid = clean + ".TW"; df = yf.Ticker(tid).history(period="1y")
        df.dropna(subset=['Close'], inplace=True)
        if df.empty:
            tid = clean + ".TWO"; df = yf.Ticker(tid).history(period="1y")
            df.dropna(subset=['Close'], inplace=True)
        if df.empty or len(df) < 65: return None
        
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
        
        if clean in hot_list: tags.append("🔥[排行熱門]")
        inst_val = inst_map.get(clean, 0)
        if inst_val > 500: tags.append("🔴[大戶進駐]")
        
        inst_display = f"{inst_val:,}" if inst_val != 0 else "--"
        name = STOCKS_DICT.get(tid, clean)
        return {'標的': f"{clean} {name}", '星等': "⭐"*s if s>0 else "休息", '收盤': round(c,2), '籌碼大戶(張)': inst_display, '今日量(張)': int(v/1000), '觸發條件': " ".join(tags), '星星數': s}
    except: return None

def diagnose_holding(ticker_in):
    try:
        clean = ticker_in.replace('.TW','').replace('.TWO','')
        tid = clean + ".TW"; df = yf.Ticker(tid).history(period="6mo")
        df.dropna(subset=['Close'], inplace=True)
        if df.empty:
            tid = clean + ".TWO"; df = yf.Ticker(tid).history(period="6mo")
            df.dropna(subset=['Close'], inplace=True)
        if df.empty or len(df) < 30: return None
        fc, _ = get_fugle_realtime(clean)
        if fc: df.iloc[-1, df.columns.get_loc('Close')] = fc
        df['MA5'] = df['Close'].rolling(5).mean(); df['MA20'] = df['Close'].rolling(20).mean(); df = calculate_kd(df)
        c, m5, m20 = df['Close'].iloc[-1], df['MA5'].iloc[-1], df['MA20'].iloc[-1]
        k, d = df['K'].iloc[-1], df['D'].iloc[-1]
        status, action = [], "🟢 續抱 (趨勢健康)"
        if c < m20: status.append("⚠️ 跌破月線"); action = "🛑 建議停損/停利"
        elif c < m5: status.append("⚠️ 跌破5日線"); action = "🟡 建議先減碼一半"
        if k < d and df['K'].iloc[-2] >= df['D'].iloc[-2] and k > 70: status.append("⚠️ KD高檔死叉"); action = "🟡 建議拔檔減碼"
        if not status: status.append("✅ 強勢多頭")
        return {"標的": clean, "收盤": round(c,2), "MA5": round(m5,2), "MA20": round(m20,2), "KD": f"K:{round(k,1)}/D:{round(d,1)}", "狀況": "、".join(status), "建議": action}
    except: return None

# === 6. 🕵️‍♂️ 經理人籌碼追蹤邏輯 (火力全開版) ===
def fetch_today_holdings_from_api(etf_code="00981A"):
    today = datetime.datetime.today().strftime('%Y-%m-%d')
    new_data = []
    
    url_twse = f"https://www.twse.com.tw/fund/ETF8?response=json&code={etf_code}"
    res = safe_get_json(url_twse, HEADERS)
    
    with st.sidebar.expander("🛠️ API 封包監控 (除錯專用)"):
        st.write(f"正在請求: {etf_code}")
        st.json(res)
        
    if res and 'data' in res and len(res['data']) > 0:
        for row in res['data']:
            ticker = str(row[0]).strip()
            name = str(row[1]).strip()
            shares = int(row[2].replace(',', '')) // 1000 
            new_data.append([today, ticker, name, shares])
    else:
        st.sidebar.error(f"⚠️ 真實 API 目前找不到 {etf_code} 的資料，將啟動火力全開測試引擎。")
        
    return pd.DataFrame(new_data, columns=['日期', '代號', '股票名稱', '持有張數'])

def get_00981a_holdings_history(force_refresh=False):
    db_path = "00981A_holdings_db.csv"
    today_str = datetime.datetime.today().strftime('%Y-%m-%d')
    
    if os.path.exists(db_path):
        df_history = pd.read_csv(db_path)
    else:
        df_history = pd.DataFrame(columns=['日期', '代號', '股票名稱', '持有張數'])
        
    if not df_history.empty and today_str in df_history['日期'].values and not force_refresh:
        return df_history
        
    if force_refresh and not df_history.empty:
        df_history = df_history[df_history['日期'] != today_str]
            
    with st.spinner("🔄 正在從連線獲取經理人今日最新持股..."):
        df_today = fetch_today_holdings_from_api("00981A")
        
    if not df_today.empty:
        df_history = pd.concat([df_history, df_today], ignore_index=True)
        df_history.to_csv(db_path, index=False)
        st.toast("✅ 今日持股資料已更新入庫！", icon="🎉")
    elif df_history.empty:
        st.info("💡 已啟動【火力全開視覺預覽模式】：為您載入模擬持股與連續籌碼動向。")
        dates = [(datetime.datetime.today() - datetime.timedelta(days=i)).strftime('%Y-%m-%d') for i in range(3, -1, -1)]
        
        mock_scenarios = [
            ("2317", "鴻海", [1000, 1500, 2000, 3000]),
            ("3231", "緯創", [2000, 2000, 2000, 3500]),
            ("2383", "台光電", [3000, 3000, 3500, 4200]),
            ("2368", "金像電", [100, 300, 500, 800]),
            ("3017", "奇鋐", [800, 800, 1200, 1800]),
            ("2345", "智邦", [1000, 1200, 1500, 1900]),
            ("3533", "嘉澤", [600, 600, 700, 900]),
            ("2330", "台積電", [8000, 8000, 8000, 8000]),
            ("2454", "聯發科", [1500, 1500, 1500, 1500]),
            ("3324", "雙鴻", [500, 500, 500, 500]),
            ("2308", "台達電", [5000, 5200, 5500, 4500]),
            ("2382", "廣達", [4000, 4000, 3000, 2000]),
            ("3034", "聯詠", [1000, 1000, 800, 500]),
            ("2603", "長榮", [5000, 4000, 3000, 2000]),
            ("3661", "世芯-KY", [400, 400, 400, 200]),
        ]
        
        dummy_rows = []
        for ticker, name, shares in mock_scenarios:
            for i, d in enumerate(dates):
                dummy_rows.append([d, ticker, f"{name} (測試)", shares[i]])
                
        return pd.DataFrame(dummy_rows, columns=['日期', '代號', '股票名稱', '持有張數'])
        
    return df_history

def analyze_manager_moves(df):
    if df.empty:
        return pd.DataFrame()
        
    df = df.sort_values(by=['代號', '日期'])
    df['單日買賣超(張)'] = df.groupby('代號')['持有張數'].diff().fillna(0)
    
    results = []
    for stock_id, group in df.groupby('代號'):
        group = group.sort_values('日期')
        diffs = group['單日買賣超(張)'].tolist()
        
        consecutive_buy = 0
        for diff in reversed(diffs):
            if diff > 0: consecutive_buy += 1
            else: break
                
        consecutive_sell = 0
        for diff in reversed(diffs):
            if diff < 0: consecutive_sell += 1
            else: break
                
        latest_record = group.iloc[-1]
        
        if consecutive_buy > 0: status, days = "🟢 主力連買", consecutive_buy
        elif consecutive_sell > 0: status, days = "🔴 經理人倒貨", consecutive_sell
        else: status, days = "⚪ 靜止觀望", 0
            
        results.append({
            "代號": stock_id,
            "股票名稱": latest_record['股票名稱'],
            "最新持股張數": int(latest_record['持有張數']),
            "今日買賣超(張)": int(latest_record['單日買賣超(張)']),
            "動向狀態": status,
            "連續天數": f"{days} 天" if days > 0 else "-"
        })
        
    return pd.DataFrame(results).sort_values(by="今日買賣超(張)", ascending=False)


# === 7. 側邊欄與介面 ===
st.sidebar.title("📡 導覽選單")
main_page = st.sidebar.radio(
    "跳轉頁面", 
    ["🎯 股神六星雷達系統", "🕵️‍♂️ 00981A 經理人跟單雷達"]
)
st.sidebar.markdown("---")

if main_page == "🎯 股神六星雷達系統":
    st.sidebar.subheader("⚙️ 自選股水庫")
    def_tickers = ", ".join([k.split('.')[0] for k in STOCKS_DICT.keys()])
    u_input = st.sidebar.text_area("代號庫：", value=def_tickers, height=200)
    s_list = [t.strip() for t in u_input.replace('，',',').split(',') if t.strip()]

# ==========================================
# 分頁 1: 🎯 股神六星雷達系統
# ==========================================
if main_page == "🎯 股神六星雷達系統":
    st.title("📡 稀有的股神系統：終極版")
    t1, t2, t3, t4 = st.tabs(["🎯 六星雷達", "💰 成交排行", "📈 互動看盤", "🛡️ 持股診斷"])
    
    with t1:
        st.markdown("""
        ### 🎯 買進策略：共振發動
        * **核心指標：** 5顆星以上股票。
        * **黃金組合：** 同時出現 **[KD金叉]**、**[爆量攻擊]**、**🔥[排行熱門]** 與 **🔴[大戶進駐]**。
        * **三不買：** 沒量不買、月線向下不買、星星掉隊不買。
        ---
        """)
        if st.button("🚀 啟動即時掃描 (全自動共振分析)", use_container_width=True):
            inst_map = get_inst_data()
            hot_list = get_hot_rank_ids()
            res, pb = [], st.progress(0)
            with ThreadPoolExecutor(max_workers=5) as ex:
                futs = [ex.submit(analyze_stock_score, t, inst_map, hot_list) for t in s_list]
                for i, f in enumerate(as_completed(futs)):
                    pb.progress((i+1)/len(s_list))
                    if f.result(): res.append(f.result())
            if res:
                df = pd.DataFrame(res).sort_values(by='星星數', ascending=False)
                st.dataframe(df[['標的', '星等', '收盤', '籌碼大戶(張)', '今日量(張)', '觸發條件']], use_container_width=True)

    with t2:
        st.markdown("""
        ### 💰 量能先行：主力足跡
        * **前 15 名：** 這裡是當前盤面上資金最滾燙的地方。
        * **連動參考：** 如果雷達星星也出現在這張清單，代表「熱點共振」。
        ---
        """)
        if st.button("🔄 刷新排行"): st.cache_data.clear()
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("📈 上市排行")
            url = "https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&type=ALLBUT0999"
            res = safe_get_json(url, HEADERS) 
            if res and 'tables' in res:
                for table in res['tables']:
                    if '證券代號' in table.get('fields', []):
                        df1 = pd.DataFrame(table['data'], columns=table['fields'])
                        df1['值'] = pd.to_numeric(df1['成交金額'].str.replace(',',''), errors='coerce')
                        d15 = df1.sort_values('值', ascending=False).head(15).copy()
                        d15['金額'] = d15['值'].apply(lambda x: f"{int(x/100000000):,} 億")
                        st.table(d15[['證券代號','證券名稱','金額']].reset_index(drop=True))
                        break
        with c2:
            st.subheader("📉 上櫃排行")
            url = "https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php?l=zh-tw&o=json"
            res = safe_get_json(url, HEADERS) 
            data_otc = res.get('aaData', []) or (res.get('tables', [{}])[0].get('data', []) if res and 'tables' in res else [])
            if data_otc:
                df2 = pd.DataFrame(data_otc)
                cv = 9 if df2.shape[1] >= 10 else df2.shape[1] - 2
                df2['值'] = pd.to_numeric(df2[cv].astype(str).str.replace(',',''), errors='coerce')
                d15b = df2.sort_values('值', ascending=False).head(15).copy()
                d15b['金額'] = d15b['值'].apply(lambda x: f"{int(x/100000000):,} 億")
                st.table(d15b[[0, 1, '金額']].rename(columns={0:'證券代號', 1:'證券名稱'}).reset_index(drop=True))

    with t3:
        st.markdown("""
        ### 📈 互動圖表：型態確認
        * **看均線：** 股價是否「帶量」穿過三條均線？
        * **看位置：** 買在突破盤整區的第一根 K 線，勝率最高。
        ---
        """)
        sid = st.text_input("🔍 代號", value="2330", key="chart_in")
        if st.button("📈 繪圖", use_container_width=True):
            tid = sid + ".TW" if "." not in sid else sid
            df = yf.Ticker(tid).history(period="1y"); df.dropna(subset=['Close'], inplace=True)
            if not df.empty:
                d = calculate_kd(df)
                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3])
                fig.add_trace(go.Candlestick(x=d.index, open=d['Open'], high=d['High'], low=d['Low'], close=d['Close'], name=tid), row=1, col=1)
                fig.add_trace(go.Scatter(x=d.index, y=d['K'], name='K', line=dict(color='yellow')), row=2, col=1)
                fig.add_trace(go.Scatter(x=d.index, y=d['D'], name='D', line=dict(color='cyan')), row=2, col=1)
                fig.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True)

    with t4:
        st.markdown("""
        ### 🛡️ 診斷儀表板：賣出紀律
        * **停損底線：** 跌破 20 日月線 = 趨勢毀掉，無條件離場。
        * **短線減碼：** 股價離 5 日線太遠或 KD 高檔死叉時，先獲利了結。
        ---
        """)
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
                else: st.error(f"**建議：** {r['建議']}")

# ==========================================
# 分頁 2: 🕵️‍♂️ 00981A 經理人跟單雷達
# ==========================================
elif main_page == "🕵️‍♂️ 00981A 經理人跟單雷達":
    st.title("🕵️‍♂️ 00981A 經理人跟單雷達 (雙引擎共振版)")
    st.markdown("""
    **💡 雙引擎共振策略**：
    我們不僅追蹤經理人「連續買進」的籌碼動向，系統還會自動呼叫【股神六星雷達】去檢驗這些標的。
    只要看到經理人狂買，且六星評等亮出 **4 顆星以上**，就是勝率極高的起漲點！
    """)
    
    col_info, col_btn = st.columns([3, 1])
    with col_info:
        st.info("🔄 系統每日比對籌碼變化，並在背景執行技術面六星掃描。")
    with col_btn:
        force_refresh = st.button("🔄 強制重新抓取今日籌碼", use_container_width=True)
    
    st.divider()
    st.subheader("🔥 經理人持股 × 六星技術面共振榜")
    
    # 執行籌碼分析
    raw_df = get_00981a_holdings_history(force_refresh=force_refresh)
    analyzed_df = analyze_manager_moves(raw_df)
    
    if not analyzed_df.empty:
        # 🚀 啟動六星聯動掃描引擎
        with st.spinner("⚡ 正在呼叫【股神六星雷達】進行技術面共振掃描..."):
            inst_map = get_inst_data()
            hot_list = get_hot_rank_ids()
            
            star_dict = {}
            with ThreadPoolExecutor(max_workers=5) as ex:
                # 針對經理人清單內的每一檔股票，送進六星雷達評分
                futs = {ex.submit(analyze_stock_score, str(t), inst_map, hot_list): t for t in analyzed_df['代號']}
                for f in as_completed(futs):
                    t = futs[f]
                    res = f.result()
                    # 如果有算出來，塞入星星；如果沒有(量不夠或均線不對)，則顯示休息
                    star_dict[t] = res['星等'] if res and res['星等'] != "休息" else "☁️ 盤整/休息"
            
            # 將算好的六星評等，精準插入到 dataframe 的第三個欄位
            analyzed_df.insert(2, '六星技術評等', analyzed_df['代號'].map(star_dict))
            
        # 顯示雙引擎共振表格
        st.dataframe(
            analyzed_df,
            use_container_width=True,
            hide_index=True,
            height=580, 
            column_config={
                "今日買賣超(張)": st.column_config.NumberColumn(
                    "今日買賣超(張)", help="正數代表買進，負數代表賣出", format="%d"
                ),
                "最新持股張數": st.column_config.NumberColumn(
                    "最新持股張數", format="%d"
                )
            }
        )
    else:
        st.warning("目前尚未收集到足夠的歷史資料，或今日 API 獲取失敗，請稍後再試。")
    
    st.divider()
    st.subheader("💡 實戰看盤訣竅")
    col1, col2 = st.columns(2)
    with col1:
        st.success("**🎯 必買黃金交叉**\n動向狀態為 **🟢 主力連買**，且旁邊的「六星技術評等」亮出 **⭐⭐⭐⭐ 以上**。這代表大人在買，且股價剛好帶量突破均線！")
    with col2:
        st.warning("**👀 伏擊區間**\n動向狀態為 **🟢 主力連買**，但技術評等顯示 **☁️ 盤整/休息**。這代表經理人正在「偷偷吃貨」但股價還沒發動，可先加入自選股觀察。")
