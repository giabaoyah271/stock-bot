"""On-demand KT03 research, no auto deployment of winning configuration."""
import pandas as pd
import streamlit as st

from risk_batch import GROUPS,selected_symbols
from strategy_policy import RESEARCH
from trade_diagnostics import completed_daily_history
from initial_stop_core import CONFIGS,evaluate_stop_cases

ALL="Cả 3 chiến lược nghiên cứu"

def render_initial_stop(get_data):
    st.markdown("**KT03 – Initial Stop Loss (nghiên cứu độc lập)**")
    st.caption("S0–S7 cố định trước khi chạy. Không tối ưu tự động và không thay đổi tín hiệu vận hành.")
    st.warning("Tín hiệu tại close; khớp open phiên sau, kể cả gap. Initial Stop theo open mua gốc, ATR tại tín hiệu mua. S2–S6 giữ trailing cũ; S7 kết hợp S6 và S1. Dữ liệu lịch sử đã được xem, không phải OOS độc lập.")
    st.dataframe(pd.DataFrame([{"Cấu hình":c.code,"Quy tắc":c.label} for c in CONFIGS]),hide_index=True,use_container_width=True)
    with st.form("kt03_form"):
        group=st.selectbox("Nhóm cổ phiếu",tuple(GROUPS),key="kt03_group")
        custom=st.text_input("Mã tùy chỉnh","HPG, MBB",key="kt03_custom")
        strategy=st.selectbox("Chiến lược nền",(RESEARCH[1],RESEARCH[0],RESEARCH[2],ALL),key="kt03_strategy")
        run=st.form_submit_button("Chạy thử nghiệm Initial Stop",type="primary")
    if run:
        st.session_state.pop("kt03_report",None)
        try:
            symbols=selected_symbols(group,custom)
        except ValueError as exc:
            st.error(str(exc))
        else:
            strategies=RESEARCH if strategy==ALL else (strategy,)
            rows,ledgers,windows,errors,curves=[],[],[],[],{}
            total=len(symbols)*len(strategies)*len(CONFIGS)
            done=0
            progress=st.progress(0,text="Đang kiểm định S0–S7...")
            for symbol in symbols:
                try:
                    data,_=completed_daily_history(get_data(symbol,"Ngày"))
                except Exception as exc:
                    data=None
                    error=type(exc).__name__
                for strat in strategies:
                    if data is None:
                        errors.append({"Mã":symbol,"Chiến lược":strat,"Cấu hình":"Tất cả","Lỗi":error})
                    else:
                        try:
                            a,b,c,d,e=evaluate_stop_cases(symbol,data,strat)
                            rows.extend(a);ledgers.extend(b);windows.extend(c);errors.extend(d)
                            curves.update({(symbol,strat,k):v for k,v in e.items()})
                        except Exception as exc:
                            errors.append({"Mã":symbol,"Chiến lược":strat,"Cấu hình":"Tất cả",
                                           "Lỗi":str(exc)[:120] if isinstance(exc,ValueError) else type(exc).__name__})
                    done+=len(CONFIGS)
                    progress.progress(done/total,text=f"Đã xử lý {symbol}: {strat}")
            progress.empty()
            st.session_state["kt03_report"]={"summary":pd.DataFrame(rows),
                 "trades":pd.concat(ledgers,ignore_index=True) if ledgers else pd.DataFrame(),
                 "windows":pd.DataFrame(windows),"errors":pd.DataFrame(errors),"curves":curves,"total":total}
    report=st.session_state.get("kt03_report")
    if report is None:
        return
    summary=report["summary"]
    st.caption(f"Hoàn thành {len(summary)}/{report['total']} trường hợp.")
    st.caption("MDD theo phiên có dấu âm (gần 0 tốt hơn); cải thiện MDD dương nghĩa là giảm độ sâu. Mỗi dòng dùng toàn vốn quy ước cho một mã, KHÔNG phải danh mục. S0 đối chiếu cả tín hiệu, ledger và Equity.")
    if not summary.empty:
        st.markdown("**Tổng hợp S0–S7 theo mã**")
        st.dataframe(summary.round(4),hide_index=True,use_container_width=True)
        st.download_button("Tải CSV tổng hợp KT03",summary.to_csv(index=False).encode("utf-8-sig"),
                           "stock_bot_kt03_tong_hop.csv","text/csv",key="kt03_summary")
        st.markdown("**So sánh theo cấu hình (trung bình các mã có đủ 8 cấu hình)**")
        counts=summary.groupby(["Mã","Chiến lược"])["Cấu hình"].transform("nunique")
        complete=summary.loc[counts==len(CONFIGS)]
        if not complete.empty:
            comparison=complete.groupby(["Chiến lược","Cấu hình"],sort=False).agg(
                So_ma=("Mã","nunique"),LN_TB=("Lợi nhuận theo phiên (%)","mean"),
                MDD_TB=("Max Drawdown theo phiên (%)","mean"),
                Chenh_LN=("Chênh LN so S0 (đpt)","mean"),Cai_thien_MDD=("Cải thiện MDD so S0 (đpt)","mean"),
                So_lenh=("Số lệnh","sum"),Thang=("Số lệnh thắng","sum")).reset_index()
            comparison["Win Rate gộp (%)"]=100*comparison["Thang"]/comparison["So_lenh"].replace(0,float("nan"))
            st.dataframe(comparison.round(3),hide_index=True,use_container_width=True)
        keys=list(report["curves"])
        pairs=list(dict.fromkeys((s,t) for s,t,k in keys))
        labels=[f"{s} | {t}" for s,t in pairs]
        chosen=st.selectbox("Xem Equity/Drawdown theo mã",labels,key="kt03_chart_case")
        pair=pairs[labels.index(chosen)]
        available=[k for s,t,k in keys if (s,t)==pair]
        selected=st.multiselect("Cấu hình biểu đồ",available,
                                default=[k for k in ("S0","S1") if k in available],key="kt03_chart_configs")
        if selected:
            for col in ["Equity","Drawdown (%)"]:
                chart=pd.DataFrame({k:report["curves"][(*pair,k)][col] for k in selected if (*pair,k) in report["curves"]})
                st.line_chart(chart)
    for key,label,filename in [
        ("trades","Tải CSV chi tiết giao dịch KT03","stock_bot_kt03_giao_dich.csv"),
        ("windows","Tải CSV cửa sổ 6 tháng KT03","stock_bot_kt03_cua_so.csv"),
        ("errors","Tải CSV lỗi KT03","stock_bot_kt03_loi.csv")]:
        frame=report[key]
        if not frame.empty:
            if key=="errors":
                st.dataframe(frame,hide_index=True,use_container_width=True)
            st.download_button(label,frame.to_csv(index=False).encode("utf-8-sig"),filename,"text/csv",key=f"kt03_{key}")
    st.caption("Lệnh thắng lớn của S0 (>=10%) được đối chiếu theo ngày khớp mua; không có lệnh đóng cùng ngày không đồng nghĩa thua lỗ. Cửa sổ 6 tháng chỉ là báo cáo hồi cứu, không tối ưu tham số.")
