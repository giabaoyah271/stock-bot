"""On-demand KT11 panel, no changes to live strategy or old reports."""
import pandas as pd
import streamlit as st
from short_term_core import CASE_IDS,evaluate_short_term
from portfolio_core import Policy
from risk_batch import GROUPS,selected_symbols
from trade_diagnostics import completed_daily_history

def render_short_term(get_data):
    st.markdown("**KT11 – Chiến lược ngắn hạn độc lập**")
    st.caption("ST1 Pullback, ST2 Breakout, ST3 Mean Reversion × 4 cấu hình thoát. 12 thử nghiệm + đối chứng S0P0-R1-A4. R1 cố định; xếp hạng Buy_Pct cũ; không tối ưu.")
    st.warning("Chỉ dùng nến ngày hoàn tất. Stop kiểm tra Close, bán Open phiên sau, time stop tính từ phiên khớp mua. Không TP/trailing bổ sung. Tín hiệu bị bỏ mua vẫn theo chu kỳ giả định; không mua bù. Không T+2/margin, không đảm bảo MDD hoặc khoản lỗ. Hồi cứu, chưa kết hợp swing.")
    st.markdown("ST1: SMA20>SMA50, Close>SMA50, Low trước ≤ SMA20 trước, Close cắt lên SMA10 và tăng. ST2: Close>SMA50, vượt High 20 phiên trước không quá 5%, Volume ≥ 1,5 TB 20 phiên trước. ST3: Close>SMA200, SMA50>SMA200, RSI cắt lên 35, Close tăng. Cùng warmup 200 phiên, ATR dương, volume dương, cạnh lên của điều kiện.")
    with st.form("short_term_form"):
        group=st.selectbox("Nhóm mã",tuple(k for k in GROUPS if k!="Tùy chỉnh"),key="st11_group")
        capital=st.number_input("Vốn ban đầu (VND)",min_value=10_000_000,max_value=10_000_000_000,value=100_000_000,step=10_000_000,key="st11_capital")
        units=st.radio("Đơn vị giá TCBS",["Nghìn đồng (25.0 = 25.000 VND)","Đồng (25000 = 25.000 VND)"],key="st11_units")
        confirmed=st.checkbox("Tôi đã kiểm tra đơn vị giá nguồn",key="st11_confirm")
        run=st.form_submit_button("Chạy thử nghiệm Short-term Trading",type="primary")
    if run:
        st.session_state.pop("st11_report",None)
        if not confirmed: st.error("Cần xác nhận đơn vị giá.")
        else:
            symbols=selected_symbols(group)
            policy=Policy(capital=float(capital),price_scale=1000 if units.startswith("Nghìn") else 1)
            histories,errors={},[]
            progress=st.progress(0,text="Đang tải dữ liệu...")
            for i,s in enumerate(symbols):
                try: histories[s],_=completed_daily_history(get_data(s,"Ngày"))
                except Exception as exc: errors.append({"Mã":s,"Lỗi":type(exc).__name__})
                progress.progress((i+1)/len(symbols),text=f"Đã tải {s}")
            progress.empty()
            if len(histories)==len(symbols):
                try:
                    with st.spinner("Đang kiểm định 13 danh mục..."):
                        report=evaluate_short_term(histories,policy)
                    report["symbols"]=symbols
                    st.session_state["st11_report"]=report
                except Exception as exc:
                    errors.append({"Mã":"Danh mục","Lỗi":str(exc)[:180] if isinstance(exc,ValueError) else type(exc).__name__})
            if errors:
                st.error("Không hoàn thành; không tự bỏ mã.")
                frame=pd.DataFrame(errors)
                st.dataframe(frame,hide_index=True)
                st.download_button("Tải CSV lỗi",frame.to_csv(index=False).encode("utf-8-sig"),"stock_bot_kt11_loi.csv","text/csv",key="st11_load_error")
    report=st.session_state.get("st11_report")
    if report is None: return
    summary=report["summary"]
    st.caption(f"Hoàn thành {len(summary)}/{len(CASE_IDS)} danh mục | Mã: {', '.join(report['symbols'])}")
    if not summary.empty:
        st.dataframe(summary.round(4),hide_index=True,use_container_width=True)
        eq=report["equity"]
        options=list(eq["Cấu hình"].unique())
        chosen=st.multiselect("Danh mục biểu đồ",options,default=options[:3],key="st11_chart")
        if chosen:
            sub=eq[eq["Cấu hình"].isin(chosen)]
            for col in ("Equity","Drawdown (%)","Exposure (%)"):
                st.line_chart(sub.pivot(index="Ngày",columns="Cấu hình",values=col))
    for key,label in (("summary","tong_hop"),("equity","equity"),("trades","giao_dich"),("orders","lenh"),
                      ("windows","cua_so"),("independent","tin_hieu"),("stocks","theo_ma"),("errors","loi")):
        frame=report[key]
        if not frame.empty:
            if key=="errors": st.dataframe(frame,hide_index=True,use_container_width=True)
            st.download_button(f"Tải CSV {label}",frame.to_csv(index=False).encode("utf-8-sig"),
                               f"stock_bot_kt11_{label}.csv","text/csv",key=f"st11_download_{key}")
    st.caption("PF độc lập tính trên tổng tỷ lệ lợi nhuận lệnh, không phải PF tiền của danh mục. MAE/MFE dựa trên OHLC gốc, phiên bán chỉ lấy Open; không giả định khớp tại High/Low. Với đối chứng A4, tín hiệu độc lập bao gồm cả lệnh bị A4 loại; cột Lệnh/Lý do phân biệt.")
