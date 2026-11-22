"""Scoring V2 experimental only: no orders, no V1 changes."""
import pandas as pd

WEIGHTS = {
    "Trend": 30,
    "Strength": 20,
    "Momentum": 20,
    "Flow": 20,
    "Reversal": 10,
}


def tinh_diem_v2(df):
    """Return a new DataFrame with V2 score columns, no look-ahead."""
    cols = [
        "open", "close", "volume", "SMA20", "SMA50", "SMA200",
        "Senkou_Span_A", "Senkou_Span_B", "Tenkan_Sen", "Kijun_Sen",
        "ADX", "Plus_DI", "Minus_DI", "RSI", "MACD", "Signal_Line",
        "MFI", "Vol_Avg", "BB_lower", "BB_upper", "Price_Min_10",
        "Prev_Price_Min", "RSI_Min_10", "Prev_RSI_Min",
        "Price_Max_10", "Prev_Price_Max", "RSI_Max_10", "Prev_RSI_Max",
    ]
    missing = sorted(set(cols) - set(df.columns))
    if missing:
        raise ValueError("V2 thieu cot: " + ", ".join(missing))
    if not df.index.is_monotonic_increasing or df.index.has_duplicates:
        raise ValueError("V2 can du lieu theo thu tu thoi gian, khong trung nen")

    d = df.copy()
    x = {col: pd.to_numeric(d[col], errors="coerce") for col in cols}
    ready = pd.DataFrame(x).notna().all(axis=1)
    ready &= (x["close"] > 0) & (x["Vol_Avg"] > 0) & (x["volume"] >= 0)

    def pts(condition, weight):
        return condition.fillna(False).astype(float) * weight

    cloud_hi = pd.concat([x["Senkou_Span_A"], x["Senkou_Span_B"]], axis=1).max(axis=1)
    cloud_lo = pd.concat([x["Senkou_Span_A"], x["Senkou_Span_B"]], axis=1).min(axis=1)

    groups = {
        "Trend": (
            pts(x["close"] > x["SMA200"], 15)
            + pts((x["close"] > x["SMA20"]) & (x["SMA20"] > x["SMA50"]), 10)
            + pts((x["close"] > cloud_hi) & (x["Tenkan_Sen"] > x["Kijun_Sen"]), 5),
            pts(x["close"] < x["SMA200"], 15)
            + pts((x["close"] < x["SMA20"]) & (x["SMA20"] < x["SMA50"]), 10)
            + pts((x["close"] < cloud_lo) & (x["Tenkan_Sen"] < x["Kijun_Sen"]), 5),
        ),
        "Strength": (
            pts((x["ADX"] > 25) & (x["Plus_DI"] > x["Minus_DI"]), 20),
            pts((x["ADX"] > 25) & (x["Minus_DI"] > x["Plus_DI"]), 20),
        ),
        "Momentum": (
            pts(x["MACD"] > x["Signal_Line"], 12)
            + pts((x["RSI"] > 50) & (x["RSI"] <= 70), 8),
            pts(x["MACD"] < x["Signal_Line"], 12)
            + pts((x["RSI"] < 50) & (x["RSI"] >= 30), 8),
        ),
        "Flow": (
            pts(x["MFI"] > 50, 12)
            + pts((x["volume"] > 1.5 * x["Vol_Avg"]) & (x["close"] > x["open"]), 8),
            pts(x["MFI"] < 40, 12)
            + pts((x["volume"] > 1.5 * x["Vol_Avg"]) & (x["close"] < x["open"]), 8),
        ),
        "Reversal": (
            pts((x["Price_Min_10"] < x["Prev_Price_Min"])
                & (x["RSI_Min_10"] > x["Prev_RSI_Min"])
                & (x["RSI"] < 45) & (x["close"] > x["close"].shift(1)), 6)
            + pts((x["close"].shift(1) < x["BB_lower"].shift(1))
                & (x["close"] > x["BB_lower"]) & (x["close"] > x["open"]), 4),
            pts((x["Price_Max_10"] > x["Prev_Price_Max"])
                & (x["RSI_Max_10"] < x["Prev_RSI_Max"])
                & (x["RSI"] > 55) & (x["close"] < x["close"].shift(1)), 6)
            + pts((x["close"].shift(1) > x["BB_upper"].shift(1))
                & (x["close"] < x["BB_upper"]) & (x["close"] < x["open"]), 4),
        ),
    }
    buy, sell = pd.Series(0.0, index=d.index), pd.Series(0.0, index=d.index)
    for name, (b, s) in groups.items():
        d[f"V2_{name}_Buy"] = b.where(ready)
        d[f"V2_{name}_Sell"] = s.where(ready)
        buy = buy + b
        sell = sell + s
    d["V2_Buy_Pct"] = buy.where(ready)
    d["V2_Sell_Pct"] = sell.where(ready)
    d["V2_Ready"] = ready
    return d
