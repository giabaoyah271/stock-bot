"""Read-only closed-trade diagnostics, using the unchanged research ledgers.

Excursions use raw OHLC quotes relative to the raw entry open (gross).
Net MFE uses hypothetical liquidation with baseline costs, not a realizable
intraday exit or a new trading rule. The sell bar contributes ONLY its open.
"""
import numpy as np
import pandas as pd

from backtesting import tao_bang_giao_dich
from strategy_experiments import chay_backtest_thu_nghiem
from strategy_policy import RESEARCH
from risk_equity import BUY_FEE, SELL_FEE, SELL_TAX, SLIPPAGE
from multi_backtest_core import RETURN, BUY_DATE, SELL_DATE, trade_metrics

BUY_SIGNAL = "Ngày tín hiệu mua"
SELL_SIGNAL = "Ngày tín hiệu bán"
MAE = "MAE giá (%)"
MFE = "MFE giá (%)"
NET_MFE = "MFE ròng giả định (%)"
GIVEBACK = "MFE ròng trừ LN ròng (đpt)"
HOLD = "Số phiên nắm giữ"
EXIT = "Nhóm thoát lệnh"
CLASS = "Nhóm chẩn đoán"
EARLY = "MAE 3 phiên đầu (%)"

FEATURES = {
    "close": "Close tín hiệu mua", "RSI": "RSI tín hiệu mua",
    "ADX": "ADX tín hiệu mua", "Plus_DI": "DI+ tín hiệu mua",
    "Minus_DI": "DI- tín hiệu mua", "MACD": "MACD tín hiệu mua",
    "Signal_Line": "MACD Signal tín hiệu mua", "MFI": "MFI tín hiệu mua",
    "ATR": "ATR tín hiệu mua", "SMA20": "SMA20 tín hiệu mua",
    "SMA50": "SMA50 tín hiệu mua", "SMA200": "SMA200 tín hiệu mua",
    "Buy_Pct": "Điểm mua V1 tại tín hiệu", "Sell_Pct": "Điểm bán V1 tại tín hiệu",
    "volume": "Volume tín hiệu mua", "Vol_Avg": "Volume TB tín hiệu mua",
}
LEDGER_COLUMNS = (BUY_SIGNAL, BUY_DATE, "Giá mua mô phỏng", SELL_SIGNAL,
                  SELL_DATE, "Giá bán mô phỏng", RETURN, "Lý do bán")
EXTRA_COLUMNS = (
    "Mã", "Chiến lược", "Dữ liệu từ", "Dữ liệu đến", HOLD,
    "Open mua gốc", "Open bán gốc", "Gap mua (%)", "Gap bán (%)",
    MAE, MFE, EARLY, "Phiên đến MFE (0 = phiên mua)",
    "Ngày MFE", "Ngày MAE", NET_MFE, GIVEBACK, "LN giá khi thoát (%)",
    "Stop ATR tại tín hiệu mua", "Khoảng cách stop từ open mua (%)",
    "RVOL theo V1", "ATR/Close tín hiệu (%)",
    "Close so với SMA200 (%)", "SMA50 so với SMA200 (%)",
    EXIT, CLASS, *FEATURES.values(),
)

def completed_daily_history(df, now=None):
    """Trim only a current incomplete Vietnam daily bar; never mutate input."""
    if df is None or df.empty or not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("Không có lịch sử ngày hợp lệ")
    idx = df.index
    if idx.hasnans or idx.has_duplicates or not idx.is_monotonic_increasing:
        raise ValueError("Thời gian thiếu, trùng hoặc không tăng dần")
    local = idx.tz_convert("Asia/Ho_Chi_Minh") if idx.tz is not None else idx
    if local.normalize().has_duplicates:
        raise ValueError("Trùng ngày giao dịch Việt Nam")
    now = pd.Timestamp.now(tz="Asia/Ho_Chi_Minh") if now is None else pd.Timestamp(now)
    now = now.tz_localize("Asia/Ho_Chi_Minh") if now.tzinfo is None else now.tz_convert("Asia/Ho_Chi_Minh")
    if local[-1].date() > now.date():
        raise ValueError("Dữ liệu chứa ngày tương lai")
    trimmed = local[-1].date() == now.date() and (now.hour, now.minute) < (15, 15)
    return (df.iloc[:-1].copy() if trimmed else df.copy()), trimmed

def _validate(df):
    if df is None or df.empty or not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("Thiếu lịch sử giá ngày")
    idx = df.index
    if idx.hasnans or idx.has_duplicates or not idx.is_monotonic_increasing:
        raise ValueError("Thời gian không hợp lệ")
    local = idx.tz_convert("Asia/Ho_Chi_Minh") if idx.tz is not None else idx
    if local.normalize().has_duplicates:
        raise ValueError("Trùng ngày giao dịch")
    required = ["open", "high", "low", "close", "volume"]
    if not set(required).issubset(df.columns):
        raise ValueError("Thiếu OHLCV")
    o = df[required].apply(pd.to_numeric, errors="coerce")
    if not np.isfinite(o.to_numpy(dtype=float)).all():
        raise ValueError("OHLCV thiếu hoặc không hữu hạn")
    if (o[required[:4]] <= 0).any().any() or (o["volume"] < 0).any():
        raise ValueError("Giá hoặc khối lượng không hợp lệ")
    if ((o["high"] < o[["open","close","low"]].max(axis=1)) |
        (o["low"] > o[["open","close"]].min(axis=1))).any():
        raise ValueError("OHLC không nhất quán")
    return o

