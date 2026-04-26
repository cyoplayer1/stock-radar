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

# === 系統設定與警告停用 ===
warnings.filterwarnings("ignore")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 設定網頁標題與版面寬度
st.set_page_config(page_title="綜合投資分析站", page_icon="📡", layout="wide")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# ================= 核心計算函數 =================
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
            k_values.append(50.0); d_values.append(50.0)
        else:
            k = (2/3) * k + (1/3) * rsv
            d = (2/3) * d + (1/3) * k
            k_values.append(k); d_values.append(d)
    df['K'], df['D'] = k_values, d_values
    return df

def analyze_stock_score(ticker, stock_name):
    """技術面評分系統"""
    try:
        stock = yf.Ticker(ticker)
        df_daily = stock.history(period="1y")
        df_daily.dropna(subset=['Close', 'Volume'], inplace=True)
        if df_daily.empty or len(df_daily) < 60: return None
        
        close_price = df_daily['Close'].iloc[-1]
        avg_vol_5d = df_daily['Volume'].tail(5).mean()
        
        # 過濾成交量太小的標的 (5日均量大於1000張)
        if avg_vol_5d < 1000000:
            return None
            
        score = 0
        tags = []
        
        # 1. 均線評分 (20MA)
        df_daily['20MA'] = df_daily['Close'].rolling(window=20).mean()
        if close_price > df_daily['20MA'].iloc[-1]:
            score += 20; tags.append("[站上月線]")
            
        # 2. 日KD評分
        df_daily = calculate_kd(df_daily.copy())
        k, d = df_daily['K'].iloc[-1], df_daily['D'].iloc[-1]
        yk, yd = df_daily['K'].iloc[-2], df_daily['D'].iloc[-2]
        if k > d and yk <= yd:
            score += 40; tags.append("[日剛金叉]")
        elif k > d:
            score += 20; tags.append("[日線偏多]")
            
        clean_ticker = ticker.replace('.TW', '').replace('.TWO', '')
        return {
            '標的名稱': f"{clean_ticker} {stock_name}",
            '評分': score,
            '收盤價': round(close_price, 2),
            '技術面狀態': " + ".join(tags) if tags else "空頭休息",
            '日K': round(k, 1),
            '5日均量(張)': int(avg_vol_5d / 1000),
            'ticker': ticker
        }
    except: return None

# ================= 股市排行系統 函數 (加入快取機制) =================
@st.cache_data(ttl=300)
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
        
        if not stock_data: return None, data.get('stat', '找不到上市股票資料')

        df = pd.DataFrame(stock_data, columns=fields)
        df = df[['證券代號', '證券名稱', '成交金額']]
        df['成交金額'] = df['成交金額'].astype(str).str.replace(',', '')
        df['成交金額'] = pd.to_numeric(df['成交金額'], errors='coerce').fillna(0)
        df_sorted = df.sort_values(by='成交金額', ascending=False).head(15)
        df_sorted['成交金額(元)'] = df_sorted['成交金額'].apply(lambda x: f"{int(x):,}")
        df_sorted = df_sorted.drop(columns=['成交金額'])
        df_sorted.index = range(1, 16)
        return df_sorted, "OK"
    except Exception as e: return None, f"上市錯誤: {e}"

@st.cache_data(ttl=300)
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
        if not stock_data: return None, "找不到上櫃股票資料"

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
    except Exception as e: return None, f"上櫃錯誤: {e}"

# ================= 預設監控清單 (百大旗艦) =================
STOCKS = {
    # 權值與半導體
    "2330.TW": "台積電", "2317.TW": "鴻海", "2454.TW": "聯發科", "2308.TW": "台達電",
    "2303.TW": "聯電", "3711.TW": "日月光", "2408.TW": "南亞科", "2344.TW": "華邦電",
    "3443.TW": "創意", "3661.TW": "世芯KY", "3034.TW": "聯詠", "2379.TW": "瑞昱",
    # AI 伺服器與周邊
    "2382.TW": "廣達", "3231.TW": "緯創", "6669.TW": "緯穎", "2356.TW": "英業達",
    "2376.TW": "技嘉", "2377.TW": "微星", "3017.TW": "奇鋐", "3324.TW": "雙鴻",
    # 重電、航運與高息ETF
    "1519.TW": "華城", "1503.TW": "士電", "1513.TW": "中興電", "2603.TW": "長榮", 
    "2609.TW": "陽明", "2618.TW": "長榮航", "00878.TW": "國泰永續", "00919.TW": "群益高息", 
    "00929.TW": "復華科技", "00713.TW": "高息低波", "8441.TW": "可寧衛", "8390.TWO": "金益鼎"
}

# ================= 視覺化上色函數 =================
def style_stock_dataframe(val):
    """台股習慣：紅色代表強勢/上漲，綠色代表弱勢/下跌"""
    if isinstance(val, str):
        if any(keyword in val for keyword in ['金叉', '多', '站上']):
            return 'color: #ff4b4b; font-weight: bold;'
        elif any(keyword in val for keyword in ['空', '休息']):
            return 'color: #00fa9a;'
    return ''

