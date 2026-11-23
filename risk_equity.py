"""Experimental daily mark-to-market equity for Stock Bot.

The independent signal replay MUST match the existing closed-trade backtest
before the daily equity curve is displayed. No trading code is modified.
"""
from __future__ import annotations

import math
import pandas as pd

from backtesting import tao_bang_giao_dich
from strategy_experiments import chay_backtest_thu_nghiem, chay_backtest_diem_v2
from v21_macd_strategy import chay_backtest_diem_v21_macd
from scoring_v2 import tinh_diem_v2

STRATEGIES = (
    "Chiến lược gốc", "Lọc SMA50/SMA200", "Lọc ADX + DI + MACD",
    "Chấm điểm V2", "V2.1 - Xác nhận MACD",
)
BUY_FEE = 0.0015
SELL_FEE = 0.0015
SELL_TAX = 0.001
SLIPPAGE = 0.001


def _test_trend(df, kind):
    """Replay signal state for parity checks; does not drive live signals."""
    trend, entry_bar, trailing, pending = -1, 0, 0.0, 0
    states = []
    for i in range(len(df)):
        row = df.iloc[i]
        if pd.isna(row["SMA200"]) or pd.isna(row["Senkou_Span_B"]):
            states.append(-1)
            continue
        adx = float(row["ADX"]) if pd.notna(row["ADX"]) else 0.0
        if adx >= 27:
            buy_limit, sell_limit = 55, 35
        elif adx >= 21:
            buy_limit, sell_limit = 60, 40
        else:
            buy_limit, sell_limit = 65, 45

        if trend == 1:
            trailing = max(trailing, float(row["close"]) - 2 * float(row["ATR"]))
            if row["close"] <= trailing and i - entry_bar >= 3:
                trend, trailing, pending = -1, 0.0, 0
                states.append(trend)
                continue

        if trend != 1:
            if kind == "sma":
                eligible = bool(pd.notna(row["SMA50"]) and
                                row["close"] > row["SMA200"] and
                                row["SMA50"] > row["SMA200"])
            elif kind == "adx_macd":
                eligible = bool(adx >= 25 and
                                row["Plus_DI"] > row["Minus_DI"] and
                                row["MACD"] > row["Signal_Line"])
            else:
                eligible = True
            if row["Buy_Pct"] >= buy_limit and eligible:
                pending += 1
                required = 1 if adx >= 30 else 2
                if pending >= required:
                    trend = 1
                    entry_bar = i
                    trailing = float(row["close"]) - 2 * float(row["ATR"])
                    pending = 0
            else:
                pending = 0
        else:
            pending = 0
            exit_signal = bool(
                row["Sell_Pct"] >= sell_limit
                or (row["Sell_Pct"] >= 35 and adx > 30
                    and row["Minus_DI"] > row["Plus_DI"])
            )
            if exit_signal:
                trend, trailing = -1, 0.0
        states.append(trend)
    return pd.Series(states, index=df.index, name="Trend")


