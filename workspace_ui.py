"""PT09 trading terminal: market overview, opportunities and explicit Paper recording."""
import io,json,time,zipfile
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from workspace_core import (
    PAGES,NAV,REF,PROBE,REPORT,SYMBOL,ADVANCED,SECTIONS,checked_reference,index_status,
    build_report,opportunities,filter_opportunities,record_preview,weights
)
from market_research_core import load_index
from signal_engine_core import local_now,local_days,END
from paper_trading_core import replay,export_account,performance,readiness,new_account,import_account,risk_preview,POLICY
from paper_trading_ui import ACCOUNT,cash_text,error,render_risk
from trading_dashboard_core import candidate_parameters,CANDIDATE
from full_universe_core import SHA_B

def go(page,symbol=None):
    st.session_state[NAV]=page
    if symbol: st.session_state[SYMBOL]=symbol

def jump(label,page,key,symbol=None):
    st.button(label,key=key,on_click=go,args=(page,symbol),use_container_width=True)

def reference_panel():
    if REF in st.session_state:
        st.caption("U5-B đã xác minh SHA-256, dùng lại trong phiên làm việc này.")
        if st.button("Gỡ ZIP tham chiếu khỏi phiên",key="pt09_remove_ref"):
            st.session_state.pop(REF,None)
            st.session_state.pop(REPORT,None)
            st.rerun()
    else:
        st.caption("Tải một lần ZIP U5-B đã nghiệm thu (115 mã). Dữ liệu giữ trong session riêng, không lưu lên GitHub.")
        up=st.file_uploader("ZIP U5-B",type="zip",key="pt09_reference_upload")
        if st.button("Xác minh và lưu tham chiếu",key="pt09_save_ref"):
            try:
                if up is None: raise ValueError("Chọn ZIP U5-B")
                st.session_state[REF]=checked_reference(up.getvalue())
                st.rerun()
            except Exception as exc: error(exc)

def fetch_market():
    from vnstock import Market
    now=local_now()
    ix=load_index(Market,now=now)
    status=index_status(ix,now)
    d=ix.copy();d.index=local_days(d.index)
    st.session_state[PROBE]={"status":status,"frame":d}
    return ix,now

def market_caption():
    probe=st.session_state.get(PROBE)
    if not probe:
        st.caption("VN-Index: chưa kiểm tra dữ liệu TCBS trong phiên làm việc.")
        return
    s=probe["status"]
    st.caption(f"VN-Index: {s['last']} | Kiểm tra lúc {s['checked_at']} | {s['status']}.")
    if s["last"]!=str(local_now().date()):
        st.caption("Không xác định chắc chắn ngày nghỉ hay lỗi cập nhật chỉ từ dữ liệu TCBS.")

def paper_backup(account,key):
    st.download_button("Tải JSON sao lưu Paper",export_account(account),"stock_bot_paper_account.json","application/json",key=key,use_container_width=True)
    st.caption("Tải sau mỗi lần ghi phiên; session Cloud có thể mất khi khởi động lại.")

def paper_record(key):
    account=st.session_state.get(ACCOUNT)
    saved=st.session_state.get(REPORT)
    if not account:
        st.info("Chưa có tài khoản mô phỏng.")
        jump("Mở danh mục để khởi tạo",PAGES[3],key+"_init")
        return
    try:
        if st.session_state.get(PROBE) and saved and st.session_state[PROBE]["status"]["last"]!=saved["identity"][0]:
            raise ValueError("Phiên vừa kiểm tra khác báo cáo đã quét")
        nxt=record_preview(account,saved)
    except Exception as exc:
        st.info("Chưa thể ghi phiên: "+(str(exc)[:350] if isinstance(exc,(ValueError,AssertionError,KeyError)) else type(exc).__name__))
        return
    date=nxt["events"][-1]["input"]["session"]
    st.caption(f"Sẵn sàng ghi mô phỏng phiên {date}; Open là giá báo cáo sau phiên, không phải giá khớp thật.")
    confirmed=st.checkbox("Xác nhận phiên hôm nay đã hoàn tất, đơn vị giá nghìn đồng và ghi mô phỏng",key=key+"_confirm")
    if st.button("Ghi phiên Paper",type="primary",disabled=not confirmed,key=key+"_record"):
        try:
            st.session_state[ACCOUNT]=record_preview(account,saved)
            st.session_state["pt09_recorded"]=date
            st.rerun()
        except Exception as exc: error(exc)

