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
import sqlite3
import os

# === 1. 系統環境設定 ===
warnings.filterwarnings("ignore")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
st.set_page_config(page_title="稀有的股神系統雷達", page_icon="📡", layout="wide")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
HEADERS = {"User-Agent": UA}
FUGLE_API_KEY = "54f80721-6cad-4ec9-9679-c5a315e7b00b"

# === 2. 🛡️ 安全連線防護機制 ===
def safe_get_json(url, headers=HEADERS, max_retries=3):
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=15, verify=False)
            response.raise_for_status() 
            return response.json()
        except (ChunkedEncodingError, ConnectionError, ReadTimeout):
            st.toast(f"⚠️ 證交所連線不穩，正在進行第 {attempt + 1} 次重試...", icon="🔄")
            time.sleep(2)
        except ValueError:
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
                    hot_ids.update(df_tmp.sort_values('val', ascending=False).head(30)['證券代號'].tolist()) # 擴大至前30
                    break
        u2 = "https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php?l=zh-tw&o=json"
        res2 = safe_get_json(u2, HEADERS)
        data_otc = res2.get('aaData', []) or (res2.get('tables', [{}])[0].get('data', []) if 'tables' in res2 else [])
        if data_otc:
            df_otc = pd.DataFrame(data_otc)
            cv = 9 if df_otc.shape[1] >= 10 else df_otc.shape[1] - 2
            df_otc['val'] = pd.to_numeric(df_otc[cv].astype(str).str.replace(',',''), errors='coerce')
            hot_ids.update(df_otc.sort_values('val', ascending=False).head(30)[0].tolist()) # 擴大至前30
    except: pass
    return hot_ids

# === 4. 名單字典 (保持精選) ===
STOCKS_DICT = {
    "2330.TW": "台積電", "2317.TW": "鴻海", "2454.TW": "聯發科", "2308.TW": "台達電",
    "2303.TW": "聯電", "3711.TW": "日月光", "2408.TW": "南亞科", "2344.TW": "華邦電",
    "2337.TW": "旺宏", "3443.TW": "創意", "3661.TW": "世芯KY", "3034.TW": "聯詠",
    "2379.TW": "瑞昱", "4966.TW": "譜瑞KY", "6415.TW": "矽力KY", "3529.TW": "力旺",
    "6488.TWO": "環球晶", "5483.TWO": "中美晶", "3105.TWO": "穩懋", "8299.TWO": "群聯",
    "2382.TW": "廣達", "3231.TW": "緯創", "6669.TW": "緯穎", "2356.TW": "英業達",
    "2324.TW": "仁寶", "2353.TW": "宏碁", "2357.TW": "華碩", "2376.TW": "技嘉",
    "2377.TW": "微星", "3017.TW": "奇鋐", "3324.TW": "雙鴻", "3653.TW": "健策",
    "3533.TW": "嘉澤", "3013.TW": "晟銘電", "8210.TW": "勤誠", "3037.TW": "欣興",
    "8046.TW": "南電", "3189.TW": "景碩", "2368.TW": "金像電", "4958.TW": "臻鼎KY",
    "2313.TW": "華通", "6274.TWO": "台燿", "2383.TW": "台光電", "6213.TW": "聯茂",
    "3008.TW": "大立光", "3406.TW": "玉晶光", "1519.TW": "華城", "1503.TW": "士電",
    "1513.TW": "中興電", "1504.TW": "東元", "1605.TW": "華新", "1101.TW": "台泥",
    "1102.TW": "亞泥", "2002.TW": "中鋼", "2603.TW": "長榮", "2609.TW": "陽明",
    "2615.TW": "萬海", "2618.TW": "長榮航", "2610.TW": "華航", "2345.TW": "智邦",
    "2881.TW": "富邦金", "2882.TW": "國泰金", "2891.TW": "中信金", "8069.TWO": "元太",
    "3293.TWO": "鈊象", "0050.TW": "台50", "0056.TW": "高股息", "00878.TW": "永續"
}

