import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import warnings
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib3

# === 系統設定與警告停用 ===
warnings.filterwarnings("ignore")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 設定網頁標題與版面寬度
st.set_page_config(page_title="綜合投資分析站", page_icon="📡", layout="wide")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# ================= 股神雷達系統 函數 =================
def calculate_kd(df):
    """計算 KD 值 (台灣標準 9,3,3)"""
    if len(df) < 9: return df
    df['9_min'] = df['Low'].rolling(window=9).min()
    df['9_max'] = df['High'].rolling(window=9).max()
    df['RSV'] = (df['Close'] - df['9_min']) / (df['9_max'] - df['9_min']) * 100
    
    k_values, d_values = [], []
    k, d = 50.0, 50.0
    for rsv in df['RSV']:
        if pd.isna(rsv):
            k_values.append(50.0)
            d_values.append(50.0)
        else:
            k = (2/3) * k + (1/3) * rsv
            d = (2/3) * d + (1/3) * k
            k_values.append(k)
            d_values.append(d)
    df['K'], df['D'] = k_values, d_values
    return df

def analyze_stock_score(ticker, stock_name):
    """評分系統，並帶入股票中文名稱"""
    try:
        stock = yf.Ticker(ticker)
        df_daily = stock.history(period="2y")
        df_daily.dropna(subset=['Close', 'Volume'], inplace=True)
        
        if df_daily.empty or len(df_daily) < 60: return None
        
        close_price = df_daily['Close'].iloc[-1]
        avg_vol_5d = df_daily['Volume'].tail(5).mean()
        
        if avg_vol_5d < 1000000:
            return None
            
        score = 0
        status_tags = []

        df_daily['20MA'] = df_daily['Close'].rolling(window=20).mean()
        if close_price > df_daily['20MA'].iloc[-1]:
            score += 20
            status_tags.append("[站上月線]")

        df_daily = calculate_kd(df_daily.copy())
        d_k, d_d = df_daily['K'].iloc[-1], df_daily['D'].iloc[-1]
        d_yest_k, d_yest_d = df_daily['K'].iloc[-2], df_daily['D'].iloc[-2]
        
        if (d_k > d_d) and (d_yest_k <= d_yest_d):
            score += 40
            status_tags.append("[日剛金叉]")
        elif d_k > d_d:
            score += 20
            status_tags.append("[日線偏多]")
            
        df_weekly = df_daily.resample('W-FRI').agg({
            'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
        }).dropna()
        df_weekly = calculate_kd(df_weekly.copy())
        w_k, w_d = df_weekly['K'].iloc[-1], df_weekly['D'].iloc[-1]
        
        if w_k > w_d:
            score += 40
            status_tags.append("[周線偏多]")

        clean_ticker = ticker.replace('.TW', '').replace('.TWO', '')
        return {
            '標的名稱': f"{clean_ticker} {stock_name}",
            '評分': f"{score}分",
            '收盤價': round(close_price, 2),
            '技術面狀態': " + ".join(status_tags) if status_tags else "空頭休息",
            '日K': round(d_k, 1),
            '周K': round(w_k, 1),
            '5日均量(張)': int(avg_vol_5d / 1000)
        }
    except Exception:
        return None

