import streamlit as st
import pandas as pd
import pandas_ta as ta
from vnstock import Vnstock
import numpy as np
import plotly.graph_objects as go

st.set_page_config(page_title="Hệ thống 80/50 - Fintech UEH", layout="wide")
st.title("🛡️ Chiến thuật Giao dịch Định lượng 80/50 (Bản chuẩn)")

symbol = st.sidebar.text_input("Nhập mã cổ phiếu", "HPG").upper()

@st.cache_data(ttl=3600)
def load_data(ticker):
    try:
        # Sử dụng nguồn KBS ổn định cho năm 2026
        stock = Vnstock().stock(symbol=ticker, source='KBS')
        return stock.quote.history(start='2024-01-01', end='2026-04-17')
    except:
        return pd.DataFrame()

df = load_data(symbol)

if not df.empty:
    # 1. TÍNH TOÁN CHỈ BÁO THEO QUY TẮC
    df['MA20'] = ta.sma(df['close'], length=20)
    df['MA50'] = ta.sma(df['close'], length=50)
    df['RSI'] = ta.rsi(df['close'], length=14)
    
    macd = ta.macd(df['close'])
    df = pd.concat([df, macd], axis=1)
    
    bbands = ta.bbands(df['close'], length=20, std=2)
    df = pd.concat([df, bbands], axis=1)
    
    ichi = ta.ichimoku(df['high'], df['low'], df['close'])[0]
    df = pd.concat([df, ichi], axis=1)

    # 2. HỆ THỐNG BỎ PHIẾU (VOTING LOGIC)
    # Tín hiệu MA: Giá trên MA và MA ngắn cắt lên MA dài
    df['V_MA'] = np.where((df['close'] > df['MA20']) & (df['MA20'] > df['MA50']), 1, -1)
    
    # Tín hiệu RSI: Dưới 30 là Quá bán (Cơ hội mua)
    df['V_RSI'] = np.where(df['RSI'] < 30, 1, np.where(df['RSI'] > 70, -1, 0))
    
    # Tín hiệu MACD: Cắt lên Signal và vượt trên đường 0
    df['V_MACD'] = np.where((df['MACD_12_26_9'] > df['MACDs_12_26_9']) & (df['MACD_12_26_9'] > 0), 1, -1)
    
    # Tín hiệu BB: Chạm dải dưới + Nến rút chân (giả lập giá đóng > mở tại dải dưới)
    df['V_BB'] = np.where((df['close'] < df['BBL_20_2.0']) & (df['close'] > df['open']), 1, 0)
    
    # Tín hiệu Ichimoku: Giá trên mây và Tenkan > Kijun
    df['V_Ichi'] = np.where((df['close'] > df['ISA_9']) & (df['ITS_9'] > df['IKS_26']), 1, -1)

    # 3. LUẬT 80/50
    votes = ['V_MA', 'V_RSI', 'V_MACD', 'V_BB', 'V_Ichi']
    df['Buy_Score'] = (df[votes] == 1).sum(axis=1) / len(votes)
    df['Sell_Score'] = (df[votes] == -1).sum(axis=1) / len(votes)
    
    df['Raw_Signal'] = 0
    df.loc[df['Buy_Score'] >= 0.8, 'Raw_Signal'] = 1  
    df.loc[df['Sell_Score'] >= 0.5, 'Raw_Signal'] = -1 
    df['State'] = df['Raw_Signal'].replace(0, np.nan).ffill().fillna(0)

    # 4. HIỂN THỊ
    last = df.iloc[-1]
    st.subheader(f"Phân tích kỹ thuật: {symbol}")
    col1, col2, col3 = st.columns(3)
    col1.metric("TRẠNG THÁI", "XANH (NẮM GIỮ)" if last['State'] == 1 else "ĐỎ (ĐỨNG NGOÀI)")
    col2.metric("ĐỒNG THUẬN MUA", f"{last['Buy_Score']*100:.0f}%")
    col3.metric("ĐỒNG THUẬN BÁN", f"{last['Sell_Score']*100:.0f}%")

    # BIỂU ĐỒ NẾN TÍCH HỢP     fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['open'], high=df['high'], low=df['low'], close=df['close'], name='Giá')])
    fig.add_trace(go.Scatter(x=df.index, y=df['BBU_20_2.0'], line=dict(color='rgba(173, 216, 230, 0.5)'), name='BB Upper'))
    fig.add_trace(go.Scatter(x=df.index, y=df['BBL_20_2.0'], line=dict(color='rgba(173, 216, 230, 0.5)'), name='BB Lower'))
    fig.update_layout(xaxis_rangeslider_visible=False, template="plotly_dark", height=600)
    st.plotly_chart(fig, use_container_width=True)

else:
    st.error("⚠️ Không lấy được dữ liệu. Vui lòng kiểm tra lại mã cổ phiếu hoặc nguồn kết nối.")
