"""Presentation helpers for Stock Bot. No trading rules are defined here."""
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from backtesting import tao_bang_giao_dich
from performance_metrics import profit_factor_money

BG = "#020617"
SURFACE = "#0F172A"
BORDER = "#334155"
TEXT = "#F8FAFC"
MUTED = "#94A3B8"
BLUE = "#60A5FA"
GREEN = "#22C55E"
RED = "#EF4444"
AMBER = "#F59E0B"
PAGES = ("Giao dịch", "Quét tín hiệu", "Nghiên cứu", "Hệ thống")
TIMEFRAMES = ("1 Giờ", "Ngày", "Tuần")

def apply_style():
    st.markdown("""
<style>
.stApp {font-variant-numeric: tabular-nums;}
.block-container {max-width: 1680px; padding-top: 2rem; padding-bottom: 2rem;}
h1,h2,h3 {letter-spacing: -.025em;}
[data-testid="stMetric"] {background: #0F172A; border: 1px solid #334155; border-radius: 8px; padding: 12px;}
[data-testid="stMetricValue"] {font-variant-numeric: tabular-nums;}
button:focus-visible, input:focus-visible, [role="radio"]:focus-visible {outline: 2px solid #93C5FD; outline-offset: 2px;}
@media (max-width: 767px) {
 .block-container {padding: 1rem .85rem 2rem;}
 [data-testid="stHorizontalBlock"] {flex-wrap: wrap;}
 [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {flex: 1 1 100% !important; min-width: 0;}
 button {min-height: 44px;}
}
@media (prefers-reduced-motion: reduce) {
 *, *::before, *::after {scroll-behavior: auto !important; animation-duration: .01ms !important; transition-duration: .01ms !important;}
}
</style>
""", unsafe_allow_html=True)

def number(value, digits=2, suffix=""):
    try:
        v = float(value)
        return f"{v:,.{digits}f}{suffix}" if np.isfinite(v) else "—"
    except (TypeError, ValueError):
        return "—"

def shell():
    apply_style()
    pending = st.session_state.pop("terminal_pending", None)
    if pending:
        st.session_state["terminal_symbol"] = pending[0]
        st.session_state["terminal_tf"] = pending[1]
        st.session_state["terminal_page"] = "Giao dịch"
    st.title("STOCK BOT")
    st.caption("TRADING INTELLIGENCE  /  Dữ liệu lịch sử · Không đặt lệnh thật")
    st.caption("TCBS · " + st.session_state.get("terminal_auth", "Chưa xác nhận xác thực trong phiên"))
    return st.radio("Khu vực", PAGES, horizontal=True, key="terminal_page")

def _save_symbol():
    st.session_state["terminal_symbol"] = st.session_state["terminal_symbol_input"].strip().upper()

def _save_tf():
    st.session_state["terminal_tf"] = st.session_state["terminal_tf_input"]

def controls(include_symbol=True, fixed_daily=False):
    st.session_state.setdefault("terminal_symbol", "HPG")
    st.session_state.setdefault("terminal_tf", "Ngày")
    if include_symbol:
        st.session_state.setdefault("terminal_symbol_input", st.session_state["terminal_symbol"])
        # Scanner navigation must overwrite a stale widget value before rendering.
        if st.session_state["terminal_symbol_input"] != st.session_state["terminal_symbol"]:
            st.session_state["terminal_symbol_input"] = st.session_state["terminal_symbol"]
        st.text_input("Mã cổ phiếu", key="terminal_symbol_input", on_change=_save_symbol)
    if fixed_daily:
        st.caption("Khung thời gian nghiên cứu: Ngày")
        return st.session_state["terminal_symbol"], "Ngày"
    st.session_state.setdefault("terminal_tf_input", st.session_state["terminal_tf"])
    if st.session_state["terminal_tf_input"] != st.session_state["terminal_tf"]:
        st.session_state["terminal_tf_input"] = st.session_state["terminal_tf"]
    st.radio("Khung thời gian", TIMEFRAMES, horizontal=True, key="terminal_tf_input", on_change=_save_tf)
    return st.session_state["terminal_symbol"], st.session_state["terminal_tf"]

def ready(df):
    return df is not None and not df.empty and {"Trend","Buy_Pct","Sell_Pct","Reason","ATR","close","open","high","low","volume","SMA20","RSI"}.issubset(df.columns)