STOCKS = {
    # === 權值與半導體 ===
    "2330.TW": "台積電", "2317.TW": "鴻海", "2454.TW": "聯發科", "2308.TW": "台達電",
    "2303.TW": "聯電", "3711.TW": "日月光", "2408.TW": "南亞科", "2344.TW": "華邦電",
    "2337.TW": "旺宏", "3443.TW": "創意", "3661.TW": "世芯KY", "3034.TW": "聯詠",
    "2379.TW": "瑞昱", "4966.TW": "譜瑞KY", "6415.TW": "矽力KY", "3529.TW": "力旺",
    "6488.TWO": "環球晶", "5483.TWO": "中美晶", "3105.TWO": "穩懋", "8299.TWO": "群聯",
    # === AI 伺服器與電腦周邊 ===
    "2382.TW": "廣達", "3231.TW": "緯創", "6669.TW": "緯穎", "2356.TW": "英業達",
    "2324.TW": "仁寶", "2353.TW": "宏碁", "2357.TW": "華碩", "2376.TW": "技嘉",
    "2377.TW": "微星", "3017.TW": "奇鋐", "3324.TW": "雙鴻", "3653.TW": "健策",
    "3533.TW": "嘉澤", "3013.TW": "晟銘電", "8210.TW": "勤誠","7769.TW": "鴻勁",
    # === PCB 與電子零組件 ===
    "3037.TW": "欣興", "8046.TW": "南電", "3189.TW": "景碩", "2368.TW": "金像電",
    "4958.TW": "臻鼎KY", "2313.TW": "華通", "6274.TWO": "台燿", "2383.TW": "台光電",
    "6213.TW": "聯茂", "3008.TW": "大立光", "3406.TW": "玉晶光",
    # === 重電、綠能與傳產 ===
    "1519.TW": "華城", "1503.TW": "士電", "1513.TW": "中興電", "1504.TW": "東元",
    "1605.TW": "華新", "1101.TW": "台泥", "1102.TW": "亞泥", "2002.TW": "中鋼",
    "2027.TW": "大成鋼", "2014.TW": "中鴻", "2207.TW": "和泰車", "9910.TW": "豐泰",
    "9921.TW": "巨大", "9904.TW": "寶成",
    # === 航運與網通 ===
    "2603.TW": "長榮", "2609.TW": "陽明", "2615.TW": "萬海", "2618.TW": "長榮航",
    "2610.TW": "華航", "2606.TW": "裕民", "3596.TW": "智易", "5388.TWO": "中磊",
    "3380.TW": "明泰", "2345.TW": "智邦",
    # === 金融業 ===
    "2881.TW": "富邦金", "2882.TW": "國泰金", "2891.TW": "中信金", "2886.TW": "兆豐金",
    "2884.TW": "玉山金", "2892.TW": "第一金", "2880.TW": "華南金", "2885.TW": "元大金",
    "2890.TW": "永豐金", "2883.TW": "開發金", "2887.TW": "台新金", "5880.TW": "合庫金",
    # === 其他熱門與 ETF ===
    "8069.TWO": "元太", "3293.TWO": "鈊象", "8436.TW": "大江",
    "0050.TW": "台灣50", "0056.TW": "高股息", "00878.TW": "國泰永續", "00919.TW": "群益高息",
    "00929.TW": "復華科技", "00713.TW": "高息低波", "006208.TW": "富邦台50","6789.TW": "采鈺","6147.TWO": "頎邦"
}

# ================= 股市排行系統 函數 =================
def get_twse_top_15():
    """獲取上市（TWSE）成交值前 15 大股票"""
    url = "https://www.twse.com.tw/exchangeReport/MI_INDEX?response=json&type=ALLBUT0999"
    try:
        res = requests.get(url, headers=HEADERS, verify=False, timeout=10)
        data = res.json()
        stock_data, fields = None, None
        
        if 'tables' in data:
            for table in data['tables']:
                if 'fields' in table and 'data' in table:
                    if '證券代號' in table['fields'] and '成交金額' in table['fields']:
                        fields = table['fields']
                        stock_data = table['data']
                        break
        
        if not stock_data:
            for key, val in data.items():
                if key.startswith('fields') and isinstance(val, list):
                    if '證券代號' in val and '成交金額' in val:
                        data_key = key.replace('fields', 'data')
                        if data_key in data:
                            fields = val
                            stock_data = data[data_key]
                            break
        
        if not stock_data:
            return None, data.get('stat', '找不到上市股票資料')

        df = pd.DataFrame(stock_data, columns=fields)
        df = df[['證券代號', '證券名稱', '成交金額']]
        df['成交金額'] = df['成交金額'].astype(str).str.replace(',', '')
        df['成交金額'] = pd.to_numeric(df['成交金額'], errors='coerce').fillna(0)
        df_sorted = df.sort_values(by='成交金額', ascending=False).head(15)
        df_sorted['成交金額(元)'] = df_sorted['成交金額'].apply(lambda x: f"{int(x):,}")
        df_sorted = df_sorted.drop(columns=['成交金額'])
        df_sorted.index = range(1, 16)
        return df_sorted, "OK"
    except Exception as e:
        return None, f"上市錯誤: {e}"

