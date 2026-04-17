import streamlit as st
import pandas as pd
from vnstock import Vnstock
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
import time

# ---------------------------------------------------------
# 1. CẤU HÌNH HỆ THỐNG & GIAO DIỆN
# ---------------------------------------------------------
st.set_page_config(page_title="Hệ thống giao dịch Đa khung thời gian", layout="wide")

# CSS để làm giao diện tối và hiện đại hơn
st.markdown("""
    <style>
    .main {background-color: #0e1117;}
    .stMetric {background-color: #161b22; padding: 15px; border-radius: 10px;}
    </style>
    """, unsafe_allow_html=True)

# Danh sách 100 mã thanh khoản (Đã tối ưu)
TOP_MARKET = [
    'SSI', 'VIX', 'VND', 'SHS', 'HPG', 'DIG', 'NVL', 'PDR', 'STB', 'MBB', 
    'SHB', 'VPB', 'TCB', 'ACB', 'VHM', 'VIC', 'VNM', 'MWG', 'FPT', 'MSN',
    'GEX', 'HSG', 'NKG', 'KBC', 'VCI', 'HCM', 'CEO', 'IDC', 'TCH', 'DXG',
    'LPB', 'HDB', 'CTG', 'BID', 'VCB', 'TPB', 'VIB', 'MSB', 'OCB', 'EIB',
    'DGC', 'DCM', 'DPM', 'CSV', 'PNJ', 'REE', 'PC1', 'HDG', 'GEG', 'POW',
    'KDH', 'NLG', 'SZC', 'VGC', 'BCM', 'PHR', 'GVR', 'DPR', 'AAA', 'ASM',
    'IDI', 'ANV', 'VHC', 'FMC', 'MPC', 'HAH', 'GMD', 'VOS', 'PVT', 'PVS',
    'PVD', 'BSR', 'OIL', 'PLX', 'GAS', 'SAB', 'BHN', 'SBT', 'QNS', 'LSS',
    'MBS', 'CTS', 'AGR', 'BSI', 'FTS', 'TNG', 'VGT', 'GIL', 'TCM', 'HT1',
    'BCC', 'KSB', 'CII', 'HUT', 'LCG', 'HHV', 'VCG', 'FCN', 'CTD', 'HBC'
]

TF_MAP = {"15 Phút": "15", "1 Giờ": "1H", "Ngày": "1D", "Tuần": "1W", "Tháng": "1M"}

# ---------------------------------------------------------
# 2. CÁC HÀM XỬ LÝ LOGIC (ĐỊNH NGHĨA TRƯỚC KHI DÙNG)
# ---------------------------------------------------------

@st.cache_data(ttl=300) # Lưu cache 5 phút để tăng tốc khi quay lại mã cũ
def get_data(symbol, tf):
    try:
        # Sử dụng nguồn DNSE hoặc KBS linh hoạt
        stock = Vnstock().stock(symbol=symbol, source='VCI') 
        df = stock.quote.history(start='2024-01-01', end=datetime.now().strftime('%Y-%m-%d'), interval=TF_MAP[tf])
        return df
    except Exception:
        return pd.DataFrame()

