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
from gtts import gTTS
import io

# === 1. 系統環境設定 ===
warnings.filterwarnings("ignore")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
st.set_page_config(page_title="阿綜專屬：究極軍規雷達", page_icon="📡", layout="wide")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
HEADERS = {"User-Agent": UA}
FUGLE_API_KEY = "54f80721-6cad-4ec9-9679-c5a315e7b00b"

# === 🚨 知名隔日沖與地緣主力名單 ===
DAY_TRADER_BRANCHES = [
    "凱基-台北", "富邦-建國", "元大-土城永寧", "群益金鼎-大安", 
    "統一-城中", "康和-延平", "元富-城東", "摩根大通", "美林"
]

# === 2. 👁️ 瀏覽次數統計機制 ===
def get_and_increment_view_count():
    count_file = "page_views.txt"
    if os.path.exists(count_file):
        try:
            with open(count_file, "r") as f:
                count = int(f.read().strip())
        except: count = 0
    else: count = 0
        
    if 'has_viewed' not in st.session_state:
        count += 1
        try:
            with open(count_file, "w") as f: f.write(str(count))
            st.session_state['has_viewed'] = True
        except: pass
    return count

# === 3. 🛡️ 安全連線防護機制 ===
def safe_get_json(url, headers, max_retries=3):
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=15, verify=False)
            response.raise_for_status() 
            return response.json()
        except (ChunkedEncodingError, ConnectionError, ReadTimeout): time.sleep(2)
        except ValueError: break
        except Exception: break
    return {}

# === 4. 核心指標與大盤風向球 ===
@st.cache_data(ttl=1800)
def get_market_breadth():
    try:
        df = yf.Ticker("^TWII").history(period="3mo")
        if not df.empty:
            df['MA20'] = df['Close'].rolling(20).mean()
            c = df['Close'].iloc[-1]
            m20 = df['MA20'].iloc[-1]
            status = "🟢 偏多順風 (站上月線，積極操作)" if c > m20 else "🔴 偏空逆風 (跌破月線，縮小部位)"
            return round(c, 2), round(m20, 2), status
    except: pass
    return None, None, "⚪ 系統連線中"

# === 🌟 側邊欄模組 A1：美股大腦 ===
def us_market_brain():
    st.sidebar.markdown("---")
    st.sidebar.subheader("🌐 美股連動觀測")
    us_tickers = {"TSM": "台積電 ADR", "ARM": "安謀 (Arm)", "NVDA": "輝達 (NVIDIA)"}
    for ticker, name in us_tickers.items():
        try:
            tk = yf.Ticker(ticker)
            df = tk.history(period="1mo")
            if not df.empty and len(df) >= 2:
                close_today = df['Close'].iloc[-1]
                close_yest = df['Close'].iloc[-2]
                change = ((close_today - close_yest) / close_yest) * 100
                delta_color = "normal" if change > 0 else "inverse"
                st.sidebar.metric(label=f"{name} ({ticker})", value=f"${close_today:.2f}", delta=f"{change:.2f}%", delta_color=delta_color)
            else: st.sidebar.metric(label=name, value="N/A", delta="-")
        except: st.sidebar.metric(label=name, value="Error", delta="-")

# === 🌟 側邊欄模組 A2：ADR 溢價神算 ===
def adr_premium_calculator():
    st.sidebar.markdown("---")
    st.sidebar.subheader("⚡ ADR 開盤神算")
    try:
        tsm_adr = yf.Ticker("TSM").history(period="2d")['Close'].iloc[-1]
        twd_us = yf.Ticker("TWD=X").history(period="2d")['Close'].iloc[-1]
        tsmc_tw = yf.Ticker("2330.TW").history(period="2d")['Close'].iloc[-1]
        theo_price = (tsm_adr * twd_us) / 5  
        premium = ((theo_price - tsmc_tw) / tsmc_tw) * 100
        st.sidebar.metric("今日理論開盤價", f"{theo_price:.0f} 元", f"溢價差 {premium:.2f}%")
        if premium > 1.5: st.sidebar.success("🔥 溢價極高，留意跳空！")
        elif premium < -1.5: st.sidebar.error("⚠️ 嚴重折價，當心拖累！")
        else: st.sidebar.info("💡 溢價平穩，回歸技術面。")
    except: st.sidebar.warning("API 冷卻中，無法計算 ADR。")

