
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
