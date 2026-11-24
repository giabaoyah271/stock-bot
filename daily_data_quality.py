"""KT05: strict pre-indicator validation for DAILY TCBS history only.

No forward filling, sorting, deduplication or fabricated missing sessions.
The 15:15 VN cutoff is a conservative local convention, not provider
confirmation that a bar is final. Naive timestamps represent Vietnam time.
"""
import numpy as np
import pandas as pd

OHLCV = ("open", "high", "low", "close", "volume")
MARKET_TZ = "Asia/Ho_Chi_Minh"
MIN_BARS = 200

class DataQualityError(ValueError):
    """Safe, user-facing validation error; never contains provider credentials."""

def prepare_daily_data(raw, now=None):
    if not isinstance(raw, pd.DataFrame) or raw.empty:
        raise DataQualityError("Không có dữ liệu OHLCV")
    if raw.columns.has_duplicates:
        raise DataQualityError("Tên cột bị trùng")
    if not set(("time", *OHLCV)).issubset(raw.columns):
        raise DataQualityError("Thiếu cột time hoặc OHLCV")
    df = raw.copy(deep=True)
    try:
        # Do not interpret bare numeric epoch timestamps as nanoseconds.
        if pd.api.types.is_numeric_dtype(df["time"]):
            raise ValueError("numeric time")
        timestamps = pd.DatetimeIndex(pd.to_datetime(df["time"], errors="raise"))
    except (ValueError, TypeError, OverflowError):
        raise DataQualityError("Thời gian không hợp lệ hoặc múi giờ không nhất quán") from None
    if timestamps.hasnans or timestamps.has_duplicates or not timestamps.is_monotonic_increasing:
        raise DataQualityError("Thời gian thiếu, trùng hoặc không tăng dần")
    local = timestamps.tz_convert(MARKET_TZ) if timestamps.tz is not None else timestamps
    if local.normalize().has_duplicates:
        raise DataQualityError("Trùng ngày giao dịch Việt Nam")
    current = pd.Timestamp.now(tz=MARKET_TZ) if now is None else pd.Timestamp(now)
    current = current.tz_localize(MARKET_TZ) if current.tzinfo is None else current.tz_convert(MARKET_TZ)
    if local[-1].date() > current.date():
        raise DataQualityError("Có ngày dữ liệu nằm trong tương lai")
    trimmed = local[-1].date() == current.date() and (current.hour, current.minute) < (15, 15)
    df["time"] = timestamps
    df.set_index("time", inplace=True)
    if trimmed:
        df = df.iloc[:-1].copy()
        local = local[:-1]
    if len(df) < MIN_BARS:
        raise DataQualityError(f"Chỉ có {len(df)} nến đã hoàn tất; cần ít nhất {MIN_BARS} nến")
    o = df[list(OHLCV)].apply(pd.to_numeric, errors="coerce")
    finite = np.isfinite(o.to_numpy(dtype=float)).all(axis=1)
    if not finite.all():
        raise DataQualityError(f"{int((~finite).sum())} nến thiếu số hoặc chứa giá trị vô cực")
    bad_price = (o[list(OHLCV[:4])] <= 0).any(axis=1)
    if bad_price.any():
        raise DataQualityError(f"{int(bad_price.sum())} nến có giá không dương")
    bad_range = ((o["high"] < o[["open","close","low"]].max(axis=1)) |
                 (o["low"] > o[["open","close"]].min(axis=1)))
    if bad_range.any():
        raise DataQualityError(f"{int(bad_range.sum())} nến có OHLC không nhất quán")
    if (o["volume"] < 0).any():
        raise DataQualityError(f"{int((o['volume'] < 0).sum())} nến khối lượng âm")
    for col in OHLCV:
        df[col] = o[col]
    return df, {
        "trimmed": bool(trimmed), "bars":len(df), "zero_volume":int((o["volume"] == 0).sum()),
        "first_date":local[0].date().isoformat(), "last_date":local[-1].date().isoformat(),
    }