def calculate_signals(df):
    if df.empty or len(df) < 50: 
        return None
    
    # Tính toán các chỉ số cơ bản
    df['SMA20'] = df['close'].rolling(20).mean()
    df['SMA50'] = df['close'].rolling(50).mean()
    df['SMA200'] = df['close'].rolling(200).mean() if len(df) >= 200 else df['close'].rolling(50).mean()
    
    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['RSI'] = 100 - (100 / (1 + gain/(loss + 1e-9)))
    
    # MACD
    exp1 = df['close'].ewm(span=12, adjust=False).mean()
    exp2 = df['close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp1 - exp2
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    
    # Ichimoku cơ bản
    df['SpanA'] = ((df['high'].rolling(9).max() + df['low'].rolling(9).min())/2 + (df['high'].rolling(26).max() + df['low'].rolling(26).min())/2)/2
    df['SpanA_Shift'] = df['SpanA'].shift(26)

    # Hệ thống bỏ phiếu (Voting System)
    v1 = 1 if df['close'].iloc[-1] > df['SMA200'].iloc[-1] else -1
    v2 = 1 if df['SMA20'].iloc[-1] > df['SMA50'].iloc[-1] else -1
    v3 = 1 if df['MACD'].iloc[-1] > df['Signal'].iloc[-1] else -1
    v4 = 1 if df['RSI'].iloc[-1] < 35 else (-1 if df['RSI'].iloc[-1] > 70 else 0)
    v5 = 1 if df['close'].iloc[-1] > df['SpanA_Shift'].iloc[-1] else -1
    v6 = 1 if df['volume'].iloc[-1] > df['volume'].rolling(20).mean().iloc[-1] else 0
    
    buy_score = (max(0,v1) + max(0,v2) + max(0,v3) + max(0,v4) + max(0,v5) + max(0,v6)) / 6
    sell_score = (abs(min(0,v1)) + abs(min(0,v2)) + abs(min(0,v3)) + abs(min(0,v4)) + abs(min(0,v5))) / 5
    
    return buy_score, sell_score, df

# ---------------------------------------------------------
# 3. SIDEBAR (ĐỊNH NGHĨA BIẾN TRƯỚC KHI SỬ DỤNG)
# ---------------------------------------------------------
st.sidebar.title("🛠️ Điều khiển")
mode = st.sidebar.radio("Chế độ", ["Phân tích chi tiết mã", "Quét tín hiệu toàn thị trường"])
timeframe = st.sidebar.selectbox("Khung thời gian", ["Ngày", "15 Phút", "1 Giờ", "Tuần", "Tháng"])

# ---------------------------------------------------------
# 4. MAIN LOGIC (XỬ LÝ DỰA TRÊN BIẾN MODE)
# ---------------------------------------------------------

if mode == "Quét tín hiệu toàn thị trường":
    st.header(f"🔍 Trình quét Top 100 thanh khoản (Khung: {timeframe})")
    
    if st.button("Bắt đầu quét danh mục"):
        results = []
        progress_bar = st.progress(0)
        status_msg = st.empty()
        
        for idx, s in enumerate(TOP_MARKET):
            status_msg.text(f" đang quét mã: {s} ({idx+1}/100)...")
            try:
                data = get_data(s, timeframe)
                # Nghỉ ngắn 0.2s để tránh bị API chặn (Rate limit)
                time.sleep(0.2)
                
                res = calculate_signals(data)
                if res:
                    b_score, s_score, _ = res
                    if b_score >= 0.65: status = "🟢 MUA"
                    elif s_score >= 0.5: status = "🔴 BÁN"
                    else: status = "⚪ THEO DÕI"
                    
                    results.append({
                        "Mã": s, 
                        "Trạng thái": status, 
                        "Điểm Mua (%)": int(b_score * 100),
                        "Điểm Bán (%)": int(s_score * 100)
                    })
            except Exception:
                continue
                
            progress_bar.progress((idx + 1) / len(TOP_MARKET))
        
        status_msg.success(f"✅ Đã quét xong {len(results)}/100 mã!")
        
        if results:
            res_df = pd.DataFrame(results).sort_values(by="Điểm Mua (%)", ascending=False)
            st.dataframe(
                res_df,
                column_config={
                    "Điểm Mua (%)": st.column_config.ProgressColumn("Đồng thuận MUA", format="%d%%", min_value=0, max_value=100),
                    "Điểm Bán (%)": st.column_config.ProgressColumn("Đồng thuận BÁN", format="%d%%", min_value=0, max_value=100),
                },
                use_container_width=True,
                height=600
            )

else:
    # CHẾ ĐỘ PHÂN TÍCH CHI TIẾT
    symbol = st.sidebar.text_input("Nhập mã cổ phiếu", "FPT").upper()
    data = get_data(symbol, timeframe)
    res = calculate_signals(data)
    
    if res:
        b_score, s_score, df_final = res
        
        # Hiển thị trạng thái
        if b_score >= 0.66:
            st.success(f"💎 KHUYẾN NGHỊ: MUA {symbol}")
            color = "#00FF00"
        elif s_score >= 0.5:
            st.error(f"⚠️ KHUYẾN NGHỊ: BÁN {symbol}")
            color = "#FF0000"
        else:
            st.info(f"⚖️ TRẠNG THÁI: THEO DÕI {symbol}")
            color = "#888888"

        # Chỉ số Metric
        c1, c2, c3 = st.columns(3)
        c1.metric("Mã", symbol)
        c2.metric("Điểm MUA", f"{b_score*100:.0f}%")
        c3.metric("Điểm BÁN", f"{s_score*100:.0f}%")

        # Vẽ biểu đồ Plotly
        fig = go.Figure()
        fig.add_trace(go.Candlestick(x=df_final.index, open=df_final['open'], high=df_final['high'], 
                                     low=df_final['low'], close=df_final['close'], name='Giá'))
        
        # Thêm SMA200
        fig.add_trace(go.Scatter(x=df_final.index, y=df_final['SMA200'], line=dict(color='yellow', width=1.5), name='SMA200'))
        
        fig.update_layout(template="plotly_dark", height=600, xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("⚠️ Không lấy được dữ liệu. Vui lòng kiểm tra lại mã hoặc khung thời gian.")
