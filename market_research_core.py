"""KT08/09: causal daily VNINDEX context; no new live signals."""
from dataclasses import dataclass
import math
import numpy as np
import pandas as pd
from daily_data_quality import prepare_daily_data
from portfolio_core import Policy,prepare_signals,simulate_portfolio
from entry_filter_core import BY_FILTER,reject_reason,signal_catalog,compare_entries

BASES=("A0","A4")
@dataclass(frozen=True)
class Case:
    code: str
    label: str
CASES=(
    Case("M0/RS0","Không bổ sung"),
    Case("M1","VN-Index > SMA50"),
    Case("M2","VN-Index > SMA200"),
    Case("M3","VN-Index > SMA50 và SMA50 > SMA200"),
    Case("M4","VN-Index > SMA200 và SMA50 > SMA50 của 20 phiên trước"),
    Case("RS1","RS20 > 0"),
    Case("RS2","RS60 > 0"),
    Case("RS3","RS20 > 0 và RS60 > 0"),
    Case("RS4","Xếp hạng theo RS60 giảm dần"),
)
BASELINE=CASES[0]
FEATURES=("VNINDEX Close","VNINDEX SMA50","VNINDEX SMA200","VNINDEX SMA50 lag20","RS20 (đpt)","RS60 (đpt)")

def load_index(market_factory,now=None):
    """Explicit TCBS index endpoint only; injected factory for offline tests."""
    t=pd.Timestamp.now(tz="Asia/Ho_Chi_Minh") if now is None else pd.Timestamp(now)
    if t.tzinfo is None: t=t.tz_localize("Asia/Ho_Chi_Minh")
    else: t=t.tz_convert("Asia/Ho_Chi_Minh")
    raw=market_factory("tcbs").index("VNINDEX").ohlcv(start="2022-01-01",end=t.date().isoformat(),interval="1D")
    df,report=prepare_daily_data(raw,now=t)
    return df

