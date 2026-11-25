"""KT18 private archive-based experiments, split LOO for Streamlit limits."""
import io,zipfile
import streamlit as st
from capacity_core import PARTS,read_kt17,evaluate_capacity
from full_universe_core import load_inputs

def render_capacity():
    st.caption("KT18: 22 kịch bản MAIN + 115 leave-one-out (LOO_ALL hoặc 5 lô × 23). Cố định A0-RS60; không đổi chỉ báo, không gọi TCBS.")
    st.warning("Nghiên cứu hồi cứu; danh mục chọn cuối kỳ, lịch sử rút ngắn, chưa xác minh pháp lý. Ngân sách rủi ro không phải mức lỗ tối đa. Walk-forward là chẩn đoán shadow, không phải ngoài mẫu độc lập.")
    files=[st.file_uploader(label,type="zip",key="kt18_"+key) for label,key in (
        ("KT15 – ZIP gốc","15"),("KT16 – ZIP gốc","16"),("U5-A – ZIP chuẩn bị 106 mã","a"),
        ("U5-B – ZIP chuẩn bị 115 mã","b"),("KT17 – ZIP đủ 40 kịch bản","17"))]
    part=st.selectbox("Phần kiểm định",PARTS,key="kt18_part")
    st.caption("Sau MAIN, chọn LOO_ALL để chạy đủ 115 kịch bản và xuất một ZIP. Nếu Cloud bị gián đoạn, dùng từng lô LOO1–LOO5. Không cần tải lại TCBS.")
    if part=="LOO_ALL":
        st.info("Chạy tuần tự 115 kịch bản, kiểm tra 4 đối chứng một lần. Giữ tab mở đến khi có báo cáo; nếu Cloud khởi động lại, dùng các lô nhỏ.")
    if st.button("Chạy KT18",type="primary",key="kt18_run"):
        st.session_state.pop("kt18_report",None)
        if any(x is None for x in files): st.error("Cần đủ 5 ZIP gốc.");return
        bar=st.progress(0,text="Xác minh dữ liệu và 4 đối chứng KT17...")
        try:
            a,b,c,d,e=[x.getvalue() for x in files]
            data=load_inputs(a,b,c,d);archive=read_kt17(e)
            report=evaluate_capacity(data,archive,part,progress=lambda i,n,s:bar.progress(i/n,text=f"{i}/{n}: {s}"))
            buf=io.BytesIO()
            with zipfile.ZipFile(buf,"w",compression=zipfile.ZIP_DEFLATED) as z:
                for k,f in report.items(): z.writestr("stock_bot_kt18_"+k+".csv",f.to_csv(index=False).encode("utf-8-sig"))
            st.session_state["kt18_report"]=(report["tong_hop"],report["loi"],report["pham_vi"],buf.getvalue(),part)
        except Exception as exc: st.error("KT18: "+(str(exc)[:500] if isinstance(exc,(ValueError,AssertionError)) else type(exc).__name__))
        finally: bar.empty()
    result=st.session_state.get("kt18_report")
    if result:
        su,err,meta,data,name=result
        st.dataframe(meta,hide_index=True,use_container_width=True)
        st.dataframe(su,hide_index=True,use_container_width=True)
        if len(err): st.error("Có lỗi, chưa nghiệm thu.");st.dataframe(err,hide_index=True)
        st.download_button("Tải ZIP KT18 "+name,data,f"stock_bot_kt18_{name}.zip","application/zip",key="kt18_download")
