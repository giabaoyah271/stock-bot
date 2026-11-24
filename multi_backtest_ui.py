"""Optional Streamlit page: on-demand multi-stock strategy comparisons."""

from datetime import date
import pandas as pd
import streamlit as st

from multi_backtest_core import (
    DEFAULT_SYMBOLS, evaluate_symbol, parse_symbols, period_dates,
)

from strategy_policy import GROUP_CHOICES, RESEARCH_NOTE, resolve_strategies

PERIOD_CHOICES = (
    "Toàn bộ dữ liệu", "2022–2024 (lịch sử)",
    "2025–2026 (lịch sử)", "Tùy chỉnh",
)


def render_multi_backtest(get_data):
    """Keep the app's TCBS connection and cached historical loader unchanged."""
    st.header("Backtesting đa mã và kiểm định chiến lược")
    st.caption(
        "Chỉ sử dụng khung Ngày. Chạy khi nhấn nút; dữ liệu lịch sử TCBS "
        "được tải qua cache có sẵn của Stock Bot. Không phát lệnh giao dịch."
    )

    with st.expander("Tổng hợp Equity và Drawdown đa mã (thử nghiệm)", expanded=False):
        from risk_batch_ui import render_batch_risk
        render_batch_risk(get_data)

    with st.expander("Walk-Forward Backtesting (kiểm định theo thời gian)", expanded=False):
        from walk_forward_ui import render_walk_forward
        render_walk_forward(get_data)

    with st.expander("KT01 + KT02 – Phân tích giao dịch và MAE/MFE", expanded=False):
        from trade_diagnostics_ui import render_trade_diagnostics
        render_trade_diagnostics(get_data)

    with st.expander("KT03 – Thử nghiệm Initial Stop Loss", expanded=False):
        from initial_stop_ui import render_initial_stop
        render_initial_stop(get_data)

    with st.expander("KT13 – Thử nghiệm Profit Protection", expanded=False):
        from profit_protection_ui import render_profit_protection
        render_profit_protection(get_data)

    with st.expander("KT06 + KT07 – Position Sizing và Portfolio Backtesting", expanded=False):
        from portfolio_ui import render_portfolio
        render_portfolio(get_data)

    st.caption(RESEARCH_NOTE)
    with st.form("multi_backtest_form"):
        symbols_text = st.text_area(
            "Mã cổ phiếu (phân tách bằng dấu phẩy)",
            value=DEFAULT_SYMBOLS,
            height=85,
        )
        strategy_group = st.selectbox("Nhóm chiến lược", GROUP_CHOICES, key="multi_strategy_group")
        chosen_period = st.selectbox("Giai đoạn đánh giá", PERIOD_CHOICES)
        left, right = st.columns(2)
        with left:
            start_date = st.date_input("Từ ngày (chỉ khi Tùy chỉnh)", value=date(2022, 1, 1))
        with right:
            end_date = st.date_input("Đến ngày (chỉ khi Tùy chỉnh)", value=date.today())
        submit = st.form_submit_button("Chạy Backtesting đa mã", type="primary")

    if submit:
        try:
            symbols = parse_symbols(symbols_text)
            label, start, end = period_dates(chosen_period, start_date, end_date)
            strategies = resolve_strategies(strategy_group)
        except ValueError as exc:
            st.error(str(exc))
        else:
            all_rows, all_errors = [], []
            progress = st.progress(0, text="Đang kiểm tra dữ liệu...")
            for i, symbol in enumerate(symbols):
                progress.progress(i / len(symbols), text=f"Đang phân tích {symbol} ({i + 1}/{len(symbols)})")
                try:
                    # Reuse the app's cached daily loader, not a new TCBS client.
                    historical = get_data(symbol, "Ngày")
                    rows, errors = evaluate_symbol(symbol, historical, label, start, end, strategies=strategies)
                    all_rows.extend(rows)
                    all_errors.extend(errors)
                except Exception as exc:
                    all_errors.append({
                        "Mã": symbol,
                        "Chiến lược": "Tải dữ liệu",
                        "Lỗi": type(exc).__name__,
                    })
            progress.empty()
            st.session_state["multi_backtest_report"] = {
                "symbols": symbols,
                "label": label,
                "strategies": strategies,
                "results": pd.DataFrame(all_rows),
                "errors": pd.DataFrame(all_errors),
            }

    report = st.session_state.get("multi_backtest_report")
    if report is None:
        st.info("Nhập danh sách mã rồi nhấn 'Chạy Backtesting đa mã' để xem báo cáo.")
        return

    st.subheader("Báo cáo Backtesting")
    st.caption("Chiến lược đã chạy: " + ", ".join(report.get("strategies", ())) )
    st.caption(f"Giai đoạn: {report['label']} | Mã yêu cầu: {', '.join(report['symbols'])}")
    st.warning(
        "Đây là phân tích lại dữ liệu lịch sử, KHÔNG phải kiểm định ngoài mẫu độc lập. "
        "Chỉ tính lệnh đã đóng và có ngày mua, ngày bán nằm hoàn toàn trong giai đoạn chọn. "
        "Lệnh giao ranh giới được đếm riêng, không tính vào chỉ tiêu. "
        "Vị thế chưa đóng không có trong Backtesting hiện hành."
    )
    st.caption(
        "Lợi nhuận tích lũy giả định tái đầu tư lần lượt theo các lệnh đã đóng của từng mã/chiến lược; "
        "sụt giảm vốn đo trên chuỗi lệnh đã đóng (không phải drawdown theo giá hằng ngày). "
        "Profit Factor tính theo số tiền lãi/lỗ của các lệnh đã đóng với tái đầu tư toàn bộ vốn, "
        "dựa trên lợi nhuận mỗi lệnh làm tròn 0,01%; để trống nếu không có lệnh lỗ. "
        "Các kết quả không đại diện danh mục đa mã."
    )

    results = report["results"]
    if results.empty:
        st.info("Không có chiến lược nào trả về kết quả hợp lệ.")
    else:
        st.dataframe(results, hide_index=True, use_container_width=True)
        st.download_button(
            "Tải CSV kết quả",
            data=results.to_csv(index=False).encode("utf-8-sig"),
            file_name="stock_bot_backtesting_da_ma.csv",
            mime="text/csv",
        )
        available = list(dict.fromkeys(results["Mã"].tolist()))
        selected = st.selectbox("Xem chi tiết một mã", available)
        st.dataframe(
            results.loc[results["Mã"] == selected].reset_index(drop=True),
            hide_index=True,
            use_container_width=True,
        )
        st.divider()
        from risk_equity_ui import render_equity_panel
        render_equity_panel(get_data, selected)

    errors = report["errors"]
    if not errors.empty:
        st.markdown("**Mã hoặc chiến lược chưa xử lý được**")
        st.dataframe(errors, hide_index=True, use_container_width=True)
