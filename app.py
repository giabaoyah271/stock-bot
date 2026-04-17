import streamlit as st
import pandas as pd
from vnstock import Vnstock
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta

# 1. Cấu hình giao diện
st.set_page_config(page_title="Hệ thống giao dịch - Fintech", layout="wide")
st.title("🛡️ Hệ thống giao dịch")

# Sidebar cấu hình
st.sidebar.header("Cài đặt thông số")
symbol = st.sidebar.text_input("Nhập mã cổ phiếu", "FPT").upper()
timeframe = st.sidebar.selectbox("Khung thời gian", ["Ngày", "Tuần", "Tháng"])

# Ánh xạ khung thời gian cho Vnstock
tf_map = {"Ngày": "1D", "Tuần": "1W", "Tháng": "1M"}

# 2. Hàm lấy dữ liệu
@st.cache_data(ttl=3600)
def load_data(ticker, tf):
    try:
        stock = Vnstock().stock(symbol=ticker, source='KBS')
        # Lấy dữ liệu đủ dài để tính SMA200
        data = stock.quote.history(start='2023-01-01', end=datetime.now().strftime('%Y-%m-%d'), interval=tf_map[tf])
        return data
    except:
        return pd.DataFrame()

df = load_data(symbol, timeframe)

if not df.empty:
    # --- TÍNH TOÁN CHỈ BÁO NÂNG CAO ---
    # SMA 20, 50, 200
    df['SMA20'] = df['close'].rolling(window=20).mean()
    df['SMA50'] = df['close'].rolling(window=50).mean()
    df['SMA200'] = df['close'].rolling(window=200).mean()
    
    # RSI 14
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    df['RSI'] = 100 - (100 / (1 + gain/(loss + 1e-9)))
    
    # MACD
    exp1 = df['close'].ewm(span=12, adjust=False).mean()
    exp2 = df['close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp1 - exp2
    df['Signal_Line'] = df['MACD'].ewm(span=9, adjust=False).mean()
    
    # Ichimoku (Mây Kumo)
    high_9 = df['high'].rolling(window=9).max()
    low_9 = df['low'].rolling(window=9).min()
    df['Tenkan'] = (high_9 + low_9) / 2
    
    high_26 = df['high'].rolling(window=26).max()
    low_26 = df['low'].rolling(window=26).min()
    df['Kijun'] = (high_26 + low_26) / 2
    
    df['SpanA'] = ((df['Tenkan'] + df['Kijun']) / 2).shift(26)
    df['SpanB'] = ((df['high'].rolling(window=52).max() + df['low'].rolling(window=52).min()) / 2).shift(26)

    # --- HỆ THỐNG BỎ PHIẾU (VOTING 70/50) ---
    # Phiếu 1: Xu hướng dài hạn (Giá > SMA200)
    df['V1'] = np.where(df['close'] > df['SMA200'], 1, -1)
    # Phiếu 2: Giao cắt MA (SMA20 > SMA50)
    df['V2'] = np.where(df['SMA20'] > df['SMA50'], 1, -1)
    # Phiếu 3: Động lượng MACD (MACD > Signal)
    df['V3'] = np.where(df['MACD'] > df['Signal_Line'], 1, -1)
    # Phiếu 4: RSI Quá bán (<35)
    df['V4'] = np.where(df['RSI'] < 35, 1, 0)
    # Phiếu 5: Ichimoku (Giá trên mây)
    df['V5'] = np.where(df['close'] > df['SpanA'], 1, -1)
    # Phiếu 6: Dòng tiền (Volume > TB 20 phiên)
    df['V6'] = np.where(df['volume'] > df['volume'].rolling(20).mean(), 1, 0)

    vote_cols = ['V1', 'V2', 'V3', 'V4', 'V5', 'V6']
    df['Buy_Score'] = (df[vote_cols] == 1).sum(axis=1) / len(vote_cols)
    df['Sell_Score'] = (df[vote_cols] == -1).sum(axis=1) / len(vote_cols)
    
    # Logic tín hiệu
    last = df.iloc[-1]
    if last['Buy_Score'] >= 0.7:
        status = "MUA"
        color = "inverse" # Xanh
    elif last['Sell_Score'] >= 0.5:
        status = "BÁN"
        color = "normal" # Đỏ
    else:
        status = "NGOÀI (THEO DÕI)"
        color = "off"

    # --- HIỂN THỊ ---
    col1, col2, col3 = st.columns(3)
    col1.metric("TRẠNG THÁI HỆ THỐNG", status, delta=f"{symbol}", delta_color=color)
    col2.write(f"**Đồng thuận Mua:** {last['Buy_Score']*100:.0f}%")
    col2.progress(last['Buy_Score'])
    col3.write(f"**Đồng thuận Bán:** {last['Sell_Score']*100:.0f}%")
    col3.progress(last['Sell_Score'])

    # Giải thích thuật ngữ
    with st.expander("ℹ️ Giải thích về 'Mây' và Chỉ số"):
        st.write("""
        - **Mây Ichimoku (Kumo):** Là vùng không gian giữa Span A và Span B. Nếu giá nằm trên mây, thị trường đang trong xu hướng tăng. Mây đóng vai trò là 'lưới an toàn' (hỗ trợ).
        - **SMA200:** Đường trung bình 200 phiên, dùng để xác định xu hướng dài hạn của cổ phiếu.
        - **Trạng thái NGOÀI:** Hệ thống không tìm thấy sự đồng thuận đủ lớn, khuyến nghị không nên vào lệnh để tránh rủi ro 'bào' vốn khi giá đi ngang.
        """)

    # --- BIỂU ĐỒ ---
    fig = go.Figure()
    # Nến
    fig.add_trace(go.Candlestick(x=df['time'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], name='Giá'))
    # Mây
    fig.add_trace(go.Scatter(x=df['time'], y=df['SpanA'], line=dict(color='rgba(0, 255, 0, 0.1)'), showlegend=False))
    fig.add_trace(go.Scatter(x=df['time'], y=df['SpanB'], line=dict(color='rgba(255, 0, 0, 0.1)'), fill='tonexty', fillcolor='rgba(0, 255, 0, 0.1)', name='Mây Kumo'))
    # Đường xu hướng
    fig.add_trace(go.Scatter(x=df['time'], y=df['SMA200'], line=dict(color='white', width=2), name='SMA200 (Dài hạn)'))
    
    fig.update_layout(xaxis_rangeslider_visible=False, template="plotly_dark", height=700)
    st.plotly_chart(fig, use_container_width=True)

else:
    st.error("⚠️ Không tìm thấy dữ liệu cho mã này hoặc khung thời gian này.")
