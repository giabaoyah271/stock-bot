import streamlit as st
import pandas as pd
import pandas_ta as ta
from vnstock import Vnstock
import numpy as np
import plotly.graph_objects as go

st.set_page_config(page_title="Hệ thống 80/50 - Fintech UEH", layout="wide")
st.title("🛡️ Chiến thuật Giao dịch 80/50 (Bản nâng cấp)")

symbol = st.sidebar.text_input("Nhập mã cổ phiếu", "HPG").upper()

@st.cache_data(ttl=3600)
def load_data(ticker):
    try:
        stock = Vnstock().stock(symbol=ticker, source='KBS')
        return stock.quote.history(start='2023-01-01', end='2026-12-31')
    except: return pd.DataFrame()

df = load_data(symbol)

if not df.empty:
    # --- TÍNH TOÁN CÁC CHỈ BÁO CHI TIẾT ---
    # 1. Đường trung bình MA (MA ngắn 20, MA dài 50)
    df['MA20'] = ta.sma(df['close'], length=20)
    df['MA50'] = ta.sma(df['close'], length=50)
    
    # 2. RSI & Phân kỳ (Dùng RSI 14)
    df['RSI'] = ta.rsi(df['close'], length=14)
    
    # 3. MACD
    macd = ta.macd(df['close'])
    df = pd.concat([df, macd], axis=1)
    
    # 4. Bollinger Bands
    bbands = ta.bbands(df['close'], length=20, std=2)
    df = pd.concat([df, bbands], axis=1)
    
    # 5. Hệ thống Ichimoku
    ichi = ta.ichimoku(df['high'], df['low'], df['close'])[0]
    df = pd.concat([df, ichi], axis=1)

    # --- LOGIC BỎ PHIẾU THEO BẢNG QUY TẮC ---
    # Phiếu MA: Giá trên MA và MA20 cắt lên MA50
    df['V_MA'] = np.where((df['close'] > df['MA20']) & (df['MA20'] > df['MA50']), 1, -1)
    
    # Phiếu RSI: RSI < 30 (Quá bán) hoặc RSI > 70 (Quá mua)
    df['V_RSI'] = np.where(df['RSI'] < 30, 1, np.where(df['RSI'] > 70, -1, 0))
    
    # Phiếu MACD: MACD cắt lên Signal và Histogram chuyển sang xanh
    df['V_MACD'] = np.where((df['MACD_12_26_9'] > df['MACDs_12_26_9']) & (df['MACDh_12_26_9'] > 0), 1, -1)
    
    # Phiếu BB: Giá chạm dải dưới (Mua) hoặc dải trên (Bán)
    df['V_BB'] = np.where(df['close'] < df['BBL_20_2.0'], 1, np.where(df['close'] > df['BBU_20_2.0'], -1, 0))
    
    # Phiếu Ichimoku: Giá trên mây và Tenkan cắt lên Kijun
    df['V_Ichi'] = np.where((df['close'] > df['ISA_9']) & (df['ITS_9'] > df['IKS_26']), 1, -1)

    # --- TỔNG HỢP LUẬT 80/50 ---
    votes = ['V_MA', 'V_RSI', 'V_MACD', 'V_BB', 'V_Ichi']
    df['Buy_Score'] = (df[votes] == 1).sum(axis=1) / len(votes)
    df['Sell_Score'] = (df[votes] == -1).sum(axis=1) / len(votes)
    
    df['Raw_Signal'] = 0
    df.loc[df['Buy_Score'] >= 0.8, 'Raw_Signal'] = 1  
    df.loc[df['Sell_Score'] >= 0.5, 'Raw_Signal'] = -1 
    df['State'] = df['Raw_Signal'].replace(0, np.nan).ffill().fillna(0)

    # GIAO DIỆN
    last = df.iloc[-1]
    st.header(f"Phân tích mã: {symbol}")
    col1, col2, col3 = st.columns(3)
    col1.metric("TÍN HIỆU", "XANH (MUA/GIỮ)" if last['State'] == 1 else "ĐỎ (BÁN/NGOÀI)")
    col2.metric("ĐỒNG THUẬN MUA", f"{last['Buy_Score']*100:.0f}%")
    col3.metric("ĐỒNG THUẬN BÁN", f"{last['Sell_Score']*100:.0f}%")

    # BIỂU ĐỒ NẾN & CHỈ BÁO
    fig = go.Figure(data=[go.Candlestick(x=df['time'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], name='Nến')])
    fig.add_trace(go.Scatter(x=df['time'], y=df['MA20'], line=dict(color='yellow', width=1), name='MA20'))
    fig.add_trace(go.Scatter(x=df['time'], y=df['ISA_9'], line=dict(color='rgba(0,255,0,0.2)'), fill='tonexty', name='Kumo Cloud'))
    fig.update_layout(xaxis_rangeslider_visible=False, height=600, template="plotly_dark")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.error("Không tìm thấy dữ liệu. Hãy kiểm tra lại mã cổ phiếu.")
