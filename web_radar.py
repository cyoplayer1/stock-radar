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
import sqlite3
import os

# === 1. 系統環境設定 ===
warnings.filterwarnings("ignore")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
st.set_page_config(page_title="稀有的老魯股神系統", page_icon="📡", layout="wide")

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

# === 2. 🛡️ 核心名稱字典 (確保股名顯示) ===
STOCKS_DICT = {
    "2330": "台積電", "2317": "鴻海", "2454": "聯發科", "2308": "台達電", "2303": "聯電", 
    "3711": "日月光", "2408": "南亞科", "3443": "創意", "3661": "世芯-KY", "3034": "聯詠",
    "2379": "瑞昱", "2382": "廣達", "3231": "緯創", "6669": "緯穎", "2356": "英業達",
    "2324": "仁寶", "2353": "宏碁", "2357": "華碩", "2376": "技嘉", "3017": "奇鋐", 
    "3324": "雙鴻", "3653": "健策", "3533": "嘉澤", "3013": "晟銘電", "8210": "勤誠", 
    "3037": "欣興", "8046": "南電", "2368": "金像電", "4958": "臻鼎KY", "2313": "華通", 
    "6274": "台燿", "2383": "台光電", "6213": "聯茂", "3008": "大立光", "3406": "玉晶光", 
    "1519": "華城", "1503": "士電", "1513": "中興電", "1605": "華新", "1101": "台泥", 
    "2002": "中鋼", "2603": "長榮", "2609": "陽明", "2615": "萬海", "2618": "長榮航", 
    "2610": "華航", "2345": "智邦", "2881": "富邦金", "2882": "國泰金", "8069": "元太", 
    "3293": "鈊象", "6789": "采鈺", "6147": "頎邦", "3016": "嘉晶"
}

# === 3. 🛡️ 安全連線防護機制 ===
def safe_get_json(url):
    try:
        res = requests.get(url, headers=HEADERS, timeout=15, verify=False)
        res.raise_for_status()
        return res.json()
    except: return {}

# === 4. 🚀 數據抓取核心 (修復 NameError) ===
@st.cache_data(ttl=3600)
def get_inst_data():
    inst_map = {}
    try:
        u1 = "https://www.twse.com.tw/fund/T86?response=json&selectType=ALLBUT0999"
        r1 = safe_get_json(u1)
        if 'data' in r1:
            for d in r1['data']: inst_map[d[0].strip()] = int(d[2].replace(',', '')) + int(d[10].replace(',', ''))
        u2 = "https://www.tpex.org.tw/web/stock/fund/T86/T86_result.php?l=zh-tw&o=json"
        r2 = safe_get_json(u2)
        if 'aaData' in r2:
            for d in r2['aaData']: inst_map[d[0].strip()] = int(d[8].replace(',', '')) + int(d[10].replace(',', ''))
    except: pass
    return inst_map

@st.cache_data(ttl=300)
def get_hot_rank_ids():
    hot_ids = set()
    try:
        u1 = "https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&type=ALLBUT0999"
        res1 = safe_get_json(u1)
        if 'tables' in res1:
            for t in res1['tables']:
                if '證券代號' in t.get('fields', []):
                    df_tmp = pd.DataFrame(t['data'], columns=t['fields'])
                    df_tmp['val'] = pd.to_numeric(df_tmp['成交金額'].str.replace(',',''), errors='coerce')
                    hot_ids.update(df_tmp.sort_values('val', ascending=False).head(30)['證券代號'].tolist())
                    break
    except: pass
    return hot_ids

def get_stock_info_realtime(ticker):
    try:
        clean = ticker.replace('.TW','').replace('.TWO','')
        tid = clean + ".TW"
        df = yf.Ticker(tid).history(period="20d")
        if df.empty:
            tid = clean + ".TWO"
            df = yf.Ticker(tid).history(period="20d")
        if not df.empty:
            return df['Close'].tolist(), df['Close'].iloc[-1], df['High'].iloc[-1], df['Low'].iloc[-1]
    except: pass
    return [], 0, 0, 0

