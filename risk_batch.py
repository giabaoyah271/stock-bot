"""Independent multi-stock daily-equity reporting; never changes trading rules.

Each case calls the existing risk_equity engine, which checks exact trade
parity against the original backtesting ledger before returning a daily curve.
All cases represent one stock and one fixed strategy, NOT a joint portfolio.
"""

import pandas as pd

from multi_backtest_core import parse_symbols, trade_metrics
from risk_equity import STRATEGIES, calculate_equity_risk

GROUP_A = "HPG, MBB, FPT, TCB, MWG, VNM"
GROUP_B = "ACB, DGC, GAS, GMD, PNJ, REE"
GROUPS = {
    "Thử nhanh: HPG, MBB": "HPG, MBB",
    "Nhóm A: 6 mã phát triển": GROUP_A,
    "Nhóm B: 6 mã bổ sung": GROUP_B,
    "Cả 12 mã": GROUP_A + ", " + GROUP_B,
    "Tùy chỉnh": None,
}


def selected_symbols(group, custom_text=""):
    """Use the same 12-ticker maximum and validation as the existing tool."""
    if group not in GROUPS:
        raise ValueError("Nhóm mã không hợp lệ")
    raw = custom_text if group == "Tùy chỉnh" else GROUPS[group]
    return parse_symbols(raw)


def _closed_trade_metrics(curve, reported_closed_count):
    """Recover realized trade returns from cash after each simulated sale.

    The equity engine already verifies all fills against backtesting.py.
    Each closed round trip reinvests the previous post-sale cash balance.
    """
    exits = curve.loc[curve["Trạng thái"] == "Bán tại mở cửa", "Tiền mặt"]
    if len(exits) != reported_closed_count:
        raise ValueError("Số lần bán và số giao dịch đã đóng không khớp")
    previous_cash = 100.0
    returns = []
    for cash in exits.to_numpy(dtype=float):
        if cash <= 0 or previous_cash <= 0:
            raise ValueError("Dòng tiền giả định không hợp lệ")
        returns.append(round((cash / previous_cash - 1.0) * 100.0, 2))
        previous_cash = cash
    return trade_metrics(pd.DataFrame({"Lợi nhuận sau chi phí (%)": pd.Series(returns, dtype=float)})), returns


def evaluate_risk_case(symbol, data, strategy):
    """Return (summary row, two-column daily chart) for a single case.

    Raises on bad data or parity failures; caller records an error rather
    than inventing a summary row.
    """
    if strategy not in STRATEGIES:
        raise ValueError("Chiến lược không được hỗ trợ")
    if data is None or data.empty or len(data) < 200:
        raise ValueError("Thiếu dữ liệu lịch sử cần thiết (tối thiểu 200 phiên)")
    if not isinstance(data.index, pd.DatetimeIndex):
        raise ValueError("Chỉ hỗ trợ dữ liệu có chỉ mục ngày giao dịch")

    curve, risk = calculate_equity_risk(data.copy(), strategy)
    trading, per_trade = _closed_trade_metrics(curve, risk["Số giao dịch đã đóng"])
    if trading["Số lệnh"] != risk["Số giao dịch đã đóng"]:
        raise ValueError("Số giao dịch khép kín không khớp")
    loss_returns = [value for value in per_trade if value < 0]
    dd_session = risk["Max Drawdown theo phiên (%)"]
    dd_closed = risk["Drawdown theo lệnh đóng (%)"]
    summary = {
        "Mã": symbol,
        "Chiến lược": strategy,
        "Dữ liệu nguồn từ": data.index[0].strftime("%d/%m/%Y"),
        "Dữ liệu nguồn đến": data.index[-1].strftime("%d/%m/%Y"),
        "Số lệnh": trading["Số lệnh"],
        "Số lệnh thắng": trading["Số lệnh thắng"],
        "Số lệnh thua": trading["Số lệnh thua"],
        "Win Rate (%)": trading["Win Rate (%)"],
        "Lợi nhuận TB (%)": trading["Lợi nhuận TB (%)"],
        "Profit Factor": trading["Profit Factor"],
        "Lợi nhuận theo phiên (%)": risk["Lợi nhuận theo phiên (%)"],
        "Max Drawdown theo phiên (%)": dd_session,
        "Drawdown theo lệnh đóng (%)": dd_closed,
        "Chênh lệch độ sâu Drawdown (điểm %)": round(dd_closed - dd_session, 2),
        "Lệnh lỗ lớn nhất (%)": min(loss_returns) if loss_returns else None,
        "Số phiên nắm giữ TB": risk["Số phiên nắm giữ TB (lệnh đã đóng)"],
        "Phiên dưới đỉnh dài nhất (đã hồi phục)": risk["Phiên dưới đỉnh dài nhất (đã hồi phục)"],
        "Phiên dưới đỉnh hiện tại": risk["Phiên dưới đỉnh hiện tại"],
        "Trạng thái cuối": risk["Trạng thái cuối"],
        "Lãi/lỗ vị thế mở (%; chưa trừ phí bán)": risk["Lãi/lỗ vị thế mở (%; chưa trừ phí bán)"],
        "Vốn cuối (ban đầu 100)": risk["Vốn cuối theo phiên"],
    }
    return summary, curve[["Equity", "Drawdown (%)"]].copy()
