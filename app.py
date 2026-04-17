@st.cache_data(ttl=300)
def get_data(symbol, tf):
    try:
        # vnstock3 sử dụng cách gọi mới
        stock = Vnstock().stock(symbol=symbol, source='DNSE') 
        df = stock.quote.history(start='2024-01-01', end=datetime.now().strftime('%Y-%m-%d'), interval=TF_MAP[tf])
        
        if df is not None and not df.empty:
            # Đảm bảo cột 'time' tồn tại trước khi set_index
            if 'time' in df.columns:
                df['time'] = pd.to_datetime(df['time'])
                df.set_index('time', inplace=True)
            return df
    except Exception as e:
        print(f"Lỗi lấy mã {symbol}: {e}") # Xem lỗi trong log nếu cần
        return pd.DataFrame()
    return pd.DataFrame()
