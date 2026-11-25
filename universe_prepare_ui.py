"""Upload exact archives; optional TCBS retry only 12 failed symbols."""
import io,json,zipfile,time
from datetime import datetime
import pandas as pd
import streamlit as st
from vnstock import Market
from universe_prepare_core import RETRY,U5_SHA,KT15_SHA,read_u5,retry_raw,prepare_batch

def render_universe_prepare():
    st.caption("KT17.0a-e: tái lập S0P0 từ OHLCV; đối chiếu 29 mã KT15. Không chạy Backtesting vốn chung hoặc phê duyệt mua.")
    a=st.file_uploader("ZIP KT17.0 gốc 120 mã",type="zip",key="kt170prep_a")
    b=st.file_uploader("ZIP KT15 gốc",type="zip",key="kt170prep_b")
    drop=st.checkbox("Mẫu bổ sung: bỏ 20 nến volume 0, tính lại từ nến thực; không khớp lệnh tại nến bỏ",value=True,key="kt170prep_zero")
    retry=st.checkbox("Tải lại đúng 12 mã lỗi OHLC từ TCBS",value=True,key="kt170prep_retry")
    prefix=st.checkbox("Nếu TCBS vẫn lỗi đúng chữ ký cũ, cho phép rút ngắn sau nến lỗi cuối cùng (mẫu bổ sung, không sửa giá)",value=False,key="kt170prep_prefix")
    if st.button("Chuẩn bị dữ liệu KT17",key="kt170prep_run",type="primary"):
        st.session_state.pop("kt170prep_report",None)
        if a is None or b is None: st.error("Tải cả hai ZIP gốc.");return
        progress=st.progress(0,text="Đọc ZIP và kiểm tra đối chứng")
        try:
            raw,cov,calendar,old,idx=read_u5(a.getvalue(),b.getvalue())
            retries={};errors=[]
            if retry:
                for i,s in enumerate(RETRY):
                    progress.progress((i+1)/132,text="Tải lại "+s)
                    try:
                        d=Market("tcbs").equity(s).ohlcv(start="2022-01-01",end="2026-11-23",interval="1D")
                        retries[s]=retry_raw(d,s,str(cov.at[s,"Lý do"]),calendar,prefix)
                    except Exception as exc:
                        errors.append({"Mã":s,"Lỗi":str(exc)[:400] if isinstance(exc,ValueError) else type(exc).__name__})
                    if i+1<len(RETRY): time.sleep(1.1)
            offset=12 if retry else 0
            coverage,signals,omitted=prepare_batch(raw,cov,calendar,old,retries,drop,
                lambda i,s:progress.progress((i+offset)/(120+offset),text=f"Tái lập {i}/120: {s}"))
            meta={"U5_SHA256":U5_SHA,"KT15_SHA256":KT15_SHA,"Đơn vị giá":1000,"Từ":"2022-01-04","Đến":"2026-11-23","Nến thực":drop,"Cho phép prefix":prefix,"Tải lại OHLC":retry,"Mã đạt":int((coverage["Trạng thái"]=="Đạt nghiên cứu").sum()),"Pháp lý":"Chưa xác minh; không dùng cho giao dịch thực tế"}
            outputs={"chat_luong":coverage,"tin_hieu":signals,"ngay_loai":omitted,"vnindex":idx,"loi_tai_lai":pd.DataFrame(errors,columns=["Mã","Lỗi"])}
            buf=io.BytesIO()
            with zipfile.ZipFile(buf,"w",compression=zipfile.ZIP_DEFLATED) as z:
                for k,f in outputs.items(): z.writestr("stock_bot_kt170prep_"+k+".csv",f.to_csv(index=False).encode("utf-8-sig"))
                z.writestr("stock_bot_kt170prep_manifest.json",json.dumps(meta,ensure_ascii=False,indent=2))
            st.session_state["kt170prep_report"]=(coverage,meta,buf.getvalue())
        except Exception as exc: st.error(str(exc)[:500] if isinstance(exc,(ValueError,AssertionError)) else type(exc).__name__)
        finally: progress.empty()
    report=st.session_state.get("kt170prep_report")
    if report:
        c,m,data=report
        st.caption(f"Đạt nghiên cứu {m['Mã đạt']}/120; đối chiếu KT15 khớp {int((c['Đối chiếu KT15']=='Khớp').sum())}/29. Pháp lý chưa xác minh.")
        st.dataframe(c,hide_index=True,use_container_width=True)
        st.download_button("Tải ZIP chuẩn bị KT17",data,"stock_bot_kt170prep_bao_cao.zip","application/zip",key="kt170prep_download")