def market_context(index,calendar):
    if not isinstance(index,pd.DataFrame) or not isinstance(index.index,pd.DatetimeIndex) or "close" not in index:
        raise ValueError("VN-Index thiếu lịch hoặc Close")
    if not isinstance(calendar,pd.DatetimeIndex) or calendar.empty or calendar.has_duplicates or not calendar.is_monotonic_increasing:
        raise ValueError("Lịch cổ phiếu không hợp lệ")
    dates=index.index
    if dates.hasnans or dates.has_duplicates or not dates.is_monotonic_increasing:
        raise ValueError("Lịch VN-Index không hợp lệ")
    local=dates.tz_convert("Asia/Ho_Chi_Minh").tz_localize(None) if dates.tz is not None else dates
    local=local.normalize()
    if local.has_duplicates or not local.equals(calendar):
        missing=calendar.difference(local)
        extra=local.difference(calendar)
        raise ValueError(f"Lịch VN-Index không khớp: thiếu {len(missing)}, thừa {len(extra)} phiên. Không tự điền.")
    close=pd.to_numeric(index["close"],errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(close).all() or (close<=0).any():
        raise ValueError("Close VN-Index không hợp lệ")
    m=pd.DataFrame({"VNINDEX Close":close},index=calendar)
    c=m["VNINDEX Close"]
    m["VNINDEX SMA50"]=c.rolling(50,min_periods=50).mean()
    m["VNINDEX SMA200"]=c.rolling(200,min_periods=200).mean()
    m["VNINDEX SMA50 lag20"]=m["VNINDEX SMA50"].shift(20)
    for n in (20,60):
        m[f"VNINDEX R{n} (%)"]=100*(c/c.shift(n)-1)
    m["VNINDEX chuẩn hóa (100)"]=100*c/c.iloc[0]
    return m

def enrich(signals,index):
    calendar=next(iter(signals.values())).index
    context=market_context(index,calendar)
    result={}
    for s,d in signals.items():
        if not d.index.equals(calendar):
            raise ValueError("Lịch cổ phiếu không đồng nhất")
        f=d.copy()
        for col in context.columns:
            f[col]=context[col]
        for n in (20,60):
            f[f"RS{n} (đpt)"]=100*(f["close"]/f["close"].shift(n)-1)-context[f"VNINDEX R{n} (%)"]
        result[s]=f
    return result,context

def market_reason(row,case):
    c=case.code
    if c in ("M0/RS0","RS4"): return ""
    cols={"M1":FEATURES[:2],"M2":(FEATURES[0],FEATURES[2]),
          "M3":FEATURES[:3],"M4":(FEATURES[0],FEATURES[2],FEATURES[1],FEATURES[3]),
          "RS1":(FEATURES[4],),"RS2":(FEATURES[5],),"RS3":FEATURES[4:]}[c]
    try: values=[float(row.get(k,np.nan)) for k in cols]
    except (TypeError,ValueError): values=[np.nan]
    if not all(math.isfinite(x) for x in values):
        return "Bộ lọc "+c+": thiếu/chỉ báo không hợp lệ"
    if c=="M1" or c=="M2": passed=values[0]>values[1]
    elif c=="M3": passed=values[0]>values[1]>values[2]
    elif c=="M4": passed=values[0]>values[1] and values[2]>values[3]
    else: passed=all(x>0 for x in values)
    return "" if passed else "Bộ lọc "+c+": không đạt"

def gate(base,case):
    def check(symbol,row):
        if base=="A4":
            reason=reject_reason(row,BY_FILTER["A4"])
            if reason: return reason
        return market_reason(row,case)
    return check

def rank_rs(symbol,row):
    rs=float(row.get("RS60 (đpt)",np.nan))
    score=float(row.get("Buy_Pct",np.nan))
    if not math.isfinite(rs) or not math.isfinite(score):
        raise ValueError("RS60/điểm mua thiếu tại tín hiệu xếp hạng")
    return (-rs,-score,symbol)

def catalog_with_context(signals):
    cat=signal_catalog(signals)
    for name in FEATURES+("Buy_Pct",):
        cat[name]=[signals[s].at[t,name] for s,t in zip(cat["Mã"],cat["Ngày tín hiệu mua"])]
    cat["Số tín hiệu đồng thời"]=cat.groupby("Ngày")["Mã"].transform("size")
    # Rank all original signals, including ones subsequently rejected by A4.
    for col,keys in (("Hạng điểm mua",["Buy_Pct","Mã"]),("Hạng RS60",["RS60 (đpt)","Buy_Pct","Mã"])):
        ordered=cat.sort_values(["Ngày"]+keys,ascending=[True]+[False]*(len(keys)-1)+[True])
        cat[col]=(ordered.groupby("Ngày").cumcount()+1).reindex(cat.index)
    return cat

def evaluate_market(histories,index,policy=Policy(),bases=BASES):
    bases=tuple(bases)
    if not bases or len(set(bases))!=len(bases) or not set(bases).issubset(BASES):
        raise ValueError("Nền A0/A4 không hợp lệ")
    original=prepare_signals(histories,"S0P0")
    signals,context=enrich(original,index)
    catalog=catalog_with_context(signals)
    rows,curves,trades,orders,windows,diagnostics,errors=[],[],[],[],[],[],[]
    for base in bases:
        original_gate=None if base=="A0" else lambda s,r:reject_reason(r,BY_FILTER["A4"])
        reference=simulate_portfolio(original,"S0P0","R1",policy,entry_gate=original_gate)
        for case in CASES:
            try:
                result=simulate_portfolio(signals,"S0P0","R1",policy,entry_gate=gate(base,case),
                           entry_rank=rank_rs if case.code=="RS4" else None)
                summary,curve,ledger,audit,window=result
                if case==BASELINE:
                    for a,b in zip(reference[1:],result[1:]): pd.testing.assert_frame_equal(a,b)
                ref=reference[0]
                diag,stats=compare_entries(catalog,reference[2],reference[3],ledger,audit,case)
                reason=diag["Lệnh thử nghiệm lý do"].fillna("").astype(str)
                new_filter=diag["Bị loại bởi bộ lọc"] & reason.str.startswith("Bộ lọc "+case.code+":")
                a4=diag["Bị loại bởi bộ lọc"] & reason.str.startswith("Bộ lọc A4:")
                diag["Bị loại riêng KT08/09"]=new_filter
                diag["Bị loại A4"]=a4
                diag["Nền"]=base
                case_id=base+"-"+case.code
                rows.append({**summary,"Nền":base,"Thử nghiệm":case.code,"Tổ hợp":case_id,"Quy tắc":case.label,
                    "Chênh LN so cùng nền (đpt)":summary["Lợi nhuận (%)"]-ref["Lợi nhuận (%)"],
                    "Cải thiện MDD so cùng nền (đpt)":summary["MDD (%)"]-ref["MDD (%)"],
                    "Chênh Exposure (đpt)":summary["Exposure TB (%)"]-ref["Exposure TB (%)"],
                    "Tín hiệu loại A4":int(a4.sum()),"Tín hiệu loại riêng KT08/09":int(new_filter.sum()),
                    "Phiên có nhiều tín hiệu":int(catalog.loc[catalog["Số tín hiệu đồng thời"]>1,"Ngày"].nunique()),
                    **stats})
                for frame,target in ((curve.reset_index(),curves),(ledger,trades),(audit,orders),(window,windows),(diag,diagnostics)):
                    if not frame.empty:
                        target.append(frame.assign(**{"Nền":base,"Thử nghiệm":case.code,"Tổ hợp":case_id}))
            except Exception as exc:
                if case==BASELINE:
                    raise ValueError(f"Đối chứng {base} không khớp KT10/KT07") from exc
                errors.append({"Nền":base,"Thử nghiệm":case.code,"Lỗi":type(exc).__name__})
    def join(frames): return pd.concat(frames,ignore_index=True) if frames else pd.DataFrame()
    return {"summary":pd.DataFrame(rows),"equity":join(curves),"trades":join(trades),
            "orders":join(orders),"windows":join(windows),"diagnostics":join(diagnostics),
            "index":context.rename_axis("Ngày").reset_index(),"errors":pd.DataFrame(errors)}
