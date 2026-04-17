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

# --- 2. HÀM LẤY TOP 100 THANH KHOẢN ---
@st.cache_data(ttl=3600)
def get_top_100_liquidity():
        return [
            'SSI', 'VIX', 'VND', 'SHS', 'HPG', 'DIG', 'NVL', 'PDR', 'STB', 'MBB', 
            'TCB', 'GEX', 'VHM', 'VIC', 'VRE', 'VPB', 'ACB', 'HDB', 'CTG', 'BID', 
            'VCB', 'MSN', 'MWG', 'FPT', 'PNJ', 'GAS', 'SAB', 'VNM', 'BVH', 'POW', 
            'KBC', 'VGC', 'IDC', 'SZC', 'NLG', 'KDH', 'DXG', 'CEO', 'HAG', 'HSG', 
            'NKG', 'DGC', 'DPM', 'DCM', 'CSV', 'GVR', 'PHR', 'DPR', 'HCM', 'VCI', 
            'MBS', 'FTS', 'CTS', 'BSI', 'AGR', 'TCH', 'HHV', 'VCG', 'LCG', 'FCN', 
            'CII', 'HUT', 'KDC', 'SBT', 'PAN', 'LTG', 'ASM', 'IDI', 'ANV', 'VHC', 
            'FMC', 'PC1', 'HDG', 'GEG', 'REE', 'NT2', 'VSH', 'TNG', 'TCM', 'GIL', 
            'HAH', 'VOS', 'PVT', 'PVS', 'PVD', 'BSR', 'OIL', 'PLX', 'BCG', 'SAM', 
            'ITA', 'HQC', 'SCR', 'CRE', 'KHG', 'TDC', 'IJC', 'VPI', 'CTD', 'LPB'
        ]

TOP_MARKET = get_top_100_liquidity()

# --- 3. TÍNH TOÁN CHỈ BÁO KỸ THUẬT ---
def calculate_indicators(df):
    if df.empty or len(df) < 20: return df
    
    df['SMA20'] = df['close'].rolling(window=20).mean()
    df['SMA50'] = df['close'].rolling(window=50).mean()
    
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / (loss + 1e-9)
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # Xác định xu hướng: Giá > SMA20 là 1 (Mua), ngược lại -1 (Bán)
    df['Trend'] = np.where(df['close'] > df['SMA20'], 1, -1)
    return df