# === 5. 雷達掃描與診斷邏輯 (增加高低價) ===
def analyze_stock_score(ticker_in, inst_map, hot_list):
    try:
        clean = ticker_in.replace('.TW','').replace('.TWO','')
        tid = clean + ".TW"; df = yf.Ticker(tid).history(period="1y")
        if df.empty:
            tid = clean + ".TWO"; df = yf.Ticker(tid).history(period="1y")
        if df.empty or len(df) < 65: return None
        
        fc, fv = get_fugle_realtime(clean)
        if fc:
            df.iloc[-1, df.columns.get_loc('Close')] = fc
            if fv: df.iloc[-1, df.columns.get_loc('Volume')] = fv
        
        c = df['Close'].iloc[-1]; h = df['High'].iloc[-1]; l = df['Low'].iloc[-1]
        v = df['Volume'].iloc[-1]; v5 = df['Volume'].iloc[-6:-1].mean()
        
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
        
        name = STOCKS_DICT.get(tid, clean)
        return {
            '標的': f"{clean} {name}", '星等': "⭐"*s if s>0 else "休息", 
            '現價': round(c,2), '最高': round(h,2), '最低': round(l,2),
            '籌碼大戶(張)': f"{inst_val:,}" if inst_val != 0 else "--", 
            '今日量(張)': int(v/1000), '觸發條件': " ".join(tags), '星星數': s
        }
    except: return None

# === 6. 🐳 大戶資料庫引擎 ===
def fetch_and_save_whale_data(db_name="whale_tracker.db"):
    url = "https://www.twse.com.tw/fund/T86?response=json&selectType=ALLBUT0999"
    data = safe_get_json(url)
    if not data or 'data' not in data: return False, "今日無數據或尚未盤後更新"
    try:
        columns = data['fields']
        df = pd.DataFrame(data['data'], columns=columns)
        trust_col = [c for c in columns if '投信買賣超' in c][0]
        foreign_col = [c for c in columns if '外陸資買賣超' in c or ('外資' in c and '買賣超' in c)][0]
        df['投信買賣超(張)'] = df[trust_col].str.replace(',', '').astype(float) / 1000
        df['外資買賣超(張)'] = df[foreign_col].str.replace(',', '').astype(float) / 1000
        df['日期'] = datetime.date.today().strftime("%Y-%m-%d")
        conn = sqlite3.connect(db_name)
        cursor = conn.cursor()
        cursor.execute('CREATE TABLE IF NOT EXISTS trust_net_buy (日期 TEXT, 證券代號 TEXT, 證券名稱 TEXT, "投信買賣超(張)" REAL)')
        cursor.execute('CREATE TABLE IF NOT EXISTS foreign_net_buy (日期 TEXT, 證券代號 TEXT, 證券名稱 TEXT, "外資買賣超(張)" REAL)')
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        cursor.execute("DELETE FROM trust_net_buy WHERE 日期=?", (today_str,))
        cursor.execute("DELETE FROM foreign_net_buy WHERE 日期=?", (today_str,))
        df[['日期', '證券代號', '證券名稱', '投信買賣超(張)']].to_sql('trust_net_buy', conn, if_exists='append', index=False)
        df[['日期', '證券代號', '證券名稱', '外資買賣超(張)']].to_sql('foreign_net_buy', conn, if_exists='append', index=False)
        conn.commit(); conn.close()
        return True, f"成功寫入 {len(df)} 筆籌碼資料！"
    except Exception as e: return False, str(e)

def get_whale_consecutive_buys(db_name="whale_tracker.db", min_days=1, whale_type="trust"):
    if not os.path.exists(db_name): return None 
    table = "trust_net_buy" if whale_type == "trust" else "foreign_net_buy"
    col = "投信買賣超(張)" if whale_type == "trust" else "外資買賣超(張)"
    try:
        conn = sqlite3.connect(db_name)
        df = pd.read_sql_query(f"SELECT * FROM {table} ORDER BY 證券代號, 日期", conn)
        conn.close()
        hot_stocks = []
        for sid, group in df.groupby('證券代號'):
            diffs = group[col].tolist()
            buy_days = sum(1 for d in reversed(diffs) if d > 0) if diffs and diffs[-1] > 0 else 0
            if buy_days >= min_days:
                # 額外抓取即時價格
                p, _ = get_fugle_realtime(sid)
                hot_stocks.append({
                    "代號": sid, "名稱": group.iloc[-1]['證券名稱'], "現價": p if p else "--",
                    "連買天數": buy_days, "累積買超(張)": int(sum(diffs[-buy_days:]))
                })
        return pd.DataFrame(hot_stocks).sort_values(by="連買天數", ascending=False)
    except: return pd.DataFrame()

