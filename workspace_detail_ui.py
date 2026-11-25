"""PT09 compact chart workstation, uses unchanged get_data and V1 indicators."""
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from workspace_core import SYMBOL,REPORT
from signal_engine_core import local_days

def show_value(row,key):
    v=row.get(key,np.nan)
    return f"{float(v):,.2f}" if pd.notna(v) and np.isfinite(float(v)) else "—"

def render_detail(get_data):
    st.title("Phân tích cổ phiếu")
    st.caption("Biểu đồ và chỉ báo kỹ thuật V1; không phải lệnh của ứng viên U5-A0-RS60.")
    a,b,c=st.columns([2,2,1])
    with a: symbol=st.text_input("Mã cổ phiếu",value=st.session_state.get(SYMBOL,"HPG"),key="pt09_detail_symbol").strip().upper()
    with b: tf=st.selectbox("Khung thời gian",["Ngày","1 Giờ","Tuần"],key="pt09_detail_tf")
    with c:
        st.write("")
        refresh=st.button("Tải dữ liệu",key="pt09_detail_load",type="primary")
    if refresh:
        st.session_state.pop("pt09_detail_data",None)
        if not symbol or not symbol.isalnum() or len(symbol)>10:
            st.error("Mã cổ phiếu không hợp lệ")
            return
        df=get_data(symbol,tf)
        if df is None or df.empty:
            st.error("Không thể kết nối dữ liệu hoặc chưa đạt chất lượng.")
            return
        st.session_state[SYMBOL]=symbol
        st.session_state["pt09_detail_data"]=(symbol,tf,df)
    saved=st.session_state.get("pt09_detail_data")
    if not saved or saved[:2]!=(symbol,tf):
        st.info("Chọn mã, khung thời gian và tải dữ liệu.")
        return
    df=saved[2];last=df.iloc[-1];quality=df.attrs.get("daily_quality",{})
    st.caption(f"Phiên dữ liệu cuối: {df.index[-1].strftime('%d/%m/%Y')} | Dữ liệu lịch sử, không phải giá thời gian thực")
    if tf=="Ngày":
        st.caption(f"Data Quality Gate: ĐẠT | {len(df):,} nến ngày đã kiểm tra trước tính chỉ báo.")
        if quality.get("trimmed"): st.info("Đã loại nến ngày hiện tại trước 15:15 giờ Việt Nam.")
        if quality.get("zero_volume"): st.warning(f"Có {quality['zero_volume']} nến khối lượng bằng 0; cần xem xét khả năng khớp lệnh.")
        latest_date=pd.Timestamp(quality.get("last_date",df.index[-1])).date()
    else: latest_date=pd.Timestamp(df.index[-1]).date()
    today_vn=pd.Timestamp.now(tz="Asia/Ho_Chi_Minh").date()
    days_old=(today_vn-latest_date).days
    if days_old<0:
        st.error("Ngày dữ liệu không hợp lệ: nằm trong tương lai.")
    elif days_old>5:
        st.warning(f"Dữ liệu cách hôm nay {days_old} ngày. Hãy kiểm tra kết nối TCBS và lịch nghỉ giao dịch.")
    cols=st.columns(5)
    cols[0].metric(f"{symbol} Close",show_value(last,"close"))
    cols[1].metric("Xu hướng V1","Xanh" if last["Trend"]==1 else "Đỏ")
    cols[2].metric("Điểm mua V1",show_value(last,"Buy_Pct")+"%")
    cols[3].metric("Điểm bán V1",show_value(last,"Sell_Pct")+"%")
    cols[4].metric("ATR",show_value(last,"ATR"))
    st.caption("Giá và ATR theo đơn vị nguồn TCBS. Xanh/đỏ là trạng thái kỹ thuật, không xác nhận vị thế.")
    x,y=st.columns([2,2])
    with x: overlays=st.multiselect("Đường giá",["SMA20","SMA50","SMA200","Bollinger","Trailing Stop V1"],default=["SMA50","SMA200"],key="pt09_detail_overlays")
    with y: panel=st.selectbox("Chỉ báo phụ",["RSI","MACD","ADX / DI","ATR","Không"],key="pt09_detail_panel")
    range_n=st.selectbox("Số nến hiển thị",[60,100,200,500],index=1,key="pt09_detail_range")
    d=df.tail(range_n);rows=2 if panel=="Không" else 3
    fig=make_subplots(rows=rows,cols=1,shared_xaxes=True,vertical_spacing=.035,row_heights=[.78,.22] if rows==2 else [.62,.18,.20])
    fig.add_trace(go.Candlestick(x=d.index,open=d["open"],high=d["high"],low=d["low"],close=d["close"],name="Nến giá"),row=1,col=1)
    cmap={"SMA20":"#64B5B5","SMA50":"#D4A64A","SMA200":"#648CC9","BB_upper":"#8694A8","BB_lower":"#8694A8","V1_Trailing_Stop":"#E08E4B"}
    lines=[]
    for k in overlays:
        lines.extend(["BB_upper","BB_lower"] if k=="Bollinger" else ["V1_Trailing_Stop"] if k=="Trailing Stop V1" else [k])
    for k in lines:
        if k in d: fig.add_trace(go.Scatter(x=d.index,y=d[k],name=k,line=dict(color=cmap[k],width=1.3),connectgaps=False),row=1,col=1)
    changes=df.loc[df["Trend"].ne(df["Trend"].shift())].iloc[1:]
    for value,name,color,marker,price in [(1,"Mua V1","#24966F","triangle-up","low"),(-1,"Thoát V1","#D45B5B","triangle-down","high")]:
        m=changes[(changes["Trend"]==value)&(changes.index>=d.index[0])]
        fig.add_trace(go.Scatter(x=m.index,y=m[price],mode="markers",name=name,marker=dict(color=color,symbol=marker,size=10)),row=1,col=1)
    fig.add_trace(go.Bar(x=d.index,y=d["volume"],name="Khối lượng",marker_color=np.where(d["close"]>=d["open"],"#26966F","#C65353")),row=2,col=1)
    keys={"RSI":["RSI"],"MACD":["MACD","Signal_Line"],"ADX / DI":["ADX","Plus_DI","Minus_DI"],"ATR":["ATR"],"Không":[]}[panel]
    for k in keys:
        if k in d: fig.add_trace(go.Scatter(x=d.index,y=d[k],name=k,line=dict(width=1.4)),row=3,col=1)
    if panel=="RSI":
        for level in (30,70): fig.add_hline(y=level,line_dash="dot",line_color="#8994A3",row=3,col=1)
    fig.update_layout(height=650 if rows==3 else 530,xaxis_rangeslider_visible=False,margin=dict(l=8,r=8,t=8,b=8),legend=dict(orientation="h"),hovermode="x unified")
    st.plotly_chart(fig,use_container_width=True,config={"scrollZoom":True},key="pt09_stock_chart")
    if tf=="Ngày" and last["Trend"]==1 and "V1_Trailing_Stop" in last:
        st.caption("Trailing Stop V1: "+show_value(last,"V1_Trailing_Stop")+" | "+("Đủ điều kiện kiểm tra" if last["V1_Stop_Eligible"] else "Chưa đủ 3 nến từ tín hiệu mua")+". Không phải giá khớp đảm bảo.")
    with st.expander("Điểm số và lý do tín hiệu",expanded=False):
        st.write(str(last.get("Reason","")))
        fields=[k for k in ("SMA20","SMA50","SMA200","RSI","MACD","Signal_Line","ADX","Plus_DI","Minus_DI","ATR","Buy_Pct","Sell_Pct") if k in df]
        st.dataframe(pd.DataFrame([last[fields]]).round(3),hide_index=True,use_container_width=True)
    if tf=="Ngày":
        r=st.session_state.get(REPORT)
        match=r and len(r.get("identity",()))==4 and r["identity"][3]=="LIVE" and r["identity"][0]==str(latest_date)
        if match:
            x=r["rows"].get(symbol,{})
            if x.get("Kỹ thuật")=="Khớp mẫu KT18":
                st.subheader("Ứng viên S0P0 – RS60")
                st.caption("Nguồn bộ quét U5 cùng ngày; độc lập với biểu đồ V1 ở trên.")
                st.write(f"{x['Tín hiệu']} | RS60 {x['RS60 (đpt)']:+.2f} đpt | Điểm mua {x['Buy Score (%)']:.1f}%")
    with st.expander("Lịch sử chuyển trạng thái V1",expanded=False):
        h=changes[["close","Trend","Buy_Pct","Sell_Pct","Reason"]].tail(50).copy()
        h["Trend"]=h["Trend"].map({1:"Mua mới",-1:"Thoát"})
        st.dataframe(h.iloc[::-1],use_container_width=True)
    with st.expander("Chất lượng dữ liệu nguồn",expanded=False):
        st.write("Số nến:",len(df),"| Trùng timestamp:",int(df.index.duplicated().sum()))
        st.dataframe(df[["open","high","low","close","volume"]].tail(5),use_container_width=True)
