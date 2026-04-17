import streamlit as st
import pandas as pd
import pandas_ta as ta
from vnstock import Vnstock
import numpy as np
import plotly.graph_objects as go

st.set_page_config(page_title="Hệ thống 80/50 - Fintech UEH", layout="wide")
st.title("🛡️ Chiến thuật Giao dịch Định lượng 80/50")

symbol = st.sidebar.text_input("Nhập mã cổ phiếu", "HPG").upper()

@st.cache_data(ttl=3600)
def load_data(ticker):
    try:
        stock = Vnstock().stock(symbol=ticker, source='KBS')
        # Lấy dữ liệu dài hơn để tính SMA200 và Ichi chính xác
        return stock.quote.history(start='2023-01-01', end='2026-12-31')
    except:
        return pd.DataFrame()

df = load_data(symbol)

if not df.empty:
    # --- TÍNH TOÁN CHỈ BÁO THEO BẢNG QUY TẮC ---
    # 1. Ichimoku
    ichi = ta.ichimoku(df['high'], df['low'], df['close'])[0]
    df = pd.concat([df, ichi], axis=1)
    
    # 2. Bollinger Bands
    bbands = ta.bbands(df['close'], length=20, std=2)
    df = pd.concat([df, bbands], axis=1)
    
    # 3. RSI & MACD
    df['RSI'] = ta.rsi(df['close'], length=14)
    macd = ta.macd(df['close'])
    df = pd.concat([df, macd], axis=1)
    
    # 4. SMA & Volume
    df['SMA200'] = ta.sma(df['close'], length=200)
    df['Vol_MA20'] = ta.sma(df['volume'], length=20)

    # --- LOGIC BỎ PHIẾU (VOTING) ---
    # Phiếu 1: Ichimoku (Giá trên mây + Tenkan > Kijun)
    df['V_Ichi'] = np.where((df['close'] > df['ISA_9']) & (df['ITS_9'] > df['IKS_26']), 1, -1)
    
    # Phiếu 2: Bollinger Bands (Giá chạm dải dưới + Nến rút chân - giả lập đơn giản)
    df['V_BB'] = np.where(df['close'] < df['BBL_20_2.0'], 1, np.where(df['close'] > df['BBU_20_2.0'], -1, 0))
    
    # Phiếu 3: RSI (Quá bán < 30 hoặc Quá mua > 70)
    df['V_RSI'] = np.where(df['RSI'] < 30, 1, np.where(df['RSI'] > 70, -1, 0))
    
    # Phiếu 4: MACD (Cắt lên Signal)
    df['V_MACD'] = np.where(df['MACD_12_26_9'] > df['MACDs_12_26_9'], 1, -1)
    
    # Phiếu 5: Xu hướng SMA200
    df['V_Trend'] = np.where(df['close'] > df['SMA200'], 1, -1)

    # --- LUẬT 80/50 ---
    votes = ['V_Ichi', 'V_BB', 'V_RSI', 'V_MACD', 'V_Trend']
    df['Buy_Score'] = (df[votes] == 1).sum(axis=1) / len(votes)
    df['Sell_Score'] = (df[votes] == -1).sum(axis=1) / len(votes)
    
    df['Raw_Signal'] = 0
    df.loc[df['Buy_Score'] >= 0.8, 'Raw_Signal'] = 1  
    df.loc[df['Sell_Score'] >= 0.5, 'Raw_Signal'] = -1 
    df['State'] = df['Raw_Signal'].replace(0, np.nan).ffill().fillna(0)

    # HIỂN THỊ
    last = df.iloc[-1]
    st.subheader(f"Kết quả phân tích: {symbol}")
    c1, c2, c3 = st.columns(3)
    c1.metric("TRẠNG THÁI", "XANH (GIỮ)" if last['State'] == 1 else "ĐỎ (NGOÀI)")
    c2.metric("ĐỒNG THUẬN MUA", f"{last['Buy_Score']*100:.0f}%")
    c3.metric("ĐỒNG THUẬN BÁN", f"{last['Sell_Score']*100:.0f}%")

    # Vẽ biểu đồ nến + Bollinger Bands
    fig = go.Figure(data=[
        go.Candlestick(x=df['time'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], name='Nến'),
        go.Scatter(x=df['time'], y=df['BBU_20_2.0'], line=dict(color='gray', width=1), name='BB Upper'),
        go.Scatter(x=df['time'], y=df['BBL_20_2.0'], line=dict(color='gray', width=1), name='BB Lower')
    ])
    fig.update_layout(xaxis_rangeslider_visible=False, height=600, template="plotly_dark")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.error("Không thể tải dữ liệu. Vui lòng kiểm tra lại GitHub hoặc Logs.")