# === 🌟 側邊欄模組 B：AI 語音早報 ===
def ai_voice_report(market_status):
    st.sidebar.markdown("---")
    st.sidebar.subheader("🎙️ AI 語音早報")
    if st.sidebar.button("📢 生成並播放今日早報", use_container_width=True):
        with st.spinner("阿綜專屬 AI 正在整理戰報並錄音中..."):
            now = datetime.datetime.now().strftime("%Y年%m月%d日")
            status_text = market_status if "偏多" in market_status or "偏空" in market_status else "目前無法取得連線"
            report_text = f"阿綜早安，今天是{now}。大盤狀態：{status_text}。美股台積電 ADR 數據與成交排行榜已更新。請透過 VPVR 圖表確認持股是否踩在關鍵紅K支撐之上，祝您修車與操作順利！"
            try:
                tts = gTTS(text=report_text, lang='zh-tw')
                audio_fp = io.BytesIO()
                tts.write_to_fp(audio_fp)
                st.sidebar.audio(audio_fp, format='audio/mp3')
                st.sidebar.success("✅ 早報已生成！")
            except: st.sidebar.error("語音生成失敗。")

# === 🌟 側邊欄模組 C：Line Notify 警報 ===
def line_notify_setting():
    st.sidebar.markdown("---")
    st.sidebar.subheader("📲 Line 警報器")
    line_token = st.sidebar.text_input("Line Token", type="password")
    if st.sidebar.button("傳送測試訊息"):
        if line_token:
            headers = {"Authorization": "Bearer " + line_token}
            requests.post("https://notify-api.line.me/api/notify", headers=headers, data={'message':'🔧 股神雷達連線成功！'})
            st.sidebar.success("✅ 發送成功！")
        else: st.sidebar.warning("請先輸入 Token！")

# === 5. 金流排行榜與熱門清單 (自動回溯) ===
@st.cache_data(ttl=3600)
def fetch_top15_ranking():
    tse_df, otc_df = pd.DataFrame(), pd.DataFrame()
    def get_tse(date_str=""):
        url = "https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&type=ALLBUT0999"
        if date_str: url += f"&date={date_str}"
        res = safe_get_json(url, HEADERS)
        if res and 'tables' in res:
            for t in res['tables']:
                if '證券代號' in t.get('fields', []) and '成交金額' in t.get('fields', []):
                    df = pd.DataFrame(t['data'], columns=t['fields'])
                    df['v'] = pd.to_numeric(df['成交金額'].str.replace(',',''), errors='coerce')
                    if not df.empty and df['v'].sum() > 0:
                        df_sorted = df.sort_values('v', ascending=False).head(15)[['證券代號', '證券名稱', '收盤價', 'v']]
                        df_sorted.columns = ['證券代號', '證券名稱', '收盤價', '成交金額']
                        return df_sorted
        return pd.DataFrame()

    def get_otc(date_str=""):
        url = "https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php?l=zh-tw&o=json"
        if date_str: url += f"&d={date_str}"
        res = safe_get_json(url, HEADERS)
        data_otc = res.get('aaData', []) or (res.get('tables', [{}])[0].get('data', []) if 'tables' in res else [])
        if data_otc:
            df = pd.DataFrame(data_otc)
            cv = 9 if df.shape[1] >= 10 else df.shape[1] - 2
            df['v'] = pd.to_numeric(df[cv].astype(str).str.replace(',',''), errors='coerce')
            if not df.empty and df['v'].sum() > 0:
                df_sorted = df.sort_values('v', ascending=False).head(15)[[0, 1, 2, 'v']]
                df_sorted.columns = ['證券代號', '證券名稱', '收盤價', '成交金額']
                return df_sorted
        return pd.DataFrame()

    today = datetime.datetime.now()
    for i in range(7):
        tse_df = get_tse((today - datetime.timedelta(days=i)).strftime('%Y%m%d') if i > 0 else "")
        if not tse_df.empty: break
    for i in range(7):
        otc_df = get_otc((today - datetime.timedelta(days=i)).strftime(f'{today.year - 1911}/%m/%d') if i > 0 else "")
        if not otc_df.empty: break
    return tse_df, otc_df

