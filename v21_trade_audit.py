"""V2.1 diagnostics: compare closed V1/V2 trades, without changing signals.

All entry indicators are read from the BUY SIGNAL candle, not later candles.
Matching buy dates and overlapping holding periods are different categories.
"""

import pandas as pd

BUY_SIGNAL = "Ngày tín hiệu mua"
BUY_DATE = "Ngày mua mô phỏng"
SELL_DATE = "Ngày bán mô phỏng"
NET_RETURN = "Lợi nhuận sau chi phí (%)"


def _prepare(trades, name):
    required = {BUY_SIGNAL, BUY_DATE, SELL_DATE, NET_RETURN}
    missing = required.difference(trades.columns)
    if missing:
        raise ValueError(f"{name} thiếu cột: {', '.join(sorted(missing))}")

    result = trades.copy().reset_index(drop=True)
    for col, internal in ((BUY_SIGNAL, "_signal"), (BUY_DATE, "_buy"),
                          (SELL_DATE, "_sell")):
        result[internal] = pd.to_datetime(result[col], utc=True, errors="coerce")
    result["_return"] = pd.to_numeric(result[NET_RETURN], errors="coerce")

    if result[["_signal", "_buy", "_sell", "_return"]].isna().any().any():
        raise ValueError(f"{name} có ngày hoặc lợi nhuận không hợp lệ")
    if ((result["_signal"] >= result["_buy"]) |
            (result["_buy"] >= result["_sell"])).any():
        raise ValueError(f"{name} có thứ tự ngày tín hiệu/khớp lệnh sai")
    if result["_buy"].duplicated().any():
        raise ValueError(f"{name} có giao dịch trùng ngày mua")
    return result.sort_values("_buy").reset_index(drop=True)


def _classify(target, reference, reference_name):
    same_buy_dates = set(reference["_buy"])
    windows = list(zip(reference["_buy"], reference["_sell"]))
    labels = []
    for _, row in target.iterrows():
        buy, sell = row["_buy"], row["_sell"]
        if buy in same_buy_dates:
            labels.append("Trùng ngày mua")
        elif any(buy < r_sell and sell > r_buy for r_buy, r_sell in windows):
            labels.append("Khác ngày mua, chồng lấn vị thế")
        else:
            labels.append(f"Không chồng lấn {reference_name}")
    return labels


def _read_signal_features(df, signals):
    from scoring_v2 import tinh_diem_v2

    scored = tinh_diem_v2(df)
    cols = [
        "Buy_Pct", "Sell_Pct", "V2_Buy_Pct", "V2_Sell_Pct",
        "V2_Trend_Buy", "V2_Strength_Buy", "V2_Momentum_Buy",
        "V2_Flow_Buy", "V2_Reversal_Buy", "RSI", "ADX",
        "Plus_DI", "Minus_DI", "MACD", "Signal_Line", "SMA50",
        "SMA200", "MFI", "volume", "Vol_Avg", "close",
    ]
    missing = set(cols).difference(scored.columns)
    if missing:
        raise ValueError("Thiếu chỉ báo: " + ", ".join(sorted(missing)))

    features = scored[cols].copy()
    features.index = pd.to_datetime(features.index, utc=True)
    if features.index.has_duplicates:
        raise ValueError("Dữ liệu giá có ngày trùng lặp")
    signals = pd.DatetimeIndex(signals)
    if not signals.isin(features.index).all():
        raise ValueError("Một số ngày tín hiệu mua không nằm trong dữ liệu giá")

    selected = features.reindex(signals).reset_index(drop=True)
    return selected.rename(columns={
        "Buy_Pct": "Điểm mua V1", "Sell_Pct": "Điểm bán V1",
        "V2_Buy_Pct": "Điểm mua V2", "V2_Sell_Pct": "Điểm bán V2",
        "V2_Trend_Buy": "V2 Xu hướng", "V2_Strength_Buy": "V2 Sức mạnh",
        "V2_Momentum_Buy": "V2 Động lượng", "V2_Flow_Buy": "V2 Dòng tiền",
        "V2_Reversal_Buy": "V2 Đảo chiều", "volume": "Khối lượng",
        "Vol_Avg": "Khối lượng TB", "close": "Giá đóng cửa tín hiệu",
    })


