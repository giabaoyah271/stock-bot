"""Opt-in Streamlit UI for fixed-strategy historical Walk-Forward diagnostics."""
from datetime import datetime, time
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from risk_batch import GROUPS, selected_symbols
from risk_equity import STRATEGIES
from walk_forward_core import evaluate_walk_forward_case, half_year_windows


ALL = "Tất cả 5 chiến lược"


def _comparison(summary):
    if summary.empty:
        return pd.DataFrame()
    groups = []
    for name, g in summary.groupby("Chiến lược", sort=False):
        groups.append({
            "Chiến lược": name,
            "Số mã đã kiểm tra": int(g["Mã"].nunique()),
            "Tổng lệnh đóng giai đoạn": int(g["Số lệnh đóng giai đoạn đánh giá"].sum()),
            "LN đánh giá trung vị (%)": round(float(g["Lợi nhuận giai đoạn đánh giá (%)"].median()), 2),
            "MDD đánh giá trung vị (%)": round(float(g["Max Drawdown giai đoạn đánh giá (%)"].median()), 2),
            "Tỷ lệ cửa sổ có lãi TB (%)": round(float(g["Tỷ lệ cửa sổ có lãi (%)"].mean()), 1),
        })
    return pd.DataFrame(groups)


def _chart(series, title, boundaries):
    """Plot Vietnam-local dates without timezone comparison conflicts."""
    index = series.index
    if isinstance(index, pd.DatetimeIndex) and index.tz is not None:
        index = index.tz_convert("Asia/Ho_Chi_Minh").tz_localize(None)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=index, y=series.values, mode="lines", name=title))
    days = index.normalize()
    for window in boundaries:
        if days.min() <= window.start <= days.max():
            # add_shape is safe for datetime axes across supported Plotly builds.
            at = window.start.to_pydatetime()
            fig.add_shape(type="line", xref="x", yref="paper",
                          x0=at, x1=at, y0=0, y1=1,
                          line=dict(color="gray", width=1, dash="dot"))
    fig.update_layout(xaxis_title="Phiên", yaxis_title=title,
                      margin=dict(l=10, r=10, t=12, b=10),
                      height=330, showlegend=False)
    return fig

