"""Historical rolling-window reporting over ONE uninterrupted Stock Bot equity replay.

The strategy and fill logic live exclusively in risk_equity.calculate_equity_risk.
Window boundaries NEVER create trades or reset inventory.  This is a
*retrospective* fixed-strategy time-slice analysis, not parameter optimization
or pristine out-of-sample walk-forward testing.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import math
import numpy as np
import pandas as pd

START_YEAR = 2024
MIN_HISTORY_BARS = 200


@dataclass(frozen=True)
class Window:
    name: str
    start: pd.Timestamp
    end: pd.Timestamp


def half_year_windows(last_date, start_year=START_YEAR):
    """Fixed inclusive calendar halves through the last available year."""
    last = pd.Timestamp(last_date)
    if last.tz is not None:
        last = last.tz_localize(None)
    if not 2020 <= int(start_year) <= 2100:
        raise ValueError("Năm bắt đầu đánh giá không hợp lệ")
    if last.year < start_year:
        return []
    windows = []
    for year in range(start_year, last.year + 1):
        for start, end in (((1, 1), (6, 30)), ((7, 1), (12, 31))):
            lo = pd.Timestamp(year=year, month=start[0], day=start[1])
            hi = pd.Timestamp(year=year, month=end[0], day=end[1])
            if lo <= last:
                windows.append(Window(f"WF{len(windows) + 1}", lo, min(hi, last)))
    return windows


def _validate_curve(curve):
    required = {"Equity", "Tiền mặt", "Số cổ phiếu quy ước", "Trạng thái", "Drawdown (%)"}
    if curve is None or curve.empty or not required.issubset(curve.columns):
        raise ValueError("Thiếu dữ liệu đường Equity hoặc trạng thái giao dịch")
    idx = curve.index
    if (not isinstance(idx, pd.DatetimeIndex) or idx.has_duplicates
            or not idx.is_monotonic_increasing or idx.tz is not None):
        raise ValueError("Chỉ mục ngày giao dịch cần tăng dần, không trùng, không múi giờ")
    numeric = curve[["Equity", "Tiền mặt", "Số cổ phiếu quy ước", "Drawdown (%)"]]
    numeric = numeric.apply(pd.to_numeric, errors="coerce")
    if not np.isfinite(numeric.to_numpy(dtype=float)).all():
        raise ValueError("Equity hoặc trạng thái chứa số không hợp lệ")
    if (numeric["Equity"] <= 0).any() or (numeric["Tiền mặt"] < 0).any() or (numeric["Số cổ phiếu quy ước"] < 0).any():
        raise ValueError("Dòng tiền hoặc số cổ phiếu không hợp lệ")
    actual_dd = (numeric["Equity"] / numeric["Equity"].cummax() - 1) * 100
    if not np.allclose(actual_dd, numeric["Drawdown (%)"], rtol=0, atol=1e-7):
        raise ValueError("Drawdown không nhất quán với Equity toàn kỳ")
    states = {"Mua tại mở cửa", "Bán tại mở cửa", "Giữ tiền mặt", "Đang nắm giữ"}
    if not set(curve["Trạng thái"]).issubset(states):
        raise ValueError("Trạng thái phiên không được hỗ trợ")
    if ((curve["Trạng thái"] == "Giữ tiền mặt") & (numeric["Số cổ phiếu quy ước"] > 0)).any():
        raise ValueError("Phiên giữ tiền mặt lại còn cổ phiếu")
    if ((curve["Trạng thái"] == "Bán tại mở cửa") & (numeric["Số cổ phiếu quy ước"] > 0)).any():
        raise ValueError("Bán xong nhưng còn cổ phiếu")
    if ((curve["Trạng thái"] == "Đang nắm giữ") & (numeric["Số cổ phiếu quy ước"] <= 0)).any():
        raise ValueError("Trạng thái đang nắm giữ nhưng không có cổ phiếu")


def _realized_sales(curve, initial_capital):
    """Attach each full round-trip to its SALE execution session.

    Cash differences are measured against prior post-sale cash. Returns are
    rounded to 0.01% like risk_batch._closed_trade_metrics, and monetary P&L
    is compounded over the WHOLE history before assigning closes to windows.
    Thus window PF uses monetary P&L of the actual trades, not fictitious
    fresh capital or fees at the window boundary.
    """
    rows = []
    last_buy = None
    last_exit_cash = float(initial_capital)
    rounded_capital = float(initial_capital)
    for session, row in curve.iterrows():
        action = row["Trạng thái"]
        if action == "Mua tại mở cửa":
            if last_buy is not None:
                raise ValueError("Mua hai lần trước khi bán")
            last_buy = session
        elif action == "Bán tại mở cửa":
            if last_buy is None:
                raise ValueError("Có lệnh bán nhưng không có lệnh mua trước đó")
            cash = float(row["Tiền mặt"])
            if cash <= 0 or last_exit_cash <= 0:
                raise ValueError("Tiền mặt sau bán không hợp lệ")
            rate = round((cash / last_exit_cash - 1) * 100, 2)
            pnl = rounded_capital * (rate / 100)
            rounded_capital += pnl
            rows.append({
                "Ngày mua": last_buy, "Ngày bán": session,
                "Lợi nhuận lệnh (%)": rate, "Lãi/lỗ bằng tiền quy ước": pnl,
            })
            last_exit_cash = cash
            last_buy = None
    if last_buy is not None and float(curve["Số cổ phiếu quy ước"].iloc[-1]) <= 0:
        raise ValueError("Có lệnh mua chưa bán nhưng cuối kỳ không còn cổ phiếu")
    return pd.DataFrame(rows, columns=["Ngày mua", "Ngày bán", "Lợi nhuận lệnh (%)", "Lãi/lỗ bằng tiền quy ước"])


def _closed_metrics(trades):
    n = len(trades)
    if n == 0:
        return {"Số lệnh đóng": 0, "Số lệnh thắng": 0, "Số lệnh thua": 0,
                "Win Rate (%)": None, "Profit Factor (theo tiền)": None}
    rates = trades["Lợi nhuận lệnh (%)"].to_numpy(dtype=float)
    cash_pnl = trades["Lãi/lỗ bằng tiền quy ước"].to_numpy(dtype=float)
    wins = int((rates > 0).sum())
    losses = int((rates < 0).sum())
    gain = float(cash_pnl[cash_pnl > 0].sum())
    loss = float(-cash_pnl[cash_pnl < 0].sum())
    return {"Số lệnh đóng": n, "Số lệnh thắng": wins, "Số lệnh thua": losses,
            "Win Rate (%)": round(wins / n * 100, 1),
            "Profit Factor (theo tiền)": round(gain / loss, 2) if loss > 0 else None}


def evaluate_windows_from_curve(curve, symbol, strategy, initial_capital=100.0, start_year=START_YEAR):
    """Returns (window_rows, aggregate_row, empty_window_errors, closed_trades).

    The first window return baseline is the LAST close before its first
    trading session, so the first session's movement is not lost.
    """
    _validate_curve(curve)
    initial_capital = float(initial_capital)
    if not math.isfinite(initial_capital) or initial_capital <= 0:
        raise ValueError("Vốn đầu kỳ không hợp lệ")
    windows = half_year_windows(curve.index[-1], start_year)
    if not windows:
        raise ValueError("Chưa có dữ liệu trong giai đoạn Walk-Forward")
    trades = _realized_sales(curve, initial_capital)
    window_rows, missing, raw_factors = [], [], []
    idx = curve.index
    for w in windows:
        mask = (idx >= w.start) & (idx <= w.end)
        positions = np.flatnonzero(mask)
        if not len(positions):
            missing.append({"Mã": symbol, "Chiến lược": strategy,
                            "Cửa sổ": w.name, "Lỗi": "Không có phiên dữ liệu trong cửa sổ"})
            continue
        p0, p1 = int(positions[0]), int(positions[-1])
        base_equity = float(curve["Equity"].iloc[p0 - 1]) if p0 > 0 else initial_capital
        segment = curve.iloc[p0:p1 + 1]
        eq = segment["Equity"].to_numpy(dtype=float)
        # Include pre-window boundary capital as reference peak and return base.
        path = np.r_[base_equity, eq]
        running = np.maximum.accumulate(path)
        local_dd = float((path / running - 1).min() * 100)
        change_factor = float(eq[-1] / base_equity)
        raw_factors.append(change_factor)
        selected = trades.loc[(trades["Ngày bán"] >= w.start) & (trades["Ngày bán"] <= w.end)]
        stats = _closed_metrics(selected)
        crossing = int((selected["Ngày mua"] < w.start).sum()) if len(selected) else 0
        shares = float(segment["Số cổ phiếu quy ước"].iloc[-1])
        window_rows.append({
            "Mã": symbol, "Chiến lược": strategy, "Cửa sổ": w.name,
            "Từ ngày": w.start.strftime("%d/%m/%Y"),
            "Đến ngày": w.end.strftime("%d/%m/%Y"),
            "Phiên đầu có dữ liệu": idx[p0].strftime("%d/%m/%Y"),
            "Phiên cuối có dữ liệu": idx[p1].strftime("%d/%m/%Y"),
            "Số phiên": len(segment),
            "Equity tại ranh giới đầu": round(base_equity, 6),
            "Equity cuối cửa sổ": round(float(eq[-1]), 6),
            "Lợi nhuận cửa sổ (%)": round((change_factor - 1) * 100, 2),
            "Max Drawdown cục bộ (%)": round(local_dd, 2),
            "Max Drawdown so đỉnh toàn kỳ (%)": round(float(segment["Drawdown (%)"].min()), 2),
            **stats,
            "Lệnh đóng có ngày mua trước cửa sổ": crossing,
            "Trạng thái cuối cửa sổ": "Đang nắm giữ" if shares > 0 else "Tiền mặt",
        })
    if not window_rows:
        raise ValueError("Không có phiên dữ liệu thuộc các cửa sổ đánh giá")
    first_eval = next(i for i, t in enumerate(idx) if t >= windows[0].start)
    initial_eval_equity = float(curve["Equity"].iloc[first_eval - 1]) if first_eval > 0 else initial_capital
    last_eval_equity = float(curve["Equity"].iloc[-1])
    composed = float(np.prod(raw_factors))
    direct = last_eval_equity / initial_eval_equity
    if not math.isclose(composed, direct, rel_tol=1e-9, abs_tol=1e-9):
        raise ValueError("Ghép lợi nhuận cửa sổ không khớp Equity liên tục")
    evaluation = curve.iloc[first_eval:]
    eval_path = np.r_[initial_eval_equity, evaluation["Equity"].to_numpy(dtype=float)]
    evaluated_dd = float((eval_path / np.maximum.accumulate(eval_path) - 1).min() * 100)
    eval_trades = trades.loc[trades["Ngày bán"] >= windows[0].start]
    eval_stats = _closed_metrics(eval_trades)
    # Compare full-history realized returns to original engine's closed count.
    full_equity = float(curve["Equity"].iloc[-1])
    total_return = (full_equity / initial_capital - 1) * 100
    mdd_full = float(curve["Drawdown (%)"].min())
    profitable = sum(v > 1 + 1e-10 for v in raw_factors)
    aggregate = {
        "Mã": symbol, "Chiến lược": strategy,
        "Số cửa sổ có dữ liệu": len(window_rows),
        "Số cửa sổ có lãi": profitable,
        "Tỷ lệ cửa sổ có lãi (%)": round(100 * profitable / len(window_rows), 1),
        "Lợi nhuận giai đoạn đánh giá (%)": round((direct - 1) * 100, 2),
        "Max Drawdown giai đoạn đánh giá (%)": round(evaluated_dd, 2),
        "Số lệnh đóng giai đoạn đánh giá": eval_stats["Số lệnh đóng"],
        "Win Rate giai đoạn (%)": eval_stats["Win Rate (%)"],
        "Profit Factor giai đoạn (theo tiền)": eval_stats["Profit Factor (theo tiền)"],
        "Lợi nhuận TOÀN lịch sử (%)": round(total_return, 2),
        "Max Drawdown TOÀN lịch sử (%)": round(mdd_full, 2),
        "Số lệnh đóng TOÀN lịch sử": len(trades),
        "Trạng thái cuối kỳ": "Đang nắm giữ" if curve["Số cổ phiếu quy ước"].iloc[-1] > 0 else "Tiền mặt",
        "Đối chiếu Equity qua cửa sổ": "ĐẠT",
    }
    return window_rows, aggregate, missing, trades


def evaluate_walk_forward_case(symbol, data, strategy):
    """Single full risk replay then read-only slices; return rows/summary/errors/curve."""
    if data is None or data.empty or len(data) < MIN_HISTORY_BARS:
        raise ValueError("Cần ít nhất 200 phiên lịch sử để chạy chiến lược")
    # Delay import so pure numerical slicing can be tested without TCBS or UI.
    from risk_equity import STRATEGIES, calculate_equity_risk
    if strategy not in STRATEGIES:
        raise ValueError("Chiến lược không hợp lệ")
    curve, risk = calculate_equity_risk(data.copy(), strategy, initial_capital=100.0)
    rows, aggregate, errors, trades = evaluate_windows_from_curve(curve, symbol, strategy)
    if aggregate["Số lệnh đóng TOÀN lịch sử"] != risk["Số giao dịch đã đóng"]:
        raise ValueError("Số lệnh toàn lịch sử không khớp risk_equity")
    if abs(aggregate["Lợi nhuận TOÀN lịch sử (%)"] - risk["Lợi nhuận theo phiên (%)"]) > 0.01:
        raise ValueError("Lợi nhuận toàn lịch sử không khớp risk_equity")
    if abs(aggregate["Max Drawdown TOÀN lịch sử (%)"] - risk["Max Drawdown theo phiên (%)"]) > 0.01:
        raise ValueError("Max Drawdown toàn lịch sử không khớp risk_equity")
    from risk_batch import _closed_trade_metrics
    original_trading, _ = _closed_trade_metrics(curve, risk["Số giao dịch đã đóng"])
    local_pf = _closed_metrics(trades)["Profit Factor (theo tiền)"]
    if local_pf != original_trading["Profit Factor"]:
        raise ValueError("Profit Factor toàn lịch sử không khớp mô-đun rủi ro gốc")
    return rows, aggregate, errors, curve[["Equity", "Drawdown (%)"]].copy()
