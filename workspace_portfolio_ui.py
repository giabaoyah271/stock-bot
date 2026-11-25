"""Compact portfolio view and integrated risk preview, original paper engine unchanged."""
import pandas as pd
import streamlit as st
from workspace_core import SECTIONS,PAGES,weights
from workspace_ui import account_setup,portfolio_metrics,jump,paper_backup,paper_record
from paper_trading_ui import ACCOUNT,error,render_risk,cash_text
from paper_trading_core import replay,performance,risk_preview,POLICY,readiness

def table(rows,empty):
    if len(rows): st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)
    else: st.info(empty)

def render_portfolio():
    st.title("Danh mục đầu tư")
    st.caption("Paper Trading nghiên cứu · Không đặt lệnh thật · Sao lưu JSON sau mỗi phiên")
    account=st.session_state.get(ACCOUNT)
    if not account:
        st.info("Chưa có tài khoản. Khởi tạo hoặc khôi phục để bắt đầu.")
        account_setup()
        return
    try: result=replay(account)
    except Exception as exc: error(exc);return
    portfolio_metrics(result)
    st.caption(f"Khóa cấu hình: {account['header']['frozen_at']} | Số phiên: {len(result['daily'])}")
    paper_backup(account,"pt09_port_backup")
    section=st.radio("Nội dung",SECTIONS,horizontal=True,key="pt09_port_section")
    if section=="Tổng quan":
        last=result["daily"][-1] if result["daily"] else None
        a,b,c=st.columns(3)
        a.metric("Lợi nhuận",f"{100*(result['equity']/POLICY.capital-1):+.2f}%")
        b.metric("P&L đã đóng",cash_text(last["P&L đã đóng"]) if last else "0 đ")
        c.metric("P&L mở",cash_text(last["P&L mở"]) if last else "0 đ")
        if last:
            st.caption("Phiên đã ghi cuối: "+last["Ngày"])
            st.line_chart(pd.DataFrame(result["daily"]).set_index("Ngày")[["Equity"]])
        else: st.info("Chưa ghi nhận phiên nào. Phiên đầu chỉ thu thập tín hiệu.")
        jump("Quét và ghi phiên mới",PAGES[1],"pt09_port_scan")
    elif section=="Vị thế":
        h,g=weights(result)
        st.subheader("Vị thế đang mở")
        table(h,"Chưa có vị thế.")
        if len(g):
            st.subheader("Tỷ trọng theo ngành tại Close")
            table(g,"Chưa có ngành.")
            st.bar_chart(g.set_index("Ngành")[["Tỷ trọng (%)"]])
            st.caption("Giới hạn tỷ trọng áp dụng tại thời điểm mua; biến động giá có thể làm tỷ trọng vượt ngưỡng sau đó.")
    elif section=="Cơ hội & rủi ro":
        st.subheader("Tín hiệu chờ phiên tiếp theo")
        table(result["pending"],"Chưa có tín hiệu chờ trong nhật ký.")
        candidates=[r for r in result["pending"] if r["Tín hiệu"]=="Mua mới dự kiến"]
        if candidates:
            selected=st.selectbox("Ước tính quy mô mua", [r["Mã"] for r in candidates],key="pt09_risk_symbol")
            row=next(r for r in candidates if r["Mã"]==selected)
            from universe_prepare_core import SECTORS
            h=result["holdings"]
            sector=sum(r["Giá trị Close"] for r in h if r["Ngành"]==SECTORS[selected])
            heat=sum(r["Rủi ro ban đầu"] for r in h)
            price=st.number_input("Open giả định (VND)",min_value=1.,value=float(row["Close"]),step=100.,key="pt09_risk_open_"+selected)
            try:
                plan=risk_preview(result["equity"],result["cash"],float(price),row["Close"],row["ATR"],sector,heat,len(h),any(r["Mã"]==selected for r in h))
                a,b,c=st.columns(3);a.metric("Khối lượng giả định",str(plan["qty"])+" CP");b.metric("Vốn mua",cash_text(plan["cost"]));c.metric("Rủi ro dự kiến",cash_text(plan["risk"]))
                st.caption(f"Stop tham chiếu: {cash_text(plan['reference'])} | {plan['reason'] or 'Ước tính từng mã riêng lẻ'}")
                st.caption("Dựa trên vốn và vị thế tại Close đã ghi, chưa biết Open thực tế và các lệnh bán/mua trước đó. Không cộng dồn các ước tính độc lập; hệ thống tính lại R1 khi ghi phiên tiếp theo.")
            except Exception as exc: error(exc)
        render_risk()
        jump("Mở bộ quét",PAGES[1],"pt09_risk_scan")
    elif section=="Nhật ký":
        for label,k in (("Lệnh mô phỏng","orders"),("Giao dịch đóng","trades")):
            st.subheader(label)
            table(result[k],"Chưa có bản ghi.")
            if result[k]:
                st.download_button("Tải CSV "+label,pd.DataFrame(result[k]).to_csv(index=False).encode("utf-8-sig"),f"stock_bot_paper_{k}.csv","text/csv",key="pt09_journal_"+k)
    elif section=="Hiệu suất":
        if not result["daily"]:
            st.info("Chưa có dữ liệu tiến tới để đánh giá hiệu suất.")
            return
        m=performance(result);a,b,c=st.columns(3)
        a.metric("Lợi nhuận",f"{m['Lợi nhuận (%)']:+.2f}%");b.metric("Drawdown tối đa",f"{m['MDD (%)']:.2f}%");c.metric("Lệnh đóng",m["Lệnh đóng"])
        d=pd.DataFrame(result["daily"]).set_index("Ngày")
        st.line_chart(d[["Equity"]]);st.line_chart(d[["Drawdown (%)"]])
        st.dataframe(pd.DataFrame([m]),hide_index=True,use_container_width=True)
        with st.expander("Chi tiết từng phiên"): st.dataframe(d,use_container_width=True)
        st.caption("Chỉ nhật ký đã ghi; CAGR/Calmar chưa tính trước một năm. Các chỉ số ít quan sát không chứng minh hiệu quả.")
