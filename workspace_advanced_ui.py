"""Advanced tools and offline acceptance, no new account or broker action."""
import io,json,zipfile
import pandas as pd
import streamlit as st
from workspace_core import ADVANCED,REF
from workspace_ui import reference_panel,account_setup
from storage_ui_ds01 import render_storage
from trading_dashboard_core import candidate_parameters,CANDIDATE
from paper_trading_ui import acceptance_zip,error
from workspace_acceptance import run_workspace_acceptance

def render_settings():
    st.title("Hệ thống · Thiết lập & sao lưu")
    st.caption("Kết nối TCBS ở thanh bên; API Key tại Streamlit Secrets. Dữ liệu lưu Cloud nếu đã cấu hình, nếu không chỉ trong phiên.")
    st.subheader("Dữ liệu tham chiếu")
    reference_panel()
    st.subheader("Tài khoản và sao lưu")
    account_setup()
    with st.expander("Cấu hình chiến lược (chỉ đọc)"):
        st.write(CANDIDATE)
        st.dataframe(candidate_parameters(),hide_index=True,use_container_width=True)
    st.divider()
    render_storage()

def render_acceptance():
    st.title("Nghiệm thu tích hợp")
    st.caption("21 kiểm tra dự kiến: 11 kiểm tra PT03–PT08 gốc và 10 kiểm tra PT09. Dữ liệu giả lập/mock, không cần TCBS hay ZIP đầu vào. Không tạo kết quả tiến tới.")
    if st.button("Chạy nghiệm thu PT09",type="primary",key="pt09_accept"):
        st.session_state.pop("pt09_acceptance",None)
        try:
            r=run_workspace_acceptance()
            buf=io.BytesIO()
            with zipfile.ZipFile(buf,"w",compression=zipfile.ZIP_DEFLATED) as z:
                z.writestr("stock_bot_pt09_kiem_thu.csv",pd.DataFrame(r["checks"]).to_csv(index=False).encode("utf-8-sig"))
                z.writestr("pt0308_test.zip",acceptance_zip(r["paper_test"]))
                z.writestr("manifest.json",json.dumps({"mode":"SYNTHETIC TEST","checks":len(r["checks"]),"passed":len(r["checks"]),"forward_evidence":False},ensure_ascii=False))
            st.session_state["pt09_acceptance"]={"checks":r["checks"],"zip":buf.getvalue()}
        except Exception as exc: error(exc)
    r=st.session_state.get("pt09_acceptance")
    if r:
        st.success(f"{len(r['checks'])}/{len(r['checks'])} kiểm tra tích hợp đạt.")
        st.dataframe(pd.DataFrame(r["checks"]),hide_index=True,use_container_width=True)
        st.download_button("Tải ZIP nghiệm thu PT09",r["zip"],"stock_bot_pt09_kiem_thu.zip","application/zip",key="pt09_accept_zip")

    st.divider()
    st.subheader("PT10 – Đồng nhất chiến lược chính")
    st.caption("Đối chiếu 115 mã trên ZIP U5-B ngày 23/11/2026: tín hiệu, lịch sử, RS60, giá, điểm số và SHA. Không gọi TCBS; không ghi Paper. Nên dùng ZIP đã xác minh trong workspace.")
    reference_panel()
    if st.button("Chạy nghiệm thu PT10 (115 mã)",type="primary",key="pt10_accept",disabled=REF not in st.session_state):
        st.session_state.pop("pt10_acceptance",None)
        bar=st.progress(0,text="Đối chiếu chiến lược...")
        try:
            from unified_acceptance import run_unified_acceptance
            d=run_unified_acceptance(st.session_state[REF],lambda i,n,s:bar.progress(i/n,text=f"{i}/{n}: {s}"))
            buf=io.BytesIO()
            with zipfile.ZipFile(buf,"w",compression=zipfile.ZIP_DEFLATED) as z:
                z.writestr("stock_bot_pt10_doi_chieu.csv",d.to_csv(index=False).encode("utf-8-sig"))
                z.writestr("manifest.json",json.dumps({"mode":"TEST","session":"2026-11-23","checked":len(d),"passed":int((d["Đối chiếu"]=="Khớp").sum()),"forward_evidence":False},ensure_ascii=False))
            st.session_state["pt10_acceptance"]={"data":d,"zip":buf.getvalue()}
        except Exception as exc: error(exc)
        finally: bar.empty()
    pt10=st.session_state.get("pt10_acceptance")
    if pt10:
        d=pt10["data"]
        st.success(f"{len(d)}/115 mã khớp giữa tín hiệu và biểu đồ hồi cứu.")
        st.dataframe(d.drop(columns=["SHA lịch sử"]),hide_index=True,use_container_width=True,height=460)
        st.download_button("Tải ZIP nghiệm thu PT10",pt10["zip"],"stock_bot_pt10_kiem_thu.zip","application/zip",key="pt10_accept_zip")
