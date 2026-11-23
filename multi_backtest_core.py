"""Read-only multi-symbol backtest reporting using Stock Bot's existing strategies.

Period views include only trades with both execution dates inside the window.
All signals and indicators retain their preceding historical context; this is
historical period analysis, NOT a pristine out-of-sample evaluation.
"""

import re
from datetime import date
import pandas as pd
from performance_metrics import profit_factor_money

DEFAULT_SYMBOLS = "HPG, MBB, FPT, TCB, MWG, VNM"
MAX_SYMBOLS = 12
STRATEGY_NAMES = (
    "Chiến lược gốc",
    "Lọc SMA50/SMA200",
    "Lọc ADX + DI + MACD",
    "Chấm điểm V2",
    "V2.1 - Xác nhận MACD",
)
RETURN = "Lợi nhuận sau chi phí (%)"
BUY_DATE = "Ngày mua mô phỏng"
SELL_DATE = "Ngày bán mô phỏng"


def parse_symbols(text):
    """Deduplicate and validate short Vietnamese equity tickers."""
    symbols = list(dict.fromkeys(re.split(r"[,;\s]+", str(text).upper().strip())))
    symbols = [s for s in symbols if s]
    if not symbols:
        raise ValueError("Hãy nhập ít nhất một mã cổ phiếu.")
    if len(symbols) > MAX_SYMBOLS:
        raise ValueError(f"Mỗi lần chạy tối đa {MAX_SYMBOLS} mã để hạn chế tải TCBS.")
    if any(not re.fullmatch(r"[A-Z][A-Z0-9]{1,5}", s) for s in symbols):
        raise ValueError("Mã không hợp lệ; dùng chữ A-Z và số, cách nhau bởi dấu phẩy.")
    return symbols


def period_dates(choice, custom_start=None, custom_end=None):
    """Return (label, inclusive start date, inclusive end date)."""
    if choice == "Toàn bộ dữ liệu":
        return choice, None, None
    if choice == "2022–2024 (lịch sử)":
        return choice, date(2022, 1, 1), date(2024, 12, 31)
    if choice == "2025–2026 (lịch sử)":
        return choice, date(2025, 1, 1), date(2026, 12, 31)
    if choice == "Tùy chỉnh":
        if custom_start is None or custom_end is None or custom_start > custom_end:
            raise ValueError("Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.")
        return f"{custom_start:%d/%m/%Y}–{custom_end:%d/%m/%Y}", custom_start, custom_end
    raise ValueError("Giai đoạn không được hỗ trợ.")


def period_trade_subset(trades, start=None, end=None):
    """Include whole closed trades only; report trades crossing date boundaries.

    Date comparisons use the session-local dates, not converted UTC calendar days.
    Trades entirely outside the window are not counted as boundary crossings.
    """
    needed = {BUY_DATE, SELL_DATE, RETURN}
    missing = needed.difference(trades.columns)
    if missing:
        raise ValueError("Thiếu cột Backtesting: " + ", ".join(sorted(missing)))
    frame = trades.copy()
    if frame.empty:
        return frame, 0
    bought = pd.to_datetime(frame[BUY_DATE], errors="coerce")
    sold = pd.to_datetime(frame[SELL_DATE], errors="coerce")
    if bought.isna().any() or sold.isna().any():
        raise ValueError("Ngày mua hoặc ngày bán không hợp lệ.")
    bday, sday = bought.dt.date, sold.dt.date
    if (bday > sday).any():
        raise ValueError("Ngày mua sau ngày bán.")
    inside = pd.Series(True, index=frame.index)
    crossing = pd.Series(False, index=frame.index)
    if start is not None:
        inside &= bday >= start
        crossing |= (bday < start) & (sday >= start)
    if end is not None:
        inside &= sday <= end
        crossing |= (bday <= end) & (sday > end)
    return frame.loc[inside].copy(), int(crossing.sum())


def trade_metrics(trades):
    """Compounded return / drawdown use sequential *closed* trades only."""
    r = pd.to_numeric(trades[RETURN], errors="coerce")
    if r.isna().any():
        raise ValueError("Lợi nhuận giao dịch chứa dữ liệu không hợp lệ.")
    r = r.astype(float)
    wins = int((r > 0).sum())
    losses = int((r < 0).sum())
    if r.empty:
        return {
            "Số lệnh": 0, "Số lệnh thắng": 0, "Số lệnh thua": 0,
            "Win Rate (%)": None, "Lợi nhuận TB (%)": None,
            "Profit Factor": None, "Lợi nhuận tích lũy (%)": None,
            "Sụt giảm vốn (%)": None,
        }
    pf = profit_factor_money(r)
    capital = pd.concat([
        pd.Series([1.0]), (1.0 + r.reset_index(drop=True) / 100.0).cumprod()
    ], ignore_index=True)
    return {
        "Số lệnh": len(r),
        "Số lệnh thắng": wins,
        "Số lệnh thua": losses,
        "Win Rate (%)": round(wins / len(r) * 100, 1),
        "Lợi nhuận TB (%)": round(float(r.mean()), 2),
        "Profit Factor": round(pf, 2) if pf is not None else None,
        "Lợi nhuận tích lũy (%)": round(float((capital.iloc[-1] - 1) * 100), 2),
        "Sụt giảm vốn (%)": round(float(((capital / capital.cummax()) - 1).min() * 100), 2),
    }


def evaluate_symbol(symbol, df, period_label, start=None, end=None):
    """Run all five existing backtests independently for one stock.

    Returns (summary rows, errors). A broken strategy does not hide others.
    """
    if df is None or df.empty:
        return [], [{"Mã": symbol, "Chiến lược": "Dữ liệu", "Lỗi": "Không có dữ liệu TCBS"}]
    if len(df) < 200:
        return [], [{"Mã": symbol, "Chiến lược": "Dữ liệu", "Lỗi": "Ít hơn 200 phiên lịch sử"}]
    if not df.index.is_monotonic_increasing or df.index.has_duplicates:
        return [], [{"Mã": symbol, "Chiến lược": "Dữ liệu", "Lỗi": "Thời gian trùng hoặc không tăng dần"}]

    from backtesting import tao_bang_giao_dich
    from strategy_experiments import chay_backtest_thu_nghiem, chay_backtest_diem_v2
    from v21_macd_strategy import chay_backtest_diem_v21_macd

    strategy_functions = (
        lambda x: tao_bang_giao_dich(x),
        lambda x: chay_backtest_thu_nghiem(x, "sma"),
        lambda x: chay_backtest_thu_nghiem(x, "adx_macd"),
        lambda x: chay_backtest_diem_v2(x),
        lambda x: chay_backtest_diem_v21_macd(x),
    )
    rows, errors = [], []
    for name, runner in zip(STRATEGY_NAMES, strategy_functions):
        try:
            # Every strategy receives a copy of the SAME fully calculated history.
            # Signal/position states are recomputed over that history.
            trades = runner(df.copy())
            selected, crossing = period_trade_subset(trades, start, end)
            metrics = trade_metrics(selected)
            rows.append({
                "Mã": symbol,
                "Chiến lược": name,
                "Giai đoạn": period_label,
                "Dữ liệu từ": df.index[0].strftime("%d/%m/%Y"),
                "Dữ liệu đến": df.index[-1].strftime("%d/%m/%Y"),
                **metrics,
                "Lệnh giao ranh giới (không tính)": crossing,
            })
        except Exception as exc:
            # Do not expose arbitrary provider messages containing credentials.
            errors.append({"Mã": symbol, "Chiến lược": name, "Lỗi": type(exc).__name__})
    return rows, errors
