import streamlit as st
import pandas as pd
from vnstock import Vnstock
import numpy as np
import plotly.graph_objects as go

st.set_page_config(page_title="Hệ thống 80/50 - UEH Fintech", layout="wide")
st.title("🛡️ Chiến thuật Giao dịch Định lượng 80/50")

symbol = st.sidebar.text_input("Nhập mã cổ phiếu", "HPG").upper()

@st.cache_data(ttl=3600)
def load_data(ticker):
    try:
        stock = Vnstock().stock(symbol=ticker, source='KBS')
        return stock.quote.history(start='2024-01-01', end='2026-04-17')
    except: return pd.DataFrame()

df = load_data(symbol)

if not df.empty:
    # --- TỰ TÍNH TOÁN CHỈ BÁO (KHÔNG CẦN PANDAS-TA) ---
    # 1. Đường trung bình MA
    df['MA20'] = df['close'].rolling(window=20).mean()
    df['MA50'] = df['close'].rolling(window=50).mean()
    
    # 2. RSI (Công thức chuẩn)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # 3. Bollinger Bands
    df['BB_Mid'] = df['close'].rolling(window=20).mean()
    df['BB_Std'] = df['close'].rolling(window=20).std()
    df['BBU'] = df['BB_Mid'] + (df['BB_Std'] * 2)
    df['BBL'] = df['BB_Mid'] - (df['BB_Std'] * 2)
    
    # 4. Ichimoku (Cơ bản)
    nine_period_high = df['high'].rolling(window=9).max()
    nine_period_low = df['low'].rolling(window=9).min()
    df['Tenkan'] = (nine_period_high + nine_period_low) / 2
    
    twenty_six_high = df['high'].rolling(window=26).max()
    twenty_six_low = df['low'].rolling(window=26).min()
    df['Kijun'] = (twenty_six_high + twenty_six_low) / 2
    
    df['SpanA'] = ((df['Tenkan'] + df['Kijun']) / 2).shift(26)

    # --- LOGIC BỎ PHIẾU 80/50 ---
    df['V_MA'] = np.where((df['close'] > df['MA20']) & (df['MA20'] > df['MA50']), 1, -1)
    df['V_RSI'] = np.where(df['RSI'] < 30, 1, np.where(df['RSI'] > 70, -1, 0))
    df['V_Ichi'] = np.where(df['close'] > df['SpanA'], 1, -1)
    df['V_Price'] = np.where(df['close'] > df['open'], 1, -1)

    votes = ['V_MA', 'V_RSI', 'V_Ichi', 'V_Price']
    df['Buy_Score'] = (df[votes] == 1).sum(axis=1) / len(votes)
    df['Sell_Score'] = (df[votes] == -1).sum(axis=1) / len(votes)
    
    df['State'] = np.where(df['Buy_Score'] >= 0.8, 1, np.where(df['Sell_Score'] >= 0.5, -1, 0))
    df['State'] = df['State'].replace(0, np.nan).ffill().fillna(0)

    # HIỂN THỊ
    last = df.iloc[-1]
    c1, c2, c3 = st.columns(3)
    c1.metric("TRẠNG THÁI", "XANH (GIỮ)" if last['State'] == 1 else "ĐỎ (NGOÀI)")
    c2.metric("MUA ĐỒNG THUẬN", f"{last['Buy_Score']*100:.0f}%")
    c3.metric("BÁN ĐỒNG THUẬN", f"{last['Sell_Score']*100:.0f}%")

    # BIỂU ĐỒ
    fig = go.Figure(data=[go.Candlestick(x=df['time'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], name='Giá')])
    fig.add_trace(go.Scatter(x=df['time'], y=df['SpanA'], line=dict(color='rgba(0,255,0,0.3)'), fill='tonexty', name='Mây Ichimoku'))
    fig.update_layout(xaxis_rangeslider_visible=False, template="plotly_dark", height=500)
    st.plotly_chart(fig, use_container_width=True)
else:
    st.warning("⚠️ Không thể lấy dữ liệu. Hãy kiểm tra lại mã cổ phiếu.")
