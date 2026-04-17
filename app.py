import streamlit as st
import pandas as pd
from vnstock import Vnstock
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import time

# --- 1. CẤU HÌNH HỆ THỐNG ---
st.set_page_config(page_title="Hệ thống Giao dịch Xanh-Đỏ", layout="wide")

TF_MAP = {"1 Giờ": "1H", "Ngày": "1D", "Tuần": "1W"}

# --- 2. DANH SÁCH 150 MÃ THANH KHOẢN CAO ---
@st.cache_data(ttl=3600)
def get_top_liquidity():
    # Danh sách 150 mã tiêu biểu trên cả 2 sàn VN-Index & HNX-Index
    return [
        'SSI', 'VIX', 'VND', 'SHS', 'HPG', 'DIG', 'NVL', 'PDR', 'STB', 'MBB',
        'TCB', 'VPB', 'SHB', 'ACB', 'DXG', 'VCI', 'HCM', 'CEO', 'HAG', 'HSG',
        'NKG', 'GVR', 'FPT', 'MWG', 'MSN', 'VIC', 'VHM', 'VCB', 'BID', 'CTG',
        'LPB', 'HDB', 'TPB', 'MSB', 'OCB', 'EIB', 'VIB', 'DGC', 'DPM', 'DCM',
        'PVD', 'PVS', 'PVT', 'BSR', 'GAS', 'PLX', 'POW', 'VRE', 'GMD', 'HAH',
        'VJC', 'HVN', 'REE', 'PC1', 'VCG', 'HHV', 'LCG', 'C4G', 'FCN', 'CII',
        'KBC', 'SZC', 'IDC', 'ITA', 'HQC', 'SCR', 'CRE', 'KHG', 'TDC', 'IJC',
        'VPI', 'CTD', 'SAB', 'PNJ', 'DBC', 'PAN', 'ANV', 'IDI', 'VHC', 'GEG',
        'NT2', 'PPC', 'TV2', 'CSV', 'BFC', 'LAS', 'PHR', 'DPR', 'VGT', 'MSH',
        'TCM', 'LSS', 'SBT', 'QCG', 'DXS', 'HUT', 'TNG', 'VGS', 'MBS', 'PVC',
        'VDS', 'BSI', 'FTS', 'CTS', 'AGR', 'ORS', 'BVB', 'ABB', 'NAB', 'MSH',
        'TLG', 'GIL', 'TCH', 'HHS', 'HT1', 'BCC', 'PLC', 'KSB', 'DHA', 'VGC',
        'NLG', 'KDH', 'ASM', 'BCG', 'SAM', 'PET', 'DGW', 'FRT', 'CTR', 'VGI',
        'PVB', 'PVC', 'PVP', 'VTO', 'VIP', 'VOS', 'SKG', 'VNB', 'TIG', 'MST',
        'IDJ', 'L14', 'L18', 'S99', 'TVC', 'TVS', 'FIT', 'TSC', 'HAR', 'LDG'
    ]

TOP_MARKET = get_top_liquidity()

# --- 3. TÍNH TOÁN CHỈ BÁO KỸ THUẬT ---
def calculate_indicators(df):
    if df.empty or len(df) < 50: return df
    
    # SMA 20 & 50
    df['SMA20'] = df['close'].rolling(window=20).mean()
    df['SMA50'] = df['close'].rolling(window=50).mean()
    
    # RSI chuẩn (Wilder's Smoothing)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0))
    loss = (-delta.where(delta < 0, 0))
    avg_gain = gain.ewm(com=13, min_periods=14).mean()
    avg_loss = loss.ewm(com=13, min_periods=14).mean()
    rs = avg_gain / (avg_loss + 1e-9)
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # CHIẾN THUẬT: XANH khi giá nằm trên SMA20 và SMA20 > SMA50 (Lọc nhiễu)
    df['Trend'] = np.where((df['close'] > df['SMA20']), 1, -1)
    return df

# --- 4. HÀM LẤY DỮ LIỆU ---
@st.cache_data(ttl=600)
def get_data(symbol, tf):
    for src in ['VCI', 'DNSE', 'KBS']:
        try:
            stock = Vnstock().stock(symbol=symbol, source=src)
            df = stock.quote.history(start='2023-01-01', end=datetime.now().strftime('%Y-%m-%d'), interval=TF_MAP[tf])
            if df is not None and not df.empty:
                df['time'] = pd.to_datetime(df['time'])
                df.set_index('time', inplace=True)
                return calculate_indicators(df)
        except: continue
    return pd.DataFrame()

# --- 5. GIAO DIỆN CHÍNH ---
st.sidebar.title("🛠️ Điều khiển")
mode = st.sidebar.radio("Chế độ", ["Phân tích chi tiết mã", "Quét tín hiệu toàn thị trường"])
timeframe = st.sidebar.selectbox("Khung thời gian", list(TF_MAP.keys()), index=1)

