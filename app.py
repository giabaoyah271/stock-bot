import streamlit as st
import pandas as pd
from vnstock3 import Vnstock
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time

# --- CẤU HÌNH ---
st.set_page_config(page_title="Hệ thống Giao dịch v3.0", layout="wide")

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

TF_MAP = {"15 Phút": "15", "1 Giờ": "1H", "Ngày": "1D", "Tuần": "1W", "Tháng": "1M"}

# --- HÀM LẤY DỮ LIỆU (SỬA LỖI KHÔNG CÓ DỮ LIỆU) ---
@st.cache_data(ttl=300)
def get_data(symbol, tf):
    try:
        # Chuyển sang nguồn 'DNSE' hoặc 'TCBS' thường ổn định hơn VCI/KBS
        stock = Vnstock().stock(symbol=symbol, source='DNSE') 
        df = stock.quote.history(start='2024-01-01', end=datetime.now().strftime('%Y-%m-%d'), interval=TF_MAP[tf])
        if df is not None and not df.empty:
            df['time'] = pd.to_datetime(df['time'])
            df.set_index('time', inplace=True)
            return df
    except:
        return pd.DataFrame()
    return pd.DataFrame()

# --- HÀM TÍNH TOÁN TÍN HIỆU & VÙNG MUA/BÁN ---
def calculate_signals(df):
    if df is None or len(df) < 50: return None
    
    # Chỉ báo kỹ thuật
    df['SMA20'] = df['close'].rolling(20).mean()
    df['SMA50'] = df['close'].rolling(50).mean()
    
    # Logic Vùng Xanh/Đỏ (Trend Following)
    # Xanh khi Giá > SMA20 và SMA20 > SMA50
    df['Trend'] = np.where((df['close'] > df['SMA20']) & (df['SMA20'] > df['SMA50']), 1, -1)
    
    # Điểm mua gần nhất (để tính lãi lỗ như hình 3)
    buy_signals = df[df['Trend'] == 1]
    if not buy_signals.empty:
        last_buy_date = buy_signals.index[-1]
        # Tìm ngày bắt đầu chu kỳ tăng hiện tại
        start_trend = df[(df.index <= last_buy_date) & (df['Trend'] == -1)].index
        entry_date = start_trend[-1] + timedelta(days=1) if not start_trend.empty else buy_signals.index[0]
        entry_price = df.loc[df.index >= entry_date, 'close'].iloc[0]
        current_price = df['close'].iloc[-1]
        profit = ((current_price / entry_price) - 1) * 100
        days_held = (df.index[-1] - entry_date).days
    else:
        entry_price, profit, days_held, entry_date = 0, 0, 0, None

    return {
        "df": df,
        "entry_price": entry_price,
        "profit": profit,
        "days_held": days_held,
        "entry_date": entry_date,
        "status": "MUA" if df['Trend'].iloc[-1] == 1 else "BÁN"
    }

# --- GIAO DIỆN SIDEBAR ---
st.sidebar.title("🛠️ Điều khiển")
mode = st.sidebar.radio("Chế độ", ["Phân tích chi tiết mã", "Quét tín hiệu toàn thị trường"])
timeframe = st.sidebar.selectbox("Khung thời gian", list(TF_MAP.keys()))

# --- LOGIC CHÍNH ---
if mode == "Quét tín hiệu toàn thị trường":
    st.header(f"🔍 Trình quét Top 100 thanh khoản")
    if st.button("Bắt đầu quét danh mục"):
        results = []
        progress_bar = st.progress(0)
        placeholder = st.empty()
        
        for idx, s in enumerate(TOP_MARKET):
            placeholder.text(f" đang quét: {s}...")
            data = get_data(s, timeframe)
            res = calculate_signals(data)
            if res:
                results.append({
                    "Mã": s,
                    "Trạng thái": "🟢 MUA" if res['status'] == "MUA" else "🔴 BÁN",
                    "Lãi/Lỗ (%)": round(res['profit'], 2) if res['status'] == "MUA" else 0,
                    "Số phiên": res['days_held'] if res['status'] == "MUA" else 0
                })
            time.sleep(0.1)
            progress_bar.progress((idx + 1) / len(TOP_MARKET))
        
        placeholder.empty()
        if results:
            st.dataframe(pd.DataFrame(results).sort_values("Lãi/Lỗ (%)", ascending=False), use_container_width=True)
        else:
            st.error("Không quét được dữ liệu. Hãy thử đổi nguồn dữ liệu hoặc khung thời gian Ngày.")

else:
    symbol = st.sidebar.text_input("Nhập mã cổ phiếu", "VTP").upper()
    data = get_data(symbol, timeframe)
    res = calculate_signals(data)
    
    if res:
        df = res['df']
        # Header phong cách hình 3
        st.markdown(f"### {symbol} - QUY TẮC GIAO DỊCH: <span style='color:#00ff00'>XANH VÀO</span> - <span style='color:#ff0000'>ĐỎ RA</span>", unsafe_allow_html=True)
        
        if res['status'] == "MUA":
            col1, col2, col3 = st.columns(3)
            col1.metric("MUA QUANH GIÁ", f"{res['entry_price']:.1f}")
            col2.metric("KẾT QUẢ", f"Lãi {res['profit']:.2f}%")
            col3.metric("NẮM GIỮ", f"{res['days_held']} phiên")
            st.success(f"Khuyến nghị: Vùng Xanh, Tiếp tục nắm giữ")
        else:
            st.error("Khuyến nghị: Vùng Đỏ, Đứng ngoài thị trường")

        # Vẽ biểu đồ Xanh/Đỏ
        fig = go.Figure()
        
        # Thêm các vùng màu nền (Vùng Xanh/Đỏ)
        for i in range(1, len(df)):
            color = "rgba(0, 255, 0, 0.2)" if df['Trend'].iloc[i] == 1 else "rgba(255, 0, 0, 0.1)"
            fig.add_vrect(x0=df.index[i-1], x1=df.index[i], fillcolor=color, layer="below", line_width=0)

        fig.add_trace(go.Candlestick(x=df.index, open=df['open'], high=df['high'], low=df['low'], close=df['close'], name='Giá'))
        fig.add_trace(go.Scatter(x=df.index, y=df['SMA20'], line=dict(color='blue', width=1), name='SMA20'))
        
        fig.update_layout(xaxis_rangeslider_visible=False, template="plotly_dark", height=600)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Không lấy được dữ liệu. Kiểm tra lại mã hoặc nguồn DNSE đang bảo trì.")
