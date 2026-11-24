"""KT12 on-demand retrospective report and separate manual snapshot."""
import pandas as pd
import streamlit as st
from portfolio_core import Policy,SECTORS
from risk_batch import GROUPS,selected_symbols
from trade_diagnostics import completed_daily_history
from market_research_ui import get_vnindex
from robustness_core import evaluate_robustness
from prospective_capture import capture_snapshot

def _load(symbols,get_data):
    histories={}
    progress=st.progress(0,text="Đang tải dữ liệu...")
    try:
        for i,s in enumerate(symbols):
            histories[s],_=completed_daily_history(get_data(s,"Ngày"))
            progress.progress((i+1)/len(symbols),text=f"Đã tải {s}")
    finally:
        progress.empty()
    return histories

def render_robustness(get_data):
    st.markdown("**KT12 – Kiểm định độ tin cậy**")
    st.warning("Hồi cứu cố định đến 23/11/2026, không phải OOS độc lập. 4 ứng viên + 4 kịch bản chi phí + 7 kiểm định độ nhạy (có đối chứng lặp), 15 dòng. Walk-forward chọn theo Sharpe train, tối thiểu 10 lệnh đóng, MDD ≤10%, nếu không đủ chọn A4. Cửa sổ test của các danh mục bóng giữ vị thế cũ; không phải tài khoản chuyển chiến lược có thể thực thi.")
    st.caption("Monte Carlo 2.000 mẫu mỗi block 5/10/20, toàn kỳ và sau warmup 200. Không mô phỏng khớp lệnh hoặc sự kiện ngoài mẫu. Đối chứng giá không phí/cổ tức, VNINDEX exposure dùng tỷ trọng phiên trước.")
    with st.form("kt12_form"):
        group=st.selectbox("Nhóm mã",tuple(k for k in GROUPS if k!="Tùy chỉnh"),key="kt12_group")
        units=st.radio("Đơn vị giá TCBS",["Nghìn đồng (25.0 = 25.000 VND)","Đồng (25000 = 25.000 VND)"],key="kt12_units")
        confirmed=st.checkbox("Tôi đã kiểm tra đơn vị giá",key="kt12_confirm")
        run=st.form_submit_button("Chạy KT12 hồi cứu",type="primary")
    if run:
        st.session_state.pop("kt12_report",None)
        if not confirmed: st.error("Cần xác nhận đơn vị giá")
        else:
            try:
                symbols=selected_symbols(group)
                histories=_load(symbols,get_data)
                with st.spinner("Đang chạy KT12..."):
                    report=evaluate_robustness(histories,get_vnindex(),Policy(price_scale=1000 if units.startswith("Nghìn") else 1),require_reference_calendar=True)
                report["symbols"]=symbols
                st.session_state["kt12_report"]=report
            except Exception as exc:
                st.error(f"KT12 không hoàn thành: {str(exc)[:180] if isinstance(exc,ValueError) else type(exc).__name__}")
    report=st.session_state.get("kt12_report")
    if report is not None:
        st.caption(f"Hoàn thành {len(report['summary'])}/15 dòng | Mã: {', '.join(report['symbols'])}")
        for key in ("summary","wf","selection","mc","benchmark"):
            st.markdown("**"+key+"**")
            st.dataframe(report[key].round(4),hide_index=True,use_container_width=True)
        st.line_chart(report["benchmark_equity"].set_index("Ngày").drop(columns="Exposure trễ (%)"))
        labels={"summary":"tong_hop","equity":"equity","trades":"giao_dich","orders":"lenh","windows":"cua_so",
                "wf":"walk_forward","selection":"lua_chon_wf","mc":"monte_carlo","mc_samples":"monte_carlo_mau",
                "benchmark":"doi_chung","benchmark_equity":"doi_chung_equity"}
        import io,zipfile
        buf=io.BytesIO()
        with zipfile.ZipFile(buf,"w",compression=zipfile.ZIP_DEFLATED) as z:
            for key,label in labels.items():
                z.writestr(f"stock_bot_kt12_{label}.csv",report[key].to_csv(index=False).encode("utf-8-sig"))
        st.download_button("Tải toàn bộ báo cáo KT12 (ZIP)",buf.getvalue(),"stock_bot_kt12_bao_cao.zip","application/zip",key="kt12_zip")
    st.divider()
    st.markdown("**KT12.6 – Ghi nhận tiến cứu A4 (thủ công, riêng tư)**")
    st.caption("Khóa 24/11/2026; chỉ phiên sau ngày khóa, dữ liệu đủ 12 mã, ngày phiên cuối phải là hôm nay và sau 15:15 VN. Vốn 100 triệu, giá nghìn đồng, không đổi tham số. Không ghi bù. Snapshot là kết quả chạy lại lịch sử kèm tín hiệu mới, không phải nhật ký khớp độc lập.")
    verified=st.checkbox("Xác nhận giá nghìn đồng, phiên hôm nay đã hoàn tất và sẽ lưu ZIP gốc riêng tư",key="kt12_pros_confirm")
    if st.button("Tạo snapshot tiến cứu hôm nay",key="kt12_pros_run",disabled=not verified):
        st.session_state.pop("kt12_snapshot",None)
        try:
            histories=_load(sorted(SECTORS),get_data)
            st.session_state["kt12_snapshot"]=capture_snapshot(histories)
        except Exception as exc:
            st.error(f"Không tạo snapshot: {str(exc)[:180] if isinstance(exc,ValueError) else type(exc).__name__}")
    snapshot=st.session_state.get("kt12_snapshot")
    if snapshot:
        data,digest,manifest,pending=snapshot
        st.caption("Phiên "+manifest["as_of_session_vn"]+" | ghi lúc "+manifest["recorded_at_vn"])
        st.code(digest)
        st.dataframe(pending,hide_index=True,use_container_width=True)
        st.download_button("Tải snapshot ZIP riêng tư",data,f"{manifest['as_of_session_vn']}_A4_snapshot.zip","application/zip",key="kt12_pros_download")
        st.caption("Lưu tệp nguyên bản và SHA-256; nếu nguồn sửa, lưu revision mới, không ghi đè. Không tải OHLCV lên repo công khai.")
