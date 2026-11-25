"""KT17.0 batch audit on demand, no live trading and no automatic exclusions."""
import io
import json
import time
import zipfile
import pandas as pd
import streamlit as st
from universe_u5 import U5,U5_VERSION,BATCHES
from universe_audit_core import reference_calendar,audit_one,manifest
from market_research_ui import get_vnindex

def render_universe_audit(get_data):
    st.markdown("**KT17.0 – Sàng lọc U5 (120 mã đã chốt)**")
    st.caption("Danh sách ứng viên cố định "+U5_VERSION+"; giữ nguyên các nhóm KT01–KT16. Đánh giá lịch sử đến 23/11/2026. Chưa phải danh sách đã được phê duyệt mua.")
    st.warning("Kiểm tra kỹ thuật không thay thế rà soát UBCKNN/HOSE/HNX, BCTC và Free Float. GTGD 20 nến là close × volume theo đơn vị nguồn, chỉ là proxy. Không tự sửa nến, không tự bỏ mã thiếu dữ liệu. Mã mới chưa đủ 200 nến được giữ trong ứng viên.")
    st.dataframe(pd.DataFrame([{"Lô":k,"Số mã":len(v),"Mã":", ".join(v)} for k,v in BATCHES.items()]),hide_index=True,use_container_width=True)
    with st.form("kt170_form"):
        chosen=st.multiselect("Lô dữ liệu (khuyến nghị 1 lô/lần)",list(BATCHES),default=["B1"],key="kt170_batches")
        units=st.radio("Đơn vị giá nguồn TCBS",["Nghìn đồng (25.0 = 25.000 VND)","Đồng (25000 = 25.000 VND)"],key="kt170_units")
        confirmed=st.checkbox("Đã kiểm tra đơn vị giá",key="kt170_confirm")
        acv=st.checkbox("Cho phép ACV rút ngắn đúng ngoại lệ KT15 đã ghi nhận (không sửa giá)",key="kt170_acv",value=False)
        submit=st.form_submit_button("Kiểm tra KT17.0",type="primary")
    if submit:
        if not chosen or not confirmed:
            st.error("Chọn lô và xác nhận đơn vị giá.")
        else:
            progress=st.progress(0,text="Đang kiểm tra lịch VN-Index...")
            try:
                calendar,context=reference_calendar(get_vnindex())
                scale=1000 if units.startswith("Nghìn") else 1
                meta=manifest(calendar,context,scale,acv)
                cache=st.session_state.get("kt170_results")
                if cache is None or cache["meta"]!=meta:
                    cache={"meta":meta,"rows":{},"gaps":{},"source":{},"index":context.rename_axis("Ngày").reset_index()}
                symbols=[s for k in chosen for s in BATCHES[k]]
                for i,s in enumerate(symbols):
                    try:
                        df=get_data(s,"Ngày",history_end="2026-11-23",kt15_acv_quarantine=acv and s=="ACV")
                        row,gaps,source=audit_one(s,df,calendar,scale,acv)
                    except Exception as exc:
                        row,gaps,source=audit_one(s,None,calendar,scale,acv,load_error=type(exc).__name__)
                    cache["rows"][s]=row
                    cache["gaps"][s]=gaps
                    cache["source"][s]=source
                    st.session_state["kt170_results"]=cache
                    progress.progress((i+1)/len(symbols),text=f"{i+1}/{len(symbols)}: {s}")
                    if i+1<len(symbols): time.sleep(1.1)
            except Exception as exc:
                st.error("KT17.0: "+(str(exc)[:300] if isinstance(exc,ValueError) else type(exc).__name__))
            finally:
                progress.empty()
    cache=st.session_state.get("kt170_results")
    if cache is None: return
    result=pd.DataFrame([cache["rows"][s] for s in U5 if s in cache["rows"]])
    st.caption(f"Đã kiểm tra {len(result)}/120 mã. Đạt kỹ thuật: {int(result['Trạng thái kỹ thuật'].str.startswith('Đạt').sum())}. Chưa xác nhận mã nào đủ điều kiện mở vị thế thực tế.")
    st.dataframe(result,hide_index=True,use_container_width=True)
    if st.button("Xóa kết quả KT17.0 trong phiên này",key="kt170_reset"):
        st.session_state.pop("kt170_results",None)
        st.rerun()
    buf=io.BytesIO()
    def concat(items):
        frames=[f for f in items.values() if not f.empty]
        return pd.concat(frames,ignore_index=True) if frames else pd.DataFrame()
    outputs={"chat_luong":result,"ngay_thieu_thua":concat(cache["gaps"]),"du_lieu_nguon":concat(cache["source"]),"vnindex":cache["index"],"pham_vi":pd.DataFrame([{**cache["meta"],"Số mã đã kiểm tra":len(result)}])}
    with zipfile.ZipFile(buf,"w",compression=zipfile.ZIP_DEFLATED) as z:
        for k,f in outputs.items():
            z.writestr("stock_bot_kt170_"+k+".csv",f.to_csv(index=False).encode("utf-8-sig"))
        z.writestr("stock_bot_kt170_manifest.json",json.dumps({**cache["meta"],"Mã đã kiểm tra":sorted(cache["rows"])},ensure_ascii=False,indent=2))
    st.download_button("Tải ZIP KT17.0",buf.getvalue(),f"stock_bot_kt170_{len(result)}_ma.zip","application/zip",key="kt170_download")
    st.caption("Kết quả cộng dồn trong phiên Streamlit nếu cùng lịch/đơn vị/ngoại lệ ACV. Tải ZIP sau mỗi lô để tránh mất kết quả nếu Cloud khởi động lại. Dữ liệu riêng tư, không đăng lên GitHub.")
