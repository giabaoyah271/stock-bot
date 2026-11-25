"""On-demand U5 technical scan. No account state, trade quantity or orders."""
import time,io,zipfile,json,hashlib
import pandas as pd
import streamlit as st
from signal_engine_core import SCOPE,U5,BATCHES,read_reference,validate_index,scan_batch,reference_batch,report_rows,local_now,local_days,END
from market_research_core import load_index
from full_universe_core import SHA_B

def render_signal_engine():
    st.title("Quét tín hiệu U5 – S0P0 / RS60")
    st.warning("PT02: tín hiệu kỹ thuật, không phải lệnh. Chưa xác minh pháp lý, tài khoản hoặc sizing. Xếp hạng chỉ trên mã khớp mẫu KT18 và có tín hiệu mua mới.")
    st.caption("So sánh TCBS hiện tại với lịch sử đóng băng 115 mã; không sửa giá, không tự bổ sung mã. Khung Ngày, giá nghìn đồng.")
    ref_bytes=st.session_state.get("pt09_reference_bytes")
    if ref_bytes is None:
        ref=st.file_uploader("ZIP U5-B đã nghiệm thu (115 mã)",type="zip",key="pt02_reference")
        ref_bytes=ref.getvalue() if ref is not None else None
    else:
        st.caption("Dùng lại ZIP U5-B đã xác minh trong workspace.")
    mode=st.radio("Chế độ PT02",("TEST","LIVE"),format_func=lambda x:"Kiểm thử ZIP – 23/11/2026 (không gọi TCBS)" if x=="TEST" else "Quét phiên mới từ TCBS",key="pt02_mode")
    now=local_now()
    if mode=="TEST":
        target=END.date()
        confirmed=True
        st.info("Kiểm thử hồi cứu tại 23/11/2026. Tái tính S0P0 và RS60 từ ZIP đã nghiệm thu; không phải tín hiệu phiên mới, không phải dữ liệu ngoài mẫu.")
    else:
        if st.button("Kiểm tra phiên cuối TCBS",key="pt02_check_index"):
            st.session_state.pop("pt02_index_check",None)
            try:
                from vnstock import Market
                ix=load_index(Market,now=now)
                last=local_days(ix.index)[-1].date()
                st.session_state["pt02_index_check"]=(last,now.isoformat())
                st.session_state["pt02_target_live"]=last
            except Exception as exc:
                st.error(str(exc)[:300] if isinstance(exc,ValueError) else type(exc).__name__)
        checked=st.session_state.get("pt02_index_check")
        if checked:
            st.caption(f"TCBS VN-Index: phiên cuối {checked[0]} | kiểm tra lúc {checked[1]}. Không xác nhận lịch nghỉ hoặc tính đầy đủ của phiên.")
            if pd.Timestamp(checked[0])<=END:
                st.warning("Chưa có phiên mới sau 23/11 trong dữ liệu TCBS. Dùng chế độ kiểm thử ZIP.")
        default=pd.Timestamp(now.date())
        if (now.hour,now.minute)<(15,15): default-=pd.Timedelta(days=1)
        while default.weekday()>=5: default-=pd.Timedelta(days=1)
        target=st.date_input("Phiên mới đã hoàn tất cần quét (giờ VN)",value=default.date(),max_value=now.date(),key="pt02_target_live")
        confirmed=st.checkbox("Tôi xác nhận đây là phiên giao dịch gần nhất đã hoàn tất và đơn vị giá TCBS là nghìn đồng",key="pt02_confirm_live")

    scope=st.selectbox("Phạm vi",SCOPE,key="pt02_scope",format_func=lambda p:"ALL – 120 mã" if p=="ALL" else p+" – 30 mã")
    st.caption("ALL chạy tuần tự; có thể chọn B1–B4. Kết quả chỉ gộp trong cùng phiên trình duyệt, cùng lịch/giá VN-Index và phiên yêu cầu.")
    if st.button("Xóa kết quả PT02",key="pt02_clear"):
        st.session_state.pop("pt02_report",None)
    if st.button("Quét tín hiệu PT02",key="pt02_run",type="primary"):
        if ref_bytes is None or not confirmed:
            st.error("Cần ZIP tham chiếu và xác nhận phiên/đơn vị.")
            return
        bar=st.progress(0,text="Kiểm tra dữ liệu tham chiếu...")
        try:
            old,zeros,reference=read_reference(ref_bytes)
            stamp=local_now()
            batch=U5 if scope=="ALL" else BATCHES[scope]
            progress=lambda i,n,s:bar.progress(i/n,text=f"{i}/{n}: {s}")
            if mode=="TEST":
                digest=hashlib.sha256(reference.to_csv(float_format="%.17g").encode()).hexdigest()
                index=reference
                result=reference_batch(batch,old,reference,progress)
            else:
                from vnstock import Market
                index,digest=validate_index(load_index(Market,now=stamp),reference,target,stamp)
                def loader(s):
                    time.sleep(1.1)
                    return Market("tcbs").equity(s).ohlcv(start="2022-01-01",end=stamp.date().isoformat(),interval="1D")
                result=scan_batch(batch,loader,index,old,zeros,stamp,progress)
            identity=(str(target),digest,SHA_B,mode)
            saved=st.session_state.get("pt02_report")
            rows=dict(saved["rows"]) if saved and saved["identity"]==identity and scope!="ALL" else {}
            for row in result:
                rows[row["Mã"]]=row
            st.session_state["pt02_report"]={"identity":identity,"rows":rows,"updated":local_now().isoformat(),
                "previous_session":index.index[-2].date().isoformat(),
                "previous_index_sha":hashlib.sha256(index.iloc[:-1].to_csv(float_format="%.17g").encode()).hexdigest()}
        except Exception as exc:
            st.error(str(exc)[:450] if isinstance(exc,(ValueError,AssertionError)) else type(exc).__name__)
            return
        finally: bar.empty()
    saved=st.session_state.get("pt02_report")
    if not saved: return
    if saved["identity"][0]!=str(target) or len(saved["identity"])!=4 or saved["identity"][3]!=mode:
        st.warning("Kết quả lưu thuộc phiên khác. Quét lại trước khi sử dụng.")
        return
    d=report_rows(saved["rows"].values())
    n=int((d["Kỹ thuật"]=="Khớp mẫu KT18").sum())
    a,b,c=st.columns(3)
    a.metric("Đã kiểm tra",f"{len(d)}/120")
    b.metric("Khớp mẫu KT18",n)
    c.metric("Mua mới kỹ thuật",int(d["Hạng mua mới (kỹ thuật)"].notna().sum()))
    st.caption(f"Phiên {saved['identity'][0]} | Cập nhật {saved['updated']} | {mode}")
    if mode=="TEST": st.warning("Kết quả KIỂM THỬ HỒI CỨU, không phải tín hiệu giao dịch mới. 5 mã ngoài mẫu chưa được kiểm tra từ TCBS.")
    st.warning("Hạng trên các mã đã kiểm tra và khớp mẫu, không phải hạng đủ 120 nếu còn mã thiếu/lỗi. Không coi hạng là khuyến nghị mua. Duy trì/thoát xu hướng không xác nhận đang sở hữu cổ phiếu.")
    options=["Tất cả","Mua mới (tín hiệu)","Duy trì xu hướng","Thoát xu hướng (tín hiệu)","Đứng ngoài","Cần kiểm tra"]
    filt=st.selectbox("Lọc tín hiệu",options,key="pt02_filter")
    shown=d
    if filt=="Cần kiểm tra": shown=d[d["Kỹ thuật"]!="Khớp mẫu KT18"]
    elif filt!="Tất cả": shown=d[d["Tín hiệu"]==filt] if "Tín hiệu" in d else d.iloc[:0]
    st.dataframe(shown,hide_index=True,use_container_width=True,height=560)
    meta={"Phiên":saved["identity"][0],"SHA VNINDEX":saved["identity"][1],"SHA U5-B":SHA_B,"Mã kiểm tra":len(d),"Khớp mẫu":n,"Cập nhật":saved["updated"],"Chỉ nghiên cứu":True,"Chế độ":mode,"Bằng chứng tiến tới":False}
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,"w",compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("stock_bot_pt02_tin_hieu.csv",d.to_csv(index=False).encode("utf-8-sig"))
        z.writestr("stock_bot_pt02_manifest.json",json.dumps(meta,ensure_ascii=False,indent=2))
    st.download_button("Tải ZIP PT02",buf.getvalue(),("stock_bot_pt02_kiem_thu_20261123.zip" if mode=="TEST" else "stock_bot_pt02_tin_hieu.zip"),"application/zip",key="pt02_download")
