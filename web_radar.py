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
st.set_page_config(page_title="老魯-股神戰情系統", page_icon="📡", layout="wide")

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
        except:
            time.sleep(2)
    return {}

# === 3. 核心計算函數 ===
def calculate_kd(df):
    if len(df) < 9: return df
    df['9_min'] = df['Low'].rolling(window=9).min()
    df['9_max'] = df['High'].rolling(window=9).max()
    df['RSV'] = (df['Close'] - df['9_min']) / (df['9_max'] - df['9_min']) * 100
    k_v, d_v, k, d = [], [], 50.0, 50.0
    for rsv in df['RSV']:
        if pd.isna(rsv): k_v.append(50.0); d_v.append(50.0)
        else:
            k = (2/3) * k + (1/3) * rsv
            d = (2/3) * d + (1/3) * k
            k_v.append(k); d_v.append(d)
    df['K'], df['D'] = k_v, d_v
    return df

def get_stock_price_info(ticker):
    """取得歷史價格(算成本)與即時價格資訊"""
    try:
        clean = ticker.replace('.TW','').replace('.TWO','')
        tid = clean + ".TW"
        df = yf.Ticker(tid).history(period="15d")
        if df.empty:
            tid = clean + ".TWO"
            df = yf.Ticker(tid).history(period="15d")
        if not df.empty:
            return df['Close'].tolist(), df['Close'].iloc[-1], df['High'].iloc[-1], df['Low'].iloc[-1]
    except: pass
    return [], 0, 0, 0

def analyze_stock_score(ticker_in, inst_map=None, hot_list=None):
    try:
        inst_map = inst_map or {}
        hot_list = hot_list or []
        clean = ticker_in.replace('.TW','').replace('.TWO','')
        tid = clean + ".TW"
        df = yf.Ticker(tid).history(period="65d")
        if df.empty: tid = clean + ".TWO"; df = yf.Ticker(tid).history(period="65d")
        if df.empty or len(df) < 20: return None
        
        c = df['Close'].iloc[-1]
        df['MA5'] = df['Close'].rolling(5).mean(); df['MA20'] = df['Close'].rolling(20).mean(); df['MA60'] = df['Close'].rolling(60).mean()
        df = calculate_kd(df)
        
        s = 0
        if c > df['MA5'].iloc[-1] > df['MA20'].iloc[-1] > df['MA60'].iloc[-1]: s+=1
        if df['MA20'].iloc[-1] > df['MA20'].iloc[-2]: s+=1
        if df['K'].iloc[-1] > df['D'].iloc[-1] and df['K'].iloc[-2] <= df['D'].iloc[-2]: s+=1
        if c > df['High'].iloc[-21:-1].max(): s+=1
        if inst_map.get(clean, 0) > 500: s+=1
        if s >= 4: s+=1 # 強勢加成
        
        return {"星等": "⭐"*s if s>0 else "休息", "星星數": s}
    except: return None

# === 4. 🐳 大戶爬蟲引擎 (投信+外資同步) ===
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
        
        today = datetime.date.today().strftime("%Y-%m-%d")
        cursor.execute("DELETE FROM trust_net_buy WHERE 日期=?", (today,))
        cursor.execute("DELETE FROM foreign_net_buy WHERE 日期=?", (today,))
        
        df[['日期', '證券代號', '證券名稱', '投信買賣超(張)']].to_sql('trust_net_buy', conn, if_exists='append', index=False)
        df[['日期', '證券代號', '證券名稱', '外資買賣超(張)']].to_sql('foreign_net_buy', conn, if_exists='append', index=False)
        conn.commit(); conn.close()
        return True, f"成功更新 {len(df)} 筆籌碼數據！"
    except Exception as e: return False, str(e)

# === 5. 🕵️‍♂️ 00981A 全成分股真實分析引擎 ===
def analyze_00981a_full_list(db_name="whale_tracker.db"):
    # 00981A 全成分股名單 (代號: (名稱, 預估權重))
    target_stocks = {
        "2330": ("台積電", 19.8), "2317": ("鴻海", 9.2), "2454": ("聯發科", 7.5), "2383": ("台光電", 6.8),
        "2345": ("智邦", 5.5), "3017": ("奇鋐", 5.2), "3324": ("雙鴻", 4.8), "6669": ("緯穎", 4.2),
        "3231": ("緯創", 3.8), "2382": ("廣達", 3.5), "3037": ("欣興", 3.2), "3533": ("嘉澤", 2.9),
        "2368": ("金像電", 2.5), "3661": ("世芯-KY", 2.2), "2308": ("台達電", 2.0), "3034": ("聯詠", 1.8),
        "2603": ("長榮", 1.5), "3711": ("日月光", 1.4), "3008": ("大立光", 1.2), "3406": ("玉晶光", 1.1),
        "6274": ("台燿", 1.0), "6213": ("聯茂", 0.9), "4966": ("譜瑞-KY", 0.8), "8046": ("南電", 0.7),
        "2408": ("南亞科", 0.6), "2303": ("聯電", 0.5), "2357": ("華碩", 0.5), "1513": ("中興電", 0.4),
        "1519": ("華城", 0.4), "2356": ("英業達", 0.3), "2324": ("仁寶", 0.3), "6789": ("采鈺", 0.2),
        "6147": ("頎邦", 0.2), "3016": ("嘉晶", 0.1), "2449": ("京元電", 0.1), "2379": ("瑞昱", 0.1)
    }

    if not os.path.exists(db_name): return None

    try:
        conn = sqlite3.connect(db_name)
        p = ','.join('?' for _ in target_stocks.keys())
        df_trust = pd.read_sql_query(f"SELECT * FROM trust_net_buy WHERE 證券代號 IN ({p})", conn, params=list(target_stocks.keys()))
        conn.close()

        if df_trust.empty: return pd.DataFrame()

        results = []
        for sid, group in df_trust.groupby('證券代號'):
            group = group.sort_values('日期')
            diffs = group['投信買賣超(張)'].tolist()
            con_buy = 0
            for d in reversed(diffs):
                if d > 0: con_buy += 1
                else: break
            
            p_list, cur_p, hi, lo = get_stock_price_info(sid)
            est_cost, dist_str = 0.0, "-"
            if con_buy > 0 and len(p_list) >= con_buy:
                buy_vols = diffs[-con_buy:]
                recent_ps = p_list[-con_buy:]
                if sum(buy_vols) > 0:
                    est_cost = sum(p * v for p, v in zip(recent_ps, buy_vols)) / sum(buy_vols)
                    dist_str = f"{((cur_p - est_cost) / est_cost) * 100:+.1f}%"

            # 權重警示
            w = target_stocks[sid][1]
            limit = 25.0 if sid == "2330" else 10.0
            if w >= (limit - 0.5): hint = "❌ 嚴禁追高"; w_str = f"🛑 {w}%"
            elif w >= (limit - 2.0): hint = "🟡 子彈將盡"; w_str = f"⚠️ {w}%"
            else: hint = "🟢 空間充裕"; w_str = f"✅ {w}%"

            results.append({
                "代號": sid, "股票名稱": target_stocks[sid][0], 
                "權重狀態": w_str, "跟單建議": hint,
                "現價": cur_p, "最高": hi, "最低": lo,
                "均價": round(est_cost, 1) if est_cost > 0 else "-",
                "成本乖離": dist_str, "今日買超": int(diffs[-1]) if diffs else 0, "連買天數": con_buy
            })
        
        # 排名邏輯：連買天數 > 今日買超量 > 權重
        return pd.DataFrame(results).sort_values(by=["連買天數", "今日買超"], ascending=[False, False])
    except: return None