def render_auth(sources):
    with st.form("tcbs_auth_form", clear_on_submit=True):
        tcbs_otp = st.text_input(
            "Smart OTP TCBS",
            type="password"
        )
        tcbs_submit = st.form_submit_button("Xác thực TCBS")

    if tcbs_submit:
        if not tcbs_otp.strip():
            st.warning("Vui lòng nhập Smart OTP.")
        else:
            try:
                sources.authenticate(
                    "tcbs",
                    otp=tcbs_otp.strip()
                )
                st.cache_data.clear()
                st.session_state.pop("terminal_scan", None)
                st.session_state["terminal_auth"] = "Đã xác thực trong phiên"
                st.success("Đã xác thực TCBS thành công!")
            except Exception as e:
                st.session_state["terminal_auth"] = "Xác thực thất bại"
                st.error(
                    f"Xác thực thất bại: {type(e).__name__}"
                )

def render_history(df):
    with st.expander("Lịch sử tín hiệu 30 nến gần nhất"):
        columns = [
            "close", "RSI", "ADX",
            "Plus_DI", "Minus_DI",
            "MACD", "Signal_Line",
            "Buy_Pct", "Sell_Pct",
            "Trend", "Reason"
        ]

        history = df[columns].tail(30).copy()

        history["Trạng thái"] = history["Trend"].map({
            1: "Vùng xanh",
            -1: "Vùng đỏ"
        })

        history = history.drop(columns=["Trend"])

        st.dataframe(
            history.round(2),
            use_container_width=True
        )
        # Lich su chuyen trang thai
        st.markdown("**Các lần thay đổi tín hiệu gần nhất**")

        changed = (
            df["Trend"].ne(df["Trend"].shift())
            & df["Trend"].shift().notna()
        )

        events = df.loc[
            changed,
            ["close", "Trend", "Buy_Pct", "Sell_Pct", "Reason"]
        ].copy()

        events["Tín hiệu"] = events["Trend"].map({
            1: "Chuyển sang vùng xanh",
            -1: "Chuyển sang vùng đỏ"
        })

        if events.empty:
            st.info("Chưa có lần thay đổi tín hiệu.")
        else:
            st.dataframe(
                events[
                    ["Tín hiệu", "close", "Buy_Pct", "Sell_Pct", "Reason"]
                ].tail(20).iloc[::-1].round(2),
                use_container_width=True
            )

def render_comparison(df):
    with st.expander("So sánh điểm mua/bán V1 và V2"):
        try:
            from scoring_v2 import tinh_diem_v2

            df_v2 = tinh_diem_v2(df)

            so_sanh = df_v2[
                [
                    "Buy_Pct",
                    "Sell_Pct",
                    "V2_Buy_Pct",
                    "V2_Sell_Pct",
                    "V2_Ready"
                ]
            ].tail(10).copy()

            so_sanh = so_sanh.rename(columns={
                "Buy_Pct": "Điểm mua V1",
                "Sell_Pct": "Điểm bán V1",
                "V2_Buy_Pct": "Điểm mua V2",
                "V2_Sell_Pct": "Điểm bán V2",
                "V2_Ready": "Đủ dữ liệu V2"
            })

            st.dataframe(
                so_sanh.round(2),
                use_container_width=True
            )

            st.caption(
                "V2 chỉ đang thử nghiệm cách chấm điểm. "
                "Chưa thay đổi tín hiệu giao dịch hiện tại."
            )

        except Exception as e:
            st.warning(
                f"Chưa thể tính điểm V2: {type(e).__name__}"
            )

