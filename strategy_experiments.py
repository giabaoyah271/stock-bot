
import pandas as pd


def danh_gia_bo_loc_xu_huong(df, trades):
    """
    Kiem tra dieu kien xu huong tai ngay tin hieu mua.
    Khong thay doi chien luoc goc.
    Khong su dung du lieu tuong lai.
    """

    required = {"close", "SMA50", "SMA200"}
    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            f"Thieu cot du lieu: {', '.join(sorted(missing))}"
        )

    if "Ngày tín hiệu mua" not in trades.columns:
        raise ValueError("Thieu cot Ngày tín hiệu mua.")

    if df.index.has_duplicates:
        raise ValueError("Thoi gian du lieu bi trung.")

    result = trades.copy()

    if result.empty:
        result["Đạt bộ lọc xu hướng"] = pd.Series(dtype=bool)
        return result

    dates = pd.to_datetime(
        result["Ngày tín hiệu mua"],
        errors="coerce"
    )

    if dates.isna().any():
        raise ValueError("Ngay tin hieu mua khong hop le.")

    # Chi lay du lieu tai ngay phat tin hieu
    signal_data = df[
        ["close", "SMA50", "SMA200"]
    ].reindex(pd.DatetimeIndex(dates))

    eligible = (
        (signal_data["close"] > signal_data["SMA200"])
        & (signal_data["SMA50"] > signal_data["SMA200"])
        & signal_data.notna().all(axis=1)
    )

    result["Đạt bộ lọc xu hướng"] = (
        eligible.to_numpy(dtype=bool)
    )

    return result



def chay_backtest_thu_nghiem(df, bo_loc="sma"):
    """
    Chay lai tin hieu mua/ban voi bo loc rieng.
    Giu nguyen backtesting.py va chien luoc goc.
    """
    from backtesting import tao_bang_giao_dich

    modes = {"goc", "sma", "adx_macd", "macd"}
    if bo_loc not in modes:
        raise ValueError("Bo loc khong hop le.")

    required = {
        "open", "close", "SMA200", "Senkou_Span_B",
        "ATR", "ADX", "Buy_Pct", "Sell_Pct",
        "Plus_DI", "Minus_DI"
    }

    if bo_loc == "sma":
        required.add("SMA50")
    elif bo_loc in {"adx_macd", "macd"}:
        required.update({"MACD", "Signal_Line"})

    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            "Thieu cot: " + ", ".join(sorted(missing))
        )

    if not df.index.is_monotonic_increasing or df.index.has_duplicates:
        raise ValueError("Thoi gian du lieu khong hop le.")

    trial = df.copy()
    if "Reason" not in trial.columns:
        trial["Reason"] = ""

    trend = -1
    entry_bar = 0
    trailing_stop = 0.0
    pending_buy = 0
    trial_trends = []

    for i in range(len(trial)):
        row = trial.iloc[i]

        if pd.isna(row["SMA200"]) or pd.isna(row["Senkou_Span_B"]):
            trial_trends.append(-1)
            continue

        adx = float(row["ADX"]) if pd.notna(row["ADX"]) else 0.0

        if adx >= 27:
            buy_threshold, sell_threshold = 55, 35
        elif adx >= 21:
            buy_threshold, sell_threshold = 60, 40
        else:
            buy_threshold, sell_threshold = 65, 45

        # Quan ly vi the dang nam giu
        if trend == 1:
            current_stop = (
                float(row["close"]) - 2 * float(row["ATR"])
            )
            trailing_stop = max(trailing_stop, current_stop)

            if (
                row["close"] <= trailing_stop
                and i - entry_bar >= 3
            ):
                trend = -1
                trailing_stop = 0.0
                pending_buy = 0
                trial.at[trial.index[i], "Reason"] = (
                    "Thu nghiem: thoat do Trailing Stop (ATR)"
                )
                trial_trends.append(trend)
                continue

        # Kiem tra dieu kien mua
        if trend != 1:
            if bo_loc == "sma":
                eligible = (
                    pd.notna(row["SMA50"])
                    and row["close"] > row["SMA200"]
                    and row["SMA50"] > row["SMA200"]
                )

            elif bo_loc == "adx_macd":
                eligible = (
                    adx >= 25
                    and row["Plus_DI"] > row["Minus_DI"]
                    and row["MACD"] > row["Signal_Line"]
                )

            elif bo_loc == "macd":
                eligible = (
                    pd.notna(row["MACD"])
                    and pd.notna(row["Signal_Line"])
                    and row["MACD"] > row["Signal_Line"]
                )

            else:
                eligible = True

            if row["Buy_Pct"] >= buy_threshold and eligible:
                pending_buy += 1
                confirm_required = 1 if adx >= 30 else 2

                if pending_buy >= confirm_required:
                    trend = 1
                    entry_bar = i
                    trailing_stop = (
                        float(row["close"])
                        - 2 * float(row["ATR"])
                    )
                    pending_buy = 0
            else:
                pending_buy = 0

        # Kiem tra dieu kien ban
        else:
            pending_buy = 0
            exit_signal = (
                row["Sell_Pct"] >= sell_threshold
                or (
                    row["Sell_Pct"] >= 35
                    and adx > 30
                    and row["Minus_DI"] > row["Plus_DI"]
                )
            )

            if exit_signal:
                trend = -1
                trailing_stop = 0.0
                trial.at[trial.index[i], "Reason"] = (
                    "Thu nghiem: thoat theo diem ban"
                )

        trial_trends.append(trend)

    trial["Trend"] = trial_trends

    return tao_bang_giao_dich(trial)

def chay_backtest_diem_v2(df):
    """
    Backtesting V2, giu nguyen V1 va backtesting.py.
    """
    from scoring_v2 import tinh_diem_v2

    trial = tinh_diem_v2(df).copy()

    # Su dung diem V2 thay cho diem V1 trong ban sao
    trial["Buy_Pct"] = trial["V2_Buy_Pct"].fillna(0)
    trial["Sell_Pct"] = trial["V2_Sell_Pct"].fillna(0)

    # Chay lai quy tac vao/thoat lenh hien tai
    return chay_backtest_thu_nghiem(
        trial, bo_loc="goc"
    )
    
