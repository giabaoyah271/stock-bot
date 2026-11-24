"""KT15 on-demand panel; partial groups explicitly marked."""
import io
import zipfile
import pandas as pd
import streamlit as st
from cross_section_core import GROUPS,evaluate_cross_section
from market_research_ui import get_vnindex
from portfolio_core import Policy
from trade_diagnostics import completed_daily_history

def render_cross_section(get_data):
    st.markdown("**KT15 – Kiểm định mở rộng Large-cap**")
    st.caption("Danh sách cố định theo đề xuất 20/11/2026. U0 12 mã cũ, U1 Top 20, U2 14 mã mới, U3 20 đa ngành. A0-C0 và A4-C0/C1/C2/C3. Không đổi tham số.")
    st.warning("Hồi cứu đến 23/11/2026; danh sách vốn hóa cuối kỳ gây thiên lệch. VPL từ 13/05/2025; BSR/MCH có khoảng chuyển sàn đã xác minh. Không tạo nến/khớp giả; vị thế trong phiên chuyển sàn định giá Close thực gần nhất. Thiếu phiên không rõ nguyên nhân: không chạy nhóm liên quan.")
    st.dataframe(pd.DataFrame([{"Nhóm":g,"Số mã":len(s),"Mã":", ".join(s)} for g,s in GROUPS.items()]),hide_index=True,use_container_width=True)
    with st.form("kt15_form"):
        chosen=st.multiselect("Nhóm kiểm định",list(GROUPS),default=["U0"],key="kt15_groups")
        units=st.radio("Đơn vị giá cổ phiếu TCBS",["Nghìn đồng (25.0 = 25.000 VND)","Đồng (25000 = 25.000 VND)"],key="kt15_units")
        confirmed=st.checkbox("Tôi đã kiểm tra đơn vị giá nguồn",key="kt15_confirm")
        quarantine=st.checkbox("Cho phép kiểm định bổ sung nếu ACV còn lỗi 16/06/2022: bỏ prefix đến ngày lỗi, khởi tạo lại 200 nến (không sửa giá)",key="kt15_acv_quarantine",value=False)
        run=st.form_submit_button("Chạy KT15",type="primary")
    if run:
        st.session_state.pop("kt15_report",None)
        if not confirmed or not chosen: st.error("Chọn nhóm và xác nhận đơn vị giá.")
        else:
            try:
                index=get_vnindex()
                symbols=sorted(set().union(*(GROUPS[g] for g in chosen)))
                histories,errors={},{}
                progress=st.progress(0,text="Đang tải dữ liệu...")
                try:
                    for i,s in enumerate(symbols):
                        try:
                            raw = get_data(s,"Ngày",history_end="2026-11-23",kt15_acv_quarantine=quarantine and s=="ACV")
                            if raw.empty:
                                errors[s]=raw.attrs.get("daily_quality_error","Không có dữ liệu TCBS")
                            else:
                                histories[s],_=completed_daily_history(raw)
                        except Exception as exc:
                            errors[s]=str(exc)[:300] if isinstance(exc,ValueError) else type(exc).__name__
                        progress.progress((i+1)/len(symbols),text=f"Đã xử lý {s} ({i+1}/{len(symbols)})")
                finally:
                    progress.empty()
                with st.spinner("Đang kiểm định danh mục và Monte Carlo..."):
                    report=evaluate_cross_section(histories,index,tuple(chosen),Policy(price_scale=1000 if units.startswith("Nghìn") else 1),load_errors=errors,allow_acv_quarantine=quarantine)
                report["expected"]=5*len(chosen)
                st.session_state["kt15_report"]=report
            except Exception as exc:
                st.error(f"KT15: {str(exc)[:300] if isinstance(exc,ValueError) else type(exc).__name__}")
    report=st.session_state.get("kt15_report")
    if report is None: return
    summary=report["summary"]
    st.caption(f"Hoàn thành {len(summary)}/{report['expected']} kịch bản")
    if not summary.empty and summary["Phạm vi ACV"].str.startswith("Rút ngắn").any():
        st.warning("Có kịch bản bổ sung ACV rút ngắn. Không nghiệm thu mẫu ACV đầy đủ; xem cột Phạm vi ACV và báo cáo chất lượng.")
    if not report["errors"].empty:
        st.warning("Báo cáo chưa đầy đủ; các nhóm bị lỗi không được nghiệm thu.")
        st.dataframe(report["errors"],hide_index=True,use_container_width=True)
    for key,title in (("coverage","Kiểm tra dữ liệu"),("summary","Tổng hợp"),("mc","Monte Carlo"),("sectors","Đóng góp ngành")):
        st.markdown("**"+title+"**")
        st.dataframe(report[key].round(4),hide_index=True,use_container_width=True)
    if not summary.empty:
        eq=report["equity"]
        options=list(eq["Kịch bản"].unique())
        choices=st.multiselect("Danh mục biểu đồ",options,default=[x for x in options if x.endswith("A4-C0")],key="kt15_chart")
        if choices:
            sub=eq[eq["Kịch bản"].isin(choices)]
            for c in ("Equity","Drawdown (%)","Exposure (%)"):
                st.line_chart(sub.pivot(index="Ngày",columns="Kịch bản",values=c))
    labels={"summary":"tong_hop","equity":"equity","trades":"giao_dich","orders":"lenh","windows":"cua_so","stocks":"theo_ma","sectors":"theo_nganh","signals":"tin_hieu","mc":"monte_carlo","mc_samples":"monte_carlo_mau","coverage":"chat_luong","missing":"ngay_thieu_thua","source":"du_lieu_nguon","calendar":"vnindex","errors":"loi"}
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,"w",compression=zipfile.ZIP_DEFLATED) as z:
        for k,label in labels.items():
            z.writestr(f"stock_bot_kt15_{label}.csv",report[k].to_csv(index=False).encode("utf-8-sig"))
    st.download_button("Tải ZIP KT15 (dữ liệu riêng tư)",buf.getvalue(),"stock_bot_kt15_bao_cao.zip","application/zip",key="kt15_zip")
    st.caption("ZIP có dữ liệu TCBS/giá gốc; lưu riêng tư, không đăng lên repo công khai. MDD phiên thiếu giao dịch dùng giá ghi sổ cũ; không phản ánh đầy đủ rủi ro. Tỷ trọng ngành giữ nguyên phân loại U0, nhóm hệ sinh thái chỉ báo cáo P&L, không thêm trần mới.")