def render_single_backtest(df):
    with st.expander("Backtesting - Giao dịch mô phỏng"):
        try:
            trades = tao_bang_giao_dich(df)
        
            # Kiem tra Backtesting goc va ban thu nghiem
            try:
                from strategy_experiments import chay_backtest_thu_nghiem
                from strategy_experiments import chay_backtest_diem_v2
                from v21_macd_strategy import chay_backtest_diem_v21_macd

                thu_goc = chay_backtest_thu_nghiem(
                    df, bo_loc="goc"
                )

                cot = [
                    c for c in trades.columns
                    if c != "Lý do bán"
                ]

                trung_khop = (
                    len(trades) == len(thu_goc)
                    and trades[cot].reset_index(drop=True).equals(
                        thu_goc[cot].reset_index(drop=True)
                    )
                )

                if trung_khop:
                    st.success(
                        "Kiểm tra thành công: "
                        "Backtesting gốc và bản thử nghiệm khớp nhau."
                    )
            
                    # V2.1: CHI PHAN TICH CAC LENH DA DONG, KHONG DOI CHIEN LUOC
                    with st.expander("V2.1 - Phân tích giao dịch V1/V2"):
                        try:
                            from v21_trade_audit import phan_tich_giao_dich_v21

                            trades_v2_audit = chay_backtest_diem_v2(df)
                            tong_hop_v21, doi_chieu_v21, lenh_lo_v21, rieng_v1 = (
                                phan_tich_giao_dich_v21(
                                    df, trades, trades_v2_audit
                                )
                            )

                            st.markdown("**Thống kê giao dịch đã đóng**")
                            st.dataframe(
                                tong_hop_v21,
                                hide_index=True,
                                use_container_width=True,
                            )

                            st.markdown("**Đối chiếu giao dịch V2 với V1**")
                            st.dataframe(
                                doi_chieu_v21.iloc[::-1].round(2),
                                hide_index=True,
                                use_container_width=True,
                            )

                            st.markdown("**Giao dịch V2 thua lỗ (lỗ lớn nhất trước)**")
                            if lenh_lo_v21.empty:
                                st.info("V2 chưa có giao dịch thua lỗ đã đóng.")
                            else:
                                st.dataframe(
                                    lenh_lo_v21.round(2),
                                    hide_index=True,
                                    use_container_width=True,
                                )

                            st.markdown("**Giao dịch V1 không chồng lấn V2**")
                            if rieng_v1.empty:
                                st.info("Không có giao dịch V1 riêng không chồng lấn.")
                            else:
                                st.dataframe(
                                    rieng_v1.iloc[::-1].round(2),
                                    hide_index=True,
                                    use_container_width=True,
                                )

                            st.caption(
                                "Chỉ đối chiếu các giao dịch đã đóng. "
                                "Trùng ngày mua khác với chồng lấn thời gian nắm giữ. "
                                "Chỉ báo mua lấy tại ngày phát tín hiệu; "
                                "không kết luận nguyên nhân thua lỗ hoặc hiệu quả ngoài mẫu."
                            )
                        except Exception as e:
                            st.warning(
                                "Chưa thể hiển thị phân tích V2.1: "
                                f"{type(e).__name__}: {e}"
                            )

                    # SO SANH 5 CHIEN LUOC DOC LAP
                    st.markdown(
                        "**So sánh Backtesting 5 chiến lược**"
                    )

                    ket_qua = []

                    for ten, bt in [
                        ("Chiến lược gốc", trades),
                        ("Lọc SMA50/SMA200",
                         chay_backtest_thu_nghiem(df, "sma")),
                        ("Lọc ADX + DI + MACD",
                         chay_backtest_thu_nghiem(df, "adx_macd")),
                        ("Chấm điểm V2",
                         chay_backtest_diem_v2(df)),
                        ("V2.1 - Xác nhận MACD",
                         chay_backtest_diem_v21_macd(df))
                    ]:
                        r = pd.to_numeric(
                            bt["Lợi nhuận sau chi phí (%)"],
                            errors="coerce"
                        ).dropna()

                        if r.empty:
                            ket_qua.append({
                                "Chiến lược": ten,
                                "Số lệnh": 0,
                                "Win Rate (%)": None,
                                "Lợi nhuận TB (%)": None,
                                "Profit Factor": None,
                                "Sụt giảm vốn (%)": None
                            })
                            continue

                        pf = profit_factor_money(r)

                        von = pd.concat(
                            [
                                pd.Series([1.0]),
                                (1 + r / 100).cumprod()
                                .reset_index(drop=True)
                            ],
                            ignore_index=True
                        )

                        dd = (
                            von / von.cummax() - 1
                        ).min() * 100

                        ket_qua.append({
                            "Chiến lược": ten,
                            "Số lệnh": len(r),
                            "Win Rate (%)": round(
                                (r > 0).mean() * 100, 1
                            ),
                            "Lợi nhuận TB (%)": round(r.mean(), 2),
                            "Profit Factor": (
                                round(pf, 2)
                                if pf is not None else None
                            ),
                            "Sụt giảm vốn (%)": round(dd, 2)
                        })

                    st.dataframe(
                        pd.DataFrame(ket_qua),
                        hide_index=True,
                        use_container_width=True
                    )

                    st.caption(
                        "Backtesting thử nghiệm trên cùng dữ liệu. "
                        "Sụt giảm vốn chỉ tính sau các lệnh đã đóng. "
                        "Chưa kiểm định ngoài mẫu."
                    )
                else:
                    st.warning(
                        "Hai phiên bản chưa khớp. "
                        f"Gốc: {len(trades)} giao dịch; "
                        f"thử nghiệm: {len(thu_goc)} giao dịch."
                    )

            except Exception as e:
                st.warning(
                    f"Lỗi kiểm tra: {type(e).__name__}: {str(e)[:200]}"
                )


            if trades.empty:
                st.info("Chưa có giao dịch hoàn tất.")
            else:
                st.write(f"Số giao dịch: {len(trades)}")
                st.dataframe(
                    trades.iloc[::-1],
                    use_container_width=True
                )
            
                # Thong ke hieu qua giao dich
                returns = pd.to_numeric(
                    trades["Lợi nhuận sau chi phí (%)"],
                    errors="coerce"
                ).dropna()

                win_rate = (returns > 0).mean() * 100
                avg_return = returns.mean()

                st.metric(
                    "Tỷ lệ giao dịch có lãi",
                    f"{win_rate:.1f}%"
                )
                st.metric(
                    "Lợi nhuận trung bình mỗi giao dịch",
                    f"{avg_return:.2f}%"
                )
            
                # Profit Factor trên số tiền lãi/lỗ, tái đầu tư toàn bộ vốn.
                profit_factor = profit_factor_money(returns)
                pf_text = (
                    f"{profit_factor:.2f}" if profit_factor is not None
                    else "Không có lệnh lỗ"
                )

                # Muc sut giam von sau cac lenh da dong
                growth = (1 + returns / 100).cumprod()
                equity = pd.concat(
                    [pd.Series([1.0]), growth.reset_index(drop=True)],
                    ignore_index=True
                )

                drawdown = (equity / equity.cummax() - 1) * 100

                col_pf, col_dd = st.columns(2)
                col_pf.metric("Profit Factor (theo tiền)", pf_text)
                col_dd.metric(
                    "Sụt giảm vốn sau các lệnh đã đóng",
                    f"{drawdown.min():.2f}%"
                )
            
                # Bieu do tang truong von mo phong
                equity_chart = pd.DataFrame(
                    {
                        "Vốn mô phỏng": equity.to_numpy() * 100
                    },
                    index=range(len(equity))
                )

                equity_chart.index.name = "Số giao dịch đã đóng"

                st.markdown("**Đường cong vốn mô phỏng**")
                st.line_chart(equity_chart)
                # SO SANH BO LOC XU HUONG
                from strategy_experiments import danh_gia_bo_loc_xu_huong

                filtered = danh_gia_bo_loc_xu_huong(df, trades)
                selected = filtered[
                    filtered["Đạt bộ lọc xu hướng"]
                ]

                st.markdown("**So sánh bộ lọc xu hướng SMA50/SMA200**")

                comparisons = []

                for name, group in [
                    ("Chiến lược gốc", trades),
                    ("Giao dịch đạt bộ lọc", selected)
                ]:
                    r = pd.to_numeric(
                        group["Lợi nhuận sau chi phí (%)"],
                        errors="coerce"
                    ).dropna()

                    if r.empty:
                        comparisons.append({
                            "Phương án": name,
                            "Số giao dịch": 0,
                            "Win Rate (%)": None,
                            "Lợi nhuận TB (%)": None,
                            "Profit Factor": None,
                            "Sụt giảm vốn (%)": None
                        })
                        continue

                    pf = profit_factor_money(r)

                    growth_test = (1 + r / 100).cumprod()
                    capital = pd.concat(
                        [
                            pd.Series([1.0]),
                            growth_test.reset_index(drop=True)
                        ],
                        ignore_index=True
                    )
                    dd = (capital / capital.cummax() - 1).min() * 100

                    comparisons.append({
                        "Phương án": name,
                        "Số giao dịch": len(r),
                        "Win Rate (%)": round((r > 0).mean() * 100, 1),
                        "Lợi nhuận TB (%)": round(r.mean(), 2),
                        "Profit Factor": (
                            round(pf, 2) if pf is not None else None
                        ),
                        "Sụt giảm vốn (%)": round(dd, 2)
                    })

                st.dataframe(
                    pd.DataFrame(comparisons),
                    hide_index=True,
                    use_container_width=True
                )

                st.caption(
                    "Thử nghiệm sàng lọc các giao dịch đã đóng. "
                    "Chưa phải Backtesting độc lập của chiến lược mới."
                )


                st.caption(
                    "Vốn ban đầu quy ước bằng 100. "
                    "Giả định tái đầu tư toàn bộ vốn sau mỗi giao dịch. "
                    "Chỉ phản ánh các giao dịch đã đóng, "
                    "chưa bao gồm biến động vốn trong lúc nắm giữ."
                )

            st.caption(
                "Mô phỏng khớp lệnh ở giá mở cửa phiên tiếp theo. "
                "Đã tính chi phí giả định. "
                "Chưa phản ánh đầy đủ giao dịch thực tế."
            )

        except Exception as e:
            st.error(
                f"Lỗi Backtesting: {type(e).__name__}"
            )

