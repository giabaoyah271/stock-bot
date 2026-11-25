"""PT10: daily chart reads only validated S0P0; intraday/weekly are indicators."""
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from workspace_core import SYMBOL,REPORT,REF
from workspace_ui import reference_panel,fetch_market
from unified_strategy_core import STRATEGY,COHORT,resolve_daily,single_snapshot,reference_stop,transition_history,supplemental
from signal_engine_core import local_now
from paper_trading_ui import error
from terminal_v3_ui import style_chart, GREEN, RED

def show_value(row,key):
    v=row.get(key,np.nan)
    return f"{float(v):,.2f}" if pd.notna(v) and np.isfinite(float(v)) else "—"

def render_detail(get_data):
    st.title("Phân tích cổ phiếu")
    st.caption("Chiến lược chính: "+STRATEGY+" | Khung Ngày; 1 Giờ / Tuần chỉ phân tích bổ trợ.")
    a,b,c=st.columns([2,2,1])
    with a: symbol=st.text_input("Mã cổ phiếu",value=st.session_state.get(SYMBOL,"HPG"),key="pt10_detail_symbol").strip().upper()
    with b: tf=st.selectbox("Khung thời gian",["Ngày","1 Giờ","Tuần"],key="pt10_detail_tf")
    with c:
        st.write("")
        refresh=st.button("Tải dữ liệu",key="pt10_detail_load",type="primary")
    if not symbol or not symbol.isalnum() or len(symbol)>10:
        st.error("Mã cổ phiếu không hợp lệ")
        return
    daily=tf=="Ngày";row=None;rank=pd.NA
    if daily:
        if symbol not in COHORT:
            st.info("Mã ngoài 115 mã đã nghiệm thu; không phát tín hiệu chính. Có thể xem chỉ báo bổ trợ 1 Giờ/Tuần hoặc công cụ nâng cao.")
            return
        report=st.session_state.get(REPORT)
        single=st.session_state.get("pt10_single")
        if single and single["row"]["Mã"]!=symbol: single=None
        if REF not in st.session_state and not (report and symbol in report.get("charts",{})):
            with st.expander("Dữ liệu tham chiếu",expanded=True): reference_panel()
        if refresh:
            st.session_state.pop("pt10_single",None);single=None
            try:
                # Existing scan is authoritative; do not replace its results with separate quotes.
                if report and report.get("identity",())[-1:]==("LIVE",) and symbol in report.get("charts",{}):
                    resolve_daily(report,symbol)
                    st.caption("Đọc lại biểu đồ từ bộ quét chung; muốn cập nhật phiên hãy quét lại toàn bộ.")
                else:
                    if REF not in st.session_state: raise ValueError("Cần ZIP U5-B đã xác minh")
                    from vnstock import Market
                    ix,now=fetch_market()
                    def loader(s): return Market("tcbs").equity(s).ohlcv(start="2022-01-01",end=now.date().isoformat(),interval="1D")
                    single=single_snapshot(symbol,st.session_state[REF],ix,loader,now)
                    # If there is an existing scan, do not show an inconsistent result.
                    resolve_daily(report,symbol,single)
                    st.session_state["pt10_single"]=single
            except Exception as exc: error(exc);return
        try: df,row,source,rank=resolve_daily(report,symbol,single)
        except Exception as exc:
            st.info(str(exc)+"; chọn Tải dữ liệu hoặc quét cơ hội trước. Không dùng V1 thay thế.")
            return
        st.caption(f"Nguồn: {source} | Phiên {row['Phiên cuối']} | SHA OHLCV {row['SHA lịch sử'][:12]}…")
        if row["Phiên cuối"]!=str(local_now().date()): st.warning("Phiên đã ghi nhận trước hôm nay; chỉ tham khảo, không phải tín hiệu mới hôm nay.")
        last=df.iloc[-1];quality={}
    else:
        if refresh:
            st.session_state.pop("pt10_aux",None)
            d=get_data(symbol,tf)
            if d is None or d.empty:
                st.error("Không thể kết nối dữ liệu hoặc chưa đạt chất lượng.")
                return
            st.session_state["pt10_aux"]=(symbol,tf,supplemental(d))
        saved=st.session_state.get("pt10_aux")
        if not saved or saved[:2]!=(symbol,tf):
            st.info("Chọn mã, khung thời gian và tải dữ liệu.")
            return
        df=saved[2];last=df.iloc[-1];quality={}
        st.caption("Phân tích bổ trợ: không hiển thị điểm mua/bán, trạng thái chiến lược, xếp hạng hoặc lệnh.")
    st.caption(f"Phiên dữ liệu cuối: {df.index[-1].strftime('%d/%m/%Y')} | Dữ liệu lịch sử, không phải giá thời gian thực")
    latest_date=pd.Timestamp(df.index[-1]).date()
    today_vn=pd.Timestamp.now(tz="Asia/Ho_Chi_Minh").date()
    days_old=(today_vn-latest_date).days
    if days_old<0:
        st.error("Ngày dữ liệu không hợp lệ: nằm trong tương lai.")
        return
    elif days_old>5:
        st.warning(f"Dữ liệu cách hôm nay {days_old} ngày. Hãy kiểm tra kết nối TCBS và lịch nghỉ giao dịch.")
    if daily:
        a,b,c=st.columns([1,2,1])
        a.metric(f"{symbol} Close",show_value(last,"close"))
        b.metric("Tín hiệu chính",row["Tín hiệu"])
        c.metric("RS60",show_value(last,"RS60 (đpt)")+" đpt")
        st.caption("Điểm mua: "+show_value(last,"Buy_Pct")+"% · Điểm bán: "+show_value(last,"Sell_Pct")+"% · Điểm kỹ thuật, không phải xác suất thắng.")
        st.caption("Hạng mua mới: "+(str(int(rank)) if pd.notna(rank) else "—")+" | Chỉ xếp hạng trên mã đã quét đạt dữ liệu. Không xác nhận vị thế hay phê duyệt mua.")
    else:
        cols=st.columns(4)
        for c,k in zip(cols,("close","RSI","ADX","ATR")): c.metric(k.upper(),show_value(last,k))
    st.caption("Giá và ATR theo đơn vị nguồn TCBS.")
    st.subheader("Biểu đồ kỹ thuật")
    x,y,z=st.columns([2,2,1])
    choices=["SMA20","SMA50","SMA200","Bollinger"]+(["Trailing Stop S0P0"] if daily else [])
    with x: overlays=st.multiselect("Đường giá",choices,default=["SMA50","SMA200"],key="pt10_overlays_"+tf)
    with y: panel=st.selectbox("Chỉ báo phụ",["RSI","MACD","ADX / DI","ATR","Không"],key="pt10_panel")
    with z: range_n=st.selectbox("Số nến",[60,100,200,500],index=1,key="pt10_detail_range")
    d=df.tail(range_n);rows=2 if panel=="Không" else 3
    fig=make_subplots(rows=rows,cols=1,shared_xaxes=True,vertical_spacing=.035,row_heights=[.78,.22] if rows==2 else [.62,.18,.20])
    fig.add_trace(go.Candlestick(x=d.index,open=d["open"],high=d["high"],low=d["low"],close=d["close"],name="Nến giá",increasing_line_color=GREEN,decreasing_line_color=RED),row=1,col=1)
    cmap={"SMA20":"#64B5B5","SMA50":"#D4A64A","SMA200":"#648CC9","BB_upper":"#8694A8","BB_lower":"#8694A8","KT03_Trailing":"#E08E4B"}
    lines=[]
    for k in overlays:
        lines.extend(["BB_upper","BB_lower"] if k=="Bollinger" else ["KT03_Trailing"] if k=="Trailing Stop S0P0" else [k])
    for k in lines:
        if k in d: fig.add_trace(go.Scatter(x=d.index,y=d[k],name=k,line=dict(color=cmap[k],width=1.3),connectgaps=False),row=1,col=1)
    if daily:
        changes=transition_history(df)
        for value,name,color,marker,price in [(1,"Mua mới S0P0",GREEN,"triangle-up","low"),(-1,"Thoát S0P0",RED,"triangle-down","high")]:
            m=changes[(changes["Trend"]==value)&(changes.index>=d.index[0])]
            fig.add_trace(go.Scatter(x=m.index,y=d.loc[m.index,price],mode="markers",name=name,marker=dict(color=color,symbol=marker,size=10)),row=1,col=1)
    fig.add_trace(go.Bar(x=d.index,y=d["volume"],name="Khối lượng",marker_color=np.where(d["close"]>=d["open"],GREEN,RED)),row=2,col=1)
    keys={"RSI":["RSI"],"MACD":["MACD","Signal_Line"],"ADX / DI":["ADX","Plus_DI","Minus_DI"],"ATR":["ATR"],"Không":[]}[panel]
    for k in keys:
        if k in d: fig.add_trace(go.Scatter(x=d.index,y=d[k],name=k,line=dict(width=1.4)),row=3,col=1)
    if panel=="RSI":
        for level in (30,70): fig.add_hline(y=level,line_dash="dot",line_color="#8994A3",row=3,col=1)
    fig.update_layout(height=650 if rows==3 else 530,xaxis_rangeslider_visible=False,margin=dict(l=8,r=8,t=8,b=8),legend=dict(orientation="h"),hovermode="x unified")
    if daily:
        chart_col,risk_col=st.columns([7,3])
        with chart_col:
            st.plotly_chart(style_chart(fig,600 if rows==3 else 500,f"{symbol}-{tf}-{range_n}-{panel}"),use_container_width=True,config={"scrollZoom":True,"displaylogo":False},key="pt10_stock_chart")
        with risk_col:
            st.subheader("Quản trị rủi ro")
            st.metric("Trailing Stop S0P0",show_value(last,"KT03_Trailing"))
            st.metric("Tham chiếu R1",f"{reference_stop(df):.2f}")
            st.caption("Nghìn VND · R1 (Close − 2 ATR) chỉ dùng sizing khi có mua mới; không phải lệnh Stop bổ sung hoặc giá khớp bảo đảm.")
            st.markdown("**Lý do tín hiệu**")
            st.write(row["Lý do"] or "Không có lý do thoát mới được ghi nhận.")
            st.caption("Trạng thái kỹ thuật không đồng nghĩa vị thế Paper hoặc lệnh đã khớp.")
    else:
        st.plotly_chart(style_chart(fig,600 if rows==3 else 500,f"{symbol}-{tf}-{range_n}-{panel}"),use_container_width=True,config={"scrollZoom":True,"displaylogo":False},key="pt10_stock_chart")
    if daily:
        with st.expander("Điểm số và lý do tín hiệu"):
            st.write(row["Lý do"] or "Không có lý do thoát mới được ghi nhận.")
            fields=["SMA50","SMA200","RSI","MACD","ADX","ATR","Buy_Pct","Sell_Pct","RS60 (đpt)"]
            st.dataframe(pd.DataFrame([last[fields]]).round(3),hide_index=True,use_container_width=True)
        with st.expander("Lịch sử chuyển trạng thái S0P0"):
            h=changes.tail(50).copy();h["Trend"]=h["Trend"].map({1:"Mua mới",-1:"Thoát"})
            st.dataframe(h.iloc[::-1],use_container_width=True)
    with st.expander("Chất lượng dữ liệu nguồn"):
        st.write("Số nến:",len(df),"| Trùng timestamp:",int(df.index.duplicated().sum()))
        st.dataframe(df[["open","high","low","close","volume"]].tail(5),use_container_width=True)
