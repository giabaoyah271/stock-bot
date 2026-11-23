"""Experimental daily equity section; original Backtesting UI stays intact."""

import pandas as pd
import streamlit as st

from risk_equity import STRATEGIES, calculate_equity_risk


def render_equity_panel(get_data, symbol):
    st.subheader("Thử nghiệm: Equity và Drawdown theo từng phiên")
    st.caption(
        "Chọn một mã và một chiến lược. Mô phỏng sử dụng TOÀN BỘ lịch sử ngày "
        "được tải, độc lập với bộ lọc giai đoạn của bảng Backtesting phía trên. "
        "Chỉ chạy khi bạn bấm nút."
    )
    choice = st.selectbox("Chiến lược kiểm tra rủi ro", STRATEGIES, key="risk_equity_strategy")
    if st.button("Tính Equity và Drawdown theo phiên", key="risk_equity_run"):
        try:
            with st.spinner(f"Đang phân tích {symbol} - {choice}..."):
                history = get_data(symbol, "Ngày")
                curve, metrics = calculate_equity_risk(history, choice)
                st.session_state["risk_equity_trial"] = {
                    "symbol": symbol,
                    "strategy": choice,
                    "curve": curve,
                    "metrics": metrics,
                }
        except Exception as exc:
            st.session_state.pop("risk_equity_trial", None)
            st.error(f"Không thể tính Equity theo phiên: {type(exc).__name__}")
            st.info("Khi tín hiệu không khớp Backtesting hiện tại, báo cáo sẽ dừng để tránh hiển thị sai.")

    report = st.session_state.get("risk_equity_trial")
    if not report or report["symbol"] != symbol or report["strategy"] != choice:
        st.info("Nhấn 'Tính Equity và Drawdown theo phiên' để xem kết quả.")
        return

    curve = report["curve"]
    metrics = report["metrics"]
    st.success("Đã đối chiếu thành công với nhật ký các lệnh đã đóng của Backtesting hiện tại.")
    st.dataframe(
        pd.DataFrame(list(metrics.items()), columns=["Chỉ tiêu", "Kết quả"]),
        hide_index=True,
        use_container_width=True,
    )
    st.markdown("**Đường cong Equity cuối phiên**")
    st.line_chart(curve["Equity"])
    st.markdown("**Drawdown theo từng phiên**")
    st.line_chart(curve["Drawdown (%)"])
    st.markdown("**10 phiên gần nhất**")
    st.dataframe(curve.tail(10).round(3), use_container_width=True)
    st.download_button(
        "Tải CSV Equity theo phiên",
        data=curve.to_csv(index_label="Ngày").encode("utf-8-sig"),
        file_name=f"equity_{symbol}_{STRATEGIES.index(choice) + 1}.csv",
        mime="text/csv",
        key="risk_equity_download",
    )
    st.caption(
        "Giả định toàn bộ vốn đầu tư vào một mã, được tái đầu tư và cho phép cổ phiếu lẻ; "
        "khớp tại giá mở cửa phiên kế tiếp, với phí/trượt giá/thuế như Backtesting gốc. "
        "Vị thế đang mở được định giá theo giá đóng cửa cuối, chưa giả định bán và chưa trừ phí bán. "
        "Thời gian dưới đỉnh được đo theo số PHIÊN. "
        "Chưa tính cổ tức, lãi tiền mặt, thanh khoản hay rủi ro gap ngoài giả định khớp lệnh. "
        "Đây là mô phỏng một mã, không phải kết quả danh mục đa mã hoặc kiểm định ngoài mẫu."
    )
