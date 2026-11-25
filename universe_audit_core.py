"""Read-only technical audit; no execution, no implicit compliance approval."""
import hashlib
import numpy as np
import pandas as pd
from universe_u5 import U5, U5_VERSION, REVIEW_SINCE, OLD_KEPT, KNOWN_NOTICES
from cross_section_core import expected_dates, local_index, quarantine_info
from robustness_core import HISTORY_END,historical_slice
from market_research_core import market_context
from trade_diagnostics import _validate
from initial_stop_core import BY_CODE,verify_baseline
from profit_protection_core import verify_p0
from strategy_policy import RESEARCH

SOURCE_COLS=["open","high","low","close","volume","ATR","SMA50","SMA200","Buy_Pct","Trend","Reason"]
TURNOVER_PROXY_LIMIT=10_000_000_000

def reference_calendar(index,require_reference=True):
    if index is None or index.empty: raise ValueError("Thiếu VN-Index")
    idx=historical_slice(index)
    calendar=local_index(idx.index)
    ctx=market_context(idx,calendar)
    if require_reference and (len(calendar)!=1217 or calendar[0]!=pd.Timestamp("2022-01-04") or calendar[-1]!=HISTORY_END):
        raise ValueError("VN-Index không khớp lịch KT15/16")
    return calendar,ctx

def audit_one(symbol,df,calendar,price_scale=1000,allow_acv_quarantine=False,load_error=None):
    if symbol not in U5 or price_scale not in (1,1000): raise ValueError("Mã/đơn vị không hợp lệ")
    notice=KNOWN_NOTICES.get(symbol,("","",""))
    row={"Mã":symbol,"Nguồn danh sách":"Cũ giữ lại" if symbol in OLD_KEPT else "Bổ sung",
        "Phiên lịch thị trường":len(calendar),"Trạng thái kỹ thuật":"Chưa đạt",
        "Pháp lý từ 2025":"Chưa xác minh đầy đủ","Tình trạng giao dịch hiện tại":"Chưa xác minh",
        "Ngày thông báo đã ghi nhận":notice[0],"Thông báo đã ghi nhận":notice[1],"Nguồn thông báo":notice[2],
        "Free Float":"Chưa xác minh","BCTC/kiểm toán":"Chưa xác minh",
        "Đủ điều kiện mua mới":"Chưa phê duyệt","Lý do":""}
    gaps=[]
    source=pd.DataFrame()
    try:
        if load_error: raise ValueError(load_error)
        if df is None or df.empty:
            msg=df.attrs.get("daily_quality_error","Không có dữ liệu TCBS") if df is not None else "Không có dữ liệu TCBS"
            raise ValueError(msg)
        d=historical_slice(df)
        _validate(d)
        d.index=local_index(d.index)
        q=quarantine_info(symbol,d,allow_acv_quarantine)
        exp=expected_dates(symbol,calendar,bool(q))
        if q and (not len(exp) or q.get("excluded_bars")!=int((calendar<=pd.Timestamp("2022-06-16")).sum()) or q.get("first_used")!=exp[0].date().isoformat()):
            raise ValueError("Metadata ACV không khớp lịch")
        missing=exp.difference(d.index)
        extra=d.index.difference(exp)
        prefix=missing[missing<d.index[0]]
        interior=missing[(missing>=d.index[0])&(missing<=d.index[-1])]
        tail=missing[missing>d.index[-1]]
        for label,dates in (("Thiếu đầu kỳ chưa xác minh",prefix),("Thiếu giữa kỳ chưa xác minh",interior),("Thiếu cuối kỳ",tail),("Thừa",extra),("Ngoại lệ đã khai báo KT15",calendar.difference(exp))):
            gaps.extend({"Mã":symbol,"Ngày":t,"Loại":label} for t in dates)
        proxy=float((d["close"].iloc[-20:]*d["volume"].iloc[-20:]*price_scale).mean()) if len(d)>=20 else np.nan
        row.update({"Phiên nguồn":len(d),"Từ":d.index[0],"Đến":d.index[-1],"Phiên dự kiến":len(exp),
            "Thiếu đầu kỳ":len(prefix),"Thiếu giữa kỳ":len(interior),"Thiếu cuối kỳ":len(tail),"Thừa":len(extra),
            "Ngoại lệ KT15":len(calendar.difference(exp)),"Nến volume 0":int((d["volume"]==0).sum()),
            "Nến volume 0 20 phiên":int((d["volume"].tail(20)==0).sum()),"Nến thứ 200":d.index[199] if len(d)>=200 else None,
            "GTGD ước tính 20 nến (VND)":proxy,"GTGD proxy >=10 tỷ":bool(proxy>=TURNOVER_PROXY_LIMIT),
            "ACV rút ngắn":bool(q),"OHLCV lỗi ACV":str(q["ohlcv"]) if q else ""})
        # Retain source snapshot for reviewing all valid OHLC rows, even if calendar fails.
        source=d[[c for c in SOURCE_COLS if c in d]].rename_axis("Ngày").reset_index().assign(Mã=symbol)
        if len(d)<200 or not set(SOURCE_COLS).issubset(d.columns):
            raise ValueError("Chưa đủ 200 nến hoặc thiếu chỉ báo")
        if len(missing) or len(extra): raise ValueError("Lịch chưa khớp; cần xác minh ngày niêm yết/chuyển sàn/gián đoạn")
        if not d["Trend"].isin([-1,1]).all() or not (d["Trend"].iloc[:199]==-1).all():
            raise ValueError("Trend không hợp lệ hoặc phát tín hiệu trước warmup")
        verify_baseline(d,RESEARCH[1])
        verify_p0(d,RESEARCH[1],BY_CODE["S0"])
        row["Trạng thái kỹ thuật"]="Đạt bổ sung ACV" if q else "Đạt kỹ thuật"
        if (d["volume"]==0).any():
            row["Trạng thái kỹ thuật"]="Cần kiểm tra volume 0"
            row["Lý do"]="Không giả định khớp lệnh tại phiên volume 0"
    except Exception as exc:
        row["Lý do"]=str(exc)[:400] if isinstance(exc,(ValueError,AssertionError)) else type(exc).__name__
    return row,pd.DataFrame(gaps,columns=["Mã","Ngày","Loại"]),source

def calendar_digest(calendar,context):
    # Same snapshot identifier across batches; closes and dates included.
    x=context[["VNINDEX Close"]].rename_axis("Ngày").reset_index()
    return hashlib.sha256(x.to_csv(index=False,float_format="%.17g").encode("utf-8")).hexdigest()

def manifest(calendar,context,price_scale,allow_acv):
    return {"Phiên bản":U5_VERSION,"Ngày bắt đầu pháp lý":REVIEW_SINCE,
        "Dữ liệu từ":calendar[0].date().isoformat(),"Dữ liệu đến":calendar[-1].date().isoformat(),
        "Số phiên":len(calendar),"Đơn vị giá":price_scale,"Cho phép ACV rút ngắn":bool(allow_acv),
        "SHA256 lịch VNINDEX":calendar_digest(calendar,context),
        "Lưu ý":"GTGD close*volume là proxy trên giá nguồn, không phải GTGD khớp lệnh chính thức. Chưa phê duyệt giao dịch."}