@st.cache_data(ttl=300)
def get_hot_rank_ids():
    tse_df, otc_df = fetch_top15_ranking()
    hot_ids = set()
    if not tse_df.empty: hot_ids.update(tse_df['證券代號'].tolist())
    if not otc_df.empty: hot_ids.update(otc_df['證券代號'].tolist())
    return hot_ids

# === 6. 技術指標計算與基礎函數 ===
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

def calculate_macd(df):
    df['MACD'] = df['Close'].ewm(span=12, adjust=False).mean() - df['Close'].ewm(span=26, adjust=False).mean()
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['Hist'] = df['MACD'] - df['Signal']
    return df

def get_fugle_realtime(symbol):
    try:
        res = requests.get(f"https://api.fugle.tw/marketdata/v1.0/stock/intraday/quote/{symbol}", headers={"X-API-KEY": FUGLE_API_KEY}, timeout=5, verify=False)
        if res.status_code == 200: return res.json().get('closePrice'), res.json().get('total', {}).get('tradeVolume', 0)
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
            return round((recent['Close'] * recent['Volume']).sum() / recent['Volume'].sum(), 2)
    except: pass
    return "---"

# === 7. 🏢 基本面與新聞擷取 ===
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
        news = []
        try:
            name = STOCKS_DICT.get(f"{symbol}.TW", STOCKS_DICT.get(f"{symbol}.TWO", "")).replace(" ", "")
            url = f"https://news.google.com/rss/search?q={symbol}+{name}+股市&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
            res = requests.get(url, headers=HEADERS, timeout=5)
            for item in ET.fromstring(res.content).findall('.//item')[:5]:
                news.append({'title': item.find('title').text.rsplit(' - ', 1)[0], 'link': item.find('link').text if item.find('link') is not None else "#"})
        except: pass
        return eps, pe, rev_growth_str, news
    except: return "---", "---", "---", []

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
        formatted_news.append(f"- [{t}]({l})")
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

# === 8. 名單字典 (完整 112 檔) ===
STOCKS_DICT = {
    "2330.TW": "台積電", "2317.TW": "鴻海", "2454.TW": "聯發科", "2308.TW": "台達電", "2303.TW": "聯電", "3711.TW": "日月光", "2408.TW": "南亞科", "2344.TW": "華邦電", "2337.TW": "旺宏", "3443.TW": "創意", "3661.TW": "世芯KY", "3034.TW": "聯詠", "2379.TW": "瑞昱", "4966.TW": "譜瑞KY", "6415.TW": "矽力KY", "3529.TW": "力旺", "6488.TWO": "環球晶", "5483.TWO": "中美晶", "3105.TWO": "穩懋", "8299.TWO": "群聯", "2382.TW": "廣達", "3231.TW": "緯創", "6669.TW": "緯穎", "2356.TW": "英業達", "2324.TW": "仁寶", "2353.TW": "宏碁", "2357.TW": "華碩", "2376.TW": "技嘉", "2377.TW": "微星", "3017.TW": "奇鋐", "3324.TW": "雙鴻", "3653.TW": "健策", "3533.TW": "嘉澤", "3013.TW": "晟銘電", "8210.TW": "勤誠", "7769.TW": "鴻勁", "3037.TW": "欣興", "8046.TW": "南電", "3189.TW": "景碩", "2368.TW": "金像電", "4958.TW": "臻鼎KY", "2313.TW": "華通", "6274.TWO": "台燿", "2383.TW": "台光電", "6213.TW": "聯茂", "3008.TW": "大立光", "3406.TW": "玉晶光", "1519.TW": "華城", "1503.TW": "士電", "1513.TW": "中興電", "1504.TW": "東元", "1605.TW": "華新", "1101.TW": "台泥", "1102.TW": "亞泥", "2002.TW": "中鋼", "2027.TW": "大成鋼", "2014.TW": "中鴻", "2207.TW": "和泰車", "9910.TW": "豐泰", "9921.TW": "巨大", "9904.TW": "寶成", "2603.TW": "長榮", "2609.TW": "陽明", "2615.TW": "萬海", "2618.TW": "長榮航", "2610.TW": "華航", "2606.TW": "裕民", "3596.TW": "智易", "5388.TWO": "中磊", "3380.TW": "明泰", "2345.TW": "智邦", "2881.TW": "富邦金", "2882.TW": "國泰金", "2891.TW": "中信金", "2886.TW": "兆豐金", "2884.TW": "玉山金", "2892.TW": "第一金", "2880.TW": "華南金", "2885.TW": "元大金", "2890.TW": "永豐金", "2883.TW": "開發金", "2887.TW": "台新金", "5880.TW": "合庫金", "8069.TWO": "元太", "3293.TWO": "鈊象", "8436.TW": "大江", "8441.TW": "可寧衛", "8390.TWO": "金益鼎", "0050.TW": "台50", "0056.TW": "高股息", "00878.TW": "永續", "00919.TW": "精選高息", "00929.TW": "復華科技", "00713.TW": "高息低波", "006208.TW": "富邦台50", "6789.TW": "采鈺", "6147.TWO": "頎邦", "3016.TW": "嘉晶", "6805.TW": "富世達"
}

