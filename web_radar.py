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
import numpy as np
import xml.etree.ElementTree as ET

# === 1. 系統環境設定 ===
warnings.filterwarnings("ignore")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
st.set_page_config(page_title="稀有的股神系統雷達", page_icon="📡", layout="wide")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
HEADERS = {"User-Agent": UA}
FUGLE_API_KEY = "54f80721-6cad-4ec9-9679-c5a315e7b00b"

# === 2. 🛡️ 安全連線防護機制 ===
def safe_get_json(url, headers, max_retries=3):
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=15, verify=False)
            response.raise_for_status() 
            return response.json()
        except (ChunkedEncodingError, ConnectionError, ReadTimeout):
            time.sleep(2)
        except ValueError:
            break
        except Exception:
            break
    return {}

# === 3. 核心指標與大盤風向球 ===
@st.cache_data(ttl=1800)
def get_market_breadth():
    try:
        df = yf.Ticker("^TWII").history(period="3mo")
        if not df.empty:
            df['MA20'] = df['Close'].rolling(20).mean()
            c = df['Close'].iloc[-1]
            m20 = df['MA20'].iloc[-1]
            status = "🟢 偏多順風 (站上月線，適合積極操作)" if c > m20 else "🔴 偏空逆風 (跌破月線，建議縮小部位)"
            return round(c, 2), round(m20, 2), status
    except: pass
    return None, None, "⚪ 未知"

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

# === 🏢 3.5 升級版：新聞超連結與 AI 情感引擎 ===
def get_fundamentals_and_news(symbol):
    try:
        tkr = yf.Ticker(f"{symbol}.TW")
        info = tkr.info
        if not info or 'symbol' not in info:
            tkr = yf.Ticker(f"{symbol}.TWO")
            info = tkr.info
        
        eps = info.get('trailingEps', '---')
        pe = info.get('trailingPE', '---')
        rev_growth = info.get('revenueGrowth', None)
        rev_growth_str = f"{rev_growth * 100:.2f} %" if rev_growth is not None else "---"
        
        # 🚀 強力新聞引擎：加入連結擷取
        news = []
        try:
            name = STOCKS_DICT.get(f"{symbol}.TW", STOCKS_DICT.get(f"{symbol}.TWO", "")).replace(" ", "")
            query = f"{symbol}+{name}+股市"
            url = f"https://news.google.com/rss/search?q={query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
            res = requests.get(url, headers=HEADERS, timeout=5)
            root = ET.fromstring(res.content)
            for item in root.findall('.//item')[:5]:
                title = item.find('title').text
                link = item.find('link').text if item.find('link') is not None else "#" # 擷取新聞超連結
                clean_title = title.rsplit(' - ', 1)[0]
                news.append({'title': clean_title, 'link': link})
        except Exception:
            pass
            
        return eps, pe, rev_growth_str, news
    except:
        return "---", "---", "---", []

def ai_news_sentiment(news_list):
    if not news_list:
        return "⚪ 尚無近期外電或財經新聞可供分析。"
    
    pos_words = ['增', '漲', '高', '好', '優', '強', '大單', '受惠', '利多', '新高', '突破', '成長', '看好', '買超', '雙增', '季增']
    neg_words = ['減', '跌', '低', '壞', '差', '弱', '砍單', '衰退', '利空', '破底', '下修', '看壞', '不如預期', '賣超', '雙減']
    
    score = 0
    formatted_news = []
    for n in news_list:
        t = n.get('title', '')
        l = n.get('link', '#')
        formatted_news.append(f"- [{t}]({l})") # 轉換成 Markdown 超連結
        for w in pos_words:
            if w in t: score += 1
        for w in neg_words:
            if w in t: score -= 1
    
    if score >= 2:
        conclusion = "🟢 **【AI 情感判定：偏多】** 近期新聞頻頻釋出利多，市場情緒樂觀，具備消息面保護傘。"
    elif score <= -2:
        conclusion = "🔴 **【AI 情感判定：偏空】** 近期新聞出現雜音或利空，請嚴格控管資金與停損。"
    else:
        conclusion = "🟡 **【AI 情感判定：中性】** 近期新聞無極端多空方向，請回歸技術面與籌碼面操作。"
        
    summary = "\n".join(formatted_news)
    return f"{conclusion}\n\n**📰 近期熱門新聞標題 (點擊可看原文)：**\n{summary}"

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

# === 4. 名單字典 (完整 112 檔) ===
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
    "6789.TW": "采鈺", "6147.TWO": "頎邦", "3016.TW": "嘉晶", "6805.TW": "富世達"
}

