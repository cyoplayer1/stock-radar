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
import json
import numpy as np
import xml.etree.ElementTree as ET
from gtts import gTTS
import io

# === 1. 系統環境設定與機密管理 ===
warnings.filterwarnings("ignore")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
st.set_page_config(page_title="阿綜專屬：究極軍規雷達 v2.0", page_icon="📡", layout="wide")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
HEADERS = {"User-Agent": UA}

# 🛡️ 安全升級：改用 Streamlit Secrets 管理 API Key，避免金鑰外洩
try:
    FUGLE_API_KEY = st.secrets["FUGLE_API_KEY"]
except (FileNotFoundError, KeyError):
    FUGLE_API_KEY = "54f80721-6cad-4ec9-9679-c5a315e7b00b" # 備用預設金鑰 (強烈建議建立 .streamlit/secrets.toml)
    st.sidebar.warning("⚠️ 偵測到尚未設定 secrets.toml，目前使用預設 API Key。")

# === 2. 外部設定檔掛載 (名單解耦機制) ===
CONFIG_FILE = "system_config.json"
DEFAULT_STOCKS = {
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
DEFAULT_SECTORS = {
    "2330": "半導體", "2454": "半導體", "3661": "半導體", "3034": "半導體",
    "2317": "AI伺服器", "3231": "AI伺服器", "2382": "AI伺服器", "2356": "AI伺服器",
    "3017": "散熱模組", "3324": "散熱模組", "3653": "散熱模組", "6805": "軸承",
    "2383": "PCB零組件", "2368": "PCB零組件", "3533": "連接器", "3037": "PCB零組件",
    "2308": "電源供應", "2345": "網通", "2603": "航運", "2609": "航運", "2881": "金融"
}

if not os.path.exists(CONFIG_FILE):
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump({"STOCKS_DICT": DEFAULT_STOCKS, "SECTOR_MAP": DEFAULT_SECTORS}, f, ensure_ascii=False, indent=4)
    except Exception as e:
        st.toast(f"建立設定檔失敗: {e}")

try:
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        config_data = json.load(f)
    STOCKS_DICT = config_data.get("STOCKS_DICT", DEFAULT_STOCKS)
    SECTOR_MAP = config_data.get("SECTOR_MAP", DEFAULT_SECTORS)
except Exception as e:
    STOCKS_DICT = DEFAULT_STOCKS
    SECTOR_MAP = DEFAULT_SECTORS
    st.toast(f"讀取設定檔失敗，使用系統預設名單: {e}")

# 建立純數字 ID 映射到完整後綴 ID 的字典 (如: "2330" -> "2330.TW")
CLEAN_TO_FULL_MAP = {k.split('.')[0]: k for k in STOCKS_DICT.keys()}

DAY_TRADER_BRANCHES = [
    "凱基-台北", "富邦-建國", "元大-土城永寧", "群益金鼎-大安", 
    "統一-城中", "康和-延平", "元富-城東", "摩根大通", "美林"
]

# === 3. 👁️ 瀏覽次數統計機制 ===
def get_and_increment_view_count():
    count_file = "page_views.txt"
    if os.path.exists(count_file):
        try:
            with open(count_file, "r") as f:
                count = int(f.read().strip())
        except:
            count = 0
    else:
        count = 0
        
    if 'has_viewed' not in st.session_state:
        count += 1
        try:
            with open(count_file, "w") as f:
                f.write(str(count))
            st.session_state['has_viewed'] = True
        except Exception:
            pass
    return count

# === 4. 🛡️ 安全連線防護機制 ===
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
        except Exception as e:
            # st.toast(f"網路連線異常: {e}") # 避免太頻繁彈出
            break
    return {}

# === 5. V8 雙渦輪引擎：YFinance 批次高速下載 (解決效能瓶頸) ===
@st.cache_data(ttl=900)
def fetch_bulk_yf_data(full_ticker_list, period="1y"):
    """使用批次下載，大幅降低 API 請求次數，防止 IP 被 Yahoo 封鎖"""
    if not full_ticker_list: return {}
    
    # 確保不會傳遞空字串
    valid_tickers = [t for t in full_ticker_list if t]
    tickers_str = " ".join(valid_tickers)
    res_dict = {}
    
    try:
        # bulk download
        data = yf.download(tickers_str, period=period, threads=True, progress=False)
        
        if len(valid_tickers) == 1:
            # 如果只有一檔，yfinance 不會回傳 MultiIndex
            df_t = data.dropna(subset=['Close'])
            if not df_t.empty:
                res_dict[valid_tickers[0]] = df_t
        else:
            # 多檔股票，解析 MultiIndex
            for t in valid_tickers:
                try:
                    df_t = pd.DataFrame({
                        'Open': data['Open'][t],
                        'High': data['High'][t],
                        'Low': data['Low'][t],
                        'Close': data['Close'][t],
                        'Volume': data['Volume'][t]
                    }).dropna(subset=['Close'])
                    if not df_t.empty:
                        res_dict[t] = df_t
                except Exception:
                    continue
        return res_dict
    except Exception as e:
        st.toast(f"YFinance 批次引擎下載失敗，嘗試降級運作: {e}")
        return {}

# === 6. 核心指標與大盤風向球 ===
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
    except Exception as e: 
        st.toast(f"大盤指標抓取異常: {e}")
    return None, None, "⚪ 系統連線中"

# === 🌟 側邊欄模組 A1：美股大腦 ===
def us_market_brain():
    st.sidebar.markdown("---")
    st.sidebar.subheader("🌐 美股連動觀測")
    us_tickers = {"TSM": "台積電 ADR", "ARM": "安謀 (Arm)", "NVDA": "輝達 (NVIDIA)"}
    
    for ticker, name in us_tickers.items():