def render_quality(df):
    with st.expander("Kiểm tra chất lượng dữ liệu TCBS"):
        cols = ["open", "high", "low", "close", "volume"]
        data = df[cols].apply(pd.to_numeric, errors="coerce")

        missing = int(data.isna().any(axis=1).sum())
        duplicates = int(df.index.duplicated().sum())

        invalid_prices = (
            (data["low"] > data["high"])
            | (data["high"] < data[["open", "close"]].max(axis=1))
            | (data["low"] > data[["open", "close"]].min(axis=1))
            | (data[["open", "high", "low", "close"]] <= 0).any(axis=1)
        )

        invalid_volume = int((data["volume"] < 0).sum())

        st.write(f"Tổng số nến: {len(df):,}")
        st.write(f"Nến thiếu dữ liệu: {missing}")
        st.write(f"Thời gian trùng lặp: {duplicates}")
        st.write(f"Nến có giá bất hợp lý: {int(invalid_prices.sum())}")
        st.write(f"Nến có khối lượng âm: {invalid_volume}")

        st.write("5 nến gần nhất:")
        st.dataframe(data.tail(5), use_container_width=True)

def render_chart(df, symbol, timeframe):
    options = [c for c in ("SMA20", "SMA50", "SMA200") if c in df]
    chosen = st.multiselect("Đường trung bình hiển thị", options, default=["SMA20"] if "SMA20" in options else [], key="terminal_ma")
    extras = [c for c in ("RSI","MACD","ADX","ATR") if c in df]
    indicator = st.selectbox("Chỉ báo dưới biểu đồ", extras, key="terminal_indicator") if extras else None
    count = st.selectbox("Số nến hiển thị", [60,100,200,400], index=1, key="terminal_chart_count")
    rows = 3 if indicator else 2
    fig = make_subplots(rows=rows, cols=1, shared_xaxes=True, vertical_spacing=.035,
                        row_heights=[.65,.16,.19] if indicator else [.8,.2])
    fig.add_trace(go.Candlestick(x=df.index, open=df.open, high=df.high, low=df.low, close=df.close,
                    increasing_line_color=GREEN, decreasing_line_color=RED, name="Nến giá"), row=1,col=1)
    for ma,color in zip(("SMA20","SMA50","SMA200"),(BLUE,AMBER,"#A78BFA")):
        if ma in chosen:
            fig.add_trace(go.Scatter(x=df.index,y=df[ma],name=ma,line=dict(color=color,width=1.4)),row=1,col=1)
    buy_signals = df[(df['Trend'] == 1) & (df['Trend'].shift(1) == -1)]
    sell_signals = df[(df['Trend'] == -1) & (df['Trend'].shift(1) == 1)]
    for events,y,marker,color,label in [(buy_signals,buy_signals.low*.97,"triangle-up",GREEN,"Chuyển vùng xanh"),
                                        (sell_signals,sell_signals.high*1.03,"triangle-down",RED,"Chuyển vùng đỏ")]:
        fig.add_trace(go.Scatter(x=events.index,y=y,mode="markers",marker=dict(symbol=marker,color=color,size=10),name=label),row=1,col=1)
    fig.add_trace(go.Bar(x=df.index,y=df.volume,marker_color=np.where(df.close>=df.open,GREEN,RED),opacity=.65,name="Khối lượng"),row=2,col=1)
    if indicator:
        fig.add_trace(go.Scatter(x=df.index,y=df[indicator],name=indicator,line=dict(color="#A78BFA",width=1.4)),row=3,col=1)
        if indicator=="MACD" and "Signal_Line" in df:
            fig.add_trace(go.Scatter(x=df.index,y=df.Signal_Line,name="Signal",line=dict(color=AMBER,width=1.4)),row=3,col=1)
    fig.update_layout(template="plotly_dark",paper_bgcolor=BG,plot_bgcolor=BG,font=dict(color=TEXT,family="IBM Plex Sans, Arial, sans-serif",size=12),
                      height=570,margin=dict(l=12,r=12,t=12,b=15),hovermode="x unified",
                      legend=dict(orientation="h",y=1.02,yanchor="bottom"),
                      uirevision=f"{symbol}-{timeframe}-{count}-{indicator}")
    fig.update_xaxes(rangeslider_visible=False,gridcolor=SURFACE,range=[df.index[-min(count,len(df))],df.index[-1]])
    fig.update_yaxes(gridcolor=SURFACE,side="right",fixedrange=False)
    st.plotly_chart(fig,use_container_width=True,config={"scrollZoom":True,"displaylogo":False})
    st.caption("Nến và dấu tam giác biểu thị dữ liệu lịch sử và các lần chuyển trạng thái; không phải lệnh đã khớp.")