def render_walk_forward(get_data):
    st.markdown("**Walk-Forward Backtesting (kiểm định theo thời gian)**")
    st.warning(
        "Phân tích hồi cứu theo các cửa sổ 6 tháng với chiến lược CỐ ĐỊNH. "
        "Không tối ưu tham số, không phải kiểm định ngoài mẫu nguyên sơ. "
        "Đường Equity được mô phỏng một lần liên tục; cửa sổ chỉ dùng để báo cáo."
    )
    st.caption(
        "2022–2023: lịch sử nền. WF1 bắt đầu 01/2024; các cửa sổ sau kéo dài 6 tháng. "
        "Vị thế được mang qua ranh giới; lệnh đóng được ghi vào cửa sổ chứa ngày khớp bán. "
        "Lợi nhuận cửa sổ tính từ Equity cuối phiên trước cửa sổ (nếu có), "
        "bao gồm biến động phiên đầu cửa sổ."
    )
    with st.form("walk_forward_run_form"):
        group = st.selectbox("Nhóm cổ phiếu", tuple(GROUPS), key="wf_group")
        custom = st.text_input("Mã tùy chỉnh (khi chọn Tùy chỉnh)", value="HPG, MBB", key="wf_custom")
        choice = st.selectbox("Chiến lược", (ALL,) + STRATEGIES, key="wf_strategy")
        run = st.form_submit_button("Chạy Walk-Forward", type="primary")

    if run:
        st.session_state.pop("walk_forward_report", None)
        try:
            symbols = selected_symbols(group, custom)
        except ValueError as e:
            st.error(str(e))
        else:
            strategies = list(STRATEGIES) if choice == ALL else [choice]
            count = len(symbols) * len(strategies)
            rows, summary, errors, charts = [], [], [], {}
            completed = 0
            trimmed = []
            progress = st.progress(0, text="Bắt đầu Walk-Forward...")
            for symbol in symbols:
                try:
                    history = get_data(symbol, "Ngày")
                    if history is None or history.empty:
                        raise ValueError("Không có dữ liệu lịch sử")
                    # Avoid an in-progress bar without fetching data again.
                    vn_now = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
                    last_stamp = pd.Timestamp(history.index[-1])
                    if last_stamp.tz is not None:
                        last_stamp = last_stamp.tz_convert("Asia/Ho_Chi_Minh")
                    if (last_stamp.date() == vn_now.date()
                            and vn_now.time() < time(15, 15)):
                        history = history.iloc[:-1].copy()
                        trimmed.append(symbol)
                    if history.empty:
                        raise ValueError("Không có phiên đã hoàn tất")
                    download_error = None
                except Exception as e:
                    history = None
                    download_error = str(e)[:140] if isinstance(e, ValueError) else type(e).__name__
                for strategy in strategies:
                    progress.progress(completed / count, text=f"{symbol}: {strategy} ({completed + 1}/{count})")
                    if download_error:
                        errors.append({"Mã": symbol, "Chiến lược": strategy, "Cửa sổ": "Dữ liệu",
                                       "Lỗi": download_error})
                    else:
                        try:
                            sliced, aggregate, missing, curve = evaluate_walk_forward_case(
                                symbol, history, strategy)
                            rows.extend(sliced)
                            summary.append(aggregate)
                            errors.extend(missing)
                            # Two series only; supports changing the selected chart without recomputation.
                            charts[(symbol, strategy)] = curve
                        except Exception as e:
                            errors.append({"Mã": symbol, "Chiến lược": strategy, "Cửa sổ": "Phân tích",
                                           "Lỗi": str(e)[:140] if isinstance(e, ValueError) else type(e).__name__})
                    completed += 1
            progress.empty()
            st.session_state["walk_forward_report"] = {
                "rows": pd.DataFrame(rows), "summary": pd.DataFrame(summary),
                "errors": pd.DataFrame(errors), "curves": charts,
                "symbols": symbols, "strategies": strategies,
                "trimmed": trimmed,
            }

    report = st.session_state.get("walk_forward_report")
    if report is None:
        st.info("Chọn nhóm mã, chiến lược rồi nhấn 'Chạy Walk-Forward' để bắt đầu.")
        return
    rows, summary, errors = report["rows"], report["summary"], report["errors"]
    st.caption(
        f"Hoàn thành {len(summary)}/{len(report['symbols']) * len(report['strategies'])} "
        "trường hợp mã/chiến lược. Một trường hợp có nhiều dòng cửa sổ."
    )
    if report["trimmed"]:
        st.info("Đã bỏ nến ngày hiện tại chưa hoàn tất: " + ", ".join(report["trimmed"]))
    if not rows.empty:
        st.markdown("**Kết quả theo cửa sổ**")
        a, b, c = st.columns(3)
        with a:
            symbol = st.selectbox("Lọc mã", ["Tất cả"] + list(dict.fromkeys(rows["Mã"])), key="wf_filter_symbol")
        with b:
            strategy = st.selectbox("Lọc chiến lược", ["Tất cả"] + list(dict.fromkeys(rows["Chiến lược"])), key="wf_filter_strategy")
        with c:
            window = st.selectbox("Lọc cửa sổ", ["Tất cả"] + list(dict.fromkeys(rows["Cửa sổ"])), key="wf_filter_window")
        show = rows
        if symbol != "Tất cả":
            show = show.loc[show["Mã"] == symbol]
        if strategy != "Tất cả":
            show = show.loc[show["Chiến lược"] == strategy]
        if window != "Tất cả":
            show = show.loc[show["Cửa sổ"] == window]
        st.dataframe(show, hide_index=True, use_container_width=True)
        st.download_button("Tải CSV kết quả từng cửa sổ", rows.to_csv(index=False).encode("utf-8-sig"),
                           "stock_bot_walk_forward_cua_so.csv", "text/csv", key="wf_csv_windows")
        st.markdown("**Tổng hợp theo mã và chiến lược**")
        st.dataframe(summary, hide_index=True, use_container_width=True)
        st.download_button("Tải CSV tổng hợp theo mã", summary.to_csv(index=False).encode("utf-8-sig"),
                           "stock_bot_walk_forward_tong_hop.csv", "text/csv", key="wf_csv_aggregate")
        comparison = _comparison(summary)
        st.markdown("**So sánh chiến lược trên các mã đã kiểm tra**")
        st.dataframe(comparison, hide_index=True, use_container_width=True)
        st.download_button("Tải CSV so sánh chiến lược", comparison.to_csv(index=False).encode("utf-8-sig"),
                           "stock_bot_walk_forward_so_sanh.csv", "text/csv", key="wf_csv_compare")
        st.caption(
            "Profit Factor tính theo TIỀN của các giao dịch đóng trong cửa sổ, "
            "kể cả lệnh bắt đầu trước cửa sổ. Vì vậy PF theo ngày đóng có thể "
            "khác dấu với lợi nhuận Equity của cùng cửa sổ. "
            "MDD cục bộ lấy Equity ranh giới đầu làm mốc; MDD so đỉnh toàn kỳ "
            "giữ đỉnh vốn từ trước năm 2024."
        )
        options = list(report["curves"])
        names = [f"{symbol} | {strategy}" for symbol, strategy in options]
        selected = st.selectbox("Xem biểu đồ một trường hợp", names, key="wf_chart_case")
        curve = report["curves"][options[names.index(selected)]]
        boundaries = half_year_windows(curve.index[-1])
        st.markdown("**Equity liên tục (đường chấm = ranh giới cửa sổ)**")
        st.plotly_chart(_chart(curve["Equity"], "Equity", boundaries), use_container_width=True)
        st.markdown("**Drawdown theo phiên (%)**")
        st.plotly_chart(_chart(curve["Drawdown (%)"], "Drawdown (%)", boundaries), use_container_width=True)
        st.download_button("Tải CSV đường Equity đang xem", curve.to_csv(index_label="Ngày").encode("utf-8-sig"),
                           "stock_bot_walk_forward_equity.csv", "text/csv", key="wf_csv_curve")
    else:
        st.info("Không có kết quả hợp lệ. Xem bảng lỗi bên dưới.")
    if not errors.empty:
        st.markdown("**Lỗi hoặc cửa sổ không có dữ liệu**")
        st.dataframe(errors, hide_index=True, use_container_width=True)
