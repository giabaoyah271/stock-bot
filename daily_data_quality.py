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

def slice_raw_history(raw, history_end):
    """KT15 only: truncate before validation/indicators; never modify OHLC."""
    if not isinstance(raw,pd.DataFrame) or raw.empty:
        return raw
    if raw.columns.has_duplicates or "time" not in raw or pd.api.types.is_numeric_dtype(raw["time"]):
        raise DataQualityError("Thời gian nguồn không hợp lệ")
    try:
        ts=pd.DatetimeIndex(pd.to_datetime(raw["time"],errors="raise"))
        if ts.hasnans or ts.has_duplicates or not ts.is_monotonic_increasing:
            raise ValueError("invalid time")
        local=ts.tz_convert(MARKET_TZ).tz_localize(None) if ts.tz is not None else ts
        if local.normalize().has_duplicates:
            raise ValueError("duplicate local day")
        cutoff=pd.Timestamp(history_end)
        if cutoff.tzinfo is not None:
            cutoff=cutoff.tz_convert(MARKET_TZ).tz_localize(None)
        if pd.isna(cutoff): raise ValueError("invalid cutoff")
    except (ValueError,TypeError,OverflowError):
        raise DataQualityError("Thời gian nguồn hoặc mốc cắt không hợp lệ") from None
    return raw.loc[local.normalize()<=cutoff.normalize()].copy()

ACV_BAD_DAY = pd.Timestamp("2022-06-16")
ACV_BAD_OHLCV = (48.97,49.09,48.85,48.76,37101.)

def prepare_kt15_acv(raw, now=None):
    """Opt-in sensitivity only; strict first, never repair or stitch prices."""
    try:
        return prepare_daily_data(raw,now)
    except DataQualityError as exc:
        if not str(exc).startswith("1 nến có OHLC không nhất quán | 2022-06-16:"):
            raise
        ts=pd.DatetimeIndex(pd.to_datetime(raw["time"],errors="raise"))
        local=ts.tz_convert(MARKET_TZ).tz_localize(None) if ts.tz is not None else ts
        day=local.normalize()
        bad=raw.loc[day==ACV_BAD_DAY,list(OHLCV)]
        if len(bad)!=1 or not np.allclose(bad.to_numpy(dtype=float)[0],ACV_BAD_OHLCV,rtol=0,atol=1e-8):
            raise
        keep=day>ACV_BAD_DAY
        daily,report=prepare_daily_data(raw.loc[keep].copy(),now)
        report["kt15_acv_quarantine"]={
            "date":ACV_BAD_DAY.date().isoformat(),
            "ohlcv":bad.to_numpy(dtype=float)[0].tolist(),
            "excluded_bars":int((~keep).sum()),
            "first_used":report["first_date"],
            "reason":str(exc)}
        return daily,report

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
        details=[]
        for k in np.flatnonzero(bad_range.to_numpy())[:5]:
            row=o.iloc[k]
            details.append(f"{local[k].date().isoformat()}: O={row['open']:.17g}, H={row['high']:.17g}, L={row['low']:.17g}, C={row['close']:.17g}, V={row['volume']:.17g}")
        raise DataQualityError(f"{int(bad_range.sum())} nến có OHLC không nhất quán | "+"; ".join(details))
    if (o["volume"] < 0).any():
        raise DataQualityError(f"{int((o['volume'] < 0).sum())} nến khối lượng âm")
    for col in OHLCV:
        df[col] = o[col]
    return df, {
        "trimmed": bool(trimmed), "bars":len(df), "zero_volume":int((o["volume"] == 0).sum()),
        "first_date":local[0].date().isoformat(), "last_date":local[-1].date().isoformat(),
    }