def render_trading(get_data):
    symbol,timeframe=controls()
    if not symbol:
        st.info("Nhập mã cổ phiếu để bắt đầu.")
        return
    with st.spinner("Đang tải dữ liệu cổ phiếu…"):
        df=get_data(symbol,timeframe)
    if not ready(df):
        st.warning("Không có dữ liệu hoặc chưa đủ lịch sử để tính tín hiệu. Kiểm tra mã và kết nối TCBS.")
        return
    last_row=df.iloc[-1]
    st.caption(
        f"Phiên dữ liệu cuối: {df.index[-1].strftime('%d/%m/%Y')}"
        " | Dữ liệu lịch sử, không phải giá thời gian thực"
    )
    latest_date = pd.Timestamp(df.index[-1]).date()
    today_vn = pd.Timestamp.now(tz="Asia/Ho_Chi_Minh").date()
    days_old = (today_vn - latest_date).days

    if days_old < 0:
        st.error("Ngày dữ liệu không hợp lệ: nằm trong tương lai.")
    elif days_old > 5:
        st.warning(
            f"Dữ liệu cách hôm nay {days_old} ngày. "
            "Hãy kiểm tra kết nối TCBS và lịch nghỉ giao dịch."
        )
    is_green = last_row['Trend'] == 1
    # Tìm điểm giao cắt tín hiệu gần nhất
    change = df[df['Trend'] != df['Trend'].shift(1)]
    entry_date = change[change['Trend'] == df['Trend'].iloc[-1]].index[-1] if not change.empty else df.index[0]
    entry_price = df.loc[entry_date, 'close']
    last_price = last_row['close']
    profit = ((last_price / entry_price) - 1) * 100
    days_held = len(df.loc[entry_date:])

    # Tính toán các mức giá (Bạn có thể tự chỉnh sửa công thức % này theo ý muốn)
    if is_green:
        stop_loss = last_price - (2 * last_row['ATR']) 
    else:
        stop_loss = 0.0 # Nếu đang ở Vùng Đỏ (đứng ngoài) thì không có giá cắt lỗ 
    target_1 = entry_price * 1.1
    target_2 = entry_price * 1.3
    target_3 = entry_price * 1.44

    action_text = "MUA" if is_green else "BÁN"
    color_action = "green" if is_green else "red"
    color_profit = "green" if profit >= 0 else "red"
    status_text = "Biến động từ tín hiệu:"
    rec_text = "Vùng Xanh, Tiếp tục nắm giữ" if is_green else "Vùng Đỏ, Đứng ngoài quan sát"
    rec_color = "green" if is_green else "red"
    st.header(f"{symbol} · {timeframe}")
    st.caption("Chiến lược đang vận hành: Gốc (V1) · Dữ liệu lịch sử TCBS")
    if is_green:
        st.success("VÙNG XANH · Tiếp tục nắm giữ theo mô hình")
    else:
        st.error("VÙNG ĐỎ · Đứng ngoài quan sát theo mô hình")
    a,b,c=st.columns(3)
    a.metric("Giá phiên gần nhất",number(last_price))
    b.metric("Giá tại lần chuyển vùng",number(entry_price))
    c.metric("Biến động từ tín hiệu",number(profit,1,"%"))
    st.caption("Biến động giá kể từ tín hiệu, không phải lãi/lỗ đã thực hiện.")
    left,right=st.columns([7,3])
    with left:
        st.subheader("Biểu đồ kỹ thuật")
        render_chart(df,symbol,timeframe)
    with right:
        st.subheader("Kế hoạch theo mô hình")
        st.caption(f"Mốc trạng thái: {entry_date:%d/%m/%Y %H:%M}" if timeframe=="1 Giờ" else f"Mốc trạng thái: {entry_date:%d/%m/%Y}")
        st.metric("Mức tham chiếu ATR (2×)",number(stop_loss) if is_green else "Không áp dụng")
        st.caption("Mức tham chiếu hiện tại, không phải mức trailing stop nội bộ.")
        st.write(f"**T1:** {number(target_1)} · **T2:** {number(target_2)} · **T3:** {number(target_3)}")
        st.caption("Mục tiêu theo công thức hiện hành; không cam kết đạt giá. Đơn vị giá theo nguồn TCBS.")
        st.subheader("Chỉ báo")
        st.dataframe(pd.DataFrame({"Chỉ báo":["RSI","ADX","MACD","ATR"],"Giá trị":[number(last_row.get(k)) for k in ("RSI","ADX","MACD","ATR")]}),hide_index=True,use_container_width=True)
    st.subheader("Giải thích tín hiệu")
    st.write(f"Điểm mua: {number(last_row['Buy_Pct'],0,'%')} · Điểm bán: {number(last_row['Sell_Pct'],0,'%')}")
    st.caption("Điểm đồng thuận kỹ thuật, không phải xác suất thắng.")
    st.write(str(last_row["Reason"]))
    if st.checkbox("Xem lịch sử tín hiệu",key="terminal_show_history"):
        render_history(df)

