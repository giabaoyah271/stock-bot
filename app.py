import streamlit as st
import pandas as pd
from vnstock import Vnstock
import numpy as np
import plotly.graph_objects as go
from datetime import datetime

# 1. Cấu hình hệ thống
st.set_page_config(page_title="Hệ thống giao dịch Đa khung thời gian", layout="wide")
st.markdown("<style>.main {background-color: #0e1117;}</style>", unsafe_allow_html=True)

# Danh sách Top 100 Thanh khoản cao nhất (VN-Index & HNX) để tránh treo Web
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

def calculate_signals(df):
    if df.empty or len(df) < 50: return None
    
    # Tính toán chỉ số
    df['SMA20'] = df['close'].rolling(20).mean()
    df['SMA50'] = df['close'].rolling(50).mean()
    df['SMA200'] = df['close'].rolling(200).mean() if len(df) > 200 else df['close'].rolling(50).mean()
    
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
    
    # Ichimoku
    df['SpanA'] = ((df['high'].rolling(9).max() + df['low'].rolling(9).min())/2 + (df['high'].rolling(26).max() + df['low'].rolling(26).min())/2)/2
    df['SpanA_Shift'] = df['SpanA'].shift(26)
    df['SpanB'] = (df['high'].rolling(52).max() + df['low'].rolling(52).min())/2
    df['SpanB_Shift'] = df['SpanB'].shift(26)

    # 6 Tiêu chí bỏ phiếu (Bản chuẩn)
    v1 = np.where(df['close'] > df['SMA200'], 1, -1)
    v2 = np.where(df['SMA20'] > df['SMA50'], 1, -1)
    v3 = np.where(df['MACD'] > df['Signal'], 1, -1)
    v4 = np.where(df['RSI'] < 35, 1, np.where(df['RSI'] > 70, -1, 0))
    v5 = np.where(df['close'] > df['SpanA_Shift'], 1, -1)
    v6 = np.where(df['volume'] > df['volume'].rolling(20).mean(), 1, 0)
    
    buy_score = ((v1[-1]==1) + (v2[-1]==1) + (v3[-1]==1) + (v4[-1]==1) + (v5[-1]==1) + (v6[-1]==1)) / 6
    sell_score = ((v1[-1]==-1) + (v2[-1]==-1) + (v3[-1]==-1) + (v4[-1]==-1) + (v5[-1]==-1)) / 5
    
    return buy_score, sell_score, df

# 2. Sidebar
st.sidebar.title("🛠️ Điều khiển")
mode = st.sidebar.radio("Chế độ", ["Phân tích chi tiết mã", "Quét tín hiệu toàn thị trường"])
timeframe = st.sidebar.selectbox("Khung thời gian", ["Ngày", "15 Phút", "1 Giờ", "Tuần", "Tháng"])

@st.cache_data(ttl=60)
def get_data(symbol, tf):
    try:
        # Lấy từ 2024-01-01 như yêu cầu
        return Vnstock().stock(symbol=symbol, source='KBS').quote.history(start='2024-01-01', end=datetime.now().strftime('%Y-%m-%d'), interval=TF_MAP[tf])
    except: return pd.DataFrame()

# 3. Main Logic
if mode == "Quét tín hiệu toàn thị trường":
    st.header(f"🔍 Trình quét Top 100 thanh khoản (Khung: {timeframe})")
    if st.button("Bắt đầu quét danh mục"):
        results = []
        progress_bar = st.progress(0)
        
        for idx, s in enumerate(TOP_MARKET):
            data = get_data(s, timeframe)
            res = calculate_signals(data)
            if res:
                b_score, s_score, _ = res
                if b_score >= 0.65: status = "🟢 MUA"
                elif s_score >= 0.5: status = "🔴 BÁN"
                else: status = "⚪ THEO DÕI"
                
                results.append({
                    "Mã": s, 
                    "Trạng thái": status, 
                    "Điểm Mua (%)": round(b_score * 100, 0),
                    "Điểm Bán (%)": round(s_score * 100, 0)
                })
            progress_bar.progress((idx + 1) / len(TOP_MARKET))
        
        res_df = pd.DataFrame(results)
        # Sắp xếp để các mã MUA nằm lên trên cùng
        res_df = res_df.sort_values(by="Điểm Mua (%)", ascending=False).reset_index(drop=True)
        
        st.write("### Bảng xếp hạng tín hiệu")
        st.dataframe(res_df, use_container_width=True, height=600)

else:
    symbol = st.sidebar.text_input("Nhập mã cổ phiếu", "FPT").upper()
    data = get_data(symbol, timeframe)
    res = calculate_signals(data)
    
    if res:
        b_score, s_score, df_final = res
        
        # Tiêu đề màu sắc
        if b_score >= 0.66:
            status_text = "MUA"
            color = "#00FF00" # Xanh lá
            st_color = "normal"
        elif s_score >= 0.5:
            status_text = "BÁN"
            color = "#FF0000" # Đỏ
            st_color = "inverse"
        else:
            status_text = "THEO DÕI (NGOÀI)"
            color = "#888888" # Xám
            st_color = "off"

        st.markdown(f"<h1 style='color: {color};'>{status_text}: {symbol}</h1>", unsafe_allow_html=True)

        # Khôi phục thanh tỷ lệ Đồng thuận (Progress Bar)
        c1, c2, c3 = st.columns(3)
        c1.metric(f"TRẠNG THÁI ({timeframe})", status_text, delta=f"{symbol}", delta_color=st_color)
        
        c2.write(f"**Đồng thuận MUA:** {b_score*100:.0f}%")
        c2.progress(float(b_score))
        
        c3.write(f"**Đồng thuận BÁN:** {s_score*100:.0f}%")
        c3.progress(float(s_score))

        # Biểu đồ
        fig = go.Figure()
        fig.add_trace(go.Candlestick(x=df_final['time'], open=df_final['open'], high=df_final['high'], 
                                     low=df_final['low'], close=df_final['close'], name='Giá'))
        
        # SMA200 màu VÀNG
        if len(df_final) > 200:
            fig.add_trace(go.Scatter(x=df_final['time'], y=df_final['SMA200'], 
                                     line=dict(color='yellow', width=2), name='SMA200 (Dài hạn)'))
        
        # Mây Ichimoku
        fig.add_trace(go.Scatter(x=df_final['time'], y=df_final['SpanA_Shift'], line=dict(width=0), showlegend=False))
        fig.add_trace(go.Scatter(x=df_final['time'], y=df_final['SpanB_Shift'], 
                                 line=dict(width=0), fill='tonexty', 
                                 fillcolor='rgba(0, 255, 0, 0.1)', name='Mây Kumo'))
        
        fig.update_layout(xaxis_rangeslider_visible=False, template="plotly_dark", height=650)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Không có đủ dữ liệu cho mã này trong khung thời gian đã chọn.")