def _signals_and_original_ledger(df, strategy):
    """Compare independently reconstructed states with original trade records."""
    if strategy not in STRATEGIES:
        raise ValueError("Chiến lược không được hỗ trợ")
    trial = df.copy()
    if strategy == "Chiến lược gốc":
        expected = tao_bang_giao_dich(trial)
        trend = trial["Trend"].copy()
    else:
        if strategy == "Lọc SMA50/SMA200":
            expected = chay_backtest_thu_nghiem(trial.copy(), "sma")
            kind = "sma"
        elif strategy == "Lọc ADX + DI + MACD":
            expected = chay_backtest_thu_nghiem(trial.copy(), "adx_macd")
            kind = "adx_macd"
        elif strategy == "Chấm điểm V2":
            expected = chay_backtest_diem_v2(trial.copy())
            trial = tinh_diem_v2(trial)
            trial["Buy_Pct"] = trial["V2_Buy_Pct"].fillna(0)
            trial["Sell_Pct"] = trial["V2_Sell_Pct"].fillna(0)
            kind = "goc"
        else:
            expected = chay_backtest_diem_v21_macd(trial.copy())
            trial = tinh_diem_v2(trial)
            valid = (trial["MACD"].notna() & trial["Signal_Line"].notna()
                     & (trial["MACD"] > trial["Signal_Line"]))
            trial["Buy_Pct"] = trial["V2_Buy_Pct"].where(valid, 0).fillna(0)
            trial["Sell_Pct"] = trial["V2_Sell_Pct"].fillna(0)
            kind = "goc"
        trend = _test_trend(trial, kind)
    trial["Trend"] = trend
    simulated = tao_bang_giao_dich(trial)
    if len(simulated) != len(expected):
        raise ValueError("Đối chiếu tín hiệu thất bại: khác số lượng lệnh")
    verify_cols = [
        "Ngày tín hiệu mua", "Ngày mua mô phỏng",
        "Ngày tín hiệu bán", "Ngày bán mô phỏng",
        "Giá mua mô phỏng", "Giá bán mô phỏng",
        "Lợi nhuận sau chi phí (%)",
    ]
    if not simulated[verify_cols].reset_index(drop=True).equals(
            expected[verify_cols].reset_index(drop=True)):
        raise ValueError("Đối chiếu tín hiệu thất bại: khác ngày, giá hoặc lợi nhuận")
    return trend, expected


def _underwater_duration(drawdown):
    """Sessions below a previous equity peak: completed and ongoing spells."""
    ongoing, longest_completed = 0, 0
    for value in drawdown:
        if value < -1e-8:
            ongoing += 1
        else:
            if ongoing:
                longest_completed = max(longest_completed, ongoing)
            ongoing = 0
    return longest_completed, ongoing


