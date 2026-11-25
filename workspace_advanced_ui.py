"""Advanced tools and offline acceptance, no new account or broker action."""
import io,json,zipfile
import pandas as pd
import streamlit as st
from workspace_core import ADVANCED
from workspace_ui import reference_panel,account_setup
from trading_dashboard_core import candidate_parameters,CANDIDATE
from paper_trading_ui import acceptance_zip,error
from workspace_acceptance import run_workspace_acceptance

def render_settings():
    st.title("Cài đặt & Nghiên cứu")
    st.subheader("Dữ liệu tham chiếu")
    reference_panel()
    st.subheader("Tài khoản và sao lưu")
    account_setup()
    with st.expander("Cấu hình chiến lược (chỉ đọc)"):
        st.write(CANDIDATE)
        st.dataframe(candidate_parameters(),hide_index=True,use_container_width=True)
    st.caption("Kết nối TCBS ở thanh bên. Không có lưu trữ lâu dài trên Cloud; lưu JSON riêng tư. Không tự kết nối dịch vụ ngoài.")

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
