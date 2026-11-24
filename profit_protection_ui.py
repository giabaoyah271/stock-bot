"""On-demand KT13 batch. Only one daily data load per stock."""
import pandas as pd
import streamlit as st
from risk_batch import GROUPS,selected_symbols
from trade_diagnostics import completed_daily_history
from profit_protection_core import BASE_CODES,PROFITS,evaluate_profit_cases

ALL="Cả S0, S2, S5"

def render_profit_protection(get_data):
    st.markdown("**KT13 – Profit Protection (nghiên cứu độc lập)**")
    st.caption("Nền SMA50/SMA200. P0 đối chiếu KT03, so sánh từng P với P0 cùng nền và S0P0. Không thay đổi tín hiệu hiện tại.")
    st.warning("Kích hoạt theo lợi nhuận ròng tại Close, tính đủ phí/thuế/trượt giá giả định. Ngưỡng bảo vệ không giảm trong vị thế. Bán ở Open phiên sau, có thể lỗ do gap. P6 bổ sung trailing 1,5 ATR sau Close lãi 5%, không thay thế trailing gốc. Không phải OOS độc lập.")
    st.dataframe(pd.DataFrame([{"Profit":p.code,"Quy tắc":p.label} for p in PROFITS]),hide_index=True,use_container_width=True)
    with st.form("kt13_form"):
        group=st.selectbox("Nhóm cổ phiếu",tuple(GROUPS),key="kt13_group")
        custom=st.text_input("Mã tùy chỉnh","HPG, MBB",key="kt13_custom")
        base=st.selectbox("Nền Initial Stop",(ALL,)+BASE_CODES,key="kt13_base")
        run=st.form_submit_button("Chạy thử nghiệm Profit Protection",type="primary")
    if run:
        st.session_state.pop("kt13_report",None)
        try:
            symbols=selected_symbols(group,custom)
        except ValueError as exc:
            st.error(str(exc))
        else:
            bases=BASE_CODES if base==ALL else (base,)
            total=len(symbols)*len(bases)*len(PROFITS)
            rows,ledgers,windows,errors,curves=[],[],[],[],{}
            progress=st.progress(0,text="Đang phân tích KT13...")
            for i,symbol in enumerate(symbols):
                try:
                    df,_=completed_daily_history(get_data(symbol,"Ngày"))
                    a,b,c,d,e=evaluate_profit_cases(symbol,df,bases=bases)
                    rows.extend(a);ledgers.extend(b);windows.extend(c);errors.extend(d)
                    curves.update({(symbol,k):v for k,v in e.items()})
                except Exception as exc:
                    errors.append({"Mã":symbol,"Nền":"Tất cả","Profit":"Tất cả","Lỗi":type(exc).__name__})
                progress.progress((i+1)/len(symbols),text=f"Đã xử lý {symbol} ({i+1}/{len(symbols)})")
            progress.empty()
            st.session_state["kt13_report"]={"summary":pd.DataFrame(rows),
                 "trades":pd.concat(ledgers,ignore_index=True) if ledgers else pd.DataFrame(),
                 "windows":pd.DataFrame(windows),"errors":pd.DataFrame(errors),"curves":curves,"total":total,"config_count":len(bases)*len(PROFITS)}
    report=st.session_state.get("kt13_report")
    if report is None:
        return
    summary=report["summary"]
    st.caption(f"Hoàn thành {len(summary)}/{report['total']} trường hợp. Mỗi dòng là một mã, không phải danh mục.")
    if not summary.empty:
        st.markdown("**So sánh cấu hình (chỉ các mã có đủ cấu hình yêu cầu)**")
        # Require every requested configuration, even when a whole base fails.
        # Infer count from stored request rather than successful rows.
        complete_count=report.get("config_count",len(PROFITS))
        counts=summary.groupby("Mã")["Cấu hình"].transform("nunique")
        complete=summary.loc[counts==complete_count]
        if not complete.empty:
            comparison=complete.groupby(["Nền","Profit"],sort=False).agg(
                So_ma=("Mã","nunique"),LN_TB=("Lợi nhuận theo phiên (%)","mean"),
                MDD_TB=("Max Drawdown theo phiên (%)","mean"),
                Chenh_LN=("Chênh LN so P0 cùng nền (đpt)","mean"),
                Cai_thien_MDD=("Cải thiện MDD so P0 cùng nền (đpt)","mean"),
                PF_trung_vi=("Profit Factor","median"),So_lenh=("Số lệnh","sum"),
                Thang=("Số lệnh thắng","sum")).reset_index()
            comparison["Win Rate gộp (%)"]=100*comparison["Thang"]/comparison["So_lenh"].replace(0,float("nan"))
            st.dataframe(comparison.round(3),hide_index=True,use_container_width=True)
        else:
            st.warning("Không có mã đủ toàn bộ cấu hình để so sánh công bằng.")
        st.dataframe(summary.round(4),hide_index=True,use_container_width=True)
        keys=list(report["curves"])
        symbol=st.selectbox("Mã biểu đồ",list(dict.fromkeys(s for s,k in keys)),key="kt13_symbol")
        options=[k for s,k in keys if s==symbol]
        selected=st.multiselect("Cấu hình biểu đồ",options,default=[k for k in ("S0P0","S2P0","S2P5") if k in options] or options[:1],key="kt13_chart")
        if selected:
            for col in ("Equity","Drawdown (%)"):
                st.line_chart(pd.DataFrame({k:report["curves"][(symbol,k)][col] for k in selected if (symbol,k) in report["curves"]}))
    for key,label,filename in [
        ("summary","Tải CSV tổng hợp KT13","stock_bot_kt13_tong_hop.csv"),
        ("trades","Tải CSV chi tiết giao dịch KT13","stock_bot_kt13_giao_dich.csv"),
        ("windows","Tải CSV cửa sổ 6 tháng KT13","stock_bot_kt13_cua_so.csv"),
        ("errors","Tải CSV lỗi KT13","stock_bot_kt13_loi.csv")]:
        frame=report[key]
        if not frame.empty:
            if key=="errors":
                st.dataframe(frame,hide_index=True,use_container_width=True)
            st.download_button(label,frame.to_csv(index=False).encode("utf-8-sig"),filename,"text/csv",key=f"kt13_{key}")
    st.caption("Chênh MDD dương là giảm độ sâu. Đỉnh Close trừ LN khớp bán có thể âm nếu open bán cao hơn đỉnh close. Đối chiếu lệnh thắng/thua P0 theo ngày mua; thiếu lệnh đóng không đồng nghĩa thua. Dữ liệu hồi cứu đã xem.")