# === 5. 技術指標與評分 ===
def calculate_kd(df):
    if len(df) < 9: return df
    df['9_min'] = df['Low'].rolling(window=9).min()
    df['9_max'] = df['High'].rolling(window=9).max()
    df['RSV'] = (df['Close'] - df['9_min']) / (df['9_max'] - df['9_min']) * 100
    k, d, k_v, d_v = 50.0, 50.0, [], []
    for rsv in df['RSV']:
        if pd.isna(rsv): k_v.append(50.0); d_v.append(50.0)
        else:
            k = (2/3) * k + (1/3) * rsv
            d = (2/3) * d + (1/3) * k
            k_v.append(k); d_v.append(d)
    df['K'], df['D'] = k_v, d_v
    return df

def analyze_star_score(ticker, inst_map=None, hot_list=None):
    try:
        inst_map, hot_list = inst_map or {}, hot_list or []
        clean = ticker.replace('.TW','').replace('.TWO','')
        df = yf.Ticker(clean+".TW").history(period="65d")
        if df.empty: df = yf.Ticker(clean+".TWO").history(period="65d")
        if df.empty or len(df) < 20: return None
        
        c = df['Close'].iloc[-1]
        df['MA5'] = df['Close'].rolling(5).mean(); df['MA20'] = df['Close'].rolling(20).mean(); df['MA60'] = df['Close'].rolling(60).mean()
        df = calculate_kd(df)
        
        s, tags = 0, []
        if c > df['MA5'].iloc[-1] > df['MA20'].iloc[-1] > df['MA60'].iloc[-1]: s+=1; tags.append("多頭")
        if df['MA20'].iloc[-1] > df['MA20'].iloc[-2]: s+=1; tags.append("月線升")
        if df['K'].iloc[-1] > df['D'].iloc[-1] and df['K'].iloc[-2] <= df['D'].iloc[-2]: s+=1; tags.append("KD金叉")
        if c > df['High'].iloc[-21:-1].max(): s+=1; tags.append("創高")
        if inst_map.get(clean, 0) > 500: s+=1; tags.append("大戶")
        if clean in hot_list: s+=1; tags.append("熱門")
        
        name = STOCKS_DICT.get(clean, "")
        display_name = f"{clean} {name}" if name else clean
        
        return {"標的名稱": display_name, "星等": "⭐"*s if s>0 else "休息", "星星數": s, "現價": round(c,2), "條件": " ".join(tags)}
    except: return None

# === 6. 🐳 籌碼更新引擎 ===
def fetch_whale_data():
    url = "https://www.twse.com.tw/fund/T86?response=json&selectType=ALLBUT0999"
    data = safe_get_json(url)
    if not data or 'data' not in data: return False, "資料未更新"
    try:
        df = pd.DataFrame(data['data'], columns=data['fields'])
        t_col = [c for c in df.columns if '投信買賣超' in c][0]
        f_col = [c for c in df.columns if '外陸資買賣超' in c or '外資' in c][0]
        df['T_NET'] = df[t_col].str.replace(',', '').astype(float) / 1000
        df['F_NET'] = df[f_col].str.replace(',', '').astype(float) / 1000
        today = datetime.date.today().strftime("%Y-%m-%d")
        conn = sqlite3.connect("whale_tracker.db")
        c = conn.cursor()
        c.execute('CREATE TABLE IF NOT EXISTS trust_net_buy (日期 TEXT, 證券代號 TEXT, 證券名稱 TEXT, "投信買賣超(張)" REAL)')
        c.execute('CREATE TABLE IF NOT EXISTS foreign_net_buy (日期 TEXT, 證券代號 TEXT, 證券名稱 TEXT, "外資買賣超(張)" REAL)')
        c.execute("DELETE FROM trust_net_buy WHERE 日期=?", (today,))
        c.execute("DELETE FROM foreign_net_buy WHERE 日期=?", (today,))
        
        d_t = df[['證券代號', '證券名稱', 'T_NET']].copy(); d_t['日期'] = today
        d_f = df[['證券代號', '證券名稱', 'F_NET']].copy(); d_f['日期'] = today
        d_t.columns = ['證券代號', '證券名稱', '投信買賣超(張)', '日期']
        d_f.columns = ['證券代號', '證券名稱', '外資買賣超(張)', '日期']
        d_t.to_sql('trust_net_buy', conn, if_exists='append', index=False)
        d_f.to_sql('foreign_net_buy', conn, if_exists='append', index=False)
        conn.commit(); conn.close()
        return True, f"成功更新 {len(df)} 筆數據"
    except Exception as e: return False, str(e)

