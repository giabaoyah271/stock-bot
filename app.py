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