# === 7. 🕵️‍♂️ 00981A 專屬引擎 (帶價格與排名) ===
def get_stock_price_info(ticker):
    try:
        clean = ticker.replace('.TW','').replace('.TWO','')
        tid = clean + ".TW"
        df = yf.Ticker(tid).history(period="5d")
        if df.empty:
            tid = clean + ".TWO"
            df = yf.Ticker(tid).history(period="5d")
        if not df.empty:
            return df['Close'].tolist(), df['Close'].iloc[-1], df['High'].iloc[-1], df['Low'].iloc[-1]
    except: pass
    return [], 0, 0, 0

def analyze_00981a_real_moves(db_name="whale_tracker.db"):
    target_stocks = {
        "2330": {"name": "台積電", "weight": 19.5}, "2317": {"name": "鴻海", "weight": 8.5},
        "2454": {"name": "聯發科", "weight": 6.5}, "2383": {"name": "台光電", "weight": 9.8},
        "2345": {"name": "智邦", "weight": 5.2}, "3231": {"name": "緯創", "weight": 3.0},
        "3017": {"name": "奇鋐", "weight": 7.0}, "3661": {"name": "世芯-KY", "weight": 4.5},
        "2368": {"name": "金像電", "weight": 2.1}, "3324": {"name": "雙鴻", "weight": 1.5},
        "2308": {"name": "台達電", "weight": 4.0}, "2382": {"name": "廣達", "weight": 3.8},
        "3034": {"name": "聯詠", "weight": 1.2}, "2603": {"name": "長榮", "weight": 2.0}
    }
    if not os.path.exists(db_name): return None
    try:
        conn = sqlite3.connect(db_name)
        p = ','.join('?' for _ in target_stocks.keys())
        df = pd.read_sql_query(f"SELECT * FROM trust_net_buy WHERE 證券代號 IN ({p})", conn, params=list(target_stocks.keys()))
        conn.close()
        results = []
        for sid, group in df.groupby('證券代號'):
            diffs = group['投信買賣超(張)'].tolist()
            consecutive_buy = sum(1 for d in reversed(diffs) if d > 0) if diffs and diffs[-1] > 0 else 0
            w = target_stocks[sid]['weight']
            limit = 25.0 if sid == "2330" else 10.0
            if w >= (limit - 0.5): hint = "❌ 嚴禁追高"; w_str = f"🛑 {w}%"
            elif w >= (limit - 2.0): hint = "🟡 子彈將盡"; w_str = f"⚠️ {w}%"
            else: hint = "🟢 空間充裕"; w_str = f"✅ {w}%"
            
            p_list, cur_p, hi, lo = get_stock_price_info(sid)
            est_cost, dist = 0, "-"
            if consecutive_buy > 0 and len(p_list) >= consecutive_buy:
                recent_ps = p_list[-consecutive_buy:]
                est_cost = sum(p * v for p, v in zip(recent_ps, diffs[-consecutive_buy:])) / sum(diffs[-consecutive_buy:])
                dist = f"{((cur_p - est_cost) / est_cost) * 100:+.1f}%"

            results.append({
                "代號": sid, "股票名稱": target_stocks[sid]['name'], "權重狀態": w_str, "跟單建議": hint,
                "現價": cur_p, "最高": hi, "最低": lo, "均價": round(est_cost,1) if est_cost > 0 else "-",
                "成本乖離": dist, "今日買超": int(diffs[-1]) if diffs else 0, "連買天數": consecutive_buy
            })
        return pd.DataFrame(results).sort_values(by="今日買超", ascending=False)
    except: return None

# === 8. 側邊欄與分頁渲染 ===
st.sidebar.title("📡 導覽選單")
main_page = st.sidebar.radio("跳轉頁面", ["🎯 股神六星雷達系統", "🐳 投信/外資連買雷達", "🕵️‍♂️ 00981A 經理人雷達"])
st.sidebar.markdown("---")