# === 7. 🕵️‍♂️ 00981A 分析 ===
def analyze_00981a_logic():
    target_stocks = {
        "2330": ("台積電", 19.5), "2317": ("鴻海", 9.5), "2454": ("聯發科", 7.8), "2383": ("台光電", 6.5),
        "2345": ("智邦", 5.2), "3017": ("奇鋐", 4.8), "3324": ("雙鴻", 4.2), "6669": ("緯穎", 3.8),
        "3231": ("緯創", 3.5), "2382": ("廣達", 3.2), "3037": ("欣興", 3.0), "3533": ("嘉澤", 2.8),
        "2368": ("金像電", 2.5), "3661": ("世芯-KY", 2.2), "2308": ("台達電", 2.0), "3034": ("聯詠", 1.8),
        "2603": ("長榮", 1.5), "3711": ("日月光", 1.4), "3008": ("大立光", 1.2), "3406": ("玉晶光", 1.1),
        "6274": ("台燿", 1.0), "6213": ("聯茂", 0.9), "4966": ("譜瑞-KY", 0.8), "8046": ("南電", 0.7),
        "2408": ("南亞科", 0.6), "2303": ("聯電", 0.5), "2357": ("華碩", 0.5), "1513": ("中興電", 0.4),
        "1519": ("華城", 0.4), "2356": ("英業達", 0.3), "2324": ("仁寶", 0.3), "6789": ("采鈺", 0.2),
        "6147": ("頎邦", 0.2), "3016": ("嘉晶", 0.1), "2449": ("京元電", 0.1), "2379": ("瑞昱", 0.1)
    }
    if not os.path.exists("whale_tracker.db"): return pd.DataFrame()
    try:
        conn = sqlite3.connect("whale_tracker.db")
        p = ','.join('?' for _ in target_stocks.keys())
        df = pd.read_sql_query(f"SELECT * FROM trust_net_buy WHERE 證券代號 IN ({p})", conn, params=list(target_stocks.keys()))
        conn.close()
        res = []
        for sid, group in df.groupby('證券代號'):
            group = group.sort_values('日期')
            diffs = group['投信買賣超(張)'].tolist()
            con_buy = 0
            for d in reversed(diffs):
                if d > 0: con_buy += 1
                else: break
            p_l, cur_p, hi, lo = get_stock_info_realtime(sid)
            est_cost, dist = 0.0, "-"
            if con_buy > 0 and len(p_l) >= con_buy:
                buy_v = diffs[-con_buy:]; rec_p = p_l[-con_buy:]
                if sum(buy_v) > 0:
                    est_cost = sum(p * v for p, v in zip(rec_p, buy_v)) / sum(buy_v)
                    dist = f"{((cur_p - est_cost) / est_cost) * 100:+.1f}%"
            w = target_stocks[sid][1]; limit = 25.0 if sid == "2330" else 10.0
            if w >= (limit-0.5): h, ic = "❌ 嚴禁追高", "🛑"
            elif w >= (limit-2.0): h, ic = "🟡 子彈將盡", "⚠️"
            else: h, ic = "🟢 空間充裕", "✅"
            res.append({"代號": sid, "股票名稱": target_stocks[sid][0], "權重狀態": f"{ic} {w}%", "跟單建議": h, "現價": cur_p, "均價": round(est_cost,1) if est_cost>0 else "-", "成本乖離": dist, "最高": hi, "最低": lo, "今日買超": int(diffs[-1]) if diffs else 0, "連買天數": con_buy})
        return pd.DataFrame(res).sort_values(by=["連買天數", "今日買超"], ascending=[False, False])
    except: return pd.DataFrame()

# === 8. UI 介面渲染 ===
st.sidebar.title("📡 老魯股神戰情室")
page = st.sidebar.radio("導覽功能", ["🕵️‍♂️ 00981A 經理人跟單", "🎯 股神六星雷達", "🐳 全市場連買榜", "🔄 資料庫更新中心"])
st.sidebar.divider()

