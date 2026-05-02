import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
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

# === 2. 🛡️ 安全連線防護機制 (無 UI 快取衝突版) ===
def safe_get_json(url, headers, max_retries=3):
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=15, verify=False)
            response.raise_for_status() 
            return response.json()
        except (ChunkedEncodingError, ConnectionError, ReadTimeout) as e:
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

def fetch_fast_price(symbol):
    fc, _ = get_fugle_realtime(str(symbol))
    if fc: return fc
    try:
        df = yf.Ticker(f"{symbol}.TW").history(period="1d")
        if not df.empty: return round(df['Close'].iloc[-1], 2)
        df = yf.Ticker(f"{symbol}.TWO").history(period="1d")
        if not df.empty: return round(df['Close'].iloc[-1], 2)
    except: pass
    return "---"

def estimate_vwap(symbol, days):
    """計算主力連買期間的推估成本 (VWAP)"""
    if days <= 0 or not isinstance(days, int): return "---"
    try:
        df = yf.Ticker(f"{symbol}.TW").history(period="1mo")
        if df.empty: df = yf.Ticker(f"{symbol}.TWO").history(period="1mo")
        if len(df) >= days:
            recent = df.tail(days)
            vwap = (recent['Close'] * recent['Volume']).sum() / recent['Volume'].sum()
            return round(vwap, 2)
    except: pass
    return "---"

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

# === 4. 名單字典與產業族群對照表 ===
STOCKS_DICT = {
    "2330.TW": "台積電", "2317.TW": "鴻海", "2454.TW": "聯發科", "2308.TW": "台達電",
    "3231.TW": "緯創", "2383.TW": "台光電", "2368.TW": "金像電", "3017.TW": "奇鋐",
    "2345.TW": "智邦", "3533.TW": "嘉澤", "3324.TW": "雙鴻", "2382.TW": "廣達",
    "3034.TW": "聯詠", "2603.TW": "長榮", "3661.TW": "世芯-KY", "6805.TW": "富世達"
}

SECTOR_MAP = {
    "2330": "半導體", "2454": "半導體", "3661": "半導體", "3034": "半導體",
    "2317": "AI伺服器", "3231": "AI伺服器", "2382": "AI伺服器",
    "3017": "散熱模組", "3324": "散熱模組", "6805": "軸承",
    "2383": "PCB零組件", "2368": "PCB零組件", "3533": "連接器",
    "2308": "電源供應", "2345": "網通", "2603": "航運"
}