def render_scanner(get_data, universe):
    _,timeframe=controls(include_symbol=False)
    st.header("Quét tín hiệu")
    st.caption("Chiến lược gốc (V1) · Quét lịch sử TCBS, không phải giá trực tiếp.")
    if st.button("Bắt đầu quét",type="primary"):
        results=[]
        failures=[]
        bar=st.progress(0)
        for i,s in enumerate(universe):
            try:
                data=get_data(s,timeframe)
                if ready(data):
                    last_s = data.iloc[-1]
                    is_green = last_s['Trend'] == 1
                    status = "Vùng Xanh" if is_green else "Vùng Đỏ"
                    change = data[data['Trend'] != data['Trend'].shift(1)]
                    entry_date = change[change['Trend'] == data['Trend'].iloc[-1]].index[-1] if not change.empty else data.index[0]
                    entry_price = data.loc[entry_date, 'close']
                    profit = ((last_s['close'] / entry_price) - 1) * 100
                    results.append({
                        "Mã":s,"Trạng thái":status,"Giá Tín Hiệu":entry_price,
                        "Giá Hiện Tại":last_s['close'],"Biến động giá từ tín hiệu (%)":profit,
                        "% Đồng Thuận Mua":last_s['Buy_Pct'],"% Đồng Thuận Bán":last_s['Sell_Pct'],
                        "Lý do":last_s['Reason'],"Phiên cuối":str(data.index[-1])
                    })
                else:
                    failures.append(s)
            except Exception:
                failures.append(s)
            bar.progress(min((i+1)/len(universe),1.0),text=f"Đã xử lý {i+1}/{len(universe)} mã")
            time.sleep(1.1)
        st.session_state["terminal_scan"]={"tf":timeframe,"results":results,"failed":failures,"total":len(universe),"at":datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).strftime("%d/%m/%Y %H:%M")}
    report=st.session_state.get("terminal_scan")
    if not report or report["tf"]!=timeframe:
        st.info("Chưa có kết quả cho khung thời gian này. Nhấn Bắt đầu quét.")
        return
    df_res=pd.DataFrame(report["results"])
    a,b,c=st.columns(3)
    a.metric("Đã xử lý",f"{len(report['results'])+len(report['failed'])}/{report['total']}")
    b.metric("Có dữ liệu",len(report["results"]))
    c.metric("Lỗi / thiếu dữ liệu",len(report["failed"]))
    st.caption(f"Lượt quét: {report['at']} (Việt Nam) · Kết quả lưu trong phiên.")
    if report["failed"]:
        with st.expander("Mã không có kết quả"):
            st.write(", ".join(report["failed"]))
    if df_res.empty:
        st.warning("Không có dữ liệu phù hợp.")
        return
    st.caption(f"Vùng Xanh: {(df_res['Trạng thái']=='Vùng Xanh').sum()} · Vùng Đỏ: {(df_res['Trạng thái']=='Vùng Đỏ').sum()}")
    search=st.text_input("Tìm mã",key="terminal_scan_search").strip().upper()
    status=st.radio("Lọc trạng thái",["Tất cả","Vùng Xanh","Vùng Đỏ"],horizontal=True,key="terminal_scan_filter")
    sort=st.selectbox("Sắp xếp",["Thứ tự quét","Mã A–Z","Điểm mua giảm dần","Biến động giảm dần"],key="terminal_scan_sort")
    for col in ("Giá Tín Hiệu","Giá Hiện Tại","Biến động giá từ tín hiệu (%)","% Đồng Thuận Mua","% Đồng Thuận Bán"):
        df_res[col]=pd.to_numeric(df_res[col],errors="coerce")
    view=df_res[df_res["Mã"].str.contains(search,regex=False)] if search else df_res
    if status!="Tất cả":
        view=view[view["Trạng thái"]==status]
    orders={"Mã A–Z":("Mã",True),"Điểm mua giảm dần":("% Đồng Thuận Mua",False),"Biến động giảm dần":("Biến động giá từ tín hiệu (%)",False)}
    if sort in orders:
        col,asc=orders[sort]
        view=view.sort_values(col,ascending=asc)
    if view.empty:
        st.info("Không có mã phù hợp bộ lọc.")
        return
    view=view.reset_index(drop=True)
    view.insert(0,"STT",range(1,len(view)+1))
    st.dataframe(view,hide_index=True,use_container_width=True,height=520,column_config={
        "Giá Tín Hiệu":st.column_config.NumberColumn("Giá tín hiệu",format="%.2f"),
        "Giá Hiện Tại":st.column_config.NumberColumn("Giá gần nhất",format="%.2f"),
        "Biến động giá từ tín hiệu (%)":st.column_config.NumberColumn("Biến động từ tín hiệu",format="%.2f%%"),
        "% Đồng Thuận Mua":st.column_config.ProgressColumn("Điểm mua",format="%.1f%%",min_value=0,max_value=100),
        "% Đồng Thuận Bán":st.column_config.ProgressColumn("Điểm bán",format="%.1f%%",min_value=0,max_value=100)})
    selected=st.selectbox("Mã muốn phân tích",list(view["Mã"]),key="terminal_scan_selected")
    if st.button("Mở phân tích mã"):
        st.session_state["terminal_pending"]=(selected,timeframe)
        st.rerun()
    st.caption("Biến động giá kể từ tín hiệu gần nhất, KHÔNG phải lãi/lỗ thực hiện. Giá giảm sau khi thoát không phát sinh khoản lỗ giao dịch mới.")

