"""PT10: one validated daily signal snapshot; no fallback to V1."""
import math
import pandas as pd
from signal_engine_core import (U5,END,local_now,local_days,read_reference,validate_index,
    scan_symbol,replay_row,history_digest,state,report_rows)
from full_universe_core import SHA_B,UNAVAILABLE
from daily_data_quality import OHLCV
from portfolio_core import _reference

STRATEGY="U5-A0-RS60-P5-R050"
COHORT=tuple(s for s in U5 if s not in UNAVAILABLE)

def validate_chart(symbol,frame,row,session):
    """Fail closed if any displayed signal differs from the authoritative scan row."""
    if symbol not in COHORT or row.get("Mã")!=symbol or row.get("Kỹ thuật")!="Khớp mẫu KT18":
        raise ValueError("Mã chưa đạt kiểm tra chiến lược chính")
    if len(frame)<200 or str(local_days(frame.index)[-1].date())!=session or row.get("Phiên cuối")!=session:
        raise ValueError("Phiên biểu đồ không khớp bộ quét")
    if history_digest(frame)!=row.get("SHA lịch sử") or history_digest(frame.iloc[:-1])!=row.get("SHA lịch sử trước phiên"):
        raise ValueError("Dấu vân tay lịch sử không khớp")
    a,b=frame.iloc[-2],frame.iloc[-1]
    if int(a["Trend"])!=row["Trend trước"] or int(b["Trend"])!=row["Trend"] or state(a["Trend"],b["Trend"])!=row["Tín hiệu"] or str(b["Reason"])!=row["Lý do"]:
        raise ValueError("Tín hiệu biểu đồ không khớp bộ quét")
    for col,key in (("open","Open (nghìn VND)"),("close","Close (nghìn VND)"),("ATR","ATR (nghìn VND)"),("Buy_Pct","Buy Score (%)"),("Sell_Pct","Sell Score (%)"),("RS60 (đpt)","RS60 (đpt)"),("GTGD proxy 20 (VND)","GTGD proxy 20 (VND)")):
        if not math.isclose(float(b[col]),float(row[key]),rel_tol=1e-12,abs_tol=1e-10): raise ValueError("Chỉ báo không khớp: "+col)
    return frame

def chart_from_report(report,symbol):
    if not report or len(report.get("identity",()))!=4 or report["identity"][3]!="LIVE" or report["identity"][2]!=SHA_B: raise ValueError("Chưa có báo cáo quét phiên mới")
    row=report["rows"].get(symbol)
    frame=report.get("charts",{}).get(symbol)
    if row is None or frame is None: raise ValueError("Mã chưa có biểu đồ đã xác minh trong báo cáo; tải phân tích riêng hoặc quét lại")
    return validate_chart(symbol,frame,row,report["identity"][0]),row

def single_snapshot(symbol,ref_bytes,ix,loader,now=None):
    """Same strict TCBS path as scan; does not insert/rerank or modify journal."""
    if symbol not in COHORT: raise ValueError("Ngoài 115 mã đã nghiệm thu; không phát tín hiệu chính")
    old,zeros,reference=read_reference(ref_bytes)
    t=local_now(now)
    session=str(local_days(ix.index)[-1].date())
    index,sha=validate_index(ix,reference,session,t)
    frames={}
    row=scan_symbol(symbol,loader(symbol),index,old,zeros,t,capture=lambda s,d:frames.__setitem__(s,d))
    d=validate_chart(symbol,frames[symbol],row,session)
    return {"identity":(session,sha,SHA_B,"LIVE"),"row":row,"frame":d,"observed_at":t.isoformat()}

def frozen_snapshot(symbol,old,index):
    if symbol not in COHORT or symbol not in old: raise ValueError("Ngoài mẫu hồi cứu 115 mã")
    if index.index[-1]!=END: raise ValueError("Sai mốc hồi cứu")
    frames={}
    row=replay_row(symbol,old[symbol][list(OHLCV)].copy(),index,old[symbol],capture=lambda s,d:frames.__setitem__(s,d))
    return validate_chart(symbol,frames[symbol],row,str(END.date())),row

def resolve_daily(report,symbol,standalone=None):
    """Never silently replace a failed scanned symbol or disagree with scan snapshot."""
    if report and len(report.get("identity",()))==4 and report["identity"][3]=="LIVE" and symbol in report["rows"]:
        row=report["rows"][symbol]
        if row.get("Kỹ thuật")!="Khớp mẫu KT18": raise ValueError("Bộ quét chưa xác minh mã này; quét lại, không dùng tín hiệu thay thế")
        if symbol in report.get("charts",{}):
            d,row=chart_from_report(report,symbol)
            rank=report_rows(report["rows"].values()).set_index("Mã").at[symbol,"Hạng mua mới (kỹ thuật)"]
            return d,row,"Báo cáo quét chung",rank
        if standalone and standalone["identity"]==report["identity"]:
            d=validate_chart(symbol,standalone["frame"],row,report["identity"][0])
            rank=report_rows(report["rows"].values()).set_index("Mã").at[symbol,"Hạng mua mới (kỹ thuật)"]
            return d,row,"Cùng dấu vân tay báo cáo quét",rank
        raise ValueError("Báo cáo chưa có biểu đồ đồng nhất; quét lại hoặc tải mã cùng phiên")
    if standalone:
        if standalone["identity"][2:]!=(SHA_B,"LIVE") or (report and report.get("identity",())[-1:] == ("LIVE",) and standalone["identity"]!=report["identity"]):
            raise ValueError("Phân tích riêng khác phiên hoặc VN-Index của bộ quét")
        return validate_chart(symbol,standalone["frame"],standalone["row"],standalone["identity"][0]),standalone["row"],"Phân tích riêng, chưa xếp hạng toàn thị trường",pd.NA
    raise ValueError("Chưa có dữ liệu chiến lược chính cho mã này")

def reference_stop(frame):
    """R1 sizing reference at signal close, not a guaranteed or extra exit."""
    b=frame.iloc[-1]
    return _reference("S0P0",float(b["close"]),b)

def transition_history(frame):
    return frame.loc[frame["Trend"].shift().notna() & frame["Trend"].ne(frame["Trend"].shift()),["close","Trend","Buy_Pct","Sell_Pct","RS60 (đpt)","Reason"]].copy()

def supplemental(frame):
    """H/Week analysis is indicators only; no alternate strategy scores/trades."""
    cols=[*OHLCV,"SMA20","SMA50","SMA200","BB_upper","BB_lower","RSI","MACD","Signal_Line","ADX","Plus_DI","Minus_DI","ATR"]
    return frame[[k for k in cols if k in frame]].copy()
