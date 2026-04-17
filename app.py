import streamlit as st
import pandas as pd
from vnstock import Vnstock
import numpy as np
import plotly.graph_objects as go

# 1. Cấu hình giao diện
st.set_page_config(page_title="Hệ thống 80/50 - Fintech UEH", layout="wide")
st.title("🛡️ Chiến thuật Giao dịch Định lượng 80/50")

symbol = st.sidebar.text_input("Nhập mã cổ phiếu", "HPG").upper()

# 2. Hàm lấy dữ liệu
@st.cache_data(ttl=3600)
def load_data(ticker):
    try:
        stock = Vnstock().stock(symbol=ticker, source='KBS')
        return stock.quote.history(start='2024-01-01', end='2026-04-17')
    except:
        return pd.DataFrame()

df = load_data(symbol)

if not df.empty:
    # --- TỰ TÍNH TOÁN CHỈ BÁO (KHÔNG DÙNG THƯ VIỆN NGOÀI) ---
    
    # MA (Đường trung bình)
    df['MA20'] = df['close'].rolling(window=20).mean()
    df['MA50'] = df['close'].rolling(window=50).mean()
    
    # RSI (Chỉ số sức mạnh tương đối)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / (loss + 1e-9)
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # Ichimoku (Chỉ tính Span A để xác định vùng mây)
    high_9 = df['high'].rolling(window=9).max()
    low_9 = df['low'].rolling(window=9).min()
    tenkan = (high_9 + low_9) / 2
    
    high_26 = df['high'].rolling(window=26).max()
    low_26 = df['low'].rolling(window=26).min()
    kijun = (high_26 + low_26) / 2
    
    df['SpanA'] = ((tenkan + kijun) / 2).shift(26)

    # --- LOGIC BỎ PHIẾU 80/50 ---
    # Phiếu 1: Xu hướng (Giá > MA20 và MA20 > MA50)
    df['V_Trend'] = np.where((df['close'] > df['MA20']) & (df['MA20'] > df['MA50']), 1, -1)
    
    # Phiếu 2: RSI (Dưới 35 là vùng mua tiềm năng)
    df['V_RSI'] = np.where(df['RSI'] < 35, 1, np.where(df['RSI'] > 70, -1, 0))
    
    # Phiếu 3: Ichimoku (Giá trên mây Span A)
    df['V_Ichi'] = np.where(df['close'] > df['SpanA'], 1, -1)
    
    # Phiếu 4: Giá đóng cửa (Nến xanh)
    df['V_Price'] = np.where(df['close'] > df['open'], 1, -1)

    votes = ['V_Trend', 'V_RSI', 'V_Ichi', 'V_Price']
    df['Buy_Score'] = (df[votes] == 1).sum(axis=1) / len(votes)
    df['Sell_Score'] = (df[votes] == -1).sum(axis=1) / len(votes)
    
    # Trạng thái hệ thống
    df['State'] = np.where(df['Buy_Score'] >= 0.8, 1, np.where(df['Sell_Score'] >= 0.5, -1, 0))
    df['State'] = df['State'].replace(0, np.nan).ffill().fillna(0)

    # 3. Hiển thị thông số
    last = df.iloc[-1]
    st.subheader(f"Phân tích mã: {symbol}")
    c1, c2, c3 = st.columns(3)
    c1.metric("TRẠNG THÁI", "MUA/GIỮ" if last['State'] == 1 else "BÁN/NGOÀI", 
              delta="XANH" if last['State'] == 1 else "ĐỎ", delta_color="normal")
    c2.write(f"**Đồng thuận Mua:** {last['Buy_Score']*100:.0f}%")
    c2.progress(last['Buy_Score'])
    c3.write(f"**Đồng thuận Bán:** {last['Sell_Score']*100:.0f}%")
    c3.progress(last['Sell_Score'])

    # 4. Vẽ biểu đồ
    fig = go.Figure(data=[go.Candlestick(
        x=df['time'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], name='Nến'
    )])
    
    # Vẽ mây Ichimoku giả lập
    fig.add_trace(go.Scatter(x=df['time'], y=df['SpanA'], line=dict(color='rgba(0, 255, 0, 0.2)'), fill='tonexty', name='Mây'))
    
    fig.update_layout(xaxis_rangeslider_visible=False, template="plotly_dark", height=600)
    st.plotly_chart(fig, use_container_width=True)

else:
    st.error("⚠️ Không thể kết nối dữ liệu. Vui lòng kiểm tra lại mã cổ phiếu.")
