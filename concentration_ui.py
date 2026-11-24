"""Run KT16 from the private, complete KT15 archive, no new network requests."""
import io
import zipfile
import pandas as pd
import streamlit as st
from concentration_core import GROUPS,case_count,read_archive,evaluate_concentration

def render_concentration():
    st.markdown("**KT16 – Kiểm định tập trung lợi nhuận**")
    st.caption("Dùng ZIP KT15 đầy đủ 31 mã / 20 kịch bản đã nghiệm thu. Không tải lại TCBS, không chỉnh sửa giá hay tham số. Kiểm tra lại 8 đối chứng A0/A4-C0 trước mọi phép thử.")
    st.warning("Dùng chuỗi Trend/ATR/SMA50 lưu trong ZIP; không tính lại toàn bộ chỉ báo. ACV có thể rút ngắn. Hồi cứu, thiên lệch chọn mã cuối kỳ. DROP2 chọn theo P&L đã quan sát, chỉ để đo độ nhạy. COMMON bắt đầu vốn mới, không mua bù tín hiệu cũ; không so chênh lợi nhuận trực tiếp với toàn kỳ.")
    st.dataframe(pd.DataFrame([{"Nhóm":g,"Số mã":len(m),"Số kịch bản":case_count((g,))} for g,m in GROUPS.items()]),hide_index=True)
    with st.form("kt16_form"):
        archive=st.file_uploader("Tải lên ZIP KT15 gốc (riêng tư)",type=["zip"],key="kt16_archive")
        groups=st.multiselect("Nhóm kiểm định",list(GROUPS),default=["U4"],key="kt16_groups")
        confirmed=st.checkbox("Xác nhận ZIP KT15 gốc và đơn vị giá trong báo cáo",key="kt16_confirm")
        run=st.form_submit_button("Chạy KT16",type="primary")
    if run:
        st.session_state.pop("kt16_report",None)
        if archive is None or not groups or not confirmed:
            st.error("Cần ZIP KT15, nhóm và xác nhận.")
        else:
            progress=st.progress(0,text="Đang kiểm tra ZIP và 8 đối chứng KT15...")
            try:
                frames,digest=read_archive(archive.getvalue())
                def update(done,total,code):
                    progress.progress(done/total,text=f"{done}/{total}: {code}")
                report=evaluate_concentration(frames,tuple(groups),progress=update)
                report["metadata"]["SHA256 ZIP KT15"]=digest
                st.session_state["kt16_report"]=report
            except Exception as exc:
                st.error("KT16 dừng: "+(str(exc)[:400] if isinstance(exc,(ValueError,AssertionError,KeyError,zipfile.BadZipFile)) else type(exc).__name__))
            finally:
                progress.empty()
    report=st.session_state.get("kt16_report")
    if report is None: return
    summary=report["summary"]
    meta=report["metadata"]
    expected=int(meta["Số kịch bản dự kiến"].iloc[0])
    st.caption(f"Hoàn thành {len(summary)}/{expected} kịch bản | 8/8 đối chứng KT15 khớp")
    st.dataframe(meta,hide_index=True,use_container_width=True)
    if not report["errors"].empty:
        st.error("Một số kịch bản không hoàn thành. Không nghiệm thu đầy đủ.")
        st.dataframe(report["errors"],hide_index=True)
    if not summary.empty:
        cols=["Nhóm","Bộ lọc","Kiểm định","Mã loại","Lợi nhuận (%)","MDD (%)","PF tiền thực hiện","Sharpe (rf=0)","Số lệnh đóng","Chênh LN so FULL (đpt)"]
        st.markdown("**Danh mục đầy đủ, loại hai mã, giai đoạn chung**")
        st.dataframe(summary.loc[summary["Kiểm định"]!="LOO",cols].round(4),hide_index=True,use_container_width=True)
        st.markdown("**Leave-one-out – từng mã bị loại**")
        st.dataframe(summary.loc[summary["Kiểm định"]=="LOO",cols].round(4),hide_index=True,use_container_width=True)
        st.markdown("**Monte Carlo danh mục FULL (2.000 mẫu/block 5,10,20)**")
        st.dataframe(report["mc"].round(4),hide_index=True,use_container_width=True)
        eq=report["equity"]
        options=list(eq.loc[eq["Kiểm định"]=="FULL","Kịch bản"].unique())
        chosen=st.multiselect("Danh mục FULL trên biểu đồ",options,default=options[:4],key="kt16_chart")
        if chosen:
            sub=eq[eq["Kịch bản"].isin(chosen)]
            st.line_chart(sub.pivot(index="Ngày",columns="Kịch bản",values="Equity"))
    labels={"summary":"tong_hop","equity":"equity","trades":"giao_dich","orders":"lenh","windows":"cua_so","stocks":"theo_ma","mc":"monte_carlo","mc_samples":"monte_carlo_mau","metadata":"pham_vi","errors":"loi"}
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,"w",compression=zipfile.ZIP_DEFLATED) as z:
        for k,label in labels.items():
            z.writestr("stock_bot_kt16_"+label+".csv",report[k].to_csv(index=False).encode("utf-8-sig"))
    suffix=meta["Nhóm"].iloc[0].replace(",","_")
    st.download_button("Tải ZIP KT16",buf.getvalue(),f"stock_bot_kt16_{suffix}.zip","application/zip",key="kt16_zip")
    st.caption("LOO xuất tổng hợp, cửa sổ và P&L theo mã; FULL/DROP2/COMMON thêm Equity, giao dịch và lệnh. Có thể chạy từng nhóm để giảm tải; lưu ZIP riêng tư. Không gửi lệnh thật.")