SECTOR_MAP = {
    "2330": "半導體", "2454": "半導體", "3661": "半導體", "3034": "半導體",
    "2317": "AI伺服器", "3231": "AI伺服器", "2382": "AI伺服器", "2356": "AI伺服器",
    "3017": "散熱模組", "3324": "散熱模組", "3653": "散熱模組", "6805": "軸承",
    "2383": "PCB零組件", "2368": "PCB零組件", "3533": "連接器", "3037": "PCB零組件",
    "2308": "電源供應", "2345": "網通", "2603": "航運", "2609": "航運", "2881": "金融"
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
        
        return_5d = (c / df['Close'].iloc[-6]) - 1 if len(df) >= 6 else 0
        bias_20 = (c / df['MA20'].iloc[-1]) - 1
        is_warning = return_5d > 0.25 or bias_20 > 0.30
        upper_shadow_pct = (df['High'].iloc[-1] / c) - 1
        is_daytrader_trap = (v > v5 * 3) and (upper_shadow_pct > 0.04)
        
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
        if is_daytrader_trap: tags.append("🪤[隔日沖倒貨區]")
        
        inst_display = f"{inst_val:,}" if inst_val != 0 else "--"
        name = STOCKS_DICT.get(tid, clean)
        risk_level = "✅ 安全"
        if is_warning: risk_level = "🚨 高風險 (處置前兆)"
        elif is_daytrader_trap: risk_level = "⚠️ 留意隔日沖砸盤"
        
        # 🔗 建立外連技術線圖網址
        chart_url = f"https://tw.stock.yahoo.com/quote/{clean}/technical-analysis"
        
        return {
            '標的': f"{clean} {name}", '看盤連結': chart_url, '星等': "⭐"*s if s>0 else "休息", '收盤': round(c,2), 
            '籌碼大戶(張)': inst_display, '今日量(張)': int(v/1000), '觸發條件': " ".join(tags), 
            '星星數': s, '處置與籌碼風險': risk_level
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
        v5_lots = int(df['Volume'].iloc[-6:-1].mean() / 1000)
        
        status, action = [], "🟢 續抱 (趨勢健康)"
        if c < m20: status.append("⚠️ 跌破月線"); action = "🛑 建議停損/停利"
        elif c < m5: status.append("⚠️ 跌破5日線"); action = "🟡 建議先減碼一半"
        if k < d and df['K'].iloc[-2] >= df['D'].iloc[-2] and k > 70: status.append("⚠️ KD高檔死叉"); action = "🟡 建議拔檔減碼"
        if not status: status.append("✅ 強勢多頭")
        return {
            "標的": clean, "收盤": round(c,2), "MA5": round(m5,2), "MA20": round(m20,2), 
            "KD": f"K:{round(k,1)}/D:{round(d,1)}", "狀況": "、".join(status), "建議": action, "5日均量": max(1, v5_lots)
        }
    except: return None

def run_simple_backtest(symbol):
    try:
        tid = f"{symbol}.TW"
        df = yf.Ticker(tid).history(period="2y")
        if df.empty:
            tid = f"{symbol}.TWO"
            df = yf.Ticker(tid).history(period="2y")
        if len(df) < 60: return None
        
        df['MA20'] = df['Close'].rolling(20).mean()
        df = df.dropna()
        
        df['Signal'] = 0
        df.loc[df['Close'] > df['MA20'], 'Signal'] = 1
        df['Return'] = df['Close'].pct_change()
        df['Strategy_Return'] = df['Signal'].shift(1) * df['Return']
        df['Equity'] = (1 + df['Strategy_Return'].fillna(0)).cumprod() * 100
        
        win_rate = len(df[df['Strategy_Return'] > 0]) / len(df[df['Strategy_Return'] != 0]) if len(df[df['Strategy_Return'] != 0]) > 0 else 0
        total_return = df['Equity'].iloc[-1] - 100
        return df, win_rate, total_return
    except: return None

# === 6. 🕵️‍♂️ 經理人籌碼追蹤邏輯 ===
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
        mock_scenarios = [
            ("2317", "鴻海", [1000, 1500, 2000, 3000]), ("3231", "緯創", [2000, 2000, 2000, 3500]),
            ("2383", "台光電", [3000, 3000, 3500, 4200]), ("6805", "富世達", [200, 400, 800, 1500]), 
            ("3017", "奇鋐", [800, 800, 1200, 1800]), ("2345", "智邦", [1000, 1200, 1500, 1900]),
            ("3533", "嘉澤", [600, 600, 700, 900]), ("2330", "台積電", [8000, 8000, 8000, 8000]),
            ("2454", "聯發科", [1500, 1500, 1500, 1500]), ("3324", "雙鴻", [500, 500, 500, 500]),
            ("2308", "台達電", [5000, 5200, 5500, 4500]), ("2382", "廣達", [4000, 4000, 3000, 2000]),
            ("3034", "聯詠", [1000, 1000, 800, 500]), ("2603", "長榮", [5000, 4000, 3000, 2000]),
            ("3661", "世芯-KY", [400, 400, 400, 200])
        ]
        dummy_rows = []
        for ticker, name, shares in mock_scenarios:
            for i, d in enumerate(dates): dummy_rows.append([d, ticker, f"{name} (測試)", shares[i]])
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
            "代號": stock_id, "股票名稱": latest_record['股票名稱'], 
            "看盤連結": f"https://tw.stock.yahoo.com/quote/{stock_id}/technical-analysis",
            "最新持股張數": int(latest_record['持有張數']),
            "今日買賣超(張)": int(latest_record['單日買賣超(張)']), "動向狀態": status, "連續天數": days,
            "連續天數顯示": f"{days} 天" if days > 0 else "-"
        })
    return pd.DataFrame(results).sort_values(by="今日買賣超(張)", ascending=False)