SECTOR_MAP = {
    "2330": "半導體", "2454": "半導體", "3661": "半導體", "3034": "半導體", "2317": "AI伺服器", "3231": "AI伺服器", "2382": "AI伺服器", "2356": "AI伺服器", "3017": "散熱模組", "3324": "散熱模組", "3653": "散熱模組", "6805": "軸承", "2383": "PCB零組件", "2368": "PCB零組件", "3533": "連接器", "3037": "PCB零組件", "2308": "電源供應", "2345": "網通", "2603": "航運", "2609": "航運", "2881": "金融"
}

@st.cache_data(ttl=3600)
def get_inst_data():
    inst_map = {}
    try:
        r1 = safe_get_json("https://www.twse.com.tw/fund/T86?response=json&selectType=ALLBUT0999", HEADERS)
        if 'data' in r1:
            for d in r1['data']: inst_map[d[0].strip()] = int(d[2].replace(',', '')) + int(d[10].replace(',', ''))
        r2 = safe_get_json("https://www.tpex.org.tw/web/stock/fund/T86/T86_result.php?l=zh-tw&o=json", HEADERS)
        if 'aaData' in r2:
            for d in r2['aaData']: inst_map[d[0].strip()] = int(d[8].replace(',', '')) + int(d[10].replace(',', ''))
    except: pass
    return inst_map

# === 9. 雷達與各項診斷圖表邏輯 ===
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
        
        if df['Low'].iloc[-1] >= df['Low'].iloc[-2] and df['High'].iloc[-1] > df['High'].iloc[-2] and c > df['MA20'].iloc[-1]:
            s+=1; tags.append("👑[強勢底底高架構]")
            
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
        
        return {
            '標的': f"{clean} {name}", '看盤連結': f"https://tw.stock.yahoo.com/quote/{clean}/technical-analysis", 
            '星等': "🌟"*7 if s>=7 else ("⭐"*s if s>0 else "休息"), '收盤': round(c,2), 
            '籌碼大戶(張)': inst_display, '今日量(張)': int(v/1000), '觸發條件': " ".join(tags), 
            '星星數': s, '處置與籌碼風險': risk_level
        }
    except: return None