def _display_dates(frame):
    out = frame.copy()
    for col in (BUY_SIGNAL, BUY_DATE, "Ngày tín hiệu bán", SELL_DATE):
        if col in out.columns:
            out[col] = pd.to_datetime(out[col], utc=True).dt.strftime("%d/%m/%Y")
    return out


def phan_tich_giao_dich_v21(df, trades_v1, trades_v2):
    """Return (overview, V2 comparison, V2 losses, nonoverlapping V1 trades).

    Overlap is descriptive, not proof that signals/returns are equivalent.
    Only completed trades are considered; open positions are excluded.
    """
    v1 = _prepare(trades_v1, "V1")
    v2 = _prepare(trades_v2, "V2")
    v2["Phân loại đối chiếu"] = _classify(v2, v1, "V1")
    v1["Phân loại đối chiếu"] = _classify(v1, v2, "V2")

    v2["Lợi nhuận V1 (cùng ngày mua) (%)"] = v2["_buy"].map(
        v1.set_index("_buy")["_return"]
    )

    candle_index = pd.to_datetime(df.index, utc=True)
    if candle_index.has_duplicates or not candle_index.is_monotonic_increasing:
        raise ValueError("Dữ liệu giá không theo thứ tự thời gian")
    buy_pos = candle_index.get_indexer(v2["_buy"])
    sell_pos = candle_index.get_indexer(v2["_sell"])
    if (buy_pos < 0).any() or (sell_pos < 0).any():
        raise ValueError("Ngày khớp lệnh không nằm trong dữ liệu giá")
    v2["Số phiên nắm giữ"] = sell_pos - buy_pos

    indicators = _read_signal_features(df, v2["_signal"])
    v2 = pd.concat([v2, indicators], axis=1)

    loss_mask = v2["_return"] < 0
    total_loss = int(loss_mask.sum())
    overview = pd.DataFrame([
        ("Giao dịch V1 đã đóng", len(v1)),
        ("Giao dịch V2 đã đóng", len(v2)),
        ("V2 trùng ngày mua V1", int((v2["Phân loại đối chiếu"] == "Trùng ngày mua").sum())),
        ("V2 khác ngày mua (kể cả chồng lấn)", int((v2["Phân loại đối chiếu"] != "Trùng ngày mua").sum())),
        ("V2 khác ngày mua, chồng lấn V1", int((v2["Phân loại đối chiếu"] == "Khác ngày mua, chồng lấn vị thế").sum())),
        ("V2 không chồng lấn V1", int((v2["Phân loại đối chiếu"] == "Không chồng lấn V1").sum())),
        ("V1 không chồng lấn V2", int((v1["Phân loại đối chiếu"] == "Không chồng lấn V2").sum())),
        ("Số giao dịch V2 thua", total_loss),
        ("Lợi nhuận TB lệnh V2 thua (%)", round(float(v2.loc[loss_mask, "_return"].mean()), 2)
         if total_loss else None),
    ], columns=["Chỉ tiêu", "Kết quả"])

    shown = [
        BUY_SIGNAL, BUY_DATE, "Giá mua mô phỏng", "Ngày tín hiệu bán",
        SELL_DATE, "Giá bán mô phỏng", "Số phiên nắm giữ", NET_RETURN,
        "Lợi nhuận V1 (cùng ngày mua) (%)", "Phân loại đối chiếu",
        "Điểm mua V1", "Điểm bán V1", "Điểm mua V2", "Điểm bán V2",
        "V2 Xu hướng", "V2 Sức mạnh", "V2 Động lượng", "V2 Dòng tiền",
        "V2 Đảo chiều", "RSI", "ADX", "Plus_DI", "Minus_DI", "MACD",
        "Signal_Line", "SMA50", "SMA200", "MFI", "Khối lượng",
        "Khối lượng TB", "Giá đóng cửa tín hiệu", "Lý do bán",
    ]
    shown = [col for col in shown if col in v2.columns]
    comparison = _display_dates(v2[shown])
    losses = _display_dates(v2.loc[loss_mask].sort_values("_return")[shown])

    only_v1 = v1.loc[v1["Phân loại đối chiếu"] == "Không chồng lấn V2"]
    only_v1 = _display_dates(only_v1[[
        BUY_SIGNAL, BUY_DATE, SELL_DATE, NET_RETURN, "Phân loại đối chiếu"
    ]])
    return overview, comparison, losses, only_v1