def portfolio_metrics(result):
    if not result:
        st.info("Chưa khởi tạo tài khoản Paper. Không có số dư hoặc hiệu suất để hiển thị.")
        return
    last=result["daily"][-1] if result["daily"] else None
    a,b,c,d=st.columns(4)
    a.metric("Equity mô phỏng",cash_text(result["equity"]))
    b.metric("Tiền mặt",cash_text(result["cash"]))
    c.metric("Vị thế",f"{len(result['holdings'])}/5")
    d.metric("Rủi ro còn mở",f"{last['Heat (%)']:.2f}%" if last else "0%")
    st.caption("Định giá theo Close phiên đã ghi, không phải giá trực tiếp.")

def render_home():
    st.title("Tổng quan giao dịch")
    st.caption("Stock Bot V3 | Paper Trading nghiên cứu • Không gửi lệnh thật")
    a,b=st.columns([2,1])
    with a: jump("Mở bộ quét cơ hội",PAGES[1],"pt09_home_scan")
    with b:
        if st.button("Cập nhật VN-Index",key="pt09_home_market",use_container_width=True):
            st.session_state.pop(PROBE,None)
            try: fetch_market()
            except Exception as exc: error(exc)
    market_caption()
    probe=st.session_state.get(PROBE)
    if probe:
        d=probe["frame"];last=d["close"].iloc[-1];prev=d["close"].iloc[-2]
        st.metric("VN-Index (Close)",f"{last:,.2f}",f"{100*(last/prev-1):+.2f}%")
        fig=go.Figure(go.Candlestick(x=d.index[-120:],open=d["open"].iloc[-120:],high=d["high"].iloc[-120:],low=d["low"].iloc[-120:],close=d["close"].iloc[-120:],name="VN-Index"))
        for n,color in ((50,"#D4A64A"),(200,"#648CC9")):
            fig.add_scatter(x=d.index[-120:],y=d["close"].rolling(n).mean().iloc[-120:],name=f"SMA{n}",line={"color":color,"width":1.3})
        fig.update_layout(height=350,xaxis_rangeslider_visible=False,margin=dict(l=5,r=5,t=8,b=5),legend=dict(orientation="h"))
        st.plotly_chart(fig,use_container_width=True,key="pt09_index_chart")
    account=st.session_state.get(ACCOUNT);result=None
    if account:
        try: result=replay(account)
        except Exception as exc: error(exc)
    portfolio_metrics(result)
    if result and result["daily"]:
        p=performance(result);last=result["daily"][-1]
        x,y,z=st.columns(3)
        x.metric("Lợi nhuận mô phỏng",f"{p['Lợi nhuận (%)']:+.2f}%")
        y.metric("P&L đã đóng",cash_text(last["P&L đã đóng"]))
        z.metric("P&L mở",cash_text(last["P&L mở"]))
    jump("Mở danh mục",PAGES[3],"pt09_home_account")
    saved=st.session_state.get(REPORT)
    st.subheader("Tín hiệu nổi bật")
    if not saved or len(saved.get("identity",()))!=4 or saved["identity"][3]!="LIVE":
        st.info("Chưa có báo cáo quét phiên mới. Kết quả kiểm thử không đưa vào bảng giao dịch.")
    else:
        d=opportunities(saved);s=saved["identity"][0]
        st.caption(f"Báo cáo phiên {s} | {len(saved['rows'])}/120 mã đã quét | Không phải báo giá trực tiếp.")
        if s!=str(local_now().date()): st.warning("Báo cáo không thuộc ngày hôm nay; không dùng để ghi phiên mới.")
        a,b,c=st.columns(3)
        a.metric("Mua mới",int((d["Tín hiệu"]=="Mua mới (tín hiệu)").sum()))
        b.metric("Duy trì",int((d["Tín hiệu"]=="Duy trì xu hướng").sum()))
        c.metric("Thoát",int((d["Tín hiệu"]=="Thoát xu hướng (tín hiệu)").sum()))
        focus=d[d["Tín hiệu"].isin(["Mua mới (tín hiệu)","Thoát xu hướng (tín hiệu)"])]
        st.dataframe(focus[["Mã","Tín hiệu","Hạng mua mới (kỹ thuật)","RS60 (đpt)","Buy Score (%)"]],hide_index=True,use_container_width=True)
    if result and result["daily"]:
        st.subheader("Equity mô phỏng")
        st.line_chart(pd.DataFrame(result["daily"]).set_index("Ngày")[["Equity"]])