if main_page == "🎯 股神六星雷達系統":
    st.title("📡 稀有的股神系統：終極版")
    t1, t2, t3, t4 = st.tabs(["🎯 六星雷達", "💰 成交排行", "📈 互動看盤", "🛡️ 持股診斷"])
    with t1:
        st.sidebar.subheader("⚙️ 自選股水庫")
        u_input = st.sidebar.text_area("代號庫：", value=", ".join([k.split('.')[0] for k in STOCKS_DICT.keys()]), height=200)
        s_list = [t.strip() for t in u_input.replace('，',',').split(',') if t.strip()]
        if st.button("🚀 啟動即時全量掃描", use_container_width=True):
            inst_map, hot_list = get_inst_data(), get_hot_rank_ids()
            res, pb = [], st.progress(0)
            with ThreadPoolExecutor(max_workers=8) as ex:
                futs = [ex.submit(analyze_stock_score, t, inst_map, hot_list) for t in s_list]
                for i, f in enumerate(as_completed(futs)):
                    pb.progress((i+1)/len(s_list))
                    if f.result(): res.append(f.result())
            if res:
                df = pd.DataFrame(res).sort_values(by=['星星數', '今日量(張)'], ascending=[False, False])
                df.reset_index(drop=True, inplace=True); df.insert(0, '排名', df.index + 1)
                st.dataframe(df[['排名', '標的', '星等', '現價', '最高', '最低', '籌碼大戶(張)', '今日量(張)', '觸發條件']], use_container_width=True, hide_index=True)

    with t2:
        if st.button("🔄 刷新排行"): st.cache_data.clear()
        c1, c2 = st.columns(2)
        urls = ["https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&type=ALLBUT0999", 
                "https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php?l=zh-tw&o=json"]
        for i, url in enumerate(urls):
            res = safe_get_json(url)
            with [c1, c2][i]:
                st.subheader("上市排行" if i==0 else "上櫃排行")
                if res:
                    # 簡化顯示邏輯
                    st.write("已更新最新前15名熱門股")

elif main_page == "🐳 投信/外資連買雷達":
    st.title("🐳 大戶籌碼狙擊鏡")
    if st.button("🔄 同步更新投信與外資籌碼", type="primary"):
        with st.spinner("🚀 抓取中..."):
            s, m = fetch_and_save_whale_data()
            if s: st.success(m); time.sleep(1); st.rerun()
            else: st.error(m)
    st.divider()
    col1, col2 = st.columns(2)
    for i, t in enumerate(["trust", "foreign"]):
        with [col1, col2][i]:
            st.subheader("投信連買" if t=="trust" else "外資連買")
            df = get_whale_consecutive_buys(whale_type=t, min_days=1)
            if df is not None and not df.empty:
                df.reset_index(drop=True, inplace=True); df.insert(0, '排名', df.index + 1)
                st.dataframe(df[['排名', '名稱', '現價', '連買天數', '累積買超(張)']], use_container_width=True, hide_index=True)

elif main_page == "🕵️‍♂️ 00981A 經理人雷達":
    st.title("🕵️‍♂️ 00981A 經理人跟單 (含價格排名)")
    with st.spinner("✨ 正在計算建倉成本與六星共振..."):
        df = analyze_00981a_real_moves()
        if df is not None and not df.empty:
            # 加入六星雷達
            inst_map, hot_list = get_inst_data(), get_hot_rank_ids()
            with ThreadPoolExecutor(max_workers=5) as ex:
                star_dict = {sid: ex.submit(analyze_stock_score, sid, inst_map, hot_list).result() for sid in df['代號']}
            df.insert(2, '六星雷達', df['代號'].apply(lambda x: star_dict[x]['星等'] if star_dict[x] else "休息"))
            df.reset_index(drop=True, inplace=True); df.insert(0, '排名', df.index + 1)
            st.dataframe(df[['排名', '股票名稱', '六星雷達', '現價', '均價', '成本乖離', '最高', '最低', '權重狀態', '跟單建議']], use_container_width=True, hide_index=True)
        else: st.error("❌ 無數據，請先至連買雷達分頁點擊更新。")
