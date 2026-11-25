import streamlit as st
import pandas as pd
from vnstock import Market, sources
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import time
from backtesting import tao_bang_giao_dich
from performance_metrics import profit_factor_money

# --- 1. CẤU HÌNH HỆ THỐNG ---
st.set_page_config(page_title="Stock Bot | Trading Intelligence", layout="wide", initial_sidebar_state="collapsed")
TF_MAP = {"1 Giờ": "1H", "Ngày": "1D", "Tuần": "1W"}
# --- XAC THUC TCBS ---
# --- 2. HÀM LẤY TOP 100 THANH KHOẢN ---
@st.cache_data(ttl=3600)
def get_top_100_liquidity():
        return [
            'SSI', 'VIX', 'VND', 'SHS', 'HPG', 'DIG', 'NVL', 'PDR', 'STB', 'MBB',
            'TCB', 'VPB', 'SHB', 'ACB', 'DXG', 'VCI', 'HCM', 'CEO', 'HAG', 'HSG',
            'NKG', 'GVR', 'FPT', 'MWG', 'MSN', 'VIC', 'VHM', 'VCB', 'BID', 'CTG',
            'LPB', 'HDB', 'TPB', 'MSB', 'OCB', 'EIB', 'VIB', 'DGC', 'DPM', 'DCM',
            'PVD', 'PVS', 'PVT', 'BSR', 'GAS', 'PLX', 'POW', 'VRE', 'GMD', 'HAH',
            'VJC', 'VPX', 'REE', 'MCH', 'VCG', 'HHV', 'LCG', 'VCK', 'FCN', 'CII',
            'KBC', 'SZC', 'IDC', 'GEX', 'VNM', 'FRT', 'FTS', 'NLG', 'DGW', 'BAF',
            'VPI', 'CTD', 'SAB', 'PNJ', 'DBC', 'PAN', 'ANV', 'VGC', 'VHC', 'GEG',
            'NT2', 'HDC', 'TV2', 'CSV', 'BFC', 'LAS', 'PHR', 'DPR', 'TCH', 'MSH',
            'TCM', 'CTS', 'GEE', 'KDH', 'BSI', 'HUT', 'TNG', 'VGS', 'MBS', 'AGR', 'BVH', 'SSB', 'PC1'
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
    # Tính toán thân nến và bóng nến
    df['body'] = abs(df['close'] - df['open'])
    df['lower_shadow'] = df[['open', 'close']].min(axis=1) - df['low']
    df['upper_shadow'] = df['high'] - df[['open', 'close']].max(axis=1)
    # Định nghĩa nến rút chân tăng (Bullish Pin Bar): Bóng dưới dài gấp ít nhất 2 lần thân nến
    df['is_bullish_pinbar'] = (df['lower_shadow'] > 2 * df['body']) & (df['lower_shadow'] > df['upper_shadow'])
    # RSI (14) - Phuong phap Wilder
    delta = df['close'].diff()
    gains = delta.clip(lower=0).to_numpy(dtype=float)
    losses = (-delta.clip(upper=0)).to_numpy(dtype=float)

    avg_gains = np.full(len(df), np.nan)
    avg_losses = np.full(len(df), np.nan)

    avg_gains[14] = gains[1:15].mean()
    avg_losses[14] = losses[1:15].mean()

    for i in range(15, len(df)):
        avg_gains[i] = (avg_gains[i - 1] * 13 + gains[i]) / 14
        avg_losses[i] = (avg_losses[i - 1] * 13 + losses[i]) / 14

    total = avg_gains + avg_losses
    rsi = np.full(len(df), np.nan)

    valid = total > 0
    rsi[valid] = 100 * avg_gains[valid] / total[valid]
    rsi[total == 0] = 50

    df['RSI'] = rsi
    df['Price_Min_10'] = df['low'].rolling(window=10).min()
    df['Price_Max_10'] = df['high'].rolling(window=10).max()
    df['RSI_Min_10'] = df['RSI'].rolling(window=10).min()
    df['RSI_Max_10'] = df['RSI'].rolling(window=10).max()
    # Lưu giá trị đỉnh/đáy của giai đoạn trước đó (phiên 11 đến 20)
    df['Prev_Price_Min'] = df['Price_Min_10'].shift(10)
    df['Prev_Price_Max'] = df['Price_Max_10'].shift(10)
    df['Prev_RSI_Min'] = df['RSI_Min_10'].shift(10)
    df['Prev_RSI_Max'] = df['RSI_Max_10'].shift(10)
    
    exp1 = df['close'].ewm(span=12, adjust=False).mean()
    exp2 = df['close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp1 - exp2
    df['Signal_Line'] = df['MACD'].ewm(span=9, adjust=False).mean()
    
    df['BB_mid'] = df['SMA20']
    df['BB_std'] = df['close'].rolling(window=20).std()
    df['BB_upper'] = df['BB_mid'] + 2 * df['BB_std']
    df['BB_lower'] = df['BB_mid'] - 2 * df['BB_std']
           
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    money_flow = typical_price * df['volume']
    positive_flow = money_flow.where(typical_price > typical_price.shift(1), 0).rolling(window=14).sum()
    negative_flow = money_flow.where(typical_price < typical_price.shift(1), 0).rolling(window=14).sum()
    df['MFI'] = 100 - (100 / (1 + positive_flow / (negative_flow + 1e-9)))
            
    df['Tenkan_Sen'] = (df['high'].rolling(window=9).max() + df['low'].rolling(window=9).min()) / 2
    df['Kijun_Sen'] = (df['high'].rolling(window=26).max() + df['low'].rolling(window=26).min()) / 2
    df['Senkou_Span_A'] = ((df['Tenkan_Sen'] + df['Kijun_Sen']) / 2).shift(26)
    df['Senkou_Span_B'] = ((df['high'].rolling(window=52).max() + df['low'].rolling(window=52).min()) / 2).shift(26)
    
    df['Vol_Avg'] = df['volume'].rolling(window=20).mean()
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift(1))
    low_close = np.abs(df['low'] - df['close'].shift(1))
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    # ATR (14) - Phuong phap Wilder
    tr_values = true_range.to_numpy(dtype=float)
    atr_values = np.full(len(tr_values), np.nan)

    atr_values[13] = tr_values[:14].mean()

    for i in range(14, len(tr_values)):
        atr_values[i] = (
            atr_values[i - 1] * 13 + tr_values[i]
        ) / 14

    df['ATR'] = atr_values

    
    # ADX (14), Plus_DI, Minus_DI - Wilder
    up_move = df['high'].diff().to_numpy(dtype=float)
    down_move = (-df['low'].diff()).to_numpy(dtype=float)

    plus_dm = np.where(
        (up_move > down_move) & (up_move > 0),
        up_move, 0.0
    )
    minus_dm = np.where(
        (down_move > up_move) & (down_move > 0),
        down_move, 0.0
    )

    n = len(df)
    tr_smooth = np.full(n, np.nan)
    plus_smooth = np.full(n, np.nan)
    minus_smooth = np.full(n, np.nan)

    tr_smooth[14] = tr_values[1:15].sum()
    plus_smooth[14] = plus_dm[1:15].sum()
    minus_smooth[14] = minus_dm[1:15].sum()

    for i in range(15, n):
        tr_smooth[i] = (
            tr_smooth[i-1] * 13 / 14 + tr_values[i]
        )
        plus_smooth[i] = (
            plus_smooth[i-1] * 13 / 14 + plus_dm[i]
        )
        minus_smooth[i] = (
            minus_smooth[i-1] * 13 / 14 + minus_dm[i]
        )

    plus_di = np.full(n, np.nan)
    minus_di = np.full(n, np.nan)
    dx = np.full(n, np.nan)

    for i in range(14, n):
        if tr_smooth[i] > 0:
            plus_di[i] = 100 * plus_smooth[i] / tr_smooth[i]
            minus_di[i] = 100 * minus_smooth[i] / tr_smooth[i]
        else:
            plus_di[i] = 0.0
            minus_di[i] = 0.0

        di_sum = plus_di[i] + minus_di[i]
        dx[i] = (
            100 * abs(plus_di[i] - minus_di[i]) / di_sum
            if di_sum > 0 else 0.0
        )

    adx = np.full(n, np.nan)
    adx[27] = np.mean(dx[14:28])

    for i in range(28, n):
        adx[i] = (adx[i-1] * 13 + dx[i]) / 14

    df['ADX'] = adx
    df['Plus_DI'] = plus_di
    df['Minus_DI'] = minus_di

        
    # --- B. LOGIC CHẤM ĐIỂM TRỌNG SỐ & QUẢN TRỊ RỦI RO ---
    trends = []
    buy_pcts = []     # THÊM MỚI
    sell_pcts = []    # THÊM MỚI
    reasons = []      # THÊM MỚI
    current_trend = -1
    entry_price = 0.0
    trailing_stop = 0.0
    entry_bar = 0        # KT1: thay thế days_in_trade sai
    pending_buy = 0      # KT3: đếm số phiên xác nhận tín hiệu mua
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
        max_score = 14.5 # Tổng điểm tuyệt đối
        reason_list = [] # Lưu lý do của phiên hiện tại
        
        # 1. NHÓM CỐT LÕI 
        if row['close'] > row['SMA200']: 
            buy_score += 2.0; reason_list.append("Giá > MA200")
        else: 
            sell_score += 2.0; reason_list.append("Giá < MA200")
        if row['volume'] > 1.5 * row['Vol_Avg']: 
            if row['close'] > row['open']: 
                buy_score += 1.5; reason_list.append("Cầu mạnh (Vol đột biến)")
            elif row['close'] < row['open']:
                sell_score += 1.5; reason_list.append("Bán tháo (Vol đột biến)")
            else:
                pass
                
        if row['MFI'] > 50: 
            buy_score += 2.0; reason_list.append("Dòng tiền dương")
        if row['MFI'] < 40: 
            sell_score += 2.0; reason_list.append("Dòng tiền yếu")

        # Nếu ADX > 25: Xu hướng mạnh, tin tưởng vào các chỉ báo hướng
        if row['ADX'] > 25:
            if row['Plus_DI'] > row['Minus_DI']:
                buy_score += 1.5; reason_list.append("Trend tăng mạnh (ADX)")
            elif row['Minus_DI'] > row['Plus_DI']:
                sell_score += 1.5; reason_list.append("Trend giảm mạnh (ADX)")
        # Nếu ADX < 20: Thị trường đi ngang, trừ điểm để cảnh báo rủi ro tín hiệu giả
        elif row['ADX'] < 20:
            reason_list.append("Sideways (ADX thấp)")
        # Giá tạo đáy thấp hơn nhưng RSI tạo đáy cao hơn
        if row['Price_Min_10'] < row['Prev_Price_Min'] and row['RSI_Min_10'] > row['Prev_RSI_Min']:
            if row['RSI'] < 45: # Chỉ xét khi RSI ở vùng thấp
                buy_score += 2.0
                reason_list.append("Phân kỳ Dương RSI (Đảo chiều tăng)")
        # Giá tạo đỉnh cao hơn nhưng RSI tạo đỉnh thấp hơn
        if row['Price_Max_10'] > row['Prev_Price_Max'] and row['RSI_Max_10'] < row['Prev_RSI_Max']:
            if row['RSI'] > 55: # Chỉ xét khi RSI ở vùng cao
                sell_score += 2.0
                reason_list.append("Phân kỳ Âm RSI (Đảo chiều giảm)")
        # 2. NHÓM XÁC NHẬN 
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
        
        # 3. NHÓM BỔ TRỢ & TÌM ĐIỂM VÀO 
        if row['RSI'] < 30: buy_score += 1.0; reason_list.append("RSI Quá bán")
        if row['RSI'] > 70: sell_score += 1.0; reason_list.append("RSI Quá mua")
        if row['MACD'] > row['Signal_Line']: buy_score += 1.0; reason_list.append("MACD Cắt lên")
        if row['MACD'] < row['Signal_Line']: sell_score += 1.0; reason_list.append("MACD Cắt xuống")
        if row['close'] < row['BB_lower']: buy_score += 0.5; reason_list.append("Chạm BB dưới")
        if row['close'] > row['BB_upper']: sell_score += 0.5; reason_list.append("Chạm BB trên")

        # --- QUY ĐỔI RA PHẦN TRĂM VÀ LƯU LẠI ---
        buy_pct = (buy_score / max_score) * 100
        sell_pct = (sell_score / max_score) * 100
        
        buy_pcts.append(buy_pct)
        sell_pcts.append(sell_pct)
        reasons.append(", ".join(reason_list) if reason_list else "Trung lập")

        # === KỸ THUẬT 2: Ngưỡng thích ứng theo ADX ===
        adx = row['ADX'] if not pd.isna(row['ADX']) else 0
        if adx >= 27:       # xu hướng mạnh → nhạy hơn
            buy_threshold  = 55
            sell_threshold = 35
        elif adx >= 21:     # xu hướng trung bình
            buy_threshold  = 60
            sell_threshold = 40
        else:               # đi ngang → lọc chặt
            buy_threshold  = 65
            sell_threshold = 45
        # === BƯỚC 1: TRAILING STOP (giữ nguyên logic cũ, chỉ sửa days_in_trade) ===
        days_in_trade = i - entry_bar   # KT1: fix O(n²), luôn chính xác
        if current_trend == 1 and entry_price > 0:
            current_stop = row['close'] - (2 * row['ATR'])
            trailing_stop = max(trailing_stop, current_stop)
            if row['close'] <= trailing_stop and days_in_trade >= 3:
                current_trend = -1
                entry_price = 0.0
                trailing_stop = 0.0
                pending_buy = 0         # reset khi bị cắt lỗ
                reasons[-1] = "Thoát do Trailing Stop (ATR). " + reasons[-1]
                trends.append(current_trend)
                continue
        # === BƯỚC 2: TÍN HIỆU KỸ THUẬT — KT1 + KT3 (Hysteresis + Confirmation) ===
        if current_trend != 1:
            # --- Đang đứng ngoài: cần xác nhận 2 phiên liên tiếp ---
            if buy_pct >= buy_threshold:
                pending_buy += 1
                confirm_required = 1 if adx >= 30 else 2   # ADX mạnh → vào ngay phiên đó
                if pending_buy >= confirm_required:
                        current_trend = 1
                        entry_bar = i
                        entry_price = row['close']
                        trailing_stop = row['close'] - (2 * row['ATR'])
                        pending_buy = 0
            else:
                pending_buy = 0                     # gián đoạn → reset đếm
        else:
            # --- KT1 Hysteresis: đang giữ lệnh → ngưỡng bán cao hơn, kiên nhẫn hơn ---
            pending_buy = 0
            thoat_lenh = False
            if sell_pct >= sell_threshold:          # bán bình thường
                thoat_lenh = True
            elif sell_pct >= 35 and adx > 30 and row['Minus_DI'] > row['Plus_DI']:
                thoat_lenh = True                   # thị trường đảo chiều mạnh → thoát nhanh
            if thoat_lenh:
                current_trend = -1
                entry_price = 0.0
                trailing_stop = 0.0
        trends.append(current_trend)        
    df['Trend'] = trends
    df['Buy_Pct'] = buy_pcts
    df['Sell_Pct'] = sell_pcts
    df['Reason'] = reasons
    return df

# --- 4. HÀM LẤY DỮ LIỆU ---
@st.cache_data(ttl=600)
def get_data(symbol, tf):
    for src in ['tcbs']:
        try:
            stock = Market(src).equity(symbol)
            df = stock.ohlcv(start='2022-01-01', end=datetime.now().strftime('%Y-%m-%d'), interval=TF_MAP[tf])
            if df is not None and not df.empty:
                df['time'] = pd.to_datetime(df['time'])
                df.set_index('time', inplace=True)
                return calculate_indicators(df)
        except Exception as e:
            st.warning(f"Nguồn {src} gặp lỗi: {type(e).__name__}")
            continue
    return pd.DataFrame()


# --- 5. GIAO DIỆN CHÍNH ---
from terminal_ui import shell, render_trading, render_scanner, render_research, render_system

page = shell()
if page == "Giao dịch":
    render_trading(get_data)
elif page == "Quét tín hiệu":
    render_scanner(get_data, TOP_MARKET)
elif page == "Nghiên cứu":
    render_research(get_data)
else:
    render_system(get_data, sources)