# === 6. 側邊欄與頁面渲染 ===
st.sidebar.title("📡 老魯-股神戰情室")
main_page = st.sidebar.radio("跳轉頁面", ["🕵️‍♂️ 00981A 經理人跟單 (全名單)", "🎯 股神六星雷達系統", "🐳 投信/外資連買雷達"])
st.sidebar.markdown("---")

if main_page == "🕵️‍♂️ 00981A 經理人跟單 (全名單)":
    st.title("🕵️‍♂️ 00981A 經理人跟單雷達 (全真實數據)")
    st.markdown("同步 00981A **36 檔全成分股**，透視大戶成本、連買天數與六星技術指標。")
    
    if st.button("🚀 啟動全成分股即時分析", use_container_width=True):
        with st.spinner("✨ 正在同步真實籌碼、計算 VWAP 均價並掃描六星雷達 (約需 5-8 秒)..."):
            df = analyze_00981a_full_list()
            if df is not None and not df.empty:
                # 串接六星雷達 (多執行緒加速)
                with ThreadPoolExecutor(max_workers=10) as ex:
                    star_dict = {sid: ex.submit(analyze_stock_score, sid).result() for sid in df['代號']}
                
                df.insert(2, '六星雷達', df['代號'].apply(lambda x: star_dict[x]['星等'] if star_dict[x] else "休息"))
                df.reset_index(drop=True, inplace=True); df.insert(0, '排名', df.index + 1)
                
                st.dataframe(
                    df[['排名', '股票名稱', '六星雷達', '現價', '最高', '最低', '均價', '成本乖離', '連買天數', '今日買超', '權重狀態', '跟單建議']], 
                    use_container_width=True, hide_index=True, height=800
                )
            else:
                st.error("❌ 找不到資料庫！請先到「投信/外資連買雷達」分頁更新籌碼。")

elif main_page == "🎯 股神六星雷達系統":
    st.title("🎯 股神六星掃描儀")
    st.sidebar.subheader("⚙️ 自選股水庫")
    u_input = st.sidebar.text_area("代號庫 (逗號分隔)：", value="2330, 2317, 2454, 2383, 2345, 3017, 3324, 6669, 3231, 2382, 3037, 3533, 1513, 1519, 2603", height=200)
    s_list = [t.strip() for t in u_input.replace('，',',').split(',') if t.strip()]

    if st.button("🚀 啟動掃描", use_container_width=True):
        inst_map = {} # 簡化
        res, pb = [], st.progress(0)
        with ThreadPoolExecutor(max_workers=8) as ex:
            futs = [ex.submit(analyze_stock_score, t, inst_map) for t in s_list]
            for i, f in enumerate(as_completed(futs)):
                pb.progress((i+1)/len(s_list))
                if f.result(): 
                    res_data = f.result()
                    res_data['代號'] = s_list[i]
                    res.append(res_data)
        if res:
            df_res = pd.DataFrame(res).sort_values(by="星星數", ascending=False)
            df_res.reset_index(drop=True, inplace=True); df_res.insert(0, '排名', df_res.index + 1)
            st.dataframe(df_res[['排名', '代號', '星等', '星星數']], use_container_width=True, hide_index=True)

elif main_page == "🐳 投信/外資連買雷達":
    st.title("🐳 大戶籌碼資料同步中心")
    st.warning("⚠️ 請在每日下午 4:00 證交所公布資料後執行更新。")
    if st.button("🔥 同步更新投信與外資籌碼", type="primary", use_container_width=True):
        with st.spinner("🚀 連線證交所中..."):
            success, msg = fetch_and_save_whale_data()
            if success:
                st.success(msg); time.sleep(1); st.rerun()
            else:
                st.error(f"更新失敗：{msg}")
