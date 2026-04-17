import streamlit as st
import pandas as pd
from vnstock import Vnstock
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import time

# --- 1. CẤU HÌNH HỆ THỐNG ---
st.set_page_config(page_title="Hệ thống Giao dịch Xanh-Đỏ Pro", layout="wide")

# Mở rộng khung thời gian: Ngày, Tuần, Tháng
TF_MAP = { 
    "1 Giờ": "1H", 
    "Ngày": "1D", 
    "Tuần": "1W", 
}
# --- 2. HÀM LẤY TOP 100 THANH KHOẢN ---
@st.cache_data(ttl=3600)
def get_top_100_liquidity():
    try:
        # Lấy top 100 mã có khối lượng giao dịch (Volume) lớn nhất sàn
        df_top = Vnstock().market.top_report(limit=100, category='top_volume')
        return df_top['symbol'].tolist()
    except:
        # Danh sách dự phòng nếu API lỗi
        return ['SSI', 'VIX', 'VND', 'SHS', 'HPG', 'DIG', 'NVL', 'PDR', 'STB', 'MBB']

TOP_MARKET = get_top_100_liquidity()

# --- 3. HÀM TÍNH TOÁN CHỈ BÁO KỸ THUẬT ---
def calculate_indicators(df):
    if df.empty or len(df) < 20: return df
    
    # MA (Moving Average)
    df['SMA20'] = df['close'].rolling(window=20).mean()
    df['SMA50'] = df['close'].rolling(window=50).mean()
    
    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # Xác định xu hướng Xanh/Đỏ (Giá trên SMA20 là Xanh)
    df['Trend'] = np.where(df['close'] > df['SMA20'], 1, -1)
    return df

# --- 4. HÀM LẤY DỮ LIỆU ---
@st.cache_data(ttl=600)
def get_data(symbol, tf):
    for src in ['VCI', 'DNSE', 'KBS']:
        try:
            stock = Vnstock().stock(symbol=symbol, source=src)
            df = stock.quote.history(start='2022-01-01', end=datetime.now().strftime('%Y-%m-%d'), interval=TF_MAP[tf])
            if df is not None and not df.empty:
                df['time'] = pd.to_datetime(df['time'])
                df.set_index('time', inplace=True)
                return calculate_indicators(df)
        except: continue
    return pd.DataFrame()

# --- 5. GIAO DIỆN SIDEBAR ---
st.sidebar.title("🛠️ Điều khiển")
mode = st.sidebar.radio("Chế độ", ["Phân tích chi tiết mã", "Quét tín hiệu toàn thị trường"])
timeframe = st.sidebar.selectbox("Khung thời gian", list(TF_MAP.keys()), index=1)

# --- 6. LOGIC HIỂN THỊ ---
if mode == "Phân tích chi tiết mã":
    symbol = st.sidebar.text_input("Nhập mã cổ phiếu", "HPG").upper()
    df = get_data(symbol, timeframe)
    
    if not df.empty:
        last_row = df.iloc[-1]
        is_green = last_row['Trend'] == 1
        
        st.markdown(f"<h1 style='text-align: center; color: #9d4edd;'>{symbol}</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; font-weight: bold;'>QUY TẮC: <span style='color:#00ff00'>XANH VÀO</span> - <span style='color:#ff0000'>ĐỎ RA</span></p>", unsafe_allow_html=True)

        if is_green:
            change = df[df['Trend'] != df['Trend'].shift(1)]
            entry_date = change[change['Trend'] == 1].index[-1]
            entry_price = df.loc[entry_date, 'close']
            profit = ((last_row['close'] / entry_price) - 1) * 100
            
            c1, c2 = st.columns(2)
            c1.metric("MUA QUANH GIÁ", f"{entry_price:.1f}", f"Ngày: {entry_date.strftime('%d/%m/%Y')}")
            c2.metric("KẾT QUẢ", f"Lãi {profit:.2f}%", f"+{len(df.loc[entry_date:])} phiên")
            st.success(f"Tín hiệu: Vùng Xanh - Mục tiêu: {entry_price*1.1:.1f} | {entry_price*1.25:.1f}")
        else:
            st.error("Tín hiệu: Vùng Đỏ - Đứng ngoài quan sát")

        # --- BIỂU ĐỒ NÂNG CẤP ---
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, 
                           vertical_spacing=0.05, 
                           row_heights=[0.6, 0.2, 0.2])

        # A. Tô màu Xanh-Đỏ cho toàn bộ biểu đồ (Vùng mua/bán)
        for i in range(1, len(df)):
            # Màu xanh nếu xu hướng tăng, màu đỏ nếu xu hướng giảm
            bg_color = "rgba(0, 255, 0, 0.15)" if df['Trend'].iloc[i] == 1 else "rgba(255, 0, 0, 0.1)"
            fig.add_vrect(x0=df.index[i-1], x1=df.index[i], fillcolor=bg_color, layer="below", line_width=0, row=1, col=1)

        # B. Nến giá & MA
        fig.add_trace(go.Candlestick(x=df.index, open=df['open'], high=df['high'], low=df['low'], close=df['close'], name="Nến giá"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['SMA20'], line=dict(color='cyan', width=1.5), name="SMA20"), row=1, col=1)

        # C. Volume & RSI
        colors_vol = ['green' if df['close'].iloc[i] >= df['open'].iloc[i] else 'red' for i in range(len(df))]
        fig.add_trace(go.Bar(x=df.index, y=df['volume'], marker_color=colors_vol, name="Khối lượng"), row=2, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], line=dict(color='purple', width=2), name="RSI"), row=3, col=1)

        # D. Cấu hình Zoom (Kéo giãn nến) và Pan
        fig.update_layout(
            xaxis_rangeslider_visible=False, 
            template="plotly_dark", 
            height=800,
            dragmode='pan', # Cho phép kéo biểu đồ
            margin=dict(l=10, r=10, t=10, b=10)
        )
        
        # Mặc định Zoom vào 100 cây nến gần nhất để không bị dính nến
        fig.update_xaxes(range=[df.index[-100], df.index[-1]])
        
        st.plotly_chart(fig, width='stretch')
    else:
        st.error("⚠️ Không thể kết nối dữ liệu mã này.")

else:
    st.header(f"🔍 Trình quét Top 100 thanh khoản (Khung: {timeframe})")
    if st.button("Bắt đầu quét danh mục"):
        results = []
        bar = st.progress(0)
        for i, s in enumerate(TOP_MARKET):
            data = get_data(s, timeframe)
            if not data.empty:
                last_s = data.iloc[-1]
                status = "🟢 MUA" if last_s['Trend'] == 1 else "🔴 BÁN"
                results.append({"Mã": s, "Trạng thái": status, "Giá": last_s['close'], "RSI": round(last_s['RSI'],1)})
            bar.progress((i + 1) / len(TOP_MARKET))
            time.sleep(0.1) # Tránh bị khóa API
        
        st.dataframe(pd.DataFrame(results), width='stretch')