def _number(row, key):
    try:
        val = float(row.get(key, np.nan))
        return val if np.isfinite(val) else np.nan
    except (TypeError, ValueError):
        return np.nan

def _ratio(n, d):
    return (n / d - 1) * 100 if np.isfinite(n) and np.isfinite(d) and d > 0 else np.nan

def _percent(n, d):
    return n / d * 100 if np.isfinite(n) and np.isfinite(d) and d > 0 else np.nan

def _exit_label(strategy, reason, df, signal_buy, signal_sell):
    # Filtered strategy ledger has explicit reason strings. V1 reason is a
    # list of indicator evidence, not a stop/score category.
    if strategy != RESEARCH[0]:
        if "thoat do Trailing Stop" in reason:
            return "Trailing Stop ATR (ghi trong ledger)"
        if "thoat theo diem ban" in reason:
            return "Điểm bán (ghi trong ledger)"
        return "Không xác định"
    # Derive stop eligibility only from observed signal-period closes/ATR,
    # not from subsequent execution price. Label as reconstructed, never proof.
    if "ATR" not in df.columns:
        return "Không xác định (V1)"
    block = df.iloc[signal_buy:signal_sell+1]
    stops = pd.to_numeric(block["close"], errors="coerce") - 2 * pd.to_numeric(block["ATR"], errors="coerce")
    if not np.isfinite(stops.to_numpy(dtype=float)).all():
        return "Không xác định (V1)"
    close = float(df["close"].iloc[signal_sell])
    if signal_sell - signal_buy >= 3 and close <= float(stops.max()):
        return "Trailing Stop ATR (suy từ quy tắc V1)"
    return "Điểm bán/khác (suy từ quy tắc V1)"