def get_tpex_top_15():
    """獲取上櫃（TPEx）成交值前 15 大股票"""
    url = "https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php?l=zh-tw&o=json"
    try:
        res = requests.get(url, headers=HEADERS, verify=False, timeout=10)
        data = res.json()
        stock_data = []
        if 'aaData' in data and data['aaData']:
            stock_data = data['aaData']
        elif 'tables' in data:
            for table in data['tables']:
                if 'data' in table and len(table['data']) > 0:
                    stock_data = table['data']
                    break
        if not stock_data:
            return None, "找不到上櫃股票資料"

        df = pd.DataFrame(stock_data)
        col_val = 9 if df.shape[1] >= 10 else df.shape[1] - 2
        df = df[[0, 1, col_val]]
        df.columns = ['證券代號', '證券名稱', '成交金額']
        df['成交金額'] = df['成交金額'].astype(str).str.replace(',', '')
        df['成交金額'] = pd.to_numeric(df['成交金額'], errors='coerce').fillna(0)
        df_sorted = df.sort_values(by='成交金額', ascending=False).head(15)
        df_sorted['成交金額(元)'] = df_sorted['成交金額'].apply(lambda x: f"{int(x):,}")
        df_sorted = df_sorted.drop(columns=['成交金額'])
        df_sorted.index = range(1, 16)
        return df_sorted, "OK"
    except Exception as e:
        return None, f"上櫃錯誤: {e}"


# ================= 網頁主畫面配置 =================
st.title("📡 綜合投資分析站")

# 建立兩個標籤頁
tab1, tab2 = st.tabs(["🎯 股神系統雷達", "💰 股市成交排行"])

# ----------------- 第一頁：股神系統雷達 -----------------
with tab1:
    st.markdown("### 操盤室級別：【技術面熱力雷達評分系統 - 百大旗艦版】")
    st.markdown("---")
    
    if st.button("🚀 啟動雷達掃描", use_container_width=True):
        start_time = time.time()
        scored_stocks = []
        processed_count = 0
        total_stocks = len(STOCKS)
        
        # 建立網頁進度條與狀態文字
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_ticker = {executor.submit(analyze_stock_score, ticker, name): ticker for ticker, name in STOCKS.items()}
            
            for future in as_completed(future_to_ticker):
                processed_count += 1
                progress_bar.progress(processed_count / total_stocks)
                status_text.text(f"🔄 雷達掃描中: {processed_count}/{total_stocks} 檔標的...")
                
                result = future.result()
                if result:
                    scored_stocks.append(result)
                    
        end_time = time.time()
        
        # 掃描結束，清除進度條，顯示完成訊息
        progress_bar.empty()
        status_text.empty()
        st.success(f"✅ 掃描完成！總耗時 {round(end_time - start_time, 1)} 秒。")
        
        if scored_stocks:
            df_result = pd.DataFrame(scored_stocks)
            df_result['Sort_Score'] = df_result['評分'].str.replace('分', '').astype(int)
            df_result = df_result.sort_values(by=['Sort_Score', '日K'], ascending=[False, False])
            df_result = df_result.drop(columns=['Sort_Score'])
            
            df_result = df_result.head(30)
            df_result.index = range(1, len(df_result) + 1)
            
            st.subheader("🔥 目前大盤最強的 30 檔標的")
            st.dataframe(df_result, use_container_width=True)
        else:
            st.error("連資料都抓不到，可能是網路連線問題。")

# ----------------- 第二頁：股市排行 -----------------
with tab2:
    st.markdown("### 台股前 15 大成交值排行榜")
    st.markdown("---")
    
    if st.button('🔄 重新抓取排行數據'):
        st.cache_data.clear()

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📈 上市 (TWSE)")
        with st.spinner("抓取上市資料中..."):
            df_twse, msg_twse = get_twse_top_15()
            if df_twse is not None:
                st.dataframe(df_twse, use_container_width=True)
            else:
                st.error(msg_twse)

    with col2:
        st.subheader("📉 上櫃 (TPEx)")
        with st.spinner("抓取上櫃資料中..."):
            df_tpex, msg_tpex = get_tpex_top_15()
            if df_tpex is not None:
                st.dataframe(df_tpex, use_container_width=True)
            else:
                st.error(msg_tpex)
