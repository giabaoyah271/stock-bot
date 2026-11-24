"""On-demand entry quality research, separate from live signals."""
import pandas as pd
import streamlit as st
from entry_filter_core import FILTERS,evaluate_entry_filters
from portfolio_core import Policy,CANDIDATES
from risk_batch import GROUPS,selected_symbols
from trade_diagnostics import completed_daily_history

def render_entry_filters(get_data):
    st.markdown("**KT14 + KT10 – Bộ lọc chất lượng điểm mua**")
    st.caption("R1, rủi ro 0,5%, 15%/mã, 25%/ngành, 5 vị thế, heat 2,5%. V0/A0 là đối chứng chung. 7 bộ lọc độc lập, không kết hợp/tối ưu tự động.")
    st.warning("Chỉ xét chỉ báo tại Close tín hiệu. Bỏ mua nếu không đạt; không mua bù trong cùng chu kỳ Trend. Không thay đổi chuỗi tín hiệu hoặc thoát lệnh KT13. Lãi/lỗ của tín hiệu bị loại là đối chứng hồi cứu, không phải P&L thực tế tránh được. Không phải OOS; giả định khớp Open như KT07.")
    st.dataframe(pd.DataFrame([{"Bộ lọc":f.code,"Điều kiện":f.label} for f in FILTERS]),hide_index=True,use_container_width=True)
    with st.form("entry_filter_form"):
        group=st.selectbox("Nhóm mã",tuple(k for k in GROUPS if k!="Tùy chỉnh"),key="ef_group")
        code=st.selectbox("Tổ hợp nền",CANDIDATES,key="ef_code")
        capital=st.number_input("Vốn ban đầu (VND)",min_value=10_000_000,max_value=10_000_000_000,value=100_000_000,step=10_000_000,key="ef_capital")
        units=st.radio("Đơn vị giá TCBS",["Nghìn đồng (25.0 = 25.000 VND)","Đồng (25000 = 25.000 VND)"],key="ef_units")
        confirmed=st.checkbox("Tôi đã kiểm tra đơn vị giá nguồn",key="ef_confirm")
        run=st.form_submit_button("Chạy thử nghiệm bộ lọc điểm mua",type="primary")
    if run:
        st.session_state.pop("ef_report",None)
        if not confirmed:
            st.error("Cần xác nhận đơn vị giá.")
        else:
            symbols=selected_symbols(group)
            policy=Policy(capital=float(capital),price_scale=1000 if units.startswith("Nghìn") else 1)
            histories={}
            errors=[]
            progress=st.progress(0,text="Đang tải dữ liệu...")
            for i,s in enumerate(symbols):
                try:
                    histories[s],_=completed_daily_history(get_data(s,"Ngày"))
                except Exception as exc:
                    errors.append({"Mã":s,"Lỗi":type(exc).__name__})
                progress.progress((i+1)/len(symbols),text=f"Đã xử lý {s}")
            progress.empty()
            if len(histories)==len(symbols):
                try:
                    report=evaluate_entry_filters(histories,code,policy)
                    report["symbols"]=symbols
                    st.session_state["ef_report"]=report
                except Exception as exc:
                    errors.append({"Cấu hình":code,"Lỗi":str(exc)[:160] if isinstance(exc,ValueError) else type(exc).__name__})
            if errors:
                st.error("Không hoàn thành danh mục; không tự bỏ mã.")
                st.dataframe(pd.DataFrame(errors),hide_index=True)
    report=st.session_state.get("ef_report")
    if report is None: return
    summary=report["summary"]
    st.caption(f"Hoàn thành {len(summary)}/{len(FILTERS)} danh mục | Mã: {', '.join(report['symbols'])}")
    if not summary.empty:
        st.dataframe(summary.round(4),hide_index=True,use_container_width=True)
        equity=report["equity"]
        chosen=st.multiselect("Bộ lọc biểu đồ",list(equity["Bộ lọc"].unique()),default=list(equity["Bộ lọc"].unique())[:3],key="ef_chart")
        if chosen:
            sub=equity[equity["Bộ lọc"].isin(chosen)]
            for col in ("Equity","Drawdown (%)","Exposure (%)"):
                st.line_chart(sub.pivot(index="Ngày",columns="Bộ lọc",values=col))
    for key,label in (("summary","tong_hop"),("equity","equity"),("trades","giao_dich"),("orders","lenh"),
                      ("windows","cua_so"),("diagnostics","tin_hieu"),("errors","loi")):
        frame=report[key]
        if not frame.empty:
            if key=="errors": st.dataframe(frame,hide_index=True,use_container_width=True)
            st.download_button(f"Tải CSV {label}",frame.to_csv(index=False).encode("utf-8-sig"),
                               f"stock_bot_entry_filter_{label}.csv","text/csv",key=f"ef_download_{key}")
    st.caption("LN/Exposure chỉ là tỷ số mô tả, không phải lợi nhuận danh mục chuẩn hóa theo rủi ro. Cần kiểm tra số lệnh, PF, Sharpe, MDD và cửa sổ thời gian cùng nhau.")
