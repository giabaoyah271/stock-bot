"""KT17 runs entirely from exact previously accepted local archives."""
import io,zipfile
import streamlit as st
from full_universe_core import GROUPS,load_inputs,evaluate

def render_full_universe():
    st.caption("KT17.1–17.7: U0=12, U4=31, U5-A=106, U5-B=115; U5 watchlist vẫn 120. Tái sử dụng ZIP gốc, không gọi TCBS.")
    st.warning("Mẫu lịch sử được chọn sau sự kiện, có ACV và 9 mã rút ngắn, 4 mã bỏ nến volume 0. Không phải kiểm định ngoài mẫu. Chưa xác minh pháp lý. Thanh khoản chỉ là proxy; không mô phỏng giới hạn giá, khớp lệnh thực tế hay T+2.")
    a=st.file_uploader("KT15 – stock_bot_kt15_bao_cao.zip",type="zip",key="kt17_15")
    b=st.file_uploader("KT16 – stock_bot_kt16_U4_U0_U1_U2_U3.zip",type="zip",key="kt17_16")
    c=st.file_uploader("U5-A – ZIP chuẩn bị 106 mã (bản đầu)",type="zip",key="kt17_a")
    d=st.file_uploader("U5-B – ZIP chuẩn bị 115 mã (bản (1))",type="zip",key="kt17_b")
    groups=st.multiselect("Nhóm chạy (chọn U5-B trước nếu Cloud giới hạn)",list(GROUPS),default=list(GROUPS),key="kt17_groups")
    common=st.checkbox("Bổ sung giai đoạn chung 33 phiên, khởi tạo tiền mặt mới",value=True,key="kt17_common")
    if st.button("Chạy KT17",type="primary",key="kt17_run"):
        st.session_state.pop("kt17_report",None)
        if not all(x is not None for x in (a,b,c,d)) or not groups:
            st.error("Cần đủ bốn ZIP gốc và ít nhất một nhóm.")
            return
        progress=st.progress(0,text="Xác minh ZIP, lịch, tín hiệu và đối chứng cũ...")
        try:
            data=load_inputs(a.getvalue(),b.getvalue(),c.getvalue(),d.getvalue())
            report=evaluate(data,tuple(groups),common,progress=lambda i,n,s:progress.progress(i/n,text=f"{i}/{n}: {s}"))
            buf=io.BytesIO()
            with zipfile.ZipFile(buf,"w",compression=zipfile.ZIP_DEFLATED) as z:
                for k,f in report.items(): z.writestr("stock_bot_kt17_"+k+".csv",f.to_csv(index=False).encode("utf-8-sig"))
            st.session_state["kt17_report"]=(report["tong_hop"],report["loi"],report["pham_vi"],buf.getvalue(),"_".join(groups))
        except Exception as exc:
            st.error("KT17: "+(str(exc)[:500] if isinstance(exc,(ValueError,AssertionError)) else type(exc).__name__))
        finally: progress.empty()
    saved=st.session_state.get("kt17_report")
    if saved:
        summary,errors,meta,data,name=saved
        st.dataframe(meta,hide_index=True,use_container_width=True)
        st.dataframe(summary,hide_index=True,use_container_width=True)
        if len(errors): st.error("Có kịch bản lỗi; không nghiệm thu đầy đủ.");st.dataframe(errors,hide_index=True)
        st.download_button("Tải ZIP KT17",data,f"stock_bot_kt17_{name}.zip","application/zip",key="kt17_download")