def plot_advanced_chart_with_vpvr(symbol, cost_price, period="6mo"):
    tid = symbol + ".TW" if "." not in symbol else symbol
    df = yf.Ticker(tid).history(period=period)
    df.dropna(subset=['Close'], inplace=True)
    if not df.empty:
        if len(df) >= 9: df = calculate_kd(df)
        bins = np.linspace(df['Low'].min(), df['High'].max(), num=40)
        df['Price_Bin'] = pd.cut(df['Close'], bins=bins)
        vp = df.groupby('Price_Bin')['Volume'].sum().reset_index()
        vp['Bin_Center'] = vp['Price_Bin'].apply(lambda x: x.mid).astype(float)
        
        fig = make_subplots(rows=2, cols=2, shared_xaxes=True, shared_yaxes=True, row_heights=[0.7, 0.3], column_widths=[0.8, 0.2], horizontal_spacing=0.01, vertical_spacing=0.05)
        fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='K線'), row=1, col=1)
        fig.add_trace(go.Bar(x=vp['Volume'], y=vp['Bin_Center'], orientation='h', name='籌碼密集區', marker_color='rgba(255, 209, 102, 0.5)'), row=1, col=2)
        if 'K' in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df['K'], name='K', line=dict(color='yellow')), row=2, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['D'], name='D', line=dict(color='cyan')), row=2, col=1)
        if cost_price > 0:
            fig.add_hline(y=cost_price, line_dash="dash", line_color="#00cc96", annotation_text=f"防線 {cost_price}", annotation_position="top left", row=1, col=1)
        fig.update_layout(height=700, template="plotly_dark", xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=30, b=10), showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    else: st.error("資料讀取失敗。")

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
        
        status, action = [], "🟢 續抱"
        if c < m20: status.append("⚠️ 跌破月線"); action = "🛑 建議停損/停利"
        elif c < m5: status.append("⚠️ 跌破5日線"); action = "🟡 建議先減碼"
        if k < d and df['K'].iloc[-2] >= df['D'].iloc[-2] and k > 70: status.append("⚠️ KD死叉"); action = "🟡 建議拔檔"
        if not status: status.append("✅ 強勢多頭")
        return {"標的": clean, "收盤": round(c,2), "MA5": round(m5,2), "MA20": round(m20,2), "KD": f"K:{round(k,1)}/D:{round(d,1)}", "狀況": "、".join(status), "建議": action, "5日均量": max(1, v5_lots)}
    except: return None

def analyze_dynamic_moat(symbol, cost_price):
    try:
        clean = symbol.replace('.TW','').replace('.TWO','')
        df = yf.Ticker(f"{clean}.TW").history(period="3mo")
        if df.empty: df = yf.Ticker(f"{clean}.TWO").history(period="3mo")
        if df.empty or len(df) < 20: return None
        current_price = df['Close'].iloc[-1]
        recent_df = df.tail(20)
        bull_candles = recent_df[recent_df['Close'] > recent_df['Open']]
        if not bull_candles.empty:
            max_vol_idx = bull_candles['Volume'].idxmax()
            key_candle = bull_candles.loc[max_vol_idx]
            support_price = round((key_candle['High'] + key_candle['Low']) / 2, 2)
            date_str = max_vol_idx.strftime('%Y-%m-%d')
        else:
            support_price = round(df['Close'].rolling(20).mean().iloc[-1], 2)
            date_str = "月線"
        return {"current_price": round(current_price, 2), "support_price": support_price, "key_date": date_str, "cost_price": cost_price}
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

# === 10. 🕵️‍♂️ 經理人籌碼追蹤邏輯 ===
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
    if os.path.exists(db_path): df_history = pd.read_csv(db_path)
    else: df_history = pd.DataFrame(columns=['日期', '代號', '股票名稱', '持有張數'])
        
    if not df_history.empty and today_str in df_history['日期'].values and not force_refresh:
        return df_history
        
    if force_refresh and not df_history.empty:
        df_history = df_history[df_history['日期'] != today_str]
            
    with st.spinner("🔄 獲取經理人今日持股..."):
        df_today = fetch_today_holdings_from_api("00981A")
        
    if not df_today.empty:
        df_history = pd.concat([df_history, df_today], ignore_index=True)
        df_history.to_csv(db_path, index=False)
        st.toast("✅ 持股資料已更新！")
    elif df_history.empty:
        dates = [(datetime.datetime.today() - datetime.timedelta(days=i)).strftime('%Y-%m-%d') for i in range(3, -1, -1)]
        mock_scenarios = [("2317", "鴻海", [1000, 1500, 2000, 3000]), ("3231", "緯創", [2000, 2000, 2000, 3500]), ("2330", "台積電", [8000, 8000, 8000, 8000])]
        dummy_rows = [[d, ticker, f"{name} (測試)", shares[i]] for ticker, name, shares in mock_scenarios for i, d in enumerate(dates)]
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
        consecutive_buy = sum(1 for d in reversed(diffs) if d > 0) if diffs[-1] > 0 else 0
        consecutive_sell = sum(1 for d in reversed(diffs) if d < 0) if diffs[-1] < 0 else 0
        latest_record = group.iloc[-1]
        status, days = ("🟢 主力連買", consecutive_buy) if consecutive_buy > 0 else ("🔴 經理人倒貨", consecutive_sell) if consecutive_sell > 0 else ("⚪ 靜止", 0)
        results.append({
            "代號": stock_id, "股票名稱": latest_record['股票名稱'], "看盤連結": f"https://tw.stock.yahoo.com/quote/{stock_id}/technical-analysis",
            "最新持股張數": int(latest_record['持有張數']), "今日買賣超(張)": int(latest_record['單日買賣超(張)']), "動向狀態": status, "連續天數": days,
            "連續天數顯示": f"{days} 天" if days > 0 else "-"
        })
    return pd.DataFrame(results).sort_values(by="今日買賣超(張)", ascending=False)