def calculate_equity_risk(df, strategy, initial_capital=100.0):
    """Return (daily frame, risk metrics); never change the source DataFrame.

    Existing fees/slippage and next-session open execution are preserved.
    Holdings are valued at each session close. An open position at the last
    candle is shown without charging hypothetical sell fees.
    Assumes fractional shares, one long position, full reinvestment, no
    dividends or cash interest. This is a single-stock simulation.
    """
    required = {"open", "close", "Trend"}
    if df is None or df.empty or not required.issubset(df.columns):
        raise ValueError("Thiếu dữ liệu open, close hoặc Trend")
    if (not isinstance(df.index, pd.DatetimeIndex) or
            df.index.has_duplicates or not df.index.is_monotonic_increasing):
        raise ValueError("Ngày giao dịch phải tăng dần và không trùng")
    if len(df) < 3:
        raise ValueError("Cần ít nhất ba phiên giao dịch")
    values = df[["open", "close"]].apply(pd.to_numeric, errors="coerce")
    if values.isna().any().any() or (values <= 0).any().any():
        raise ValueError("Giá open hoặc close không hợp lệ")
    initial_capital = float(initial_capital)
    if not math.isfinite(initial_capital) or initial_capital <= 0:
        raise ValueError("Vốn ban đầu phải dương")

    trend, ledger = _signals_and_original_ledger(df, strategy)
    states = trend.to_numpy()
    opens = values["open"].to_numpy(dtype=float)
    closes = values["close"].to_numpy(dtype=float)

    cash, shares = initial_capital, 0.0
    last_buy_cost = 0.0
    event_buy_dates, event_sell_dates, equity_rows = [], [], []
    for i in range(len(df)):
        action = "Giữ tiền mặt"
        # The signal at i-1 executes at the OPEN of candle i.
        # Backtesting's signal loop begins at candle 1: i>=2.
        if i >= 2 and states[i - 2] == -1 and states[i - 1] == 1 and shares == 0:
            buy_fill = opens[i] * (1 + SLIPPAGE)
            last_buy_cost = buy_fill * (1 + BUY_FEE)
            shares = cash / last_buy_cost
            cash = 0.0
            event_buy_dates.append(df.index[i])
            action = "Mua tại mở cửa"
        elif i >= 2 and states[i - 2] == 1 and states[i - 1] == -1 and shares > 0:
            sell_fill = opens[i] * (1 - SLIPPAGE)
            cash = shares * sell_fill * (1 - SELL_FEE - SELL_TAX)
            shares = 0.0
            last_buy_cost = 0.0
            event_sell_dates.append(df.index[i])
            action = "Bán tại mở cửa"
        elif shares > 0:
            action = "Đang nắm giữ"

        equity = cash + shares * closes[i]
        if not math.isfinite(equity) or equity <= 0:
            raise ValueError("Giá trị vốn mô phỏng không hợp lệ")
        equity_rows.append((equity, cash, shares, action))

    if len(event_sell_dates) != len(ledger):
        raise ValueError("Số giao dịch đóng không khớp Backtesting gốc")
    for actual, expected in zip(event_buy_dates, ledger["Ngày mua mô phỏng"].tolist()):
        if actual != expected:
            raise ValueError("Ngày mua không khớp Backtesting gốc")
    for actual, expected in zip(event_sell_dates, ledger["Ngày bán mô phỏng"].tolist()):
        if actual != expected:
            raise ValueError("Ngày bán không khớp Backtesting gốc")
    if len(event_buy_dates) - len(event_sell_dates) != int(shares > 0):
        raise ValueError("Trạng thái vị thế không khớp")

    result = pd.DataFrame(
        equity_rows, index=df.index,
        columns=["Equity", "Tiền mặt", "Số cổ phiếu quy ước", "Trạng thái"],
    )
    highwater = result["Equity"].cummax()
    result["Drawdown (%)"] = (result["Equity"] / highwater - 1) * 100
    result["Lợi nhuận tích lũy (%)"] = (result["Equity"] / initial_capital - 1) * 100
    result["Giá đóng cửa"] = closes
    completed, ongoing = _underwater_duration(result["Drawdown (%)"].to_numpy())

    r = pd.to_numeric(ledger["Lợi nhuận sau chi phí (%)"], errors="coerce")
    closed_growth = float((1 + r / 100).prod())
    closed_curve = pd.concat(
        [pd.Series([1.0]), (1 + r.reset_index(drop=True) / 100).cumprod()],
        ignore_index=True,
    )
    closed_dd = float((closed_curve / closed_curve.cummax() - 1).min() * 100)
    last_flat_equity = initial_capital
    if event_sell_dates:
        last_flat_equity = float(result.loc[event_sell_dates[-1], "Tiền mặt"])
    # Each source return was rounded to 0.01%, so allow roundoff to compound.
    tolerance = max(0.001, len(r) * 0.00006 * initial_capital)
    if abs(last_flat_equity - initial_capital * closed_growth) > tolerance:
        raise ValueError("Đối chiếu lợi nhuận đã đóng không khớp Backtesting gốc")

    open_pnl = ((closes[-1] / last_buy_cost) - 1) * 100 if shares else None
    metrics = {
        "Chiến lược": strategy,
        "Vốn cuối theo phiên": round(float(result["Equity"].iloc[-1]), 3),
        "Lợi nhuận theo phiên (%)": round(float(result["Lợi nhuận tích lũy (%)"].iloc[-1]), 2),
        "Max Drawdown theo phiên (%)": round(float(result["Drawdown (%)"].min()), 2),
        "Drawdown theo lệnh đóng (%)": round(closed_dd, 2),
        "Phiên dưới đỉnh dài nhất (đã hồi phục)": completed,
        "Phiên dưới đỉnh hiện tại": ongoing,
        "Trạng thái cuối": "Đang nắm giữ" if shares else "Tiền mặt",
        "Lãi/lỗ vị thế mở (%; chưa trừ phí bán)": round(open_pnl, 2) if open_pnl is not None else None,
        "Số giao dịch đã đóng": len(ledger),
        "Số phiên nắm giữ TB (lệnh đã đóng)": round(
            float(sum(df.index.get_loc(s) - df.index.get_loc(b)
                      for b, s in zip(ledger["Ngày mua mô phỏng"],
                                      ledger["Ngày bán mô phỏng"])) / len(ledger)), 1,
        ) if len(ledger) else None,
        "Lệnh lỗ lớn nhất (%)": float(r.min()) if len(r) else None,
    }
    return result, metrics