# --- 4. HÀM LẤY DỮ LIỆU ---
@st.cache_data(ttl=600)
def get_data(symbol, tf):
    for src in ['TCBS','VCI', 'DNSE', 'KBS']:
        try:
            stock = Vnstock().stock(symbol=symbol, source=src)
            df = stock.quote.history(start='2022-01-01', end=datetime.now().strftime('%Y-%m-%d'), interval=TF_MAP[tf])
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
        
        st.markdown(f"<h1 style='text-align: center; color: #800080; font-size: 60px; margin-bottom:0px;'>{symbol}</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; font-weight: bold;'>QUY TẮC GIAO DỊCH: <span style='color:#00ff00'>XANH VÀO</span> - <span style='color:#ff0000'>ĐỎ RA</span></p>", unsafe_allow_html=True)

        # Tìm điểm giao cắt tín hiệu gần nhất
        change = df[df['Trend'] != df['Trend'].shift(1)]
        entry_date = change[change['Trend'] == df['Trend'].iloc[-1]].index[-1] if not change.empty else df.index[0]
        entry_price = df.loc[entry_date, 'close']
        last_price = last_row['close']
        profit = ((last_price / entry_price) - 1) * 100
        days_held = len(df.loc[entry_date:])

        col_info1, col_info2 = st.columns(2)
        with col_info1:
            st.markdown(f"<h3 style='color:blue;'>GIÁ TẠI ĐIỂM {('MUA' if is_green else 'BÁN')}: {entry_price:.2f}</h3>", unsafe_allow_html=True)
            st.markdown(f"<h3 style='color:black;'>GIÁ HIỆN TẠI: {last_price:.2f}</h3>", unsafe_allow_html=True)
        with col_info2:
            st.write(f"**Ngày Tín Hiệu:** {entry_date.strftime('%d/%m/%Y')}")
            color_pct = "green" if profit >= 0 else "red"
            st.markdown(f"**BIẾN ĐỘNG: <span style='color:{color_pct}; font-size:20px;'>{profit:.2f}%</span> | Đã qua {days_held} phiên**", unsafe_allow_html=True)

        if is_green:
            st.success(f"Khuyến nghị: Đang ở Vùng Xanh (MUA) - Tiếp tục nắm giữ")
        else:
            st.error(f"Khuyến nghị: Đang ở Vùng Đỏ (BÁN) - Đứng ngoài quan sát")

        # --- VẼ BIỂU ĐỒ ---
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.6, 0.2, 0.2])

        # Nến giá & SMA
        fig.add_trace(go.Candlestick(x=df.index, open=df['open'], high=df['high'], low=df['low'], close=df['close'], name="Nến giá"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['SMA20'], line=dict(color='cyan', width=1.5), name="SMA20"), row=1, col=1)
        
        # MŨI TÊN TÍN HIỆU MUA/BÁN
        buy_signals = df[(df['Trend'] == 1) & (df['Trend'].shift(1) == -1)]
        sell_signals = df[(df['Trend'] == -1) & (df['Trend'].shift(1) == 1)]
        
        fig.add_trace(go.Scatter(x=buy_signals.index, y=buy_signals['low']*0.97, mode='markers', marker=dict(symbol='triangle-up', color='lime', size=16), name='Điểm MUA'), row=1, col=1)
        fig.add_trace(go.Scatter(x=sell_signals.index, y=sell_signals['high']*1.03, mode='markers', marker=dict(symbol='triangle-down', color='red', size=16), name='Điểm BÁN'), row=1, col=1)

        # Volume & RSI
        colors_vol = ['green' if df['close'].iloc[i] >= df['open'].iloc[i] else 'red' for i in range(len(df))]
        fig.add_trace(go.Bar(x=df.index, y=df['volume'], marker_color=colors_vol, name="Khối lượng"), row=2, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], line=dict(color='purple', width=2), name="RSI"), row=3, col=1)

        fig.update_layout(xaxis_rangeslider_visible=False, template="plotly_dark", height=750, margin=dict(l=10, r=10, t=10, b=10), hovermode='x unified')
        fig.update_xaxes(range=[df.index[-100], df.index[-1]])
        st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True})
    else:
        st.error("⚠️ Không thể kết nối dữ liệu.")

else:
    st.header(f"🔍 Trình quét tín hiệu (Khung: {timeframe})")
    if st.button("Bắt đầu quét"):
        results = []
        bar = st.progress(0)
        for i, s in enumerate(TOP_MARKET):
            data = get_data(s, timeframe)
            if not data.empty:
                last_s = data.iloc[-1]
                is_green = last_s['Trend'] == 1
                status = "🟢 MUA" if is_green else "🔴 BÁN"
                
                # Tìm mức giá tại ngày báo tín hiệu
                change = data[data['Trend'] != data['Trend'].shift(1)]
                entry_date = change[change['Trend'] == data['Trend'].iloc[-1]].index[-1] if not change.empty else data.index[0]
                entry_price = data.loc[entry_date, 'close']
                profit = ((last_s['close'] / entry_price) - 1) * 100
                
                results.append({
                    "Mã": s, 
                    "Trạng thái": status, 
                    "Giá Tín Hiệu": entry_price, 
                    "Giá Hiện Tại": last_s['close'],
                    "Lời/Lỗ (%)": profit
                })
            
            bar.progress(min((i + 1) / len(TOP_MARKET), 1.0))
            time.sleep(0.1) # Tránh bị API block
        
        # Format bảng hiển thị đẹp mắt
        df_res = pd.DataFrame(results)
        if not df_res.empty:
            st.dataframe(
                df_res.style.format({
                    "Giá Tín Hiệu": "{:.2f}", 
                    "Giá Hiện Tại": "{:.2f}", 
                    "Lời/Lỗ (%)": "{:.2f}%"
                }), 
                use_container_width=True,
                height=600
            )
