import streamlit as st
import pandas as pd
import pandas_ta as ta
from vnstock import Vnstock
import numpy as np
import plotly.graph_objects as go

st.set_page_config(page_title="Hệ thống 80/50", layout="wide")

st.title("🛡️ Chiến thuật Giao dịch Định lượng 80/50")
st.sidebar.header("Cài đặt")

symbol = st.sidebar.text_input("Nhập mã cổ phiếu", "HPG").upper()

@st.cache_data(ttl=3600) # Lưu bộ nhớ đệm 1 tiếng để web chạy nhanh
def get_data(symbol):
    try:
        stock = Vnstock().stock(symbol=symbol, source='KBS')
        df = stock.quote.history(start='2024-01-01', end='2026-04-17')
        return df
    except:
        return pd.DataFrame()

df = get_data(symbol)

if not df.empty:
    # --- TÍNH TOÁN ---
    ichi = ta.ichimoku(df['high'], df['low'], df['close'])[0]
    df = pd.concat([df, ichi], axis=1)
    df['SMA200'] = ta.sma(df['close'], length=200)
    df['RSI'] = ta.rsi(df['close'], length=14)
    macd = ta.macd(df['close'])
    df = pd.concat([df, macd], axis=1)
    df['Vol_MA20'] = ta.sma(df['volume'], length=20)

    # --- VOTING LOGIC ---
    df['V_Ichi'] = np.where(df['close'] > df['ISA_9'], 1, np.where(df['close'] < df['ISB_26'], -1, 0))
    df['V_Trend'] = np.where(df['close'] > df['SMA200'], 1, -1)
    df['V_RSI'] = np.where(df['RSI'] < 35, 1, np.where(df['RSI'] > 70, -1, 0))
    df['V_MACD'] = np.where(df['MACD_12_26_9'] > df['MACDs_12_26_9'], 1, -1)
    df['V_Vol'] = np.where(df['volume'] > df['Vol_MA20'] * 1.3, 1, 0)
    df['V_Price'] = np.where(df['close'] > df['open'], 1, -1)

    votes = ['V_Ichi', 'V_Trend', 'V_RSI', 'V_MACD', 'V_Vol', 'V_Price']
    df['Buy_Score'] = (df[votes] == 1).sum(axis=1) / len(votes)
    df['Sell_Score'] = (df[votes] == -1).sum(axis=1) / len(votes)
    df['Raw_Signal'] = 0
    df.loc[df['Buy_Score'] >= 0.8, 'Raw_Signal'] = 1  
    df.loc[df['Sell_Score'] >= 0.5, 'Raw_Signal'] = -1 
    df['State'] = df['Raw_Signal'].replace(0, np.nan).ffill().fillna(0)

    # --- HIỂN THỊ ---
    last = df.iloc[-1]
    col1, col2, col3 = st.columns(3)
    
    with col1:
        color = "green" if last['State'] == 1 else "red" if last['State'] == -1 else "gray"
        st.metric("TRẠNG THÁI", "XANH (GIỮ)" if last['State'] == 1 else "ĐỎ (BÁN)", delta_color="normal")
    with col2:
        st.metric("ĐỒNG THUẬN MUA", f"{last['Buy_Score']*100:.0f}%")
    with col3:
        st.metric("ĐỒNG THUẬN BÁN", f"{last['Sell_Score']*100:.0f}%")

    # Biểu đồ nến
    fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['open'], high=df['high'], low=df['low'], close=df['close'])])
    fig.update_layout(title=f"Biểu đồ kỹ thuật {symbol}", xaxis_rangeslider_visible=False)
    st.plotly_chart(fig, use_container_width=True)
else:
    st.error("Không tìm thấy dữ liệu cho mã này.")
