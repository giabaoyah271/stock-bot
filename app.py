import streamlit as st
import pandas as pd
from vnstock import Vnstock
import numpy as np
import plotly.graph_objects as go
from datetime import datetime

# 1. Cấu hình hệ thống
st.set_page_config(page_title="Hệ thống giao dịch chuyên nghiệp", layout="wide")
st.markdown("<style>.main {background-color: #0e1117;}</style>", unsafe_allow_html=True)

# Danh sách mã quét (VN30 là tối ưu nhất để tránh lag)
VN30 = ['ACB', 'BCM', 'BID', 'BVH', 'CTG', 'FPT', 'GVR', 'HDB', 'HPG', 'MBB', 'MSN', 'MWG', 'PLX', 'POW', 'SAB', 'SHB', 'SSB', 'SSI', 'STB', 'TCB', 'TPB', 'VCB', 'VHM', 'VIB', 'VIC', 'VNM', 'VPB', 'VRE']

def calculate_signals(df):
    if df.empty or len(df) < 200: return None
    # Tính toán chỉ số
    df['SMA20'] = df['close'].rolling(20).mean()
    df['SMA50'] = df['close'].rolling(50).mean()
    df['SMA200'] = df['close'].rolling(200).mean()
    
    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['RSI'] = 100 - (100 / (1 + gain/(loss + 1e-9)))
    
    # Ichimoku
    df['SpanA'] = ((df['high'].rolling(9).max() + df['low'].rolling(9).min())/2 + (df['high'].rolling(26).max() + df['low'].rolling(26).min())/2)/2
    df['SpanA'] = df['SpanA'].shift(26)

    # Hệ thống bỏ phiếu (70/50)
    v1 = np.where(df['close'] > df['SMA200'], 1, -1)
    v2 = np.where(df['SMA20'] > df['SMA50'], 1, -1)
    v3 = np.where(df['RSI'] < 35, 1, 0)
    v4 = np.where(df['close'] > df['SpanA'], 1, -1)
    
    buy_score = (v1==1).sum() + (v2==1).sum() + (v3==1).sum() + (v4==1).sum() # Giản lược logic quét nhanh
    # Tính toán Score cho dòng cuối cùng
    last_buy = ( (v1[-1]==1) + (v2[-1]==1) + (v3[-1]==1) + (v4[-1]==1) ) / 4
    last_sell = ( (v1[-1]==-1) + (v2[-1]==-1) + (v4[-1]==-1) ) / 3
    return last_buy, last_sell, df

# 2. Giao diện Sidebar
st.sidebar.title("🔍 Bộ lọc & Phân tích")
mode = st.sidebar.radio("Chế độ", ["Quét thị trường (VN30)", "Phân tích chi tiết mã"])

# Hàm lấy data nhanh (Cache 1 phút)
@st.cache_data(ttl=60)
def get_data(symbol):
    try:
        return Vnstock().stock(symbol=symbol, source='KBS').quote.history(start='2023-01-01', end=datetime.now().strftime('%Y-%m-%d'))
    except: return pd.DataFrame()

# 3. Thực thi logic
if mode == "Quét thị trường (VN30)":
    st.header("📋 Danh sách khuyến nghị hôm nay")
    results = []
    with st.spinner('Đang quét toàn bộ VN30...'):
        for s in VN30:
            data = get_data(s)
            res = calculate_signals(data)
            if res:
                b, s_score, _ = res
                status = "MUA" if b >= 0.7 else ("BÁN" if s_score >= 0.5 else "THEO DÕI")
                results.append({"Mã": s, "Trạng thái": status, "Đồng thuận Mua": f"{b*100:.0f}%"})
    
    res_df = pd.DataFrame(results)
    col_buy, col_sell = st.columns(2)
    col_buy.success("🟢 MÃ KHUYẾN NGHỊ MUA")
    col_buy.table(res_df[res_df['Trạng thái'] == "MUA"])
    col_sell.error("🔴 MÃ KHUYẾN NGHỊ BÁN")
    col_sell.table(res_df[res_df['Trạng thái'] == "BÁN"])

else:
    symbol = st.sidebar.text_input("Nhập mã", "FPT").upper()
    data = get_data(symbol)
    res = calculate_signals(data)
    
    if res:
        b, s_score, df_final = res
        last_price = df_final['close'].iloc[-1]
        
        # Hiển thị Header màu sắc
        if b >= 0.7:
            st.markdown(f"<h1 style='color: #00FF00;'>MUA: {symbol} (Đồng thuận {b*100:.0f}%)</h1>", unsafe_allow_html=True)
        elif s_score >= 0.5:
            st.markdown(f"<h1 style='color: #FF0000;'>BÁN: {symbol} (Đồng thuận {s_score*100:.0f}%)</h1>", unsafe_allow_html=True)
        else:
            st.markdown(f"<h1>THEO DÕI: {symbol}</h1>", unsafe_allow_html=True)

        # Biểu đồ
        fig = go.Figure()
        fig.add_trace(go.Candlestick(x=df_final['time'], open=df_final['open'], high=df_final['high'], low=df_final['low'], close=df_final['close'], name='Giá'))
        # SMA200 màu Vàng
        fig.add_trace(go.Scatter(x=df_final['time'], y=df_final['SMA200'], line=dict(color='yellow', width=2), name='SMA200'))
        # Mây Ichimoku
        fig.add_trace(go.Scatter(x=df_final['time'], y=df_final['SpanA'], line=dict(color='rgba(0, 255, 0, 0.2)'), fill='tospectrum', name='Mây'))
        
        fig.update_layout(xaxis_rangeslider_visible=False, template="plotly_dark", height=600)
        st.plotly_chart(fig, use_container_width=True)
