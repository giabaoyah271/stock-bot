import streamlit as st
import pandas as pd
from vnstock import Vnstock # Dùng thư viện vnstock mới nhất
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time

# --- 1. CẤU HÌNH ---
st.set_page_config(page_title="Hệ thống Giao dịch Xanh-Đỏ v4.0", layout="wide")

TOP_MARKET = ['SSI', 'VIX', 'VND', 'SHS', 'HPG', 'DIG', 'NVL', 'PDR', 'STB', 'MBB', 'FPT', 'VTP', 'MWG', 'VNM', 'VIC']
TF_MAP = {"Ngày": "1D", "1 Giờ": "1H", "15 Phút": "15"}

# --- 2. HÀM LẤY DỮ LIỆU CẢI TIẾN ---
@st.cache_data(ttl=600)
def get_data(symbol, tf):
    # Thử các nguồn ổn định hơn TCBS vào lúc này
    for src in ['VCI', 'DNSE', 'KBS']:
        try:
            stock = Vnstock().stock(symbol=symbol, source=src)
            # Lấy dữ liệu từ đầu năm 2024 đến ngày hôm nay (tháng 4/2026)
            df = stock.quote.history(start='2024-01-01', end=datetime.now().strftime('%Y-%m-%d'), interval=TF_MAP[tf])
            
            if df is not None and not df.empty and len(df) > 10:
                if 'time' in df.columns:
                    df['time'] = pd.to_datetime(df['time'])
                    df.set_index('time', inplace=True)
                return df
        except Exception as e:
            continue # Thử nguồn tiếp theo nếu nguồn này lỗi
    return pd.DataFrame()

def calculate_signals(df):
    if df is None or df.empty or len(df) < 30: 
        return None
    
    # Tính SMA20 để xác định vùng Xanh/Đỏ
    df['SMA20'] = df['close'].rolling(20).mean()
    df['Trend'] = np.where(df['close'] > df['SMA20'], 1, -1)
    
    last_status = df['Trend'].iloc[-1]
    res = {"df": df, "status": "BÁN"}
    
    if last_status == 1:
        # Tìm điểm bắt đầu chu kỳ Xanh
        change = df[df['Trend'] != df['Trend'].shift(1)]
        entry_date = change[change['Trend'] == 1].index[-1]
        entry_price = df.loc[entry_date, 'close']
        current_price = df['close'].iloc[-1]
        
        # Tính toán các thông số như hình 3
        res.update({
            "status": "MUA",
            "entry_price": entry_price,
            "entry_date": entry_date.strftime('%d/%m/%Y'),
            "profit": ((current_price / entry_price) - 1) * 100,
            "days": len(df.loc[entry_date:]),
            "stop_loss": entry_price * 0.95,
            "targets": [entry_price * 1.1, entry_price * 1.25, entry_price * 1.5]
        })
    return res

# --- 3. GIAO DIỆN ---
st.sidebar.title("🛠️ Điều khiển")
mode = st.sidebar.radio("Chế độ", ["Phân tích chi tiết mã", "Quét tín hiệu toàn thị trường"])
timeframe = st.sidebar.selectbox("Khung thời gian", list(TF_MAP.keys()))

if mode == "Quét tín hiệu toàn thị trường":
    st.header(f"🔍 Trình quét tín hiệu ({timeframe})")
    if st.button("Bắt đầu quét danh mục"):
        results = []
        bar = st.progress(0)
        status = st.empty()
        
        for i, s in enumerate(TOP_MARKET):
            status.text(f"🚀 Đang kiểm tra: {s}...")
            data = get_data(s, timeframe)
            ans = calculate_signals(data)
            if ans:
                results.append({
                    "Mã": s, 
                    "Trạng thái": "🟢 XANH" if ans['status'] == "MUA" else "🔴 ĐỎ",
                    "Lãi (%)": round(ans.get('profit', 0), 2) if ans['status'] == "MUA" else 0,
                    "Số phiên": ans.get('days', 0) if ans['status'] == "MUA" else 0
                })
            bar.progress((i+1)/len(TOP_MARKET))
            time.sleep(0.1)
            
        status.empty()
        if results:
            st.dataframe(pd.DataFrame(results).sort_values("Lãi (%)", ascending=False), width='stretch')
        else:
            st.error("⚠️ Không lấy được dữ liệu. Kiểm tra lại kết nối API.")

else:
    symbol = st.sidebar.text_input("Nhập mã cổ phiếu", "VTP").upper()
    data = get_data(symbol, timeframe)
    ans = calculate_signals(data)
    
    if ans:
        df = ans['df']
        # Giao diện phong cách chuyên nghiệp (Hình 3)
        st.markdown(f"<h1 style='text-align: center; color: #9d4edd;'>{symbol}</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; font-weight: bold;'>QUY TẮC: <span style='color:#00ff00'>XANH VÀO</span> - <span style='color:#ff0000'>ĐỎ RA</span></p>", unsafe_allow_html=True)
        
        if ans['status'] == "MUA":
            col1, col2 = st.columns(2)
            with col1:
                st.metric("MUA QUANH GIÁ", f"{ans['entry_price']:.1f}", f"Ngày: {ans['entry_date']}")
                st.write(f"**Giá cắt lỗ (5%):** {ans['stop_loss']:.1f}")
            with col2:
                st.metric("KẾT QUẢ", f"Lãi {ans['profit']:.2f}%", f"+{ans['days']} phiên")
                st.write(f"**Mục tiêu:** {ans['targets'][0]:.1f} | {ans['targets'][1]:.1f} | {ans['targets'][2]:.1f}")
            st.success("Tín hiệu: Vùng Xanh - Tiếp tục nắm giữ")
        else:
            st.error("Tín hiệu: Vùng Đỏ - Đứng ngoài quan sát")

        # Vẽ biểu đồ
        fig = go.Figure()
        # Tô màu nền
        for i in range(1, len(df)):
            color = "rgba(0, 255, 0, 0.12)" if df['Trend'].iloc[i] == 1 else "rgba(255, 0, 0, 0.08)"
            fig.add_vrect(x0=df.index[i-1], x1=df.index[i], fillcolor=color, layer="below", line_width=0)
        
        fig.add_trace(go.Candlestick(x=df.index, open=df['open'], high=df['high'], low=df['low'], close=df['close'], name="Nến giá"))
        fig.add_trace(go.Scatter(x=df.index, y=df['SMA20'], line=dict(color='cyan', width=1), name="SMA20"))
        
        fig.update_layout(xaxis_rangeslider_visible=False, template="plotly_dark", height=600, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, width='stretch')
    else:
        st.warning("⚠️ Không thể kết nối dữ liệu. Thử đổi mã khác (ví dụ: HPG, FPT) hoặc đổi Khung thời gian.")