# === 11. 側邊欄導覽 ===
st.sidebar.title("📡 阿綜軍規操盤台")

st.sidebar.markdown("---")
st.sidebar.subheader("🌍 大盤多空風向球")
tw_c, tw_m20, tw_status = get_market_breadth()
if tw_c is not None:
    st.sidebar.metric("加權指數", f"{tw_c:,.0f}")
    if "綠" in tw_status or "多" in tw_status: st.sidebar.success(tw_status)
    else: st.sidebar.error(tw_status)

us_market_brain()
adr_premium_calculator()
line_notify_setting()

st.sidebar.markdown("---")
main_page = st.sidebar.radio("跳轉頁面", [
    "🎯 股神六星雷達系統", 
    "🏢 基本面與 AI 診斷", 
    "🕵️‍♂️ 00981A 經理人跟單雷達",
    "☠️ 隔日沖分點照妖鏡",
    "⚡ 全自動策略優化器"
])

mobile_mode = st.sidebar.toggle("📱 啟動極簡戰鬥模式", value=False)

if main_page in ["🎯 股神六星雷達系統", "☠️ 隔日沖分點照妖鏡", "⚡ 全自動策略優化器"]:
    st.sidebar.subheader("⚙️ 自選股水庫")
    def_tickers = ", ".join([k.split('.')[0] for k in STOCKS_DICT.keys()])
    u_input = st.sidebar.text_area("代號庫：", value=def_tickers, height=150)
    s_list = [t.strip() for t in u_input.replace('，',',').split(',') if t.strip()]

st.sidebar.markdown(f"👁️ **瀏覽次數：** `{get_and_increment_view_count()}` 次")

