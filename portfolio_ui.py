"""On-demand shared-cash portfolio research, one fetch per symbol."""
import pandas as pd
import streamlit as st
from portfolio_core import CANDIDATES,MODES,Policy,prepare_signals,simulate_portfolio,SECTORS
from trade_diagnostics import completed_daily_history
from risk_batch import GROUPS,selected_symbols

def render_portfolio(get_data):
    st.markdown("**KT06 + KT07 – Danh mục vốn chung**")
    st.warning("Mô phỏng long-only, lô 100, không margin, không T+2. Bán trước mua tại cùng Open, giả định khớp đủ và tiền bán dùng ngay. Không phải giao dịch thật hoặc OOS. Giới hạn tỷ trọng/heat tại lúc mua, không cưỡng bức bán nếu giá biến động. DD 9% dừng mua mới; nếu tiền mặt hoàn toàn dưới đỉnh, R2 có thể dừng vô thời hạn.")
    st.caption("S0 dùng Stop tham chiếu Close tín hiệu - 2 ATR để sizing, chưa kích hoạt ngay. S2/S5 dùng Initial Stop tại Open mua. Heat là tổng rủi ro ban đầu các vị thế còn mở, không giảm theo trailing. R0 không áp trần rủi ro/lệnh và heat, để đối chiếu sizing.")
    with st.form("portfolio_form"):
        group=st.selectbox("Nhóm mã",tuple(k for k in GROUPS if k!="Tùy chỉnh"),key="pf_group")
        capital=st.number_input("Vốn ban đầu (VND)",min_value=10_000_000,max_value=10_000_000_000,value=100_000_000,step=10_000_000,key="pf_capital")
        units=st.radio("Đơn vị giá OHLC TCBS (kiểm tra giá mẫu trên phân tích chi tiết)",["Nghìn đồng (25.0 = 25.000 VND)","Đồng (25000 = 25.000 VND)"],key="pf_units")
        confirmed=st.checkbox("Tôi đã kiểm tra đơn vị giá nguồn",key="pf_confirm")
        modes=st.multiselect("Phương thức phân bổ",list(MODES),default=list(MODES),key="pf_modes")
        codes=st.multiselect("Tổ hợp",list(CANDIDATES),default=list(CANDIDATES),key="pf_codes")
        run=st.form_submit_button("Chạy Portfolio Backtesting",type="primary")
    if run:
        st.session_state.pop("pf_report",None)
        if not confirmed or not modes or not codes:
            st.error("Xác nhận đơn vị giá và chọn cấu hình/phương thức.")
        else:
            symbols=selected_symbols(group)
            policy=Policy(capital=float(capital),price_scale=1000 if units.startswith("Nghìn") else 1)
            histories={}
            errors=[]
            progress=st.progress(0,text="Đang tải dữ liệu...")
            for i,s in enumerate(symbols):
                try:
                    df,_=completed_daily_history(get_data(s,"Ngày"))
                    histories[s]=df
                except Exception as exc:
                    errors.append({"Mã":s,"Lỗi":type(exc).__name__})
                progress.progress((i+1)/len(symbols),text=f"Đã tải {s}")
            summary,curves,trades,audits,windows=[],[],[],[],[]
            if len(histories)==len(symbols):
                for i,code in enumerate(codes):
                    try:
                        signals=prepare_signals(histories,code)
                        for mode in modes:
                            try:
                                a,b,c,d,e=simulate_portfolio(signals,code,mode,policy)
                                summary.append(a)
                                for frame,target in [(b.reset_index(),curves),(c,trades),(d,audits),(e,windows)]:
                                    if not frame.empty:
                                        target.append(frame.assign(**{"Cấu hình":code,"Sizing":mode}))
                            except Exception as exc:
                                errors.append({"Cấu hình":code,"Sizing":mode,"Lỗi":type(exc).__name__})
                    except Exception as exc:
                        errors.append({"Cấu hình":code,"Lỗi":str(exc)[:150] if isinstance(exc,ValueError) else type(exc).__name__})
                    progress.progress((i+1)/len(codes),text=f"Đã xử lý {code}")
            else:
                st.error("Thiếu dữ liệu ít nhất một mã; dừng cả danh mục, không tự bỏ mã.")
            progress.empty()
            def join(frames):
                return pd.concat(frames,ignore_index=True) if frames else pd.DataFrame()
            st.session_state["pf_report"]={"summary":pd.DataFrame(summary),"curves":join(curves),"trades":join(trades),
                "orders":join(audits),"windows":join(windows),"errors":pd.DataFrame(errors),"total":len(codes)*len(modes),
                "symbols":symbols,"zero_volume":sum(int((d["volume"]==0).sum()) for d in histories.values()),
                "raw_prices":{s:float(d["close"].iloc[-1]) for s,d in histories.items()}}
    report=st.session_state.get("pf_report")
    if report is None: return
    st.caption(f"Hoàn thành {len(report['summary'])}/{report['total']} danh mục | Mã: {', '.join(report['symbols'])}")
    st.caption("Giá Close thô phiên cuối: "+", ".join(f"{s}={v:g}" for s,v in report["raw_prices"].items()))
    if report["zero_volume"]:
        st.warning(f"Có {report['zero_volume']} nến khối lượng 0. Mô hình giả định khớp tại Open, chưa mô phỏng thanh khoản/giá sàn.")
    summary=report["summary"]
    if not summary.empty:
        st.dataframe(summary.round(3),hide_index=True,use_container_width=True)
        curves=report["curves"].copy()
        curves["Tổ hợp"]=curves["Cấu hình"]+"-"+curves["Sizing"]
        chosen=st.multiselect("Biểu đồ danh mục",list(curves["Tổ hợp"].unique()),default=list(curves["Tổ hợp"].unique())[:3],key="pf_chart")
        if chosen:
            sub=curves[curves["Tổ hợp"].isin(chosen)]
            for col in ("Equity","Drawdown (%)","Exposure (%)"):
                st.line_chart(sub.pivot(index="Ngày",columns="Tổ hợp",values=col))
    for key,label in [("summary","tong_hop"),("curves","equity"),("trades","giao_dich"),("orders","lenh"),("windows","cua_so"),("errors","loi")]:
        frame=report[key]
        if not frame.empty:
            if key=="errors": st.dataframe(frame,hide_index=True,use_container_width=True)
            st.download_button(f"Tải CSV {label}",frame.to_csv(index=False).encode("utf-8-sig"),
                               f"stock_bot_portfolio_{label}.csv","text/csv",key=f"pf_download_{key}")
    st.caption("Phân ngành cố định phục vụ nghiên cứu: "+", ".join(f"{s}: {SECTORS[s]}" for s in report["symbols"]))
