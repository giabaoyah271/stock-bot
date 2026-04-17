import streamlit as st
import pandas as pd
from vnstock import Vnstock
import numpy as np
import plotly.graph_objects as go
from datetime import datetime

# 1. Cấu hình hệ thống
st.set_page_config(page_title="Hệ thống giao dịch", layout="wide")

# Danh sách mã quét (VN30 + Nhóm Ngân hàng tiêu biểu)
WATCHLIST = ['ACB', 'BID', 'CTG', 'HDB', 'MBB', 'SHB', 'STB', 'TCB', 'TPB', 'VCB', 'VIB', 'VPB', 
             'FPT', 'HPG', 'MSN', 'MWG', 'SSI', 'VHM', 'VIC', 'VNM']

def calculate_signals(df):
    if df.empty or len(df) < 200: return None
    # Tính toán nhanh các chỉ số
    df['SMA20'] = df['close'].rolling(20).mean()
    df['SMA50'] = df['close'].rolling(50).mean()
    df['SMA200'] = df['close'].rolling(200).mean()
    
    # RSI 14
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['RSI'] = 100 - (100 / (1 + gain/(loss + 1e-9)))
    
    # Ichimoku Cloud (Vẽ mây chuẩn)
    high_9 = df['high'].rolling(9).max()
    low_9 = df['low'].rolling(9).min()
    high_26 = df['high'].rolling(26).max()
    low_26 = df['low'].rolling(26).min()
    df['SpanA'] = ((high_9 + low_9)/2 + (high_26 + low_26)/2)/2
    df['SpanB'] = (df['high'].rolling(52).max() + df['low'].rolling(52).min())/2
    df['SpanA_Shift'] = df['SpanA'].shift(26)
    df['SpanB_Shift'] = df['SpanB'].shift(26)

    # Logic Voting 70/50
    v1 = np.where(df['close'] > df['SMA200'], 1, -1)
    v2 = np.where(df['SMA20'] > df['SMA50'], 1, -1)
    v3 = np.where(df['RSI'] < 35, 1, 0)
    v4 = np.where(df['close'] > df['SpanA_Shift'], 1, -1)
    
    last_buy = ((v1[-1]==1) + (v2[-1]==1) + (v3[-1]==1) + (v4[-1]==1)) / 4
    last_sell = ((v1[-1]==-1) + (v2[-1]==-1) + (v4[-1]==-1)) / 3
    return last_buy, last_sell, df

# 2. Sidebar
st.sidebar.title("🛠️ Điều khiển")
mode = st.sidebar.radio("Chế độ", ["Quét tín hiệu", "Soi chi tiết mã"])

@st.cache_data(ttl=60) # Cache 1 phút để cập nhật giá Realtime
def get_data(symbol):
    try:
        return Vnstock().stock(symbol=symbol, source='KBS').quote.history(start='2023-01-01', end=datetime.now().strftime('%Y-%m-%d'))
    except: return pd.DataFrame()

# 3. Main Logic
if mode == "Quét tín hiệu":
    st.header("🔍 Trình quét tín hiệu thị trường")
    if st.button("Bắt đầu quét danh mục"):
        results = []
        progress_bar = st.progress(0)
        for idx, s in enumerate(WATCHLIST):
            data = get_data(s)
            res = calculate_signals(data)
            if res:
                b, s_score, _ = res
                status = "MUA" if b >= 0.7 else ("BÁN" if s_score >= 0.5 else "THEO DÕI")
                results.append({"Mã": s, "Trạng thái": status, "Độ mạnh Mua": f"{b*100:.0f}%"})
            progress_bar.progress((idx + 1) / len(WATCHLIST))
        
        res_df = pd.DataFrame(results)
        c1, c2 = st.columns(2)
        with c1:
            st.success("🟢 DANH SÁCH MUA")
            st.dataframe(res_df[res_df['Trạng thái'] == "MUA"], use_container_width=True)
        with c2:
            st.error("🔴 DANH SÁCH BÁN")
            st.dataframe(res_df[res_df['Trạng thái'] == "BÁN"], use_container_width=True)

else:
    symbol = st.sidebar.text_input("Nhập mã cổ phiếu", "ACB").upper()
    data = get_data(symbol)
    res = calculate_signals(data)
    
    if res:
        b, s_score, df_final = res
        
        # Tiêu đề màu sắc theo trạng thái
        if b >= 0.7:
            st.markdown(f"<h1 style='color: #00FF00;'>MUA: {symbol} (+{b*100:.0f}%)</h1>", unsafe_allow_html=True)
        elif s_score >= 0.5:
            st.markdown(f"<h1 style='color: #FF0000;'>BÁN: {symbol} (-{s_score*100:.0f}%)</h1>", unsafe_allow_html=True)
        else:
            st.markdown(f"<h1 style='color: #888888;'>THEO DÕI: {symbol}</h1>", unsafe_allow_html=True)

        # Biểu đồ
        fig = go.Figure()
        # Nến
        fig.add_trace(go.Candlestick(x=df_final['time'], open=df_final['open'], high=df_final['high'], 
                                     low=df_final['low'], close=df_final['close'], name='Giá'))
        
        # SMA200 màu VÀNG
        fig.add_trace(go.Scatter(x=df_final['time'], y=df_final['SMA200'], 
                                 line=dict(color='yellow', width=2), name='SMA200 (Dài hạn)'))
        
        # Vẽ mây Ichimoku chuẩn
        fig.add_trace(go.Scatter(x=df_final['time'], y=df_final['SpanA_Shift'], line=dict(width=0), showlegend=False))
        fig.add_trace(go.Scatter(x=df_final['time'], y=df_final['SpanB_Shift'], 
                                 line=dict(width=0), fill='tonexty', 
                                 fillcolor='rgba(0, 255, 0, 0.1)', name='Mây Kumo'))
        
        fig.update_layout(xaxis_rangeslider_visible=False, template="plotly_dark", height=650)
        st.plotly_chart(fig, use_container_width=True)