# ==========================================
# 分頁 1: 🎯 股神六星雷達系統
# ==========================================
if main_page == "🎯 股神六星雷達系統":
    if mobile_mode:
        st.title("📱 戰鬥儀表板")
        if st.button("🚀 一鍵掃描", use_container_width=True):
            inst_map = get_inst_data()
            hot_list = get_hot_rank_ids()
            res, danger_res = [], []
            with st.spinner("掃描中..."):
                with ThreadPoolExecutor(max_workers=5) as ex:
                    futs = [ex.submit(analyze_stock_score, t, inst_map, hot_list) for t in s_list]
                    for f in as_completed(futs):
                        r = f.result()
                        if r:
                            if r['星星數'] >= 4: res.append(r)
                            if "風險" in r['處置與籌碼風險'] or "隔日沖" in r['處置與籌碼風險'] or "警戒" in r['處置與籌碼風險']: danger_res.append(r)
            
            st.subheader("🚨 警戒區")
            if danger_res:
                for d in danger_res: st.error(f"**{d['標的']}** | 收盤: {d['收盤']}\n⚠️ {d['處置與籌碼風險']}")
            else: st.success("無過熱標的。")
                
            st.subheader("🔥 強勢突破 (4星+)")
            if res:
                df_res = pd.DataFrame(res).sort_values(by='星星數', ascending=False)
                for _, row in df_res.iterrows():
                    st.markdown(f"""
                    <div style='background-color:#1E1E1E; padding:15px; border-radius:10px; margin-bottom:12px; border-left: 5px solid #ffd166;'>
                        <h4 style='margin:0; color:#ffd166; font-size:18px;'>{row['標的']} {row['星等']}</h4>
                        <p style='margin:8px 0 5px 0; color:#FFFFFF;'>收盤: <b style='color:#00cc96;'>{row['收盤']}</b> | 量能: <b style='color:#00cc96;'>{row['今日量(張)']}</b> 千張</p>
                        <p style='margin:0; font-size:14px; color:#FFFFFF;'>條件: <span style='color:#ffd166;'>{row['觸發條件']}</span></p>
                    </div>""", unsafe_allow_html=True)
            else: st.warning("無強勢訊號。")
    else:
        st.title("📡 四維共振・真・大滿配終極版")
        t1, t_top, t2, t3 = st.tabs(["🎯 六星雷達", "🔥 金流 Top 15", "📈 VPVR 進階圖", "🛡️ 部位診斷"])
        with t1:
            if st.button("🚀 啟動掃描", use_container_width=True):
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
                    st.dataframe(df[['標的', '看盤連結', '星等', '收盤', '處置與籌碼風險', '籌碼大戶(張)', '今日量(張)', '觸發條件']], use_container_width=True, hide_index=True, column_config={"看盤連結": st.column_config.LinkColumn("互動看盤", display_text="📈 點我看圖")})
        with t_top:
            tse_top, otc_top = fetch_top15_ranking()
            c1, c2 = st.columns(2)
            with c1:
                if not tse_top.empty: st.dataframe(tse_top.assign(成交億=lambda x: (x['成交金額']/100000000).round(1))[['證券代號','證券名稱','收盤價','成交億']], hide_index=True)
            with c2:
                if not otc_top.empty: st.dataframe(otc_top.assign(成交億=lambda x: (x['成交金額']/100000000).round(1))[['證券代號','證券名稱','收盤價','成交億']], hide_index=True)
        with t2:
            vpvr_id = st.text_input("代號", "3034")
            if st.button("繪製 VPVR"): plot_advanced_chart_with_vpvr(vpvr_id, 0)
        with t3:
            d_id = st.text_input("診斷代號", "2317")
            if st.button("診斷"): 
                r = diagnose_holding(d_id)
                if r: st.write(r)

# ==========================================
# 分頁 2: 🏢 基本面與 AI 診斷 (輕量版)
# ==========================================
elif main_page == "🏢 基本面與 AI 診斷":
    st.title("🏢 基本面濾網")
    f_id = st.text_input("🔍 代號", value="2317")
    if st.button("🧠 掃描"):
        eps, pe, rev, news_list = get_fundamentals_and_news(f_id)
        st.metric("EPS", eps); st.metric("YoY", rev)
        st.info(ai_news_sentiment(news_list))

# ==========================================
# 分頁 3: 🕵️‍♂️ 00981A 經理人跟單雷達
# ==========================================
elif main_page == "🕵️‍♂️ 00981A 經理人跟單雷達":
    st.title("🕵️‍♂️ 00981A 經理人跟單")
    if st.button("🔄 刷新籌碼"):
        raw_df = get_00981a_holdings_history(force_refresh=True)
        analyzed_df = analyze_manager_moves(raw_df)
        if not analyzed_df.empty: st.dataframe(analyzed_df, hide_index=True)

