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
            'TCB', 'VPB', 'SHB', 'ACB', 'DXG', 'VCI', 'HCM', 'CEO', 'HAG', 'HSG',
            'NKG', 'GVR', 'FPT', 'MWG', 'MSN', 'VIC', 'VHM', 'VCB', 'BID', 'CTG',
            'LPB', 'HDB', 'TPB', 'MSB', 'OCB', 'EIB', 'VIB', 'DGC', 'DPM', 'DCM',
            'PVD', 'PVS', 'PVT', 'BSR', 'GAS', 'PLX', 'POW', 'VRE', 'GMD', 'HAH',
            'VJC', 'HVN', 'REE', 'PC1', 'VCG', 'HHV', 'LCG', 'C4G', 'FCN', 'CII',
            'KBC', 'SZC', 'IDC', 'ITA', 'HQC', 'SCR', 'CRE', 'KHG', 'TDC', 'IJC',
            'VPI', 'CTD', 'SAB', 'PNJ', 'DBC', 'PAN', 'ANV', 'IDI', 'VHC', 'GEG',
            'NT2', 'PPC', 'TV2', 'CSV', 'BFC', 'LAS', 'PHR', 'DPR', 'VGT', 'MSH',
            'TCM', 'LSS', 'SBT', 'QCG', 'DXS', 'HUT', 'TNG', 'VGS', 'MBS', 'PVC'
        ]

TOP_MARKET = get_top_100_liquidity()

