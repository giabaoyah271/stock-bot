"""PT03–PT08 UI. Explicit actions, no broker orders, no automatic persistence."""
import io,json,zipfile
import pandas as pd
import streamlit as st
from paper_trading_core import (
    POLICY,new_account,replay,append_session,export_account,import_account,
    snapshot_from_report,risk_preview,performance,readiness,local_now
)
from paper_acceptance import run_acceptance

ACCOUNT="pt0308_paper_account"
ACCEPT="pt0308_test_report"

def cash_text(v):
    return f"{v:,.0f} đ"

def error(exc):
    st.error(str(exc)[:450] if isinstance(exc,(ValueError,AssertionError,KeyError)) else type(exc).__name__)

def render_risk():
    with st.expander("PT03 – Risk Manager (tính thử độc lập)",expanded=False):
        st.caption("Nhập giả định bằng VND, không phải báo giá hay lệnh. Không thay đổi tài khoản.")
        with st.form("pt03_risk"):
            left,right=st.columns(2)
            with left:
                eq=st.number_input("Equity (VND)",min_value=1.,value=100000000.,step=1000000.)
                cash=st.number_input("Tiền mặt (VND)",min_value=0.,value=100000000.,step=1000000.)
                close=st.number_input("Close tín hiệu (VND)",min_value=1.,value=25000.,step=100.)
                atr=st.number_input("ATR (VND)",min_value=0.,value=750.,step=50.)
            with right:
                price=st.number_input("Open kế tiếp giả định (VND)",min_value=1.,value=25200.,step=100.)
                sector=st.number_input("Giá trị ngành đang nắm giữ (VND)",min_value=0.,value=0.,step=1000000.)
                heat=st.number_input("Rủi ro ban đầu còn mở (VND)",min_value=0.,value=0.,step=100000.)
                count=st.number_input("Số vị thế đang mở",min_value=0,max_value=5,value=0)
                held=st.checkbox("Đã sở hữu mã này")
            calc=st.form_submit_button("Tính thử R1")
        if calc:
            try:
                if cash>eq or sector>eq or cash+sector>eq+1e-6: raise ValueError("Tiền mặt/giá trị ngành vượt Equity")
                r=risk_preview(eq,cash,price,close,atr,sector,heat,int(count),held)
                st.metric("Khối lượng giả định",f"{r['qty']:,} CP")
                st.dataframe(pd.DataFrame([{"Stop tham chiếu":r["reference"],"Vốn mua gồm phí":r["cost"],"Rủi ro dự kiến":r["risk"],"Ngân sách":r["risk_budget"],"Lý do bỏ mua":r["reason"]}]),hide_index=True,use_container_width=True)
                st.caption("Stop tham chiếu dùng để sizing, không đảm bảo mức lỗ thực tế.")
            except Exception as exc: error(exc)

def acceptance_zip(test):
    b=io.BytesIO()
    with zipfile.ZipFile(b,"w",compression=zipfile.ZIP_DEFLATED) as z:
        def csv(name,rows):
            z.writestr("stock_bot_pt0308_"+name+".csv",pd.DataFrame(rows).to_csv(index=False).encode("utf-8-sig"))
        csv("kiem_thu",test["checks"])
        for k in ("daily","orders","trades","holdings","pending"): csv(k,test["result"][k])
        csv("hieu_suat",[test["metrics"]]);csv("san_sang",test["readiness"])
        z.writestr("stock_bot_pt0308_TEST_account.json",export_account(test["account"]))
        z.writestr("manifest.json",json.dumps({"mode":"TEST","source":"SYNTHETIC TEST","checks":len(test["checks"]),"passed":len(test["checks"]),"forward_evidence":False},ensure_ascii=False))
    return b.getvalue()

