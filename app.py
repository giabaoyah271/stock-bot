import streamlit as st
import pandas as pd
from vnstock import Vnstock # Sử dụng thư viện mới nhất
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time

# --- 1. CẤU HÌNH ---
st.set_page_config(page_title="Hệ thống Giao dịch Xanh-Đỏ", layout="wide")

TOP_MARKET = ['SSI', 'VIX', 'VND', 'SHS', 'HPG', 'DIG', 'NVL', 'PDR', 'STB', 'MBB', 'FPT', 'VTP', 'MWG']
TF_MAP = {"Ngày": "1D", "1 Giờ": "1H", "15 Phút": "15"}

# --- 2. HÀM LẤY DỮ LIỆU (FIX LỖI 404) ---
@st.cache_data(ttl=600)
def get_data(symbol, tf):
    # Ưu tiên nguồn VCI vì TCBS đang lỗi 404 trên Streamlit Cloud
    for src in ['VCI', 'DNSE']:
        try:
            stock = Vnstock().stock(symbol=symbol, source=src)
            df = stock.quote.history(start='2024-01-01', end=datetime.now().strftime('%Y-%m-%d'), interval=TF_MAP[tf])
            if df is not None and not df.empty:
                df['time'] = pd.to_datetime(df['time'])
                df.set_index('time', inplace=True)
                return df
        except:
            continue
    return pd.DataFrame()

def calculate_signals(df):
    if df is None or len(df) < 50: return None
    
    # Logic nến Xanh/Đỏ
    df['SMA20'] = df['close'].rolling(20).mean()
    df['Trend'] = np.where(df['close'] > df['SMA20'], 1, -1)
    
    last_status = df['Trend'].iloc[-1]
    res = {"df": df, "status": "BÁN"}
    
    if last_status == 1:
        # Tìm điểm mua
        change = df[df['Trend'] != df['Trend'].shift(1)]
        entry_date = change[change['Trend'] == 1].index[-1]
        entry_price = df.loc[entry_date, 'close']
        current_price = df['close'].iloc[-1]
        
        res.update({
            "status": "MUA",
            "entry_price": entry_price,
            "entry_date": entry_date.strftime('%d/%m/%Y'),
            "profit": ((current_price / entry_price) - 1) * 100,
            "days": len(df.loc[entry_date:]),
            "stop_loss": entry_price * 0.95,
            "target": [entry_price * 1.1, entry_price * 1.2, entry_price * 1.5]
        })
    return res

# --- 3. GIAO DIỆN ---
st.sidebar.title("🛠️ Điều khiển")
mode = st.sidebar.radio("Chế độ", ["Phân tích chi tiết mã", "Quét tín hiệu toàn thị trường"])
timeframe = st.sidebar.selectbox("Khung thời gian", list(TF_MAP.keys()))

if mode == "Quét tín hiệu toàn thị trường":
    st.header(f"🔍 Trình quét thị trường ({timeframe})")
    if st.button("Bắt đầu quét danh mục"):
        results = []
        bar = st.progress(0)
        for i, s in enumerate(TOP_MARKET):
            data = get_data(s, timeframe)
            ans = calculate_signals(data)
            if ans:
                results.append({
                    "Mã": s, "Trạng thái": "🟢 XANH" if ans['status'] == "MUA" else "🔴 ĐỎ",
                    "Lãi (%)": round(ans.get('profit', 0), 2) if ans['status'] == "MUA" else 0
                })
            bar.progress((i+1)/len(TOP_MARKET))
            time.sleep(0.1)
        st.dataframe(pd.DataFrame(results), use_container_width=True)

else:
    symbol = st.sidebar.text_input("Nhập mã cổ phiếu", "VTP").upper()
    data = get_data(symbol, timeframe)
    ans = calculate_signals(data)
    
    if ans:
        df = ans['df']
        # HIỂN THỊ GIỐNG HÌNH 3
        st.markdown(f"<h1 style='text-align: center; color: #7b2cbf;'>{symbol}</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; font-weight: bold;'>QUY TẮC GIAO DỊCH: <span style='color:green'>XANH VÀO</span> - <span style='color:red'>ĐỎ RA</span></p>", unsafe_allow_html=True)
        
        if ans['status'] == "MUA":
            c1, c2 = st.columns(2)
            c1.markdown(f"### MUA QUANH GIÁ: <span style='color:blue'>{ans['entry_price']:.1f}</span>", unsafe_allow_html=True)
            c1.markdown(f"### Ngày MUA: {ans['entry_date']}")
            c2.markdown(f"### KẾT QUẢ: Đã Lãi <span style='color:green'>{ans['profit']:.2f}%</span>", unsafe_allow_html=True)
            c2.markdown(f"### Đã nắm giữ: +{ans['days']} phiên")
            
            st.markdown(f"**Giá Chốt Lãi/Cắt Lỗ:** <span style='color:red'>{ans['stop_loss']:.1f}</span> | **Mục tiêu dự kiến:** {ans['target'][0]:.1f} | {ans['target'][1]:.1f} | {ans['target'][2]:.1f}", unsafe_allow_html=True)
            st.success(f"Khuyến nghị: Vùng Xanh, Tiếp tục nắm giữ")
        else:
            st.error("Khuyến nghị: Vùng Đỏ, Đứng ngoài thị trường")

        # BIỂU ĐỒ
        fig = go.Figure()
        for i in range(1, len(df)):
            color = "rgba(0, 255, 0, 0.15)" if df['Trend'].iloc[i] == 1 else "rgba(255, 0, 0, 0.1)"
            fig.add_vrect(x0=df.index[i-1], x1=df.index[i], fillcolor=color, layer="below", line_width=0)
        
        fig.add_trace(go.Candlestick(x=df.index, open=df['open'], high=df['high'], low=df['low'], close=df['close'], name="Giá"))
        fig.update_layout(xaxis_rangeslider_visible=False, template="plotly_dark", height=600)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.error("❌ Lỗi: Không thể lấy dữ liệu. Hãy thử đổi Khung thời gian hoặc đợi vài phút.")