# ================= 網頁主畫面配置 =================
st.title("📡 綜合投資分析站 V3.0")

# 建立三個標籤頁
tab1, tab2, tab3 = st.tabs(["🎯 股神系統雷達", "💰 股市成交排行", "📈 互動看盤分析"])

# ----------------- 第一頁：股神系統雷達 -----------------
with tab1:
    st.markdown("### 操盤室級別：【技術面熱力雷達評分系統 - 百大旗艦版】")
    st.markdown("---")
    
    if st.button("🚀 啟動雷達掃描", use_container_width=True):
        start_time = time.time()
        scored_stocks = []
        processed_count = 0
        total_stocks = len(STOCKS)
        
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
        
        progress_bar.empty()
        status_text.empty()
        st.success(f"✅ 掃描完成！總耗時 {round(end_time - start_time, 1)} 秒。")
        
        if scored_stocks:
            df_result = pd.DataFrame(scored_stocks)
            df_result = df_result.sort_values(by=['評分', '日K'], ascending=[False, False])
            df_result['評分'] = df_result['評分'].astype(str) + "分"
            df_result = df_result.head(30)
            df_result.index = range(1, len(df_result) + 1)
            
            st.subheader("🔥 目前大盤最強的 30 檔標的")
            # 隱藏用不到的 ticker 欄位並上色
            styled_df = df_result.drop(columns=['ticker']).style.map(style_stock_dataframe, subset=['技術面狀態'])
            st.dataframe(styled_df, use_container_width=True)
        else:
            st.error("連資料都抓不到，可能是網路連線問題。")

# ----------------- 第二頁：股市排行 -----------------
with tab2:
    st.markdown("### 台股前 15 大成交值排行榜")
    st.markdown("*(資料每 5 分鐘自動快取更新，保護伺服器不被封鎖)*")
    st.markdown("---")
    
    if st.button('🔄 強制重新抓取排行數據'):
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

# ----------------- 第三頁：互動看盤分析 -----------------
with tab3:
    st.markdown("### 📊 專業互動式 K 線看盤區")
    st.markdown("---")
    
    col_input, _ = st.columns([1, 3])
    with col_input:
        stock_input = st.text_input("輸入台股代號 (例如: 2330 或 00919)", value="2330")
        period = st.selectbox("選擇觀察區間", ["3個月", "6個月", "1年", "2年"], index=1)
    
    period_map = {"3個月": "3mo", "6個月": "6mo", "1年": "1y", "2年": "2y"}
    # 處理台股代號邏輯 (自動補上 .TW，如果是上櫃股票請自行輸入 .TWO)
    if "." not in stock_input:
        # 簡單判斷：如果是ETF(00開頭)或常見上市代號預設加.TW
        ticker_full = stock_input + ".TW"
    else:
        ticker_full = stock_input
    
    with st.spinner("圖表載入中..."):
        try:
            data = yf.Ticker(ticker_full).history(period=period_map[period])
            if data.empty:
                st.warning("查無資料！如果是上櫃股票，請在代號後加上 `.TWO` (例如: 8299.TWO)")
            else:
                data = calculate_kd(data)
                data['5MA'] = data['Close'].rolling(window=5).mean()
                data['20MA'] = data['Close'].rolling(window=20).mean()
                data['60MA'] = data['Close'].rolling(window=60).mean()
                
                # 建立上下兩個子圖 (K線區 70%，KD區 30%)
                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.7, 0.3])
                
                # 上圖：K線與均線
                fig.add_trace(go.Candlestick(x=data.index, open=data['Open'], high=data['High'], low=data['Low'], close=data['Close'], name='K線'), row=1, col=1)
                fig.add_trace(go.Scatter(x=data.index, y=data['5MA'], line=dict(color='white', width=1), name='5MA'), row=1, col=1)
                fig.add_trace(go.Scatter(x=data.index, y=data['20MA'], line=dict(color='orange', width=1.5), name='20MA'), row=1, col=1)
                fig.add_trace(go.Scatter(x=data.index, y=data['60MA'], line=dict(color='cyan', width=1), name='60MA'), row=1, col=1)
                
                # 下圖：KD指標
                fig.add_trace(go.Scatter(x=data.index, y=data['K'], line=dict(color='#ffeb3b', width=1.5), name='K值'), row=2, col=1) # 黃色K
                fig.add_trace(go.Scatter(x=data.index, y=data['D'], line=dict(color='#03a9f4', width=1.5), name='D值'), row=2, col=1) # 藍色D
                fig.add_hline(y=80, line_dash="dash", line_color="#ff4b4b", row=2, col=1) # 超買區紅線
                fig.add_hline(y=20, line_dash="dash", line_color="#00fa9a", row=2, col=1) # 超賣區綠線
                
                # 調整圖表外觀
                fig.update_layout(
                    height=700, 
                    template="plotly_dark", 
                    xaxis_rangeslider_visible=False, 
                    margin=dict(l=10, r=10, t=10, b=10),
                    hovermode="x unified"
                )
                
                st.plotly_chart(fig, use_container_width=True)
                
        except Exception as e:
            st.error(f"繪圖發生錯誤: {e}")