def render_research(get_data):
    st.header("Phòng nghiên cứu chiến lược")
    st.caption("Mô phỏng lịch sử · Chiến lược thử nghiệm không thay thế chiến lược gốc.")
    tool=st.selectbox("Công cụ",["Backtesting một mã","So sánh điểm V1/V2","Backtesting đa mã","Walk-Forward","Equity & Drawdown đa mã","Equity & Drawdown một mã"],key="terminal_research_tool")
    if tool=="Backtesting đa mã":
        from multi_backtest_ui import render_multi_backtest
        render_multi_backtest(get_data, include_advanced=False)
    elif tool=="Walk-Forward":
        from walk_forward_ui import render_walk_forward
        render_walk_forward(get_data)
    elif tool=="Equity & Drawdown đa mã":
        from risk_batch_ui import render_batch_risk
        render_batch_risk(get_data)
    elif tool=="Equity & Drawdown một mã":
        from risk_equity_ui import render_equity_panel
        symbol,_=controls(fixed_daily=True)
        if symbol:
            render_equity_panel(get_data,symbol)
    else:
        symbol,tf=controls(fixed_daily=tool=="Backtesting một mã")
        if symbol:
            st.caption(f"{symbol} · {tf} · Khớp mô phỏng mở cửa phiên tiếp theo đối với Backtesting.")
            # Explicitly opt in; a collapsed expander alone would execute.
            if st.checkbox("Hiển thị báo cáo",key="terminal_research_show"):
                df=get_data(symbol,tf)
                if not ready(df):
                    st.warning("Không đủ dữ liệu.")
                elif tool=="Backtesting một mã":
                    st.caption(f"Dữ liệu từ {df.index[0]} đến {df.index[-1]} · Ngưỡng MDD đánh giá: 10%, không phải quy tắc thoát lệnh.")
                    render_single_backtest(df)
                else:
                    render_comparison(df)

