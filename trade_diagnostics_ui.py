"""On-demand diagnostics, one cached daily request per ticker."""
import pandas as pd
import streamlit as st

from risk_batch import GROUPS, selected_symbols
from strategy_policy import RESEARCH
from trade_diagnostics import (
    completed_daily_history, evaluate_trade_case, RETURN, MAE, MFE, NET_MFE,
    GIVEBACK, CLASS, EXIT, HOLD, EARLY,
)

ALL = "Nhóm nghiên cứu chính (3 chiến lược)"

def render_trade_diagnostics(get_data):
    st.markdown("**KT01 + KT02 – Phân tích giao dịch đã đóng**")
    st.caption(
        "Chỉ khung Ngày, chỉ chạy khi bấm nút. Giữ nguyên tín hiệu, phí và khớp open phiên kế tiếp. "
        "V2/V2.1 không chạy ở đây. Không phải kiểm định ngoài mẫu hoặc chiến lược mới."
    )
    with st.form("trade_diagnostics_form"):
        group = st.selectbox("Nhóm cổ phiếu", tuple(GROUPS), key="td_group")
        custom = st.text_input("Mã tùy chỉnh", "HPG, MBB", key="td_custom")
        choice = st.selectbox("Chiến lược", (ALL,) + RESEARCH, key="td_strategy")
        run = st.form_submit_button("Chạy phân tích giao dịch", type="primary")
    if run:
        st.session_state.pop("td_report", None)
        try:
            symbols = selected_symbols(group, custom)
        except ValueError as e:
            st.error(str(e))
        else:
            strategies = RESEARCH if choice == ALL else (choice,)
            total = len(symbols)*len(strategies)
            progress = st.progress(0, text="Đang phân tích giao dịch...")
            details, summary, errors, trimmed = [], [], [], []
            done = 0
            for symbol in symbols:
                try:
                    df, cut = completed_daily_history(get_data(symbol,"Ngày"))
                    if cut:
                        trimmed.append(symbol)
                except Exception as e:
                    df = None
                    failure = type(e).__name__
                for strategy in strategies:
                    if df is None:
                        errors.append({"Mã":symbol,"Chiến lược":strategy,"Lỗi":failure})
                    else:
                        try:
                            rows, stats = evaluate_trade_case(symbol,df,strategy)
                            details.append(rows)
                            summary.append(stats)
                        except Exception as e:
                            errors.append({"Mã":symbol,"Chiến lược":strategy,
                                           "Lỗi":str(e)[:150] if isinstance(e,ValueError) else type(e).__name__})
                    done += 1
                    progress.progress(done/total, text=f"Đã xử lý {symbol}: {strategy} ({done}/{total})")
            progress.empty()
            st.session_state["td_report"] = {
                "details":pd.concat(details,ignore_index=True) if details else pd.DataFrame(),
                "summary":pd.DataFrame(summary),"errors":pd.DataFrame(errors),
                "total":total,"trimmed":trimmed,
            }
    report = st.session_state.get("td_report")
    if report is None:
        st.info("Chọn nhóm mã, chiến lược rồi nhấn Chạy phân tích giao dịch.")
        return
    summary, details = report["summary"], report["details"]
    st.caption(f"Hoàn thành {len(summary)}/{report['total']} trường hợp; {len(details)} lệnh đóng.")
    if report["trimmed"]:
        st.info("Đã loại nến ngày hiện tại chưa hoàn tất (trước 15:15 giờ Việt Nam): "+", ".join(report["trimmed"]))
    st.warning(
        "MAE/MFE giá dùng open mua gốc, high/low từ phiên mua đến trước phiên bán và chỉ open phiên bán. "
        "MFE ròng là giá cực trị quy đổi theo phí/trượt giá giả định, không phải mức lợi nhuận chắc chắn đạt được. "
        "Giveback là chênh lệch giữa MFE ròng và lợi nhuận ròng chưa làm tròn tại open bán. "
        "OHLC ngày không biết thứ tự high/low trong phiên; phân nhóm chỉ mô tả, không khẳng định nguyên nhân."
    )
    if not summary.empty:
        st.markdown("**Tổng hợp theo mã và chiến lược**")
        st.dataframe(summary, hide_index=True, use_container_width=True)
        st.download_button("Tải CSV tổng hợp chẩn đoán",summary.to_csv(index=False).encode("utf-8-sig"),
                           "stock_bot_trade_diagnostics_tong_hop.csv","text/csv",key="td_summary_csv")
    if not details.empty:
        st.markdown("**Chi tiết giao dịch**")
        st.download_button("Tải CSV toàn bộ giao dịch",details.to_csv(index=False).encode("utf-8-sig"),
                           "stock_bot_trade_diagnostics_chi_tiet.csv","text/csv",key="td_detail_csv")
        a,b,c = st.columns(3)
        with a:
            symbol = st.selectbox("Lọc mã",["Tất cả"]+list(details["Mã"].unique()),key="td_filter_symbol")
        with b:
            strategy = st.selectbox("Lọc chiến lược",["Tất cả"]+list(details["Chiến lược"].unique()),key="td_filter_strategy")
        with c:
            outcome = st.selectbox("Kết quả",["Tất cả","Lỗ","Lãi","Hòa vốn"],key="td_outcome")
        shown = details
        if symbol != "Tất cả":
            shown = shown.loc[shown["Mã"] == symbol]
        if strategy != "Tất cả":
            shown = shown.loc[shown["Chiến lược"] == strategy]
        if outcome != "Tất cả":
            mask = {"Lỗ":shown[RETURN]<0,"Lãi":shown[RETURN]>0,"Hòa vốn":shown[RETURN]==0}
            shown = shown.loc[mask[outcome]]
        if not shown.empty:
            st.dataframe(shown.sort_values(RETURN).round(4),hide_index=True,use_container_width=True)
            st.markdown("**MAE/MFE và lợi nhuận ròng**")
            st.scatter_chart(shown,x=MAE,y=MFE,color="Chiến lược")
            st.dataframe(shown.groupby([ "Chiến lược", CLASS],sort=False).size().rename("Số lệnh").reset_index(),
                         hide_index=True,use_container_width=True)
            st.dataframe(shown.groupby(["Chiến lược",EXIT],sort=False)[RETURN].agg(["count","mean"]).reset_index(),
                         hide_index=True,use_container_width=True)
        else:
            st.info("Không có giao dịch khớp bộ lọc.")
    elif not summary.empty:
        st.info("Các trường hợp hoàn thành chưa có lệnh đóng.")
    if not report["errors"].empty:
        st.markdown("**Trường hợp chưa xử lý được**")
        st.dataframe(report["errors"],hide_index=True,use_container_width=True)
        st.download_button("Tải CSV lỗi",report["errors"].to_csv(index=False).encode("utf-8-sig"),
                           "stock_bot_trade_diagnostics_loi.csv","text/csv",key="td_errors_csv")
