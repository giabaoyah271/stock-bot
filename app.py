import streamlit as st
import pandas as pd
from vnstock3 import Vnstock
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
import time

# --- 1. Cấu hình ---
st.set_page_config(page_title="Hệ thống Giao dịch Pro", layout="wide")

TOP_MARKET = [
    'SSI', 'VIX', 'VND', 'SHS', 'HPG', 'DIG', 'NVL', 'PDR', 'STB', 'MBB', 
    'SHB', 'VPB', 'TCB', 'ACB', 'VHM', 'VIC', 'VNM', 'MWG', 'FPT', 'MSN',
    'GEX', 'HSG', 'NKG', 'KBC', 'VCI', 'HCM', 'CEO', 'IDC', 'TCH', 'DXG',
    'LPB', 'HDB', 'CTG', 'BID', 'VCB', 'TPB', 'VIB', 'MSB', 'OCB', 'EIB',
    'DGC', 'DCM', 'DPM', 'CSV', 'PNJ', 'REE', 'PC1', 'HDG', 'GEG', 'POW',
    'KDH', 'NLG', 'SZC', 'VGC', 'BCM', 'PHR', 'GVR', 'DPR', 'AAA', 'ASM',
    'IDI', 'ANV', 'VHC', 'FMC', 'MPC', 'HAH', 'GMD', 'VOS', 'PVT', 'PVS',
    'PVD', 'BSR', 'OIL', 'PLX', 'GAS', 'SAB', 'BHN', 'SBT', 'QNS', 'LSS',
    'MBS', 'CTS', 'AGR', 'BSI', 'FTS', 'TNG', 'VGT', 'GIL', 'TCM', 'HT1',
    'BCC', 'KSB', 'CII', 'HUT', 'LCG', 'HHV', 'VCG', 'FCN', 'CTD', 'HBC'
]

TF_MAP = {"Ngày": "1D", "1 Giờ": "1H", "15 Phút": "15", "Tuần": "1W", "Tháng": "1M"}

# --- 2. Hàm lấy dữ liệu với cơ chế dự phòng (Fix lỗi kết nối) ---
@st.cache_data(ttl=300)
def get_data(symbol, tf):
    # Thử lần lượt các nguồn dữ liệu khác nhau nếu một nguồn bị lỗi
    for source in ['TCBS', 'DNSE', 'VCI']:
        try:
            stock = Vnstock().stock(symbol=symbol, source=source)
            df = stock.quote.history(start='2024-01-01', end=datetime.now().strftime('%Y-%m-%d'), interval=TF_MAP[tf])
            if df is not None and not df.empty:
                if 'time' in df.columns:
                    df['time'] = pd.to_datetime(df['time'])
                    df.set_index('time', inplace=True)
                return df
        except:
            continue # Thử nguồn tiếp theo
    return pd.DataFrame()

def calculate_signals(df):
    if df is None or df.empty or len(df) < 20: 
        return None
    
    # Tính SMA
    df['SMA20'] = df['close'].rolling(window=20).mean()
    df['SMA50'] = df['close'].rolling(window=50).mean()
    
    # Trend: 1 là Xanh, -1 là Đỏ
    df['Trend'] = np.where((df['close'] > df['SMA20']), 1, -1)
    
    # Thống kê lãi lỗ
    last_status = df['Trend'].iloc[-1]
    entry_price, profit, days_held = 0, 0, 0
    
    if last_status == 1:
        # Tìm điểm đảo chiều từ Đỏ sang Xanh gần nhất
        change_points = df[df['Trend'] != df['Trend'].shift(1)]
        buy_date = change_points[change_points['Trend'] == 1].index[-1]
        entry_price = df.loc[buy_date, 'close']
        profit = ((df['close'].iloc[-1] / entry_price) - 1) * 100
        days_held = len(df.loc[buy_date:])

    return {
        "df": df,
        "status": "MUA" if last_status == 1 else "BÁN",
        "entry_price": entry_price,
        "profit": profit,
        "days_held": days_held
    }

# --- 3. Giao diện ---
st.sidebar.title("🛠️ Điều khiển")
mode = st.sidebar.radio("Chế độ", ["Phân tích chi tiết mã", "Quét tín hiệu toàn thị trường"])
timeframe = st.sidebar.selectbox("Khung thời gian", list(TF_MAP.keys()))

if mode == "Quét tín hiệu toàn thị trường":
    st.header(f"🔍 Trình quét thị trường ({timeframe})")
    if st.button("Bắt đầu quét danh mục"):
        results = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for idx, s in enumerate(TOP_MARKET):
            status_text.text(f"🚀 Đang kiểm tra: {s}...")
            data = get_data(s, timeframe)
            time.sleep(0.05) # Delay cực ngắn để tránh bị block
            
            res = calculate_signals(data)
            if res:
                results.append({
                    "Mã": s,
                    "Trạng thái": "🟢 XANH" if res['status'] == "MUA" else "🔴 ĐỎ",
                    "Lãi (%)": round(res['profit'], 2) if res['status'] == "MUA" else 0,
                    "Số phiên": res['days_held'] if res['status'] == "MUA" else 0
                })
            progress_bar.progress((idx + 1) / len(TOP_MARKET))
        
        status_text.empty()
        if results:
            st.dataframe(pd.DataFrame(results).sort_values("Lãi (%)", ascending=False), use_container_width=True)
        else:
            st.error("Không có dữ liệu. Vui lòng thử lại sau hoặc đổi nguồn.")

else:
    symbol = st.sidebar.text_input("Nhập mã cổ phiếu", "VTP").upper()
    data = get_data(symbol, timeframe)
    res = calculate_signals(data)
    
    if res:
        df = res['df']
        st.subheader(f"Biểu đồ {symbol} - {timeframe}")
        
        # Thống kê nhanh
        c1, c2, c3 = st.columns(3)
        if res['status'] == "MUA":
            c1.success(f"TRẠNG THÁI: XANH (MUA)")
            c2.metric("Giá vào", f"{res['entry_price']:.1f}")
            c3.metric("Lãi tạm tính", f"{res['profit']:.2f}%")
        else:
            c1.error("TRẠNG THÁI: ĐỎ (BÁN)")
        
        # Vẽ biểu đồ nến & Vùng Xanh/Đỏ
        fig = go.Figure()
        
        # Tô màu vùng
        for i in range(1, len(df)):
            color = "rgba(0, 255, 0, 0.1)" if df['Trend'].iloc[i] == 1 else "rgba(255, 0, 0, 0.1)"
            fig.add_vrect(x0=df.index[i-1], x1=df.index[i], fillcolor=color, layer="below", line_width=0)

        fig.add_trace(go.Candlestick(x=df.index, open=df['open'], high=df['high'], low=df['low'], close=df['close'], name="Giá"))
        fig.add_trace(go.Scatter(x=df.index, y=df['SMA20'], line=dict(color='blue', width=1), name="SMA20"))
        
        fig.update_layout(xaxis_rangeslider_visible=False, template="plotly_dark", height=600)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.error("❌ Không thể kết nối dữ liệu. Vui lòng kiểm tra lại mã hoặc đổi Khung thời gian.")