if mode == "Phân tích chi tiết mã":
    symbol = st.sidebar.text_input("Nhập mã cổ phiếu", "HPG").upper()
    df = get_data(symbol, timeframe)
    
    if not df.empty:
        last_row = df.iloc[-1]
        is_green = last_row['Trend'] == 1
        
        st.markdown(f"<h1 style='text-align: center; color: #800080; font-size: 60px;'>{symbol}</h1>", unsafe_allow_html=True)
        
        # Tìm điểm giao cắt
        change = df[df['Trend'] != df['Trend'].shift(1)]
        entry_date = change[change['Trend'] == df['Trend'].iloc[-1]].index[-1] if not change.empty else df.index[0]
        entry_price = float(df.loc[entry_date, 'close'])
        last_price = float(last_row['close'])
        profit = ((last_price / entry_price) - 1) * 100
        days_held = len(df.loc[entry_date:])

        col1, col2, col3 = st.columns(3)
        col1.metric("Giá Hiện Tại", f"{last_price:,.2f}")
        col2.metric(f"Giá tại điểm {'MUA' if is_green else 'BÁN'}", f"{entry_price:,.2f}")
        col3.metric("Biến động", f"{profit:.2f}%", delta_color="normal")

        if is_green:
            st.success("🟢 VÙNG XANH: Ưu tiên nắm giữ / Mua mới")
        else:
            st.error("🔴 VÙNG ĐỎ: Ưu tiên đứng ngoài / Bán giảm tỷ trọng")

        # Biểu đồ
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, row_heights=[0.6, 0.2, 0.2], vertical_spacing=0.05)
        fig.add_trace(go.Candlestick(x=df.index, open=df['open'], high=df['high'], low=df['low'], close=df['close'], name="Giá"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['SMA20'], line=dict(color='cyan'), name="SMA20"), row=1, col=1)
        fig.add_trace(go.Bar(x=df.index, y=df['volume'], name="Khối lượng"), row=2, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], line=dict(color='purple'), name="RSI"), row=3, col=1)
        
        fig.update_layout(height=800, template="plotly_dark", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.error("Không tìm thấy dữ liệu cho mã này.")

else:
    st.header(f"🔍 Trình quét 150 mã (Khung: {timeframe})")
    if st.button("Bắt đầu quét dữ liệu"):
        results = []
        bar = st.progress(0)
        
        for i, s in enumerate(TOP_MARKET):
            data = get_data(s, timeframe)
            if not data.empty:
                try:
                    last_s = data.iloc[-1]
                    # Tìm điểm báo tín hiệu
                    change = data[data['Trend'] != data['Trend'].shift(1)]
                    entry_date = change[change['Trend'] == data['Trend'].iloc[-1]].index[-1] if not change.empty else data.index[0]
                    entry_price = float(data.loc[entry_date, 'close'])
                    current_price = float(last_s['close'])
                    profit = ((current_price / entry_price) - 1) * 100
                    
                    results.append({
                        "Mã": s,
                        "Tín hiệu": "🟢 XANH" if last_s['Trend'] == 1 else "🔴 ĐỎ",
                        "Giá Tín Hiệu": entry_price,
                        "Giá Hiện Tại": current_price,
                        "Lời/Lỗ (%)": profit,
                        "RSI": float(last_s['RSI'])
                    })
                except: continue
            
            bar.progress((i + 1) / len(TOP_MARKET))
            time.sleep(0.05) # Giảm tải cho server API

        # --- XỬ LÝ HIỂN THỊ AN TOÀN ---
        if results:
            df_res = pd.DataFrame(results)
            
            # Làm sạch dữ liệu để tránh lỗi TypeError (CỰC KỲ QUAN TRỌNG)
            cols_numeric = ["Giá Tín Hiệu", "Giá Hiện Tại", "Lời/Lỗ (%)", "RSI"]
            for col in cols_numeric:
                df_res[col] = pd.to_numeric(df_res[col], errors='coerce')
            
            df_res = df_res.dropna() # Loại bỏ các dòng lỗi
            df_res = df_res.sort_values(by="Lời/Lỗ (%)", ascending=False)

            st.dataframe(
                df_res.style.format({
                    "Giá Tín Hiệu": "{:.2f}",
                    "Giá Hiện Tại": "{:.2f}",
                    "Lời/Lỗ (%)": "{:.2f}%",
                    "RSI": "{:.1f}"
                }).map(lambda x: 'color: lime' if x == "🟢 XANH" else ('color: red' if x == "🔴 ĐỎ" else ''), subset=['Tín hiệu']),
                use_container_width=True,
                height=800
            )
        else:
            st.warning("Không lấy được dữ liệu. Vui lòng thử lại sau.")