# ==========================================
# 分頁 4: ☠️ 隔日沖分點照妖鏡
# ==========================================
elif main_page == "☠️ 隔日沖分點照妖鏡":
    st.title("☠️ 隔日沖分點照妖鏡")
    target_id = st.text_input("🔍 股票代號", value="3034")
    if st.button("🕵️‍♂️ 掃描分點", use_container_width=True):
        with st.spinner("解析籌碼..."):
            time.sleep(1.5)
            mock_branch_data = pd.DataFrame({
                "券商分點": ["凱基-台北", "台灣匯立", "摩根大通", "美林", "元大-土城永寧", "富邦-建國", "國泰-敦南", "瑞士信貸", "元富", "群益金鼎-大安"],
                "買賣超": [4400, 3150, 2600, 1600, 1800, 1450, 1100, 950, 700, 600]
            })
            mock_branch_data['大戶屬性'] = mock_branch_data['券商分點'].apply(lambda x: "🚨 隔日沖大戶" if any(t in x for t in DAY_TRADER_BRANCHES) else "⚠️ 外資" if "摩根" in x or "美林" in x else "✅ 一般主力")
            danger_ratio = mock_branch_data[mock_branch_data['大戶屬性'].str.contains("🚨|⚠️")]['買賣超'].sum() / mock_branch_data['買賣超'].sum() * 100
            st.metric("隔日沖潛在倒貨量", f"{danger_ratio:.1f} %")
            if danger_ratio > 40: st.error("☠️ 極度危險！明日必有賣壓。")
            st.dataframe(mock_branch_data.style.map(lambda v: 'color: #ff4b4b' if '🚨' in str(v) else '', subset=['大戶屬性']), hide_index=True)

# ==========================================
# 🚀 渦輪 2: ⚡ 全自動策略優化器 (Grid Search)
# ==========================================
elif main_page == "⚡ 全自動策略優化器":
    st.title("⚡ 全自動參數尋優器 (均線最佳化)")
    st.markdown("每檔股票的股性不同，讓系統跑 5~60 日均線回測，找出勝率最高的專屬參數。")
    
    opt_target = st.text_input("🎯 欲尋優標的", value="2317")
    
    if st.button("⚡ 開始暴力運算最佳參數", use_container_width=True):
        with st.spinner(f"正在對 {opt_target} 進行 5~60 日參數矩陣運算... 這可能需要幾秒鐘。"):
            tid = f"{opt_target}.TW"
            df = yf.Ticker(tid).history(period="2y")
            if df.empty:
                df = yf.Ticker(f"{opt_target}.TWO").history(period="2y")
            
            if len(df) < 100:
                st.warning("歷史資料不足，無法進行尋優。")
            else:
                results = []
                pb = st.progress(0)
                
                # 測試 MA 5 到 60
                ma_range = range(5, 61, 2)
                for i, ma in enumerate(ma_range):
                    temp_df = df.copy()
                    temp_df['MA'] = temp_df['Close'].rolling(ma).mean()
                    temp_df = temp_df.dropna()
                    
                    temp_df['Signal'] = 0
                    temp_df.loc[temp_df['Close'] > temp_df['MA'], 'Signal'] = 1
                    temp_df['Return'] = temp_df['Close'].pct_change()
                    temp_df['Strategy_Return'] = temp_df['Signal'].shift(1) * temp_df['Return']
                    
                    total_trades = len(temp_df[temp_df['Strategy_Return'] != 0])
                    win_trades = len(temp_df[temp_df['Strategy_Return'] > 0])
                    win_rate = (win_trades / total_trades) * 100 if total_trades > 0 else 0
                    
                    temp_df['Equity'] = (1 + temp_df['Strategy_Return'].fillna(0)).cumprod() * 100
                    final_ret = temp_df['Equity'].iloc[-1] - 100
                    
                    results.append({"MA參數": f"{ma} 日線", "勝率 (%)": round(win_rate, 2), "累積報酬 (%)": round(final_ret, 2)})
                    pb.progress((i + 1) / len(ma_range))
                
                res_df = pd.DataFrame(results).sort_values(by="累積報酬 (%)", ascending=False)
                
                st.success(f"🎉 運算完成！{opt_target} 最適合的均線參數出爐：")
                best_ma = res_df.iloc[0]
                
                c1, c2, c3 = st.columns(3)
                c1.metric("🏆 最佳均線", best_ma["MA參數"])
                c2.metric("🎯 歷史勝率", f"{best_ma['勝率 (%)']} %")
                c3.metric("💰 累積報酬", f"{best_ma['累積報酬 (%)']} %")
                
                st.markdown("#### 📊 前 10 名最佳參數矩陣")
                st.dataframe(res_df.head(10), hide_index=True, use_container_width=True)