def render_acceptance():
    st.subheader("Nghiệm thu tích hợp PT03–PT08")
    st.caption("Chạy một lần, không cần TCBS, không cần ZIP nguồn. Dữ liệu giả lập 115 mã, 3 phiên, kiểm tra các nhánh mua/bán/bỏ mua, khôi phục nhật ký và chặn sai dữ liệu. Không ảnh hưởng tài khoản Paper.")
    if st.button("Chạy nghiệm thu PT03–PT08",type="primary",key="pt0308_accept"):
        st.session_state.pop(ACCEPT,None)
        try:
            test=run_acceptance()
            st.session_state[ACCEPT]={"checks":test["checks"],"zip":acceptance_zip(test)}
        except Exception as exc: error(exc)
    test=st.session_state.get(ACCEPT)
    if test:
        st.success(f"{len(test['checks'])}/{len(test['checks'])} kiểm tra tích hợp đạt (SYNTHETIC TEST).")
        st.dataframe(pd.DataFrame(test["checks"]),hide_index=True,use_container_width=True)
        st.download_button("Tải ZIP nghiệm thu",test["zip"],"stock_bot_pt0308_kiem_thu.zip","application/zip",key="pt0308_test_zip")

def render_portfolio():
    st.title("Danh mục & Nhật ký")
    st.warning("Paper Trading nghiên cứu, không gửi lệnh thật. Lưu tạm trong session Streamlit; tải JSON sau mỗi lần ghi phiên. Mất session hoặc khởi động lại Cloud có thể mất trạng thái nếu chưa tải bản sao.")
    render_acceptance()
    render_risk()
    st.subheader("PT04–PT05 – Tài khoản Paper Trading")
    account=st.session_state.get(ACCOUNT)
    with st.expander("Khởi tạo / khôi phục tài khoản",expanded=account is None):
        st.caption("Khởi tạo tài khoản mới = khóa cấu hình tại thời điểm bấm nút. Chỉ ghi phiên sau ngày khóa. Bắt đầu 100 triệu tiền mặt, không kế thừa vị thế từ Backtesting.")
        if account is None and st.button("Khởi tạo tài khoản Paper",key="pt05_create"):
            try: st.session_state[ACCOUNT]=new_account();st.rerun()
            except Exception as exc: error(exc)
        uploaded=st.file_uploader("Khôi phục JSON Paper mới nhất",type="json",key="pt05_upload")
        replace=st.checkbox("Tôi đã sao lưu tài khoản hiện có và muốn thay thế",key="pt05_replace") if account else True
        if st.button("Khôi phục nhật ký",key="pt05_restore",disabled=not replace):
            try:
                if uploaded is None: raise ValueError("Chọn file JSON Paper")
                st.session_state[ACCOUNT]=import_account(uploaded.getvalue());st.rerun()
            except Exception as exc: error(exc)
    if account is None:
        st.info("Chưa khởi tạo tài khoản Paper. Bạn có thể nghiệm thu tích hợp ở trên mà không cần khởi tạo.")
        return
    try: result=replay(account)
    except Exception as exc: error(exc);return
    st.caption(f"Khóa cấu hình: {account['header']['frozen_at']} | Số phiên đã ghi: {len(account['events'])} | Hash cuối: {result['last_hash'][:16]}…")
    a,b,c,d=st.columns(4)
    a.metric("Equity mô phỏng",cash_text(result["equity"]));b.metric("Tiền mặt",cash_text(result["cash"]));c.metric("Vị thế",f"{len(result['holdings'])}/5")
    d.metric("Heat còn mở",f"{result['daily'][-1]['Heat (%)']:.2f}%" if result["daily"] else "0%")
    st.download_button("Sao lưu JSON Paper (tải sau mỗi phiên)",export_account(account),"stock_bot_paper_account.json","application/json",key="pt05_backup")
    st.subheader("Ghi nhận phiên mới (PT07)")
    st.caption("Quét PT02 LIVE đủ 120 mã, 115 mã khớp mẫu, sau 15:15 hôm nay; không dùng ZIP TEST. Ghi nhận Open mô phỏng theo tín hiệu đã lưu ở phiên trước, sau khi phiên hiện tại kết thúc. Không phải giá khớp thực tế. Nếu thiếu phiên hoặc lịch sử sửa đổi, dừng để kiểm tra.")
    saved=st.session_state.get("pt02_report")
    if saved:
        st.write("Phiên PT02 đang lưu:",saved["identity"][0],"|",saved["identity"][-1],"|",len(saved["rows"]),"mã")
    else: st.info("Chưa có báo cáo PT02 trong session này.")
    confirm=st.checkbox("Tôi xác nhận chỉ ghi nhận mô phỏng phiên hôm nay, đã kiểm tra lịch phiên và dữ liệu TCBS",key="pt05_confirm")
    if st.button("Ghi phiên Paper",key="pt05_record",disabled=not confirm or not saved):
        try:
            if saved is None: raise ValueError("Thiếu PT02")
            event=snapshot_from_report(saved)
            updated=append_session(account,event)
            st.session_state[ACCOUNT]=updated
            st.rerun()
        except Exception as exc: error(exc)
    st.subheader("Vị thế mô phỏng")
    if result["holdings"]: st.dataframe(pd.DataFrame(result["holdings"]),hide_index=True,use_container_width=True)
    else: st.info("Chưa có vị thế mở.")
    st.subheader("Tín hiệu chờ Open tiếp theo")
    if result["pending"]: st.dataframe(pd.DataFrame(result["pending"]),hide_index=True,use_container_width=True)
    else: st.info("Chưa có tín hiệu chờ.")
    for label,key in (("Nhật ký lệnh","orders"),("Giao dịch đã đóng","trades")):
        st.subheader(label)
        if result[key]:
            frame=pd.DataFrame(result[key]);st.dataframe(frame,hide_index=True,use_container_width=True)
            st.download_button("Tải CSV "+label,frame.to_csv(index=False).encode("utf-8-sig"),f"stock_bot_paper_{key}.csv","text/csv",key="pt05_"+key)
        else: st.info("Chưa có bản ghi.")