def diagnose_ledger(symbol, strategy, df, trades):
    """Annotate an original closed ledger; validate dates and execution parity."""
    if strategy not in RESEARCH:
        raise ValueError("Chỉ hỗ trợ ba chiến lược nghiên cứu")
    o = _validate(df)
    if not set(LEDGER_COLUMNS).issubset(trades.columns):
        raise ValueError("Thiếu cột nhật ký giao dịch")
    records = []
    previous_exit = -1
    for _, trade in trades.iterrows():
        positions = []
        for name in (BUY_SIGNAL, BUY_DATE, SELL_SIGNAL, SELL_DATE):
            loc = df.index.get_indexer([pd.Timestamp(trade[name])])[0]
            if loc < 0:
                raise ValueError("Ngày giao dịch không thuộc lịch sử giá")
            positions.append(int(loc))
        sb, b, ss, s = positions
        if not (sb >= 1 and b == sb + 1 and ss >= b and s == ss + 1 and b > previous_exit):
            raise ValueError("Trình tự hoặc giá mở cửa kế tiếp không khớp ledger")
        previous_exit = s
        entry, exit_open = float(o["open"].iloc[b]), float(o["open"].iloc[s])
        buy_fill = entry * (1 + SLIPPAGE)
        sell_fill = exit_open * (1 - SLIPPAGE)
        net_factor = (1 - SLIPPAGE) * (1 - SELL_FEE - SELL_TAX) / (buy_fill * (1 + BUY_FEE))
        net = (exit_open * net_factor - 1) * 100
        for col, expected, digits in (("Giá mua mô phỏng", buy_fill, 3),
                                       ("Giá bán mô phỏng", sell_fill, 3),
                                       (RETURN, net, 2)):
            val = float(trade[col])
            if not np.isfinite(val) or abs(val - round(expected, digits)) > 1e-8:
                raise ValueError("Giá/chi phí không khớp Backtesting gốc: " + col)
        # All buy-day OHLC is inside exposure. Sell-day high/low/close are not.
        # Include entry open to anchor gross excursion at zero.
        high = np.r_[entry, o["high"].iloc[b:s].to_numpy(dtype=float), exit_open]
        low = np.r_[entry, o["low"].iloc[b:s].to_numpy(dtype=float), exit_open]
        extreme_positions = np.r_[b, np.arange(b,s), s]
        h, l = int(np.argmax(high)), int(np.argmin(low))
        mfe = _ratio(float(high[h]), entry)
        mae = _ratio(float(low[l]), entry)
        # First 3 held bars; include sell open only if sale occurs within
        # this interval (entry offset 0, 1 or 2).
        early_values = np.r_[entry, o["low"].iloc[b:min(s,b+3)].to_numpy(dtype=float)]
        if s - b < 3:
            early_values = np.r_[early_values, exit_open]
        early = _ratio(float(early_values.min()), entry)
        best_net = (float(high[h]) * net_factor - 1) * 100
        giveback = max(0.0, best_net - net)
        reported_net = float(trade[RETURN])
        if reported_net < 0:
            if best_net <= 0:
                diagnosis = "Lỗ: chưa có cơ hội lãi ròng theo giá cực trị"
            elif best_net >= 2:
                diagnosis = "Lỗ: từng có MFE ròng >= 2%"
            else:
                diagnosis = "Lỗ: từng có MFE ròng 0–2%"
        elif reported_net > 0:
            diagnosis = "Lãi"
        else:
            diagnosis = "Hòa vốn theo ledger"
        signal = df.iloc[sb]
        stop = _number(signal, "close") - 2 * _number(signal, "ATR")
        if not np.isfinite(stop):
            stop = np.nan
        record = trade.to_dict()
        record.update({
            "Mã": symbol, "Chiến lược": strategy,
            "Dữ liệu từ": df.index[0], "Dữ liệu đến": df.index[-1],
            HOLD: s-b, "Open mua gốc": entry, "Open bán gốc": exit_open,
            "Gap mua (%)": _ratio(entry, float(o["close"].iloc[sb])),
            "Gap bán (%)": _ratio(exit_open, float(o["close"].iloc[ss])),
            MAE: mae, MFE: mfe, EARLY: early,
            "Phiên đến MFE (0 = phiên mua)": int(extreme_positions[h])-b,
            "Ngày MFE": df.index[int(extreme_positions[h])],
            "Ngày MAE": df.index[int(extreme_positions[l])],
            NET_MFE: best_net, GIVEBACK: giveback,
            "LN giá khi thoát (%)": _ratio(exit_open, entry),
            "Stop ATR tại tín hiệu mua": stop,
            "Khoảng cách stop từ open mua (%)": _percent(entry-stop,entry),
            "RVOL theo V1": _number(signal,"volume")/_number(signal,"Vol_Avg")
                if _number(signal,"Vol_Avg") > 0 else np.nan,
            "ATR/Close tín hiệu (%)": _percent(_number(signal,"ATR"), _number(signal,"close")),
            "Close so với SMA200 (%)": _ratio(_number(signal,"close"), _number(signal,"SMA200")),
            "SMA50 so với SMA200 (%)": _ratio(_number(signal,"SMA50"), _number(signal,"SMA200")),
            EXIT: _exit_label(strategy,str(trade["Lý do bán"]),df,sb,ss),
            CLASS: diagnosis,
        })
        record.update({label: _number(signal,col) for col,label in FEATURES.items()})
        records.append(record)
    return pd.DataFrame(records, columns=list(LEDGER_COLUMNS)+list(EXTRA_COLUMNS))

def evaluate_trade_case(symbol, df, strategy):
    if len(df) < 200:
        raise ValueError("Cần tối thiểu 200 phiên lịch sử")
    _validate(df)
    if strategy == RESEARCH[0]:
        trades = tao_bang_giao_dich(df.copy())
    elif strategy == RESEARCH[1]:
        trades = chay_backtest_thu_nghiem(df.copy(), "sma")
    elif strategy == RESEARCH[2]:
        trades = chay_backtest_thu_nghiem(df.copy(), "adx_macd")
    else:
        raise ValueError("Chiến lược không thuộc nhóm nghiên cứu")
    details = diagnose_ledger(symbol,strategy,df,trades)
    return details, summarize_case(symbol,strategy,details,df)

def summarize_case(symbol, strategy, details, df):
    losses = details.loc[details[RETURN] < 0] if len(details) else details
    def mean(frame, col):
        return round(float(frame[col].mean()), 4) if len(frame) else None
    metrics = trade_metrics(details)
    return {
        "Mã":symbol, "Chiến lược":strategy, "Dữ liệu từ":df.index[0],
        "Dữ liệu đến":df.index[-1], **metrics,
        "MAE TB (%)":mean(details,MAE), "MFE TB (%)":mean(details,MFE),
        "MAE 3 phiên đầu TB (%)":mean(details,EARLY),
        "MFE ròng TB (%)":mean(details,NET_MFE),
        "Giveback TB (đpt)":mean(details,GIVEBACK),
        "Số phiên giữ TB":mean(details,HOLD),
        "Lệnh lỗ chưa có MFE ròng dương":int((losses[NET_MFE] <= 0).sum()),
        "Lệnh lỗ từng có MFE ròng > 0":int((losses[NET_MFE] > 0).sum()),
        "Lệnh lỗ từng có MFE ròng >= 2%":int((losses[NET_MFE] >= 2).sum()),
        "Lệnh lỗ từng có MFE ròng >= 5%":int((losses[NET_MFE] >= 5).sum()),
        "Lệnh lỗ MAE 3 phiên đầu TB (%)":mean(losses,EARLY),
    }
