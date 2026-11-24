"""KT08/09 Streamlit panel. TCBS index and stock loaders run only on demand."""
import pandas as pd
import streamlit as st
from market_research_core import BASES,CASES,load_index,evaluate_market
from portfolio_core import Policy
from risk_batch import GROUPS,selected_symbols
from trade_diagnostics import completed_daily_history

@st.cache_data(ttl=600)
def get_vnindex():
    from vnstock import Market
    return load_index(Market)

def render_market_research(get_data):
    st.markdown("**KT08 + KT09 – VN-Index và Relative Strength**")
    st.caption("S0P0-R1, nền A0/A4. 9 cấu hình độc lập mỗi nền. RS là chênh lệch lợi nhuận giá cổ phiếu và VN-Index, không phải RSI. RS4 chỉ đổi thứ tự mua, không thêm điều kiện RS dương.")
    st.warning("TCBS duy nhất, lịch phiên phải khớp hoàn toàn. Dùng Close tín hiệu, không dùng Open/Close tương lai để lọc hoặc xếp hạng. Không ép bán, không mua bù, không tối ưu tự động. VN-Index giá chỉ để tham chiếu, không tính cổ tức; không phải OOS.")
    st.dataframe(pd.DataFrame([{"Mã":c.code,"Quy tắc":c.label} for c in CASES]),hide_index=True,use_container_width=True)
    with st.form("market_research_form"):
        group=st.selectbox("Nhóm mã",tuple(k for k in GROUPS if k!="Tùy chỉnh"),key="mr_group")
        bases=st.multiselect("Nền Anti-chasing",list(BASES),default=list(BASES),key="mr_bases")
        capital=st.number_input("Vốn ban đầu (VND)",min_value=10_000_000,max_value=10_000_000_000,value=100_000_000,step=10_000_000,key="mr_capital")
        units=st.radio("Đơn vị giá cổ phiếu TCBS",["Nghìn đồng (25.0 = 25.000 VND)","Đồng (25000 = 25.000 VND)"],key="mr_units")
        confirmed=st.checkbox("Tôi đã kiểm tra đơn vị giá cổ phiếu",key="mr_confirm")
        run=st.form_submit_button("Chạy Market Regime và Relative Strength",type="primary")
    if run:
        st.session_state.pop("mr_report",None)
        if not confirmed or not bases:
            st.error("Xác nhận đơn vị giá và chọn ít nhất một nền.")
        else:
            symbols=selected_symbols(group)
            policy=Policy(capital=float(capital),price_scale=1000 if units.startswith("Nghìn") else 1)
            errors=[]
            try:
                index=get_vnindex()
                st.caption(f"TCBS VN-Index: {len(index)} phiên, {index.index[0]} – {index.index[-1]}")
            except Exception as exc:
                index=None
                errors.append({"Mã":"VNINDEX","Lỗi":type(exc).__name__})
            histories={}
            if index is not None:
                progress=st.progress(0,text="Đang tải dữ liệu cổ phiếu...")
                for i,s in enumerate(symbols):
                    try: histories[s],_=completed_daily_history(get_data(s,"Ngày"))
                    except Exception as exc: errors.append({"Mã":s,"Lỗi":type(exc).__name__})
                    progress.progress((i+1)/len(symbols),text=f"Đã xử lý {s}")
                progress.empty()
                if len(histories)==len(symbols):
                    try:
                        with st.spinner("Đang kiểm định danh mục..."):
                            report=evaluate_market(histories,index,policy,bases)
                        report["symbols"]=symbols
                        report["total"]=len(bases)*len(CASES)
                        st.session_state["mr_report"]=report
                    except Exception as exc:
                        errors.append({"Mã":"Danh mục","Lỗi":str(exc)[:200] if isinstance(exc,ValueError) else type(exc).__name__})
            if errors:
                st.error("Không hoàn thành kiểm định; không tự đổi nguồn hoặc bỏ mã. Kiểm tra TCBS/OTP/lịch phiên.")
                error_frame=pd.DataFrame(errors)
                st.dataframe(error_frame,hide_index=True)
                st.download_button("Tải CSV lỗi",error_frame.to_csv(index=False).encode("utf-8-sig"),"stock_bot_market_loi.csv","text/csv",key="mr_load_error")
    report=st.session_state.get("mr_report")
    if report is None: return
    summary=report["summary"]
    st.caption(f"Hoàn thành {len(summary)}/{report['total']} danh mục | Mã: {', '.join(report['symbols'])}")
    market=report["index"]
    st.caption(f"Nguồn TCBS VNINDEX | {len(market)} phiên | Close cuối: {market['VNINDEX Close'].iloc[-1]:.2f}")
    st.line_chart(market.set_index("Ngày")[["VNINDEX Close","VNINDEX SMA50","VNINDEX SMA200"]])
    if not summary.empty:
        st.dataframe(summary.round(4),hide_index=True,use_container_width=True)
        eq=report["equity"]
        options=list(eq["Tổ hợp"].unique())
        chosen=st.multiselect("Tổ hợp biểu đồ",options,default=[k for k in ("A0-M0/RS0","A4-M0/RS0") if k in options],key="mr_chart")
        if chosen:
            sub=eq[eq["Tổ hợp"].isin(chosen)]
            normalized=sub.pivot(index="Ngày",columns="Tổ hợp",values="Equity")
            normalized=100*normalized/normalized.iloc[0]
            normalized["VNINDEX (giá)"]=market.set_index("Ngày")["VNINDEX chuẩn hóa (100)"]
            st.line_chart(normalized)
            for col in ("Drawdown (%)","Exposure (%)"):
                st.line_chart(sub.pivot(index="Ngày",columns="Tổ hợp",values=col))
    for key,label in (("summary","tong_hop"),("equity","equity"),("trades","giao_dich"),("orders","lenh"),("windows","cua_so"),("diagnostics","tin_hieu"),("index","vnindex"),("errors","loi")):
        frame=report[key]
        if not frame.empty:
            if key=="errors": st.dataframe(frame,hide_index=True,use_container_width=True)
            st.download_button(f"Tải CSV {label}",frame.to_csv(index=False).encode("utf-8-sig"),f"stock_bot_market_{label}.csv","text/csv",key=f"mr_download_{key}")
    st.caption("Hạng RS và điểm mua được tính trên toàn bộ tín hiệu gốc cùng phiên. A4 vẫn có thể loại tín hiệu. P&L đối chứng bị loại không phải khoản lãi/lỗ tránh được thực tế. MDD thấp không đảm bảo sinh lời cao.")
