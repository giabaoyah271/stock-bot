
import pandas as pd


def tao_bang_giao_dich(
    df,
    phi_mua=0.0015,
    phi_ban=0.0015,
    thue_ban=0.001,
    truot_gia=0.001
):
    """
    Mo phong giao dich theo tin hieu Stock Bot.
    Lenh duoc khop gia mo cua nen tiep theo.
    Cac muc chi phi chi la gia dinh co the dieu chinh.
    """

    required = {"open", "Trend"}

    if not required.issubset(df.columns):
        raise ValueError("Thieu cot open hoac Trend.")

    if not df.index.is_monotonic_increasing or df.index.has_duplicates:
        raise ValueError("Thoi gian bi trung hoac chua sap xep.")

    if df["open"].isna().any() or (df["open"] <= 0).any():
        raise ValueError("Gia mo cua khong hop le.")

    columns = [
        "Ngày tín hiệu mua",
        "Ngày mua mô phỏng",
        "Giá mua mô phỏng",
        "Ngày tín hiệu bán",
        "Ngày bán mô phỏng",
        "Giá bán mô phỏng",
        "Lợi nhuận sau chi phí (%)",
        "Lý do bán"
    ]

    results = []
    position = None

    for i in range(1, len(df) - 1):
        previous = df["Trend"].iloc[i - 1]
        current = df["Trend"].iloc[i]

        if previous == -1 and current == 1 and position is None:
            buy_price = float(df["open"].iloc[i + 1])
            buy_price *= (1 + truot_gia)

            position = (
                df.index[i],
                df.index[i + 1],
                buy_price
            )

        elif previous == 1 and current == -1 and position is not None:
            sell_price = float(df["open"].iloc[i + 1])
            sell_price *= (1 - truot_gia)

            net_return = (
                sell_price * (1 - phi_ban - thue_ban)
                / (position[2] * (1 + phi_mua)) - 1
            ) * 100

            reason = (
                str(df["Reason"].iloc[i])
                if "Reason" in df.columns else ""
            )

            results.append([
                position[0],
                position[1],
                round(position[2], 3),
                df.index[i],
                df.index[i + 1],
                round(sell_price, 3),
                round(net_return, 2),
                reason
            ])

            position = None

    return pd.DataFrame(results, columns=columns)