if page == "🕵️‍♂️ 00981A 經理人跟單":
    st.title("🕵️‍♂️ 00981A 經理人全成分股追蹤")
    if st.button("🚀 啟動全成分股即時共振掃描", use_container_width=True):
        with st.spinner("✨ 同步中..."):
            df = analyze_00981a_logic()
            if not df.empty:
                inst_map = get_inst_data()
                with ThreadPoolExecutor(max_workers=10) as ex:
                    star_dict = {sid: ex.submit(analyze_star_score, sid, inst_map).result() for sid in df['代號']}
                df.insert(2, '六星雷達', df['代號'].apply(lambda x: star_dict[x]['星等'] if star_dict[x] else "休息"))
                df.reset_index(drop=True, inplace=True); df.insert(0, '排名', df.index + 1)
                st.dataframe(df[['排名', '股票名稱', '六星雷達', '現價', '均價', '成本乖離', '最高', '最低', '連買天數', '今日買超', '權重狀態', '跟單建議']], use_container_width=True, hide_index=True, height=750)
            else: st.error("❌ 無數據，請點擊資料庫更新中心。")

elif page == "🎯 股神六星雷達":
    st.title("🎯 股神六星掃描儀")
    u_in = st.sidebar.text_area("代號庫：", value="2330, 2317, 2454, 2383, 2345, 3017, 3324, 6669, 3231, 2382, 3037, 3533, 1513, 1519, 2603", height=200)
    s_list = [t.strip() for t in u_in.replace('，',',').split(',') if t.strip()]
    if st.button("🚀 全自動即時掃描", use_container_width=True):
        inst_map, hot_list = get_inst_data(), get_hot_rank_ids()
        res, pb = [], st.progress(0)
        with ThreadPoolExecutor(max_workers=10) as ex:
            futs = {ex.submit(analyze_star_score, t, inst_map, hot_list): t for t in s_list}
            for i, f in enumerate(as_completed(futs)):
                pb.progress((i+1)/len(s_list))
                if f.result(): res.append(f.result())
        if res:
            df = pd.DataFrame(res).sort_values(by="星星數", ascending=False)
            df.reset_index(drop=True, inplace=True); df.insert(0, '排名', df.index + 1)
            st.dataframe(df[['排名', '標的名稱', '星等', '現價', '條件']], use_container_width=True, hide_index=True)

elif page == "🐳 全市場連買榜":
    st.title("🐳 全市場大戶籌碼榜")
    t = st.radio("選擇榜單", ["🟢 投信連買榜", "🦅 外資連買榜"], horizontal=True)
    whale = "trust" if "投信" in t else "foreign"
    if os.path.exists("whale_tracker.db"):
        conn = sqlite3.connect("whale_tracker.db")
        tbl = "trust_net_buy" if whale == "trust" else "foreign_net_buy"
        col = "投信買賣超(張)" if whale == "trust" else "外資買賣超(張)"
        df = pd.read_sql_query(f"SELECT * FROM {tbl} ORDER BY 證券代號, 日期", conn); conn.close()
        hot = []
        for sid, group in df.groupby('證券代號'):
            diffs = group[col].tolist()
            buy_d = sum(1 for d in reversed(diffs) if d > 0) if diffs and diffs[-1] > 0 else 0
            if buy_d >= 1:
                name = STOCKS_DICT.get(sid, group.iloc[-1]['證券名稱'])
                hot.append({"標的": f"{sid} {name}", "連買天數": buy_d, "累積買超": int(sum(diffs[-buy_d:]))})
        df_hot = pd.DataFrame(hot).sort_values(by="連買天數", ascending=False)
        df_hot.reset_index(drop=True, inplace=True); df_hot.insert(0, '排名', df_hot.index + 1)
        st.dataframe(df_hot, use_container_width=True, hide_index=True)

elif page == "🔄 資料庫更新中心":
    st.title("🔄 數據同步中心")
    if st.button("🔥 同步更新投信與外資大戶籌碼", type="primary", use_container_width=True):
        with st.spinner("🚀 同步中..."):
            s, m = fetch_whale_data()
            if s: st.success(m); time.sleep(1); st.rerun()
            else: st.error(m)
