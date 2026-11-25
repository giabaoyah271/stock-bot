"""Stock Bot V3 presentation layer. No market, ranking or paper decisions."""
import streamlit as st

BG="#020617"
SURFACE="#0F172A"
ELEVATED="#1E293B"
BORDER="#334155"
TEXT="#F8FAFC"
SECONDARY="#94A3B8"
BLUE="#60A5FA"
GREEN="#22C55E"
RED="#EF4444"
AMBER="#F59E0B"

MENU=("Tổng quan","Cơ hội giao dịch","Phân tích cổ phiếu","Danh mục","Nghiên cứu","Hệ thống")
MENU_KEY="v3_terminal_menu"
GROUP_KEY="v3_terminal_group"
RESEARCH_IDS=(1,2,3,4)
SYSTEM_IDS=(0,5,6)

def apply_theme():
    st.markdown("""
<style>
.stApp {font-variant-numeric: tabular-nums;}
.block-container {max-width: 1680px; padding: 1.4rem 2rem 2.5rem;}
h1 {font-size: 1.85rem !important; letter-spacing:-.035em; line-height:1.2;}
h2 {font-size: 1.25rem !important; letter-spacing:-.015em;}
h3 {font-size: 1.05rem !important;}
[data-testid="stSidebar"] {border-right:1px solid #334155;}
[data-testid="stSidebar"] [data-testid="stRadio"] label {padding: 7px 4px;}
[data-testid="stMetric"] {background:#0F172A; border:1px solid #334155; border-radius:8px; padding:12px; min-width:0;}
[data-testid="stMetricLabel"] p {font-size:.84rem; white-space:normal;}
[data-testid="stMetricValue"] {font-variant-numeric:tabular-nums; font-size:clamp(1.05rem,1.45vw,1.65rem);}
[data-testid="stMetricValue"] > div {white-space:normal; overflow-wrap:anywhere;}
[data-testid="stDataFrame"] {border:1px solid #334155; border-radius:6px;}
button:focus-visible, input:focus-visible, [role="radio"]:focus-visible, [role="combobox"]:focus-visible {outline:2px solid #93C5FD; outline-offset:2px;}
@media (max-width: 767px) {
 .block-container {padding: 1rem .85rem 2rem;}
 [data-testid="stHorizontalBlock"] {flex-wrap:wrap;}
 [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {flex:1 1 100% !important; min-width:0; width:100% !important;}
 [data-testid="stMetricValue"] {font-size:1.35rem;}
 button {min-height:44px;}
}
@media (prefers-reduced-motion: reduce) {
 *, *::before, *::after {scroll-behavior:auto !important; animation-duration:.01ms !important; transition-duration:.01ms !important;}
}
</style>
""",unsafe_allow_html=True)

def menu_for_page(page,pages,group):
    if page in pages[:4]:
        return MENU[pages.index(page)]
    return MENU[4] if group==MENU[4] else MENU[5]

def page_for_menu(menu,pages):
    return pages[MENU.index(menu)] if menu in MENU[:4] else pages[4]

def workspace_navigation(pages,nav,advanced):
    state=st.session_state
    state.setdefault(nav,pages[0])
    desired=menu_for_page(state[nav],pages,state.get(GROUP_KEY,MENU[5]))
    if state.get(MENU_KEY)!=desired:
        state[MENU_KEY]=desired
    def navigate():
        selected=state[MENU_KEY]
        state[nav]=page_for_menu(selected,pages)
        if selected in MENU[4:]:
            state[GROUP_KEY]=selected
    st.sidebar.markdown("### STOCK BOT V3")
    st.sidebar.caption("TRADING TERMINAL")
    chosen=st.sidebar.radio("Không gian làm việc",MENU,key=MENU_KEY,on_change=navigate)
    st.sidebar.divider()
    st.sidebar.caption("U5-A0-RS60-P5-R050 · Paper nghiên cứu")
    st.sidebar.caption("TCBS · "+state.get("v3_auth_result","Chưa xác nhận xác thực trong phiên"))
    st.sidebar.caption("Không đặt lệnh thật · Không phải dữ liệu trực tiếp")
    page=page_for_menu(chosen,pages)
    tool=None
    if chosen in MENU[4:]:
        ids=RESEARCH_IDS if chosen==MENU[4] else SYSTEM_IDS
        tool=st.sidebar.selectbox("Công cụ",tuple(advanced[i] for i in ids),key="v3_tool_"+("research" if chosen==MENU[4] else "system"))
    return page,tool

def readiness_strip(ref,probe,report,account):
    state=st.session_state
    r=state.get(report)
    live=bool(r and len(r.get("identity",()))==4 and r["identity"][3]=="LIVE")
    cols=st.columns([2,2,3])
    cols[0].caption("THAM CHIẾU U5-B")
    cols[0].markdown("**Đã xác minh**" if ref in state else "**Chưa tải ZIP**")
    cols[1].caption("PAPER TRADING")
    cols[1].markdown("**Đã có tài khoản**" if state.get(account) else "**Chưa khởi tạo**")
    cols[2].caption("BÁO CÁO QUÉT LIVE")
    cols[2].markdown("**"+str(r["identity"][0])+"**" if live else "**Chưa có báo cáo LIVE**")
    st.divider()

def style_chart(fig,height=None,revision=None):
    settings=dict(template="plotly_dark",paper_bgcolor=BG,plot_bgcolor=BG,
        font=dict(family="IBM Plex Sans, Arial, sans-serif",color=TEXT,size=12),
        margin=dict(l=8,r=12,t=24,b=12),hoverlabel=dict(bgcolor=SURFACE,font_color=TEXT),
        legend=dict(orientation="h",y=1.02,yanchor="bottom",x=0))
    if height is not None: settings["height"]=height
    if revision is not None: settings["uirevision"]=revision
    fig.update_layout(**settings)
    fig.update_xaxes(gridcolor=ELEVATED,rangeslider_visible=False,zeroline=False)
    fig.update_yaxes(gridcolor=ELEVATED,zerolinecolor=BORDER,side="right")
    return fig

def line_chart(frame,key,title=None):
    import plotly.graph_objects as go
    fig=go.Figure()
    for col in frame.columns:
        color=RED if "Drawdown" in col else BLUE
        fig.add_trace(go.Scatter(x=frame.index,y=frame[col],name=str(col),mode="lines",line=dict(color=color,width=2)))
    fig.update_layout(hovermode="x unified",showlegend=len(frame.columns)>1)
    if title: st.markdown("**"+title+"**")
    st.plotly_chart(style_chart(fig,290),use_container_width=True,config={"displaylogo":False},key=key)