def render_performance():
    st.title("Hiệu suất & Kiểm chứng")
    st.warning("Chỉ hiển thị nhật ký Paper đã ghi; không dùng Equity Backtesting làm kết quả thực tế. Không tự phê duyệt giao dịch tiền thật.")
    account=st.session_state.get(ACCOUNT)
    if not account:
        st.info("Chưa có tài khoản Paper. Vào Danh mục & Nhật ký để khởi tạo hoặc khôi phục.")
        return
    try: result=replay(account);m=performance(result);checks=readiness(result,"PAPER")
    except Exception as exc: error(exc);return
    a,b,c=st.columns(3);a.metric("Phiên đã ghi",m["Số phiên"]);b.metric("Lệnh đóng",m["Lệnh đóng"]);c.metric("Equity mô phỏng",cash_text(result["equity"]))
    st.subheader("PT06 – Hiệu suất")
    st.dataframe(pd.DataFrame([m]),hide_index=True,use_container_width=True)
    if result["daily"]:
        d=pd.DataFrame(result["daily"]).set_index("Ngày")
        st.line_chart(d[["Equity"]]);st.line_chart(d[["Drawdown (%)"]])
        st.dataframe(d,use_container_width=True)
    else: st.info("Chưa có phiên ghi nhận; không có đường Equity thực nghiệm.")
    st.subheader("PT07 – Forward Validation")
    st.write("Khóa cấu hình:",account["header"]["frozen_at"])
    st.caption("60 phiên và 30 lệnh đóng là ngưỡng đánh giá sơ bộ, không phải đủ an toàn. Nên tiếp tục 120–250+ phiên và đủ số giao dịch; không backfill, không đổi cấu hình giữa kỳ.")
    st.subheader("PT08 – Trading Readiness")
    st.error("Chưa phê duyệt giao dịch tiền thật.")
    st.dataframe(pd.DataFrame(checks),hide_index=True,use_container_width=True)
    st.caption("Các mục pháp lý, báo cáo tài chính, Free Float, thanh khoản thực tế, điều chỉnh giá, Monte Carlo và khớp lệnh cần xác minh độc lập. Không có nút bật giao dịch thật.")