def render_system(get_data,sources):
    st.header("Hệ thống")
    st.subheader("Kết nối TCBS")
    st.caption("Trạng thái xác thực trong phiên không bảo đảm API còn hoạt động. Không lưu OTP.")
    render_auth(sources)
    st.subheader("Chất lượng dữ liệu")
    symbol,tf=controls()
    if st.checkbox("Kiểm tra dữ liệu mã đã chọn",key="terminal_quality_show") and symbol:
        df=get_data(symbol,tf)
        if df is None or df.empty:
            st.warning("Không có dữ liệu để kiểm tra.")
        elif not {"open","high","low","close","volume"}.issubset(df.columns):
            st.warning("Thiếu cột OHLCV.")
        else:
            st.caption(f"Nguồn: TCBS · Phiên cuối: {df.index[-1]}")
            render_quality(df)
    st.subheader("Thông tin chiến lược")
    st.write("Gốc (V1): chiến lược vận hành. V2, V2.1 và bộ lọc là nghiên cứu độc lập.")
    st.caption("Backtesting khớp giả định tại giá mở cửa phiên tiếp theo; không áp đặt T+2/T+3. Dữ liệu lịch sử không phải giá trực tiếp.")
    st.caption("Giao diện Professional Terminal v1 · Streamlit / Plotly")
