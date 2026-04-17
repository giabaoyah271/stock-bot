import streamlit as st
import pandas as pd
from vnstock import Vnstock
import numpy as np
import plotly.graph_objects as go

# Cấu hình giao diện
st.set_page_config(page_title="Hệ thống 80/50 - Fintech UEH", layout="wide")

st.title("🛡️ Chiến thuật Giao dịch Định lượng 80/50")
st.markdown("---")

# Sidebar chọn mã
symbol = st.sidebar.text_input("Nhập mã cổ phiếu (VD: HPG, FPT, VNM)", "HPG").upper()

# Hàm lấy dữ liệu từ nguồn KBS ổn định
@st.cache_data(ttl=3600)
def load_data(ticker):
    try:
        stock = Vnstock().stock(symbol=ticker, source='KBS')
        return stock.quote.history(start='2024-01-01', end='2026-12-31')
    except:
        return pd.DataFrame()

df = load_data(symbol)

if not df.empty:
    # 1. Tính toán chỉ báo
    # Ichimoku
    ichi = ichimoku(df['high'], df['low'], df['close'])[0]
    df = pd.concat([df, ichi], axis=1)
    
    # SMA, RSI, MACD
    df['SMA200'] = ta.sma(df['close'], length=200)
    df['RSI'] = ta.rsi(df['close'], length=14)
    macd = ta.macd(df['close'])
    df = pd.concat([df, macd], axis=1)
    df['Vol_MA20'] = ta.sma(df['volume'], length=20)

    # 2. Logic Bỏ phiếu (Voting)
    df['V_Ichi'] = np.where(df['close'] > df['ISA_9'], 1, np.where(df['close'] < df['ISB_26'], -1, 0))
    df['V_Trend'] = np.where(df['close'] > df['SMA200'], 1, -1)
    df['V_RSI'] = np.where(df['RSI'] < 35, 1, np.where(df['RSI'] > 70, -1, 0))
    df['V_MACD'] = np.where(df['MACD_12_26_9'] > df['MACDs_12_26_9'], 1, -1)
    df['V_Vol'] = np.where(df['volume'] > df['Vol_MA20'] * 1.3, 1, 0)
    df['V_Price'] = np.where(df['close'] > df['open'], 1, -1)

    # 3. Áp dụng luật 80/50
    votes = ['V_Ichi', 'V_Trend', 'V_RSI', 'V_MACD', 'V_Vol', 'V_Price']
    df['Buy_Score'] = (df[votes] == 1).sum(axis=1) / len(votes)
    df['Sell_Score'] = (df[votes] == -1).sum(axis=1) / len(votes)
    
    df['Raw_Signal'] = 0
    df.loc[df['Buy_Score'] >= 0.8, 'Raw_Signal'] = 1  
    df.loc[df['Sell_Score'] >= 0.5, 'Raw_Signal'] = -1 
    df['State'] = df['Raw_Signal'].replace(0, np.nan).ffill().fillna(0)

    # 4. Hiển thị thông số
    last = df.iloc[-1]
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("TÍN HIỆU", "XANH (MUA/GIỮ)" if last['State'] == 1 else "ĐỎ (BÁN/NGOÀI)", delta_color="normal")
    with c2:
        st.write(f"**Đồng thuận Mua:** {last['Buy_Score']*100:.0f}%")
        st.progress(last['Buy_Score'])
    with c3:
        st.write(f"**Đồng thuận Bán:** {last['Sell_Score']*100:.0f}%")
        st.progress(last['Sell_Score'])

    # 5. Vẽ biểu đồ
    fig = go.Figure(data=[go.Candlestick(x=df['time'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], name=symbol)])
    fig.update_layout(xaxis_rangeslider_visible=False, height=600, template="plotly_dark")
    st.plotly_chart(fig, use_container_width=True)

else:
    st.warning("⚠️ Không thể kết nối dữ liệu. Vui lòng kiểm tra lại mã cổ phiếu.")
