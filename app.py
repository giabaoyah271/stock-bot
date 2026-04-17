import streamlit as st
import pandas as pd
from vnstock3 import Vnstock
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time

# --- 1. CẤU HÌNH HỆ THỐNG ---
st.set_page_config(page_title="Hệ thống Giao dịch Xanh-Đỏ v3.0", layout="wide")

# Danh sách 100 mã thanh khoản cao nhất
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

# --- 2. HÀM HỖ TRỢ (PHẢI ĐẶT TRƯỚC LOGIC CHÍNH) ---

@st.cache_data(ttl=300)
def get_data(symbol, tf):
    try:
        # Sử dụng nguồn DNSE để ổn định dữ liệu
        stock = Vnstock().stock(symbol=symbol, source='DNSE') 
        df = stock.quote.history(start='2024-01-01', end=datetime.now().strftime('%Y-%m-%d'), interval=TF_MAP[tf])
        
        if df is not None and not df.empty:
            if 'time' in df.columns:
                df['time'] = pd.to_datetime(df['time'])
                df.set_index('time', inplace=True)
            return df
    except:
        return pd.DataFrame()
    return pd.DataFrame()

def calculate_signals(df):
    if df is None or len(df) < 50: 
        return None
    
    # Chỉ báo kỹ thuật cơ bản
    df['SMA20'] = df['close'].rolling(20).mean()
    df['SMA50'] = df['close'].rolling(50).mean()
    
    # Logic Vùng Xanh (Mua/Nắm giữ) và Vùng Đỏ (Bán/Đứng ngoài)
    # Xanh khi: Giá đóng cửa > SMA20 và SMA20 > SMA50
    df['Trend'] = np.where((df['close'] > df['SMA20']) & (df['SMA20'] > df['SMA50']), 1, -1)
    
    # Tính toán hiệu quả (Lãi/Lỗ) từ điểm mua gần nhất
    current_status = df['Trend'].iloc[-1]
    entry_price, profit, days_held, entry_date = 0, 0, 0, None

    if current_status == 1:
        # Tìm ngày bắt đầu chu kỳ Xanh hiện tại
        trend_changes = df[df['Trend'] != df['Trend'].shift(1)]
        entry_date = trend_changes[trend_changes['Trend'] == 1].index[-1]
        entry_price = df.loc[entry_date, 'close']
        current_price = df['close'].iloc[-1]
        profit = ((current_price / entry_price) - 1) * 100
        days_held = len(df[df.index >= entry_date])

    return {
        "df": df,
        "entry_price": entry_price,
        "profit": profit,
        "days_held": days_held,
        "entry_date": entry_date,
        "status": "MUA" if current_status == 1 else "BÁN"
    }

# --- 3. GIAO DIỆN SIDEBAR ---
st.sidebar.title("🛠️ Điều khiển")
mode = st.sidebar.radio("Chế độ", ["Phân tích chi tiết mã", "Quét tín hiệu toàn thị trường"])
timeframe = st.sidebar.selectbox("Khung thời gian", list(TF_MAP.keys()))

# --- 4. LOGIC HIỂN THỊ ---

if mode == "Quét tín hiệu toàn thị trường":
    st.header(f"🔍 Trình quét Top 100 thanh khoản (Khung: {timeframe})")
    
    if st.button("Bắt đầu quét danh mục"):
        results = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for idx, s in enumerate(TOP_MARKET):
            status_text.text(f"🚀 Đang kiểm tra mã: {s} ({idx+1}/100)...")
            data = get_data(s, timeframe)
            # Nghỉ 0.1s để tránh bị API chặn do gửi yêu cầu quá nhanh
            time.sleep(0.1)
            
            res = calculate_signals(data)
            if res:
                results.append({
                    "Mã": s,
                    "Trạng thái": "🟢 XANH (MUA)" if res['status'] == "MUA" else "🔴 ĐỎ (BÁN)",
                    "Giá vào": round(res['entry_price'], 1) if res['status'] == "MUA" else 0,
                    "Lãi/Lỗ (%)": round(res['profit'], 2) if res['status'] == "MUA" else 0,
                    "Số phiên": res['days_held'] if res['status'] == "MUA" else 0
                })
            progress_bar.progress((idx + 1) / len(TOP_MARKET))
        
        status_text.success(f"✅ Đã quét xong {len(results)} mã!")
        
        if results:
            res_df = pd.DataFrame(results).sort_values(by="Lãi/Lỗ (%)", ascending=False)
            st.dataframe(
                res_df,
                column_config={
                    "Lãi/Lỗ (%)": st.column_config.ProgressColumn("Hiệu suất Lãi/Lỗ", format="%.2f%%", min_value=-20, max_value=20),
                },
                use_container_width=True,
                height=600
            )

else:
    # CHẾ ĐỘ PHÂN TÍCH CHI TIẾT (Giống hình 3 bạn yêu cầu)
    symbol = st.sidebar.text_input("Nhập mã cổ phiếu", "VTP").upper()
    data = get_data(symbol, timeframe)
    res = calculate_signals(data)
    
    if res:
        df = res['df']
        st.markdown(f"## {symbol} - CHIẾN THUẬT: <span style='color:#00ff00'>XANH VÀO</span> - <span style='color:#ff0000'>ĐỎ RA</span>", unsafe_allow_html=True)
        
        # Hiển thị các Metric thống kê
        c1, c2, c3, c4 = st.columns(4)
        if res['status'] == "MUA":
            c1.metric("TRẠNG THÁI", "VÙNG XANH", delta="MUA/NẮM GIỮ")
            c2.metric("MUA QUANH GIÁ", f"{res['entry_price']:.1f}")
            c3.metric("LÃI/LỖ TẠM TÍNH", f"{res['profit']:.2f}%")
            c4.metric("SỐ PHIÊN GIỮ", f"{res['days_held']} phiên")
        else:
            c1.metric("TRẠNG THÁI", "VÙNG ĐỎ", delta="- BÁN/ĐỨNG NGOÀI", delta_color="inverse")
            c2.metric("GIÁ HIỆN TẠI", f"{df['close'].iloc[-1]:.1f}")
            c3.metric("TÍN HIỆU", "CHỜ ĐỢI")
            c4.metric("XU HƯỚNG", "GIẢM")

        # Vẽ biểu đồ kỹ thuật
        fig = go.Figure()

        # Tô màu vùng Xanh/Đỏ cho nền biểu đồ
        for i in range(1, len(df)):
            bg_color = "rgba(0, 255, 0, 0.15)" if df['Trend'].iloc[i] == 1 else "rgba(255, 0, 0, 0.08)"
            fig.add_vrect(x0=df.index[i-1], x1=df.index[i], fillcolor=bg_color, layer="below", line_width=0)

        # Biểu đồ nến
        fig.add_trace(go.Candlestick(x=df.index, open=df['open'], high=df['high'], low=df['low'], close=df['close'], name='Giá nến'))
        
        # Đường hỗ trợ SMA20
        fig.add_trace(go.Scatter(x=df.index, y=df['SMA20'], line=dict(color='cyan', width=1.5), name='SMA20'))

        fig.update_layout(xaxis_rangeslider_visible=False, template="plotly_dark", height=650, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.error("⚠️ Không thể kết nối dữ liệu. Vui lòng kiểm tra lại mã cổ phiếu hoặc đổi Khung thời gian.")