def render_opportunities():
    st.title("Cơ hội giao dịch")
    st.caption("U5: 120 mã theo dõi · 115 mã trong mẫu cố định · Khung Ngày · S0P0 / RS60")
    with st.expander("Dữ liệu tham chiếu",expanded=REF not in st.session_state):
        reference_panel()
    market_caption()
    with st.expander("Tùy chọn phạm vi",expanded=False):
        scope=st.selectbox("Phạm vi quét",("ALL","B1","B2","B3","B4"),format_func=lambda x:"Toàn bộ 120 mã" if x=="ALL" else x+" – 30 mã",key="pt09_scope")
        st.caption("Quét từng lô nếu Cloud giới hạn tài nguyên; chỉ gộp cùng phiên và cùng dấu vân tay VN-Index.")
    confirm=st.checkbox("Tôi xác nhận đơn vị giá TCBS là nghìn đồng; chỉ dùng nến đã hoàn tất",key="pt09_scan_confirm")
    if st.button("Quét cơ hội theo phiên mới nhất",type="primary",key="pt09_scan",disabled=REF not in st.session_state or not confirm):
        previous=st.session_state.pop(REPORT,None)
        st.session_state.pop(PROBE,None)
        bar=st.progress(0,text="Xác định phiên VN-Index...")
        try:
            from vnstock import Market
            ix,now=fetch_market()
            def loader(s):
                time.sleep(1.1)
                return Market("tcbs").equity(s).ohlcv(start="2022-01-01",end=now.date().isoformat(),interval="1D")
            saved=build_report(st.session_state[REF],ix,loader,scope,previous,now,lambda i,n,s:bar.progress(i/n,text=f"{i}/{n}: {s}"))
            st.session_state[REPORT]=saved
            st.rerun()
        except Exception as exc: error(exc)
        finally: bar.empty()
    saved=st.session_state.get(REPORT)
    if saved and (len(saved.get("identity",()))!=4 or saved["identity"][3]!="LIVE"): saved=None
    d=opportunities(saved)
    if saved:
        n=int((d["Kỹ thuật"]=="Khớp mẫu KT18").sum())
        a,b,c=st.columns(3);a.metric("Đã quét",f"{len(saved['rows'])}/120");b.metric("Khớp mẫu",f"{n}/115");c.metric("Mua mới kỹ thuật",int((d["Tín hiệu"]=="Mua mới (tín hiệu)").sum()))
        st.caption(f"Phiên {saved['identity'][0]} | Ghi nhận {saved['updated']}. Xếp hạng trên các mã đạt dữ liệu, không tự phê duyệt mua.")
        if saved["identity"][0]!=str(local_now().date()): st.warning("Phiên cũ: chỉ tham khảo, không ghi Paper hôm nay.")
    else: st.info("Chưa có kết quả quét phiên mới. Hiển thị Watchlist, không có giá hoặc tín hiệu giả.")
    x,y,z=st.columns([1,2,2])
    with x: q=st.text_input("Tìm mã",key="pt09_search")
    with y: sector=st.multiselect("Ngành",sorted(d["Ngành (sơ bộ)"].unique()),key="pt09_sectors")
    with z: signals=st.multiselect("Tín hiệu",list(dict.fromkeys(d["Tín hiệu"])),key="pt09_signals")
    with st.expander("Lọc chất lượng và cột chuyên sâu"):
        quality=st.multiselect("Chất lượng",list(dict.fromkeys(d["Kỹ thuật"])),key="pt09_quality")
        deep=st.checkbox("Hiện Sell Score, phiên cuối và phạm vi hồi cứu",key="pt09_deep")
    shown=filter_opportunities(d,q,sector,signals,quality)
    cols=["Mã","Ngành (sơ bộ)","Close (nghìn VND)","Tín hiệu","Hạng mua mới (kỹ thuật)","RS60 (đpt)","Buy Score (%)","GTGD 20 nến (tỷ VND)","Kỹ thuật"]
    if deep: cols+=["Sell Score (%)","Phiên cuối","Phạm vi KT18","Dữ liệu hồi cứu","Lý do"]
    st.dataframe(shown[cols],hide_index=True,use_container_width=True,height=470,column_config={
        "RS60 (đpt)":st.column_config.NumberColumn(format="%.2f"),
        "Buy Score (%)":st.column_config.NumberColumn(format="%.1f"),
        "GTGD 20 nến (tỷ VND)":st.column_config.NumberColumn(format="%.2f"),
        "Close (nghìn VND)":st.column_config.NumberColumn(format="%.2f")})
    st.caption(f"{len(shown)}/120 mã · RS60 là chênh lệch lợi nhuận giá so với VN-Index (điểm phần trăm). Thanh khoản là Close × Volume, không phải GTGD thực tế.")
    if len(shown):
        symbol=st.selectbox("Mã cần phân tích",shown["Mã"].tolist(),key="pt09_open_symbol")
        jump("Mở biểu đồ cổ phiếu",PAGES[2],"pt09_open_detail",symbol)
    if saved:
        with st.expander("Chi tiết dữ liệu và tải báo cáo"):
            errs=d[d["Kỹ thuật"]!="Khớp mẫu KT18"][["Mã","Kỹ thuật","Lý do"]]
            st.dataframe(errs,hide_index=True,use_container_width=True)
            b=io.BytesIO()
            with zipfile.ZipFile(b,"w",compression=zipfile.ZIP_DEFLATED) as z:
                z.writestr("stock_bot_pt09_co_hoi.csv",d.to_csv(index=False).encode("utf-8-sig"))
                z.writestr("manifest.json",json.dumps({"mode":"LIVE","session":saved["identity"][0],"index_sha":saved["identity"][1],"reference_sha":SHA_B,"updated":saved["updated"],"scanned":len(saved["rows"]),"forward_evidence":False},ensure_ascii=False))
            st.download_button("Tải ZIP kết quả quét",b.getvalue(),"stock_bot_pt09_co_hoi.zip","application/zip",key="pt09_scan_zip")
    st.subheader("Ghi phiên mô phỏng")
    if st.session_state.get("pt09_recorded"): st.success("Đã ghi phiên "+st.session_state["pt09_recorded"]+". Hãy sao lưu JSON.")
    paper_record("pt09_op")
    if st.session_state.get(ACCOUNT):
        try: paper_backup(st.session_state[ACCOUNT],"pt09_op_backup")
        except Exception as exc: error(exc)

def account_setup():
    account=st.session_state.get(ACCOUNT)
    st.caption("Tài khoản mới khóa cấu hình tại thời điểm tạo, 100 triệu tiền mặt; chỉ ghi sau ngày khóa.")
    if account is None and st.button("Khởi tạo tài khoản Paper",key="pt09_create"):
        try:
            st.session_state[ACCOUNT]=new_account()
            st.session_state.pop("pt09_recorded",None)
            st.rerun()
        except Exception as exc: error(exc)
    uploaded=st.file_uploader("Khôi phục JSON Paper",type="json",key="pt09_restore_file")
    replace=st.checkbox("Đã sao lưu tài khoản hiện tại, đồng ý thay thế",key="pt09_replace") if account else True
    if st.button("Khôi phục tài khoản",disabled=not replace or uploaded is None,key="pt09_restore"):
        try:
            st.session_state[ACCOUNT]=import_account(uploaded.getvalue())
            st.session_state.pop("pt09_recorded",None)
            st.rerun()
        except Exception as exc: error(exc)
    if account:
        try: paper_backup(account,"pt09_settings_backup")
        except Exception as exc: error(exc)