# --- 3. TÍNH TOÁN CHỈ BÁO KỸ THUẬT ---
def calculate_indicators(df):
    if df.empty or len(df) < 200: 
        return df
    
    # --- A. TÍNH TOÁN CÁC CHỈ BÁO ---
    df['SMA20'] = df['close'].rolling(window=20).mean()
    df['SMA50'] = df['close'].rolling(window=50).mean()
    df['SMA200'] = df['close'].rolling(window=200).mean()
    
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    df['RSI'] = 100 - (100 / (1 + gain / (loss + 1e-9)))
    
    exp1 = df['close'].ewm(span=12, adjust=False).mean()
    exp2 = df['close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp1 - exp2
    df['Signal_Line'] = df['MACD'].ewm(span=9, adjust=False).mean()
    
    df['BB_mid'] = df['SMA20']
    df['BB_std'] = df['close'].rolling(window=20).std()
    df['BB_upper'] = df['BB_mid'] + 2 * df['BB_std']
    df['BB_lower'] = df['BB_mid'] - 2 * df['BB_std']
    
    df['Tenkan_Sen'] = (df['high'].rolling(window=9).max() + df['low'].rolling(window=9).min()) / 2
    df['Kijun_Sen'] = (df['high'].rolling(window=26).max() + df['low'].rolling(window=26).min()) / 2
    df['Senkou_Span_A'] = ((df['Tenkan_Sen'] + df['Kijun_Sen']) / 2).shift(26)
    df['Senkou_Span_B'] = ((df['high'].rolling(window=52).max() + df['low'].rolling(window=52).min()) / 2).shift(26)
    
    df['Vol_Avg'] = df['volume'].rolling(window=20).mean()

    # --- B. LOGIC CHẤM ĐIỂM TRỌNG SỐ & QUẢN TRỊ RỦI RO ---
    trends = []
    buy_pcts = []     # THÊM MỚI
    sell_pcts = []    # THÊM MỚI
    reasons = []      # THÊM MỚI
    current_trend = -1  # Mặc định là Đỏ (Bán)
    entry_price = 0.0   # Biến lưu giá vốn để tính cắt lỗ
    
    for i in range(len(df)):
        row = df.iloc[i]
        
        # Bỏ qua giai đoạn đầu chưa đủ dữ liệu vẽ mây Ichimoku và MA200
        if pd.isna(row['SMA200']) or pd.isna(row['Senkou_Span_B']):
            trends.append(-1)
            buy_pcts.append(0)
            sell_pcts.append(0)
            reasons.append("Chưa đủ dữ liệu")
            continue
            
        buy_score = 0.0
        sell_score = 0.0
        max_score = 10.0 # Tổng điểm tuyệt đối
        reason_list = [] # Lưu lý do của phiên hiện tại
        
        # 1. NHÓM CỐT LÕI (Trọng số cao: 2.0 điểm)
        if row['close'] > row['SMA200']: 
            buy_score += 2.0; reason_list.append("Giá > MA200")
        else: 
            sell_score += 2.0; reason_list.append("Giá < MA200")
            
        if row['volume'] > 1.5 * row['Vol_Avg']: 
            buy_score += 2.0; reason_list.append("Vol đột biến")
        
        # 2. NHÓM XÁC NHẬN (Trọng số trung bình: 1.5 điểm)
        if row['close'] > row['SMA20'] and row['SMA20'] > row['SMA50']: 
            buy_score += 1.5; reason_list.append("Đà tăng ngắn hạn")
        if row['close'] < row['SMA20']: 
            sell_score += 1.5; reason_list.append("Gãy MA20")
            
        cloud_top = max(row['Senkou_Span_A'], row['Senkou_Span_B'])
        cloud_bottom = min(row['Senkou_Span_A'], row['Senkou_Span_B'])
        if row['close'] > cloud_top and row['Tenkan_Sen'] > row['Kijun_Sen']: 
            buy_score += 1.5; reason_list.append("Vượt mây Ichi")
        if row['close'] < cloud_bottom or row['Tenkan_Sen'] < row['Kijun_Sen']: 
            sell_score += 1.5; reason_list.append("Thủng mây/Cắt xuống Ichi")
        
        # 3. NHÓM BỔ TRỢ & TÌM ĐIỂM VÀO (Trọng số thấp: 1.0 điểm)
        if row['RSI'] < 30: buy_score += 1.0; reason_list.append("RSI Quá bán")
        if row['RSI'] > 70: sell_score += 1.0; reason_list.append("RSI Quá mua")
        if row['MACD'] > row['Signal_Line']: buy_score += 1.0; reason_list.append("MACD Cắt lên")
        if row['MACD'] < row['Signal_Line']: sell_score += 1.0; reason_list.append("MACD Cắt xuống")
        if row['close'] < row['BB_lower']: buy_score += 1.0; reason_list.append("Chạm BB dưới")
        if row['close'] > row['BB_upper']: sell_score += 1.0; reason_list.append("Chạm BB trên")
        
        # --- QUY ĐỔI RA PHẦN TRĂM VÀ LƯU LẠI ---
        buy_pct = (buy_score / max_score) * 100
        sell_pct = (sell_score / max_score) * 100
        
        buy_pcts.append(buy_pct)
        sell_pcts.append(sell_pct)
        reasons.append(", ".join(reason_list) if reason_list else "Trung lập")
        
        # --- BƯỚC 1: XỬ LÝ CẮT LỖ CỨNG (QUẢN TRỊ RỦI RO 2%) ---
        if current_trend == 1 and entry_price > 0:
            loss_pct = ((row['close'] / entry_price) - 1) * 100
            if loss_pct <= -2.0:
                current_trend = -1     # Kích hoạt BÁN ngay lập tức
                entry_price = 0.0      # Xóa vị thế
                trends.append(current_trend)
                continue # Bỏ qua bước kiểm tra kỹ thuật bên dưới, sang phiên tiếp theo
                
        # --- BƯỚC 2: XỬ LÝ TÍN HIỆU KỸ THUẬT ---
        if buy_pct >= 60:
            if current_trend != 1:     # Nếu phiên trước đang Đỏ, phiên này chuyển Xanh
                entry_price = row['close'] # Ghi nhận giá lúc báo Mua
            current_trend = 1
        elif sell_pct >= 30:
            current_trend = -1
            entry_price = 0.0          # Bán chốt lời/cắt lỗ xong thì xóa vị thế
            
        trends.append(current_trend)
        
    df['Trend'] = trends
    df['Buy_Pct'] = buy_pcts
    df['Sell_Pct'] = sell_pcts
    df['Reason'] = reasons
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

        # Tính toán các mức giá (Bạn có thể tự chỉnh sửa công thức % này theo ý muốn)
        stop_loss = entry_price * 0.98 if is_green else entry_price * 1.02 
        target_1 = entry_price * 1.1
        target_2 = entry_price * 1.3
        target_3 = entry_price * 1.44
        
        action_text = "MUA" if is_green else "BÁN"
        color_action = "blue" if is_green else "red"
        color_profit = "blue" if profit >= 0 else "red"
        status_text = "Đã Lãi" if profit >= 0 else "Đang Lỗ"
        rec_text = "Vùng Xanh, Tiếp tục nắm giữ" if is_green else "Vùng Đỏ, Đứng ngoài quan sát"
        rec_color = "green" if is_green else "red"

        # Hiển thị layout giống hình mẫu
        st.markdown(f"""
        <div style='text-align: center; font-family: Arial, sans-serif; line-height: 1.4;'>
            <h3 style='color: {color_action}; display: inline-block; margin-right: 20px;'>{action_text} QUANH GIÁ: {entry_price:.1f}</h3>
            <h3 style='color: purple; display: inline-block;'>Ngày {action_text}: {entry_date.strftime('%d/%m/%Y')}</h3>
            <br>
            <h3 style='color: {color_profit}; margin-top: 0;'>(KẾT QUẢ: {status_text} {profit:.1f}% | Đã nắm giữ +{days_held} phiên)</h3>
            <h4 style='color: red; display: inline-block; margin-right: 15px;'>Giá Chốt Lãi/Cắt Lỗ: {stop_loss:.1f}</h4>
            <h4 style='color: magenta; display: inline-block;'>Mục tiêu dự kiến: {target_1:.1f} | {target_2:.1f} | {target_3:.1f}</h4>
            <h2 style='color: purple; margin-top: 5px;'>GIÁ HIỆN TẠI: {last_price:.2f}</h2>
            <h3 style='color: {rec_color}; margin-top: -10px;'>Khuyến nghị: {rec_text}</h3>
        </div>
        """, unsafe_allow_html=True)
        
        # Bổ sung hiển thị Đồng thuận & Lý do
        st.info(f"📊 **Đồng thuận hệ thống:** MUA ({last_row['Buy_Pct']:.0f}%) - BÁN ({last_row['Sell_Pct']:.0f}%)\n\n📌 **Lý do tín hiệu:** {last_row['Reason']}")

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
    if st.button("Bắt đầu phân tích"):
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
                    "Lời/Lỗ (%)": profit,
                    "% Đồng Thuận Mua": last_s['Buy_Pct'],
                    "% Đồng Thuận Bán": last_s['Sell_Pct'],
                    "Lý do": last_s['Reason']
                })
            
            bar.progress(min((i + 1) / len(TOP_MARKET), 1.0))
            time.sleep(1.4) # Tránh bị API block
        df_res = pd.DataFrame(results)
        if not df_res.empty:
            # Ép kiểu số để tính toán và định dạng chính xác
            cols_to_fix = ["Giá Tín Hiệu", "Giá Hiện Tại", "Lời/Lỗ (%)"]
            for col in cols_to_fix:
                if col in df_res.columns:
                    df_res[col] = pd.to_numeric(df_res[col], errors='coerce')
            # --- PHẦN QUAN TRỌNG: TẠO CỘT STT ---
            # Sắp xếp lại index và tạo cột STT bắt đầu từ 1
            df_res = df_res.reset_index(drop=True)
            df_res.insert(0, "STT", range(1, len(df_res) + 1))
            # 2. Hiển thị bảng
            st.dataframe(
                df_res,
                column_config={
                    "STT": st.column_config.NumberColumn("STT", width="small"),
                    "Giá Tín Hiệu": st.column_config.NumberColumn("Giá Tín Hiệu", format="%.2f"),
                    "Giá Hiện Tại": st.column_config.NumberColumn("Giá Hiện Tại", format="%.2f"),
                    "Lời/Lỗ (%)": st.column_config.NumberColumn("Lời/Lỗ (%)", format="%.2f%%"),
                    "% Đồng Thuận Mua": st.column_config.ProgressColumn("% MUA", format="%f%%", min_value=0, max_value=100),
                    "% Đồng Thuận Bán": st.column_config.ProgressColumn("% BÁN", format="%f%%", min_value=0, max_value=100),
                },
                use_container_width=True,
                height=600,
                hide_index=True # Ẩn cột chỉ số mặc định của Pandas để dùng cột STT mình tự tạo
            )
        else:
            st.warning("Không có dữ liệu nào được tìm thấy.")