# === 5. 雷達掃描與診斷邏輯 (加入處置警戒算法) ===
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
        
        # 🚨 處置股預判演算法：5日漲幅 > 25% 或 月線乖離 > 30%
        return_5d = (c / df['Close'].iloc[-6]) - 1 if len(df) >= 6 else 0
        bias_20 = (c / df['MA20'].iloc[-1]) - 1
        is_warning = return_5d > 0.25 or bias_20 > 0.30
        
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
        if is_warning: tags.append("🚨[處置警戒]")
        
        inst_display = f"{inst_val:,}" if inst_val != 0 else "--"
        name = STOCKS_DICT.get(tid, clean)
        
        return {
            '標的': f"{clean} {name}", 
            '星等': "⭐"*s if s>0 else "休息", 
            '收盤': round(c,2), 
            '籌碼大戶(張)': inst_display, 
            '今日量(張)': int(v/1000), 
            '觸發條件': " ".join(tags), 
            '星星數': s,
            '處置風險': "⚠️ 高風險 (短線過熱)" if is_warning else "✅ 安全"
        }
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
    if res and 'data' in res and len(res['data']) > 0:
        for row in res['data']:
            ticker = str(row[0]).strip()
            name = str(row[1]).strip()
            shares = int(row[2].replace(',', '')) // 1000 
            new_data.append([today, ticker, name, shares])
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
        
        # 加入一檔「飆股」來測試處置警戒 (富世達)
        mock_scenarios = [
            ("2317", "鴻海", [1000, 1500, 2000, 3000]),
            ("3231", "緯創", [2000, 2000, 2000, 3500]),
            ("2383", "台光電", [3000, 3000, 3500, 4200]),
            ("6805", "富世達", [200, 400, 800, 1500]), # 模擬飆股
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
    if df.empty: return pd.DataFrame()
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
            "連續天數": days,
            "連續天數顯示": f"{days} 天" if days > 0 else "-"
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
    st.title("📡 稀有的股神系統：終極大滿配")
    t1, t2, t3, t4, t5 = st.tabs(["🎯 六星雷達", "💰 成交排行", "📈 互動看盤", "🛡️ 智能部位診斷", "🚨 處置警戒清單"])
    
    with t1:
        st.markdown("### 🎯 買進策略：共振發動")
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
                # 將處置風險獨立顯示提醒
                st.dataframe(df[['標的', '星等', '收盤', '處置風險', '籌碼大戶(張)', '今日量(張)', '觸發條件']], use_container_width=True)

    with t2:
        st.markdown("### 💰 量能先行：主力足跡")
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
        st.markdown("### 📈 互動圖表：型態確認")
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
        st.markdown("### 🛡️ 智能部位計算機與紀律診斷")
        col_diag, col_calc = st.columns([1, 1])
        with col_diag:
            d_id = st.text_input("🔍 欲買進標的代號", value="2317", key="diag_in")
        with col_calc:
            capital = st.number_input("💰 本次預計投入總資金 (台幣)", value=500000, step=50000)
            risk_pct = st.slider("⚖️ 單筆可承受最大虧損比例 (%)", 1.0, 5.0, 2.0, 0.5)

        if st.button("🛡️ 執行診斷與資金計算", use_container_width=True):
            r = diagnose_holding(d_id)
            if r:
                st.markdown(f"### 🎯 {r['標的']} 戰情室")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("即時價", r['收盤']); c2.metric("5日線", r['MA5'])
                c3.metric("月線 (防守點)", r['MA20']); c4.metric("KD狀態", r['KD'])
                
                price = r['收盤']
                stop_loss = r['MA20']
                
                if price <= stop_loss:
                    st.error("⚠️ **目前股價已低於月線，趨勢轉弱，強烈建議不要買進！**")
                else:
                    risk_per_share = price - stop_loss
                    max_loss_amount = capital * (risk_pct / 100)
                    suggested_shares = max_loss_amount / (risk_per_share * 1000)
                    
                    st.success(f"**趨勢狀況：** {r['狀況']}")
                    st.info(f"""
                    #### 🤖 系統建議買進張數： **{max(1, int(suggested_shares))} 張**
                    * **操作紀律**：買進後，若未來收盤跌破月線 ({stop_loss}) 請無條件停損。
                    * **風控說明**：在此紀律下，就算看錯停損，您的最大虧損將被控制在 **{max_loss_amount:,.0f} 元** 左右，不會傷及筋骨！
                    """)

    with t5:
        st.markdown("""
        ### 🚨 處置/注意警戒清單 (多頭陷阱迴避)
        * **法規預判：** 系統自動抓出「5日漲幅 > 25%」或「乖離月線 > 30%」的飆股。
        * **實戰紀律：** 這些股票隨時會被證交所「關緊閉 (處置)」，買盤容易急凍。**看到請忍住，嚴禁追高！**
        ---
        """)
        if st.button("⚠️ 掃描全市場過熱標的", use_container_width=True):
            inst_map = get_inst_data()
            hot_list = get_hot_rank_ids()
            danger_list = []
            pb = st.progress(0)
            
            with ThreadPoolExecutor(max_workers=5) as ex:
                futs = [ex.submit(analyze_stock_score, t, inst_map, hot_list) for t in s_list]
                for i, f in enumerate(as_completed(futs)):
                    pb.progress((i+1)/len(s_list))
                    res = f.result()
                    # 只抓出被標記為處置警戒的股票
                    if res and "處置警戒" in res['觸發條件']:
                        danger_list.append(res)
            
            if danger_list:
                df_danger = pd.DataFrame(danger_list)
                st.error(f"🚨 **發現 {len(df_danger)} 檔短線過熱標的，隨時面臨處置風險！**")
                st.dataframe(df_danger[['標的', '收盤', '處置風險', '觸發條件']], use_container_width=True)
            else:
                st.success("✅ 目前自選庫中沒有面臨處置風險的過熱標的。")

# ==========================================
# 分頁 2: 🕵️‍♂️ 00981A 經理人跟單雷達
# ==========================================
elif main_page == "🕵️‍♂️ 00981A 經理人跟單雷達":
    st.title("🕵️‍♂️ 00981A 經理人跟單雷達 (大滿配防護版)")
    
    force_refresh = st.button("🔄 強制重新抓取今日籌碼")
    
    raw_df = get_00981a_holdings_history(force_refresh=force_refresh)
    analyzed_df = analyze_manager_moves(raw_df)
    
    if not analyzed_df.empty:
        with st.spinner("⚡ 正在獲取最新股價、計算主力成本，並進行處置風險判定..."):
            inst_map = get_inst_data()
            hot_list = get_hot_rank_ids()
            
            star_dict, price_dict, vwap_dict, warning_dict = {}, {}, {}, {}
            
            with ThreadPoolExecutor(max_workers=8) as ex:
                futs = {ex.submit(analyze_stock_score, str(row['代號']), inst_map, hot_list): row['代號'] for _, row in analyzed_df.iterrows()}
                for f in as_completed(futs):
                    t = futs[f]
                    res = f.result()
                    if res:
                        star_dict[t] = res['星等'] if res['星等'] != "休息" else "☁️ 盤整/休息"
                        price_dict[t] = res['收盤']
                        warning_dict[t] = res.get('處置風險', "✅ 安全")
                    else:
                        star_dict[t] = "☁️ 盤整/休息"
                        price_dict[t] = fetch_fast_price(t)
                        warning_dict[t] = "✅ 安全" # 歷史不足暫不列警戒
            
            for _, row in analyzed_df.iterrows():
                if row['動向狀態'] == "🟢 主力連買":
                    vwap_dict[row['代號']] = estimate_vwap(row['代號'], row['連續天數'])
                else:
                    vwap_dict[row['代號']] = "---"
            
            analyzed_df.insert(2, '最新收盤價', analyzed_df['代號'].map(price_dict))
            analyzed_df.insert(3, '主力推估成本', analyzed_df['代號'].map(vwap_dict))
            analyzed_df.insert(4, '處置風險', analyzed_df['代號'].map(warning_dict))
            analyzed_df.insert(5, '六星技術評等', analyzed_df['代號'].map(star_dict))
            analyzed_df['產業族群'] = analyzed_df['代號'].map(SECTOR_MAP).fillna("其他/未分類")

        # 🗺️ 資金熱力圖
        st.subheader("🗺️ 資金熱力圖 (主力買賣板塊)")
        try:
            heat_df = analyzed_df[analyzed_df['今日買賣超(張)'] != 0].copy()
            if not heat_df.empty:
                fig = px.treemap(
                    heat_df, 
                    path=[px.Constant("全市場動向"), '產業族群', '股票名稱'],
                    values=heat_df['今日買賣超(張)'].abs(),
                    color='今日買賣超(張)', 
                    color_continuous_scale='RdYlGn',
                    color_continuous_midpoint=0,
                    title="板塊面積大小代表張數，綠色代表買進，紅色代表賣出"
                )
                fig.update_traces(textinfo="label+value")
                st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            st.error("熱力圖生成失敗")

        # 📊 戰情總覽
        st.divider()
        st.subheader("📊 盤面戰情總覽")
        buy_count = analyzed_df[analyzed_df['動向狀態'].str.contains('買')].shape[0]
        sell_count = analyzed_df[analyzed_df['動向狀態'].str.contains('倒貨|賣')].shape[0]
        star_count = analyzed_df[(analyzed_df['動向狀態'].str.contains('買')) & (analyzed_df['六星技術評等'].str.count('⭐') >= 4)].shape[0]
        danger_count = analyzed_df[analyzed_df['處置風險'].str.contains('高風險')].shape[0]
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("🔥 主力連買標的", f"{buy_count} 檔")
        m2.metric("🧊 經理人倒貨標的", f"{sell_count} 檔")
        m3.metric("⭐ 雙引擎共振標的", f"{star_count} 檔")
        m4.metric("🚨 處置高風險標的", f"{danger_count} 檔", help="即將面臨處置關緊閉，禁止追高！")
        
        st.divider()
        st.subheader("🔥 經理人持股 × 成本防護 × 雙引擎共振榜")
        
        display_df = analyzed_df.drop(columns=['連續天數', '產業族群'])
        display_df = display_df.rename(columns={'連續天數顯示': '連續天數'})
        
        # 使用 Styler 讓表格中的高風險變紅色，安全變綠色
        def highlight_danger(val):
            if isinstance(val, str) and '高風險' in val: return 'color: red; font-weight: bold'
            elif isinstance(val, str) and '安全' in val: return 'color: green'
            return ''
            
        styled_df = display_df.style.map(highlight_danger, subset=['處置風險'])
        
        st.dataframe(
            styled_df,
            use_container_width=True,
            hide_index=True,
            height=580, 
            column_config={
                "今日買賣超(張)": st.column_config.NumberColumn("今日買賣超(張)", format="%d"),
                "最新持股張數": st.column_config.NumberColumn("最新持股張數", format="%d")
            }
        )
    else:
        st.warning("目前尚未收集到足夠的歷史資料，或今日 API 獲取失敗，請稍後再試。")
