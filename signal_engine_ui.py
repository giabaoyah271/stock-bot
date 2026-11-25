"""On-demand U5 technical scan. No account state, trade quantity or orders."""
import time,io,zipfile,json
import pandas as pd
import streamlit as st
from signal_engine_core import SCOPE,U5,BATCHES,read_reference,validate_index,scan_batch,report_rows,local_now
from market_research_core import load_index
from full_universe_core import SHA_B

def render_signal_engine():
    st.title("Quét tín hiệu U5 – S0P0 / RS60")
    st.warning("PT02: tín hiệu kỹ thuật, không phải lệnh. Chưa xác minh pháp lý, tài khoản hoặc sizing. Xếp hạng chỉ trên mã khớp mẫu KT18 và có tín hiệu mua mới.")
    st.caption("So sánh TCBS hiện tại với lịch sử đóng băng 115 mã; không sửa giá, không tự bổ sung mã. Khung Ngày, giá nghìn đồng.")
    ref=st.file_uploader("ZIP U5-B đã nghiệm thu (115 mã)",type="zip",key="pt02_reference")
    now=local_now();default=pd.Timestamp(now.date())
    if (now.hour,now.minute)<(15,15): default-=pd.Timedelta(days=1)
    while default.weekday()>=5: default-=pd.Timedelta(days=1)
    target=st.date_input("Phiên đã hoàn tất cần quét (giờ VN)",value=default.date(),max_value=now.date(),key="pt02_target")
    confirmed=st.checkbox("Tôi xác nhận phiên giao dịch gần nhất đã hoàn tất và đơn vị giá TCBS là nghìn đồng",key="pt02_confirm")
    scope=st.selectbox("Phạm vi",SCOPE,key="pt02_scope",format_func=lambda p:"ALL – 120 mã" if p=="ALL" else p+" – 30 mã")
    st.caption("ALL chạy tuần tự; có thể chọn B1–B4. Kết quả chỉ gộp trong cùng phiên trình duyệt, cùng lịch/giá VN-Index và phiên yêu cầu.")
    if st.button("Xóa kết quả PT02",key="pt02_clear"):
        st.session_state.pop("pt02_report",None)
    if st.button("Quét tín hiệu PT02",key="pt02_run",type="primary"):
        if ref is None or not confirmed:
            st.error("Cần ZIP tham chiếu và xác nhận phiên/đơn vị.")
            return
        bar=st.progress(0,text="Kiểm tra dữ liệu tham chiếu và VN-Index...")
        try:
            from vnstock import Market
            old,zeros,reference=read_reference(ref.getvalue())
            stamp=local_now()
            index,digest=validate_index(load_index(Market,now=stamp),reference,target,stamp)
            identity=(str(target),digest,SHA_B)
            saved=st.session_state.get("pt02_report")
            rows=dict(saved["rows"]) if saved and saved["identity"]==identity and scope!="ALL" else {}
            def loader(s):
                time.sleep(1.1)
                return Market("tcbs").equity(s).ohlcv(start="2022-01-01",end=stamp.date().isoformat(),interval="1D")
            batch=U5 if scope=="ALL" else BATCHES[scope]
            for row in scan_batch(batch,loader,index,old,zeros,stamp,lambda i,n,s:bar.progress(i/n,text=f"{i}/{n}: {s}")):
                rows[row["Mã"]]=row
            st.session_state["pt02_report"]={"identity":identity,"rows":rows,"updated":local_now().isoformat()}
        except Exception as exc:
            st.error(str(exc)[:450] if isinstance(exc,(ValueError,AssertionError)) else type(exc).__name__)
            return
        finally: bar.empty()
    saved=st.session_state.get("pt02_report")
    if not saved: return
    if saved["identity"][0]!=str(target):
        st.warning("Kết quả lưu thuộc phiên khác. Quét lại trước khi sử dụng.")
        return
    d=report_rows(saved["rows"].values())
    n=int((d["Kỹ thuật"]=="Khớp mẫu KT18").sum())
    a,b,c=st.columns(3)
    a.metric("Đã kiểm tra",f"{len(d)}/120")
    b.metric("Khớp mẫu KT18",n)
    c.metric("Mua mới kỹ thuật",int(d["Hạng mua mới (kỹ thuật)"].notna().sum()))
    st.caption(f"Phiên {saved['identity'][0]} | Cập nhật {saved['updated']}")
    st.warning("Hạng trên các mã đã kiểm tra và khớp mẫu, không phải hạng đủ 120 nếu còn mã thiếu/lỗi. Không coi hạng là khuyến nghị mua. Duy trì/thoát xu hướng không xác nhận đang sở hữu cổ phiếu.")
    options=["Tất cả","Mua mới (tín hiệu)","Duy trì xu hướng","Thoát xu hướng (tín hiệu)","Đứng ngoài","Cần kiểm tra"]
    filt=st.selectbox("Lọc tín hiệu",options,key="pt02_filter")
    shown=d
    if filt=="Cần kiểm tra": shown=d[d["Kỹ thuật"]!="Khớp mẫu KT18"]
    elif filt!="Tất cả": shown=d[d["Tín hiệu"]==filt] if "Tín hiệu" in d else d.iloc[:0]
    st.dataframe(shown,hide_index=True,use_container_width=True,height=560)
    meta={"Phiên":saved["identity"][0],"SHA VNINDEX":saved["identity"][1],"SHA U5-B":SHA_B,"Mã kiểm tra":len(d),"Khớp mẫu":n,"Cập nhật":saved["updated"],"Chỉ nghiên cứu":True}
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,"w",compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("stock_bot_pt02_tin_hieu.csv",d.to_csv(index=False).encode("utf-8-sig"))
        z.writestr("stock_bot_pt02_manifest.json",json.dumps(meta,ensure_ascii=False,indent=2))
    st.download_button("Tải ZIP PT02",buf.getvalue(),"stock_bot_pt02_tin_hieu.zip","application/zip",key="pt02_download")
