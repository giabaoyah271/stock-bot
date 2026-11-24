"""Opt-in batch risk report UI: no API calls on filter changes."""

import pandas as pd
import streamlit as st

from risk_batch import GROUPS, evaluate_risk_case, selected_symbols
from strategy_policy import CHOICES, RESEARCH_NOTE, resolve_strategies

SORT_OPTIONS = (
    "Theo mã và chiến lược", "Drawdown theo phiên xấu nhất trước",
    "Lợi nhuận theo phiên cao nhất trước",
)


def render_batch_risk(get_data):
    st.markdown("**Tổng hợp Equity và Drawdown đa mã**")
    st.caption(
        "Báo cáo theo TOÀN BỘ lịch sử giá khung Ngày (không theo khoảng thời gian "
        "chọn ở Backtesting phía dưới). Chỉ tính khi nhấn nút; mỗi mã lấy "
        "dữ liệu TCBS một lần qua cache hiện có."
    )
    st.caption(RESEARCH_NOTE)
    with st.form("batch_risk_form"):
        group = st.selectbox("Nhóm cổ phiếu", tuple(GROUPS), key="batch_risk_group")
        custom = st.text_input(
            "Mã tùy chỉnh (chỉ áp dụng khi chọn Tùy chỉnh)",
            value="HPG, MBB", key="batch_risk_custom",
        )
        choice = st.selectbox(
            "Chiến lược cần kiểm tra", CHOICES,
            key="batch_risk_strategy",
        )
        pressed = st.form_submit_button("Chạy tổng hợp rủi ro", type="primary")

    if pressed:
        st.session_state.pop("batch_risk_report", None)
        try:
            symbols = selected_symbols(group, custom)
        except ValueError as exc:
            st.error(str(exc))
        else:
            strategies = resolve_strategies(choice)
            count = len(symbols) * len(strategies)
            rows, failures, curves = [], [], {}
            completed = 0
            progress = st.progress(0, text="Bắt đầu tính rủi ro...")
            for symbol in symbols:
                try:
                    history = get_data(symbol, "Ngày")
                except Exception as exc:
                    history = None
                    download_error = type(exc).__name__
                else:
                    download_error = "Không có dữ liệu giá" if history is None or history.empty else None

                for strategy in strategies:
                    progress.progress(
                        completed / count,
                        text=f"Đang xử lý {symbol}: {strategy} ({completed + 1}/{count})",
                    )
                    if download_error:
                        failures.append({"Mã": symbol, "Chiến lược": strategy, "Lỗi": download_error})
                    else:
                        try:
                            row, curve = evaluate_risk_case(symbol, history, strategy)
                            rows.append(row)
                            curves[(symbol, strategy)] = curve
                        except Exception as exc:
                            detail = str(exc)[:150] if isinstance(exc, ValueError) else type(exc).__name__
                            failures.append({"Mã": symbol, "Chiến lược": strategy, "Lỗi": detail})
                    completed += 1
            progress.empty()
            st.session_state["batch_risk_report"] = {
                "rows": pd.DataFrame(rows),
                "failures": pd.DataFrame(failures),
                "curves": curves,
                "symbols": symbols,
                "strategies": strategies,
            }

    report = st.session_state.get("batch_risk_report")
    if report is None:
        st.info("Chọn nhóm mã và chiến lược, rồi nhấn 'Chạy tổng hợp rủi ro'.")
        return

    rows, failures = report["rows"], report["failures"]
    st.caption(
        f"Hoàn thành {len(rows)}/{len(report['symbols']) * len(report['strategies'])} "
        "trường hợp. Mỗi dòng là mô phỏng MỘT mã và MỘT chiến lược riêng biệt."
    )
    st.warning(
        "Đây là đánh giá hồi cứu bằng dữ liệu lịch sử, KHÔNG phải kiểm định ngoài mẫu "
        "độc lập hay lợi nhuận của danh mục 12 mã. Equity theo giá đóng cửa từng phiên; "
        "vị thế mở chưa trừ phí bán giả định. Drawdown theo lệnh đóng dùng lợi nhuận "
        "được làm tròn 0,01%; chênh lệch Drawdown tính theo độ sâu (điểm %). "
        "Profit Factor tính theo tiền lãi/lỗ các giao dịch đã đóng khi tái đầu tư toàn bộ vốn."
    )
    if not rows.empty:
        left, mid, right = st.columns(3)
        with left:
            selected_symbol = st.selectbox(
                "Lọc mã", ["Tất cả"] + list(dict.fromkeys(rows["Mã"])),
                key="batch_risk_filter_symbol",
            )
        with mid:
            selected_strategy = st.selectbox(
                "Lọc chiến lược", ["Tất cả"] + list(dict.fromkeys(rows["Chiến lược"])),
                key="batch_risk_filter_strategy",
            )
        with right:
            sort_by = st.selectbox("Sắp xếp", SORT_OPTIONS, key="batch_risk_sort")
        shown = rows.copy()
        if selected_symbol != "Tất cả":
            shown = shown.loc[shown["Mã"] == selected_symbol]
        if selected_strategy != "Tất cả":
            shown = shown.loc[shown["Chiến lược"] == selected_strategy]
        if sort_by == "Drawdown theo phiên xấu nhất trước":
            shown = shown.sort_values("Max Drawdown theo phiên (%)", ascending=True)
        elif sort_by == "Lợi nhuận theo phiên cao nhất trước":
            shown = shown.sort_values("Lợi nhuận theo phiên (%)", ascending=False)
        else:
            shown = shown.sort_values(["Mã", "Chiến lược"])
        st.dataframe(shown, hide_index=True, use_container_width=True)
        st.download_button(
            "Tải CSV tổng hợp rủi ro (toàn bộ kết quả)",
            data=rows.to_csv(index=False).encode("utf-8-sig"),
            file_name="stock_bot_rui_ro_da_ma.csv", mime="text/csv",
            key="batch_risk_export",
        )

        available = list(report["curves"].keys())
        descriptions = [f"{symbol} | {strategy}" for symbol, strategy in available]
        detail = st.selectbox("Xem Equity và Drawdown một trường hợp", descriptions, key="batch_risk_detail")
        curve = report["curves"][available[descriptions.index(detail)]]
        st.markdown("**Equity theo phiên (vốn ban đầu quy ước 100)**")
        st.line_chart(curve["Equity"])
        st.markdown("**Drawdown theo phiên (%)**")
        st.line_chart(curve["Drawdown (%)"])
        st.download_button(
            "Tải CSV đường cong đang xem",
            data=curve.to_csv(index_label="Ngày").encode("utf-8-sig"),
            file_name="stock_bot_equity_chi_tiet.csv", mime="text/csv",
            key="batch_risk_curve_export",
        )
    else:
        st.info("Không có trường hợp nào hoàn thành. Xem bảng lỗi bên dưới.")

    if not failures.empty:
        st.markdown("**Trường hợp lỗi hoặc thiếu dữ liệu**")
        st.dataframe(failures, hide_index=True, use_container_width=True)