# === 7. 側邊欄與大盤風向球 ===
st.sidebar.title("📡 導覽選單")

st.sidebar.markdown("---")
st.sidebar.subheader("🌍 大盤多空風向球")
tw_c, tw_m20, tw_status = get_market_breadth()
if tw_c:
    st.sidebar.metric("加權指數", f"{tw_c:,.0f}")
    if "綠" in tw_status or "多" in tw_status: st.sidebar.success(tw_status)
    else: st.sidebar.error(tw_status)
else:
    st.sidebar.write("大盤資料讀取中...")
st.sidebar.markdown("---")

main_page = st.sidebar.radio("跳轉頁面", ["🎯 股神六星雷達系統", "🕵️‍♂️ 00981A 經理人跟單雷達"])

if main_page == "🎯 股神六星雷達系統":
    st.sidebar.subheader("⚙️ 自選股水庫")
    def_tickers = ", ".join([k.split('.')[0] for k in STOCKS_DICT.keys()])
    u_input = st.sidebar.text_area("代號庫 (支援完整112檔)：", value=def_tickers, height=200)
    s_list = [t.strip() for t in u_input.replace('，',',').split(',') if t.strip()]

# ==========================================
# 分頁 1: 🎯 股神六星雷達系統
# ==========================================
if main_page == "🎯 股神六星雷達系統":
    st.title("📡 稀有的股神系統：四維共振・真・大滿配終極版")
    t1, t2, t3, t4, t5, t6, t7 = st.tabs(["🎯 六星雷達", "💰 成交排行", "📈 互動看盤", "🛡️ 智能部位診斷", "🚨 處置與隔日沖", "🧪 回測實驗室", "🏢 基本面與 AI 診斷"])
    
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
                # ⚙️ 讓表格中的「看盤連結」變成可以點擊的網頁圖示
                st.dataframe(
                    df[['標的', '看盤連結', '星等', '收盤', '處置與籌碼風險', '籌碼大戶(張)', '今日量(張)', '觸發條件']], 
                    use_container_width=True,
                    column_config={
                        "看盤連結": st.column_config.LinkColumn("互動看盤", display_text="📈 點我看圖")
                    }
                )

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
                v5_avg = r['5日均量']
                
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
                    * **風控說明**：最大虧損將被控制在 **{max_loss_amount:,.0f} 元** 左右。
                    """)
                    
                    if suggested_shares > (v5_avg * 0.01):
                        st.error(f"💧 **流動性滑價警告**：您預計買進的張數超過該股近5日均量({v5_avg}張)的 1%！大資金進出將產生嚴重滑價，建議降低部位或分批建倉！")

    with t5:
        st.markdown("### 🚨 處置與隔日沖警戒清單 (多頭陷阱迴避)")
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
                    if res and ("處置" in res['處置與籌碼風險'] or "隔日沖" in res['處置與籌碼風險']):
                        danger_list.append(res)
            if danger_list:
                df_danger = pd.DataFrame(danger_list)
                st.error(f"🚨 **發現 {len(df_danger)} 檔高風險標的！請避免追高！**")
                st.dataframe(
                    df_danger[['標的', '看盤連結', '收盤', '處置與籌碼風險', '觸發條件']], 
                    use_container_width=True,
                    column_config={"看盤連結": st.column_config.LinkColumn("互動看盤", display_text="📈 點我看圖")}
                )
            else:
                st.success("✅ 目前自選庫中沒有面臨風險的過熱標的。")

    with t6:
        st.markdown("### 🧪 策略回測實驗室 (2年期)")
        st.markdown("驗證『突破月線買進、跌破月線賣出』的波段策略，在過去兩年套用於該股票的真實績效。")
        bt_id = st.text_input("🔍 欲回測標的代號", value="2317", key="bt_in")
        if st.button("🧪 執行歷史回測", use_container_width=True):
            res = run_simple_backtest(bt_id)
            if res:
                df_bt, win_rate, total_ret = res
                c1, c2 = st.columns(2)
                c1.metric("策略歷史勝率", f"{win_rate*100:.1f} %")
                c2.metric("2年期累積報酬率", f"{total_ret:.1f} %")
                fig = px.line(df_bt, x=df_bt.index, y='Equity', title=f"{bt_id} 波段策略權益曲線 (起點為100)")
                fig.update_layout(template="plotly_dark")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("資料不足，無法回測。")

    with t7:
        st.markdown("### 🏢 基本面濾網與 AI 財報新聞分析")
        st.markdown("結合企業獲利動能與最新市場消息，打造「技術＋籌碼＋基本面＋消息面」四維防護。")
        f_id = st.text_input("🔍 欲查探基本面的標的代號", value="2330", key="fund_in")
        if st.button("🧠 啟動 AI 智能診斷", use_container_width=True):
            with st.spinner("⚡ 正在爬取最新財報數據與 Google News 外電新聞..."):
                eps, pe, rev, news_list = get_fundamentals_and_news(f_id)
                ai_report = ai_news_sentiment(news_list)
                st.markdown(f"#### 📊 {f_id} 核心基本面數據")
                c1, c2, c3 = st.columns(3)
                c1.metric("近四季 EPS (元)", eps)
                c2.metric("本益比 (P/E)", pe)
                c3.metric("最新營收年增率 (YoY)", rev)
                if rev != "---" and float(rev.replace('%','').strip()) > 10:
                    st.success("✅ **營收成長動能強勁！具備戴維斯雙擊潛力。**")
                st.divider()
                st.markdown("#### 🧠 AI 消息面情感解析")
                st.info(ai_report)

# ==========================================
# 分頁 2: 🕵️‍♂️ 00981A 經理人跟單雷達
# ==========================================
elif main_page == "🕵️‍♂️ 00981A 經理人跟單雷達":
    st.title("🕵️‍♂️ 00981A 經理人跟單雷達 (大滿配防護版)")
    force_refresh = st.button("🔄 強制重新抓取今日籌碼")
    
    raw_df = get_00981a_holdings_history(force_refresh=force_refresh)
    analyzed_df = analyze_manager_moves(raw_df)
    
    if not analyzed_df.empty:
        with st.spinner("⚡ 正在獲取最新股價、計算主力成本與持股權重，並進行風險判定..."):
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
                        warning_dict[t] = res.get('處置與籌碼風險', "✅ 安全")
                    else:
                        star_dict[t] = "☁️ 盤整/休息"
                        price_dict[t] = fetch_fast_price(t)
                        warning_dict[t] = "✅ 安全"
            
            for _, row in analyzed_df.iterrows():
                if row['動向狀態'] == "🟢 主力連買":
                    vwap_dict[row['代號']] = estimate_vwap(row['代號'], row['連續天數'])
                else:
                    vwap_dict[row['代號']] = "---"
            
            analyzed_df.insert(2, '最新收盤價', analyzed_df['代號'].map(price_dict))
            analyzed_df.insert(3, '主力推估成本', analyzed_df['代號'].map(vwap_dict))
            analyzed_df.insert(4, '處置與風險', analyzed_df['代號'].map(warning_dict))
            analyzed_df.insert(5, '六星技術評等', analyzed_df['代號'].map(star_dict))
            analyzed_df['產業族群'] = analyzed_df['代號'].map(SECTOR_MAP).fillna("其他/未分類")

            # ==========================================
            # 🌟 新增功能：計算 ETF 持股權重與加碼水位空間
            # ==========================================
            # 將收盤價轉為數值，以計算總市值預估值
            analyzed_df['最新收盤價_num'] = pd.to_numeric(analyzed_df['最新收盤價'], errors='coerce').fillna(0)
            analyzed_df['市值預估'] = analyzed_df['最新持股張數'] * analyzed_df['最新收盤價_num'] * 1000
            total_assets = analyzed_df['市值預估'].sum()

            def calc_weight_and_space(row):
                if total_assets > 0:
                    weight = (row['市值預估'] / total_assets) * 100
                else:
                    weight = 0.0
                
                # ⚖️ 判定持股上限 (台積電 2330 為 25%，其餘標的 10%)
                limit = 25.0 if str(row['代號']) == "2330" else 10.0
                space = limit - weight
                
                # 狀態判定 (小於 0.5% 視為滿水位，小於 2% 視為快滿)
                if space <= 0.5:
                    status = f"🛑 滿水位 (剩 {max(0, space):.1f}%)"
                elif space <= 2.0:
                    status = f"⚠️ 快滿 (剩 {space:.1f}%)"
                else:
                    status = f"✅ 充足 (剩 {space:.1f}%)"
                    
                return pd.Series([round(weight, 2), status])

            analyzed_df[['預估權重(%)', '加碼空間']] = analyzed_df.apply(calc_weight_and_space, axis=1)
            # ==========================================

        # 🗺️ 資金熱力圖 (自定義紅綠色系)
        st.subheader("🗺️ 資金熱力圖 (主力買賣板塊)")
        try:
            heat_df = analyzed_df[analyzed_df['今日買賣超(張)'] != 0].copy()
            if not heat_df.empty:
                fig = px.treemap(
                    heat_df, 
                    path=[px.Constant("全市場動向"), '產業族群', '股票名稱'],
                    values=heat_df['今日買賣超(張)'].abs(),
                    color='今日買賣超(張)', 
                    color_continuous_scale=['#00cc96', '#262730', '#ff4b4b'], # 綠色(賣出) -> 深色(平盤) -> 紅色(買進)
                    color_continuous_midpoint=0,
                    title="板塊面積大小代表張數，紅色代表買進，綠色代表賣出 (台股慣例)"
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
        danger_count = analyzed_df[analyzed_df['處置與風險'].str.contains('風險|警戒|隔日沖')].shape[0]
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("🔥 主力連買標的", f"{buy_count} 檔")
        m2.metric("🧊 經理人倒貨標的", f"{sell_count} 檔")
        m3.metric("⭐ 雙引擎共振標的", f"{star_count} 檔")
        m4.metric("🚨 處置/隔日沖警戒", f"{danger_count} 檔", help="即將面臨處置或有隔日沖砸盤風險！")
        
        st.divider()
        st.subheader("🔥 經理人持股 × 成本防護 × 雙引擎共振榜")
        
        # 移除暫存的計算用欄位，整理顯示表格
        display_df = analyzed_df.drop(columns=['連續天數', '產業族群', '最新收盤價_num', '市值預估'])
        display_df = display_df.rename(columns={'連續天數顯示': '連續天數'})
        
        # 🎨 為表格加上重點顏色警示
        def highlight_danger(val):
            if isinstance(val, str) and ('風險' in val or '警戒' in val or '隔日沖' in val or '滿水位' in val): 
                return 'color: #ff4b4b; font-weight: bold'
            elif isinstance(val, str) and ('安全' in val or '充足' in val): 
                return 'color: #00cc96'
            elif isinstance(val, str) and '快滿' in val:
                return 'color: #ffd166; font-weight: bold'
            return ''
            
        # 同時將警示色套用到「處置與風險」跟「加碼空間」兩個欄位
        styled_df = display_df.style.map(highlight_danger, subset=['處置與風險', '加碼空間'])
        
        # ⚙️ 讓表格中的「看盤連結」變成可以點擊的網頁圖示
        st.dataframe(
            styled_df,
            use_container_width=True,
            hide_index=True,
            height=580, 
            column_config={
                "今日買賣超(張)": st.column_config.NumberColumn("今日買賣超(張)", format="%d"),
                "最新持股張數": st.column_config.NumberColumn("最新持股張數", format="%d"),
                "預估權重(%)": st.column_config.NumberColumn("預估權重(%)", format="%.2f %%"),
                "看盤連結": st.column_config.LinkColumn("互動看盤", display_text="📈 點我看圖")
            }
        )
    else:
        st.warning("目前尚未收集到足夠的歷史資料，或今日 API 獲取失敗，請稍後再試。")
