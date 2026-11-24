"""KT14/KT10: independent entry gates on the unchanged portfolio replay."""
from dataclasses import dataclass
import math
import numpy as np
import pandas as pd
from portfolio_core import Policy, CANDIDATES, prepare_signals, simulate_portfolio, BUY_MULT, SELL_MULT

@dataclass(frozen=True)
class EntryFilter:
    code: str
    label: str
    feature: str = ""
    limit: float = 0.

FILTERS=(
    EntryFilter("V0/A0","Không lọc"),
    EntryFilter("V1","ATR/Close ≤ 3%","ATR/Close (%)",3.),
    EntryFilter("V2","ATR/Close ≤ 4%","ATR/Close (%)",4.),
    EntryFilter("V3","ATR/Close ≤ 5%","ATR/Close (%)",5.),
    EntryFilter("A1","Close/SMA20 - 1 ≤ 5%","Cách SMA20 (%)",5.),
    EntryFilter("A2","Close/SMA20 - 1 ≤ 8%","Cách SMA20 (%)",8.),
    EntryFilter("A3","RSI ≤ 70","RSI",70.),
    EntryFilter("A4","Close/SMA50 - 1 ≤ 15%","Cách SMA50 (%)",15.),
)
BY_FILTER={f.code:f for f in FILTERS}
BASELINE=FILTERS[0].code

def _number(row,key):
    try:
        x=float(row.get(key,np.nan))
        return x if math.isfinite(x) else np.nan
    except (TypeError,ValueError):
        return np.nan

def signal_features(row):
    close=_number(row,"close")
    atr=_number(row,"ATR")
    sma20=_number(row,"SMA20")
    sma50=_number(row,"SMA50")
    rsi=_number(row,"RSI")
    valid_close=close>0
    return {"ATR/Close (%)":100*atr/close if valid_close and atr>=0 else np.nan,
            "Cách SMA20 (%)":100*(close/sma20-1) if valid_close and sma20>0 else np.nan,
            "Cách SMA50 (%)":100*(close/sma50-1) if valid_close and sma50>0 else np.nan,
            "RSI":rsi if 0<=rsi<=100 else np.nan}

def reject_reason(row,config):
    if config not in FILTERS:
        raise ValueError("Bộ lọc không hợp lệ")
    if not config.feature:
        return ""
    value=signal_features(row)[config.feature]
    if not math.isfinite(value):
        return "Bộ lọc "+config.code+": thiếu/chỉ báo không hợp lệ"
    if value>config.limit+1e-10:
        return "Bộ lọc "+config.code+": vượt ngưỡng"
    return ""

def signal_catalog(signals):
    """Read-only ex-post audit of original signal cycles.
    A rejected entry still follows the original strategy's virtual cycle;
    no extra entry until next fresh transition. Future exit only for audit.
    """
    rows=[]
    for symbol,d in sorted(signals.items()):
        state=d["Trend"].to_numpy()
        entries=np.flatnonzero((state[:-1]==-1)&(state[1:]==1))+1
        exits=np.flatnonzero((state[:-1]==1)&(state[1:]==-1))+1
        for i in entries:
            if i<1 or i+1>=len(d):
                continue
            j=int(np.searchsorted(exits,i,side="right"))
            sell=int(exits[j]) if j<len(exits) else None
            entry=float(d["open"].iloc[i+1])
            closed=sell is not None and sell+1<len(d)
            ret=(float(d["open"].iloc[sell+1])*SELL_MULT/(entry*BUY_MULT)-1)*100 if closed else None
            rows.append({"Mã":symbol,"Ngày tín hiệu mua":d.index[i],"Ngày":d.index[i+1],
                         "Ngày bán giả định":d.index[sell+1] if closed else pd.NaT,
                         "LN lệnh độc lập giả định (%)":ret,
                         **signal_features(d.iloc[i])})
    return pd.DataFrame(rows,columns=["Mã","Ngày tín hiệu mua","Ngày","Ngày bán giả định",
                "LN lệnh độc lập giả định (%)","ATR/Close (%)","Cách SMA20 (%)","Cách SMA50 (%)","RSI"])

def _orders_view(audit,name):
    cols=["Mã","Ngày","Lệnh","Lý do"]
    if audit.empty:
        return pd.DataFrame(columns=["Mã","Ngày",name,name+" lý do"])
    out=audit.loc[audit["Lệnh"].isin(["Mua","Bỏ mua"]),cols].copy()
    if out.duplicated(["Mã","Ngày"]).any():
        raise ValueError("Trùng lệnh mua")
    return out.rename(columns={"Lệnh":name,"Lý do":name+" lý do"})

def _ledger_view(ledger,name):
    cols=["Mã","Ngày mua","Lợi nhuận ròng (%)","Lãi/lỗ (VND)"]
    if ledger.empty:
        return pd.DataFrame(columns=["Mã","Ngày",name+" LN (%)",name+" P&L (VND)"])
    out=ledger[cols].copy()
    if out.duplicated(["Mã","Ngày mua"]).any():
        raise ValueError("Trùng giao dịch mua")
    return out.rename(columns={"Ngày mua":"Ngày","Lợi nhuận ròng (%)":name+" LN (%)","Lãi/lỗ (VND)":name+" P&L (VND)"})

def compare_entries(catalog,base_ledger,base_orders,ledger,orders,config):
    out=catalog.copy()
    for frame in (_orders_view(base_orders,"Lệnh đối chứng"),_orders_view(orders,"Lệnh thử nghiệm"),
                  _ledger_view(base_ledger,"Đối chứng"),_ledger_view(ledger,"Thử nghiệm")):
        if frame.empty:
            for col in frame.columns:
                if col not in ("Mã","Ngày"):
                    out[col]=np.nan
        else:
            out=out.merge(frame,on=["Mã","Ngày"],how="left",validate="one_to_one")
    if not out.empty and (out["Lệnh thử nghiệm"].isna().any() or out["Lệnh đối chứng"].isna().any()):
        raise ValueError("Tín hiệu mua không khớp nhật ký danh mục")
    reason=out["Lệnh thử nghiệm lý do"].fillna("").astype(str)
    filtered=(out["Lệnh thử nghiệm"]=="Bỏ mua")&reason.str.startswith("Bộ lọc ")
    out["Bị loại bởi bộ lọc"]=filtered
    out["Bị từ chối bởi sizing"]=(out["Lệnh thử nghiệm"]=="Bỏ mua")&~filtered
    out["Bộ lọc"]=config.code
    actual=filtered&(out["Lệnh đối chứng"]=="Mua")
    net=pd.to_numeric(out["Đối chứng LN (%)"],errors="coerce")
    hypothetical=pd.to_numeric(out["LN lệnh độc lập giả định (%)"],errors="coerce")
    newly_bought=(out["Lệnh đối chứng"]=="Bỏ mua")&(out["Lệnh thử nghiệm"]=="Mua")
    stats={"Tín hiệu mua":len(out),"Tín hiệu bị lọc":int(filtered.sum()),
           "Tín hiệu bị từ chối sizing":int(out["Bị từ chối bởi sizing"].sum()),
           "Tín hiệu bị lọc thiếu chỉ báo":int((filtered&reason.str.contains("thiếu/chỉ báo",regex=False)).sum()),
           "Lệnh độc lập bị lọc có lãi":int((filtered&(hypothetical>0)).sum()),
           "Lệnh độc lập bị lọc bị lỗ":int((filtered&(hypothetical<0)).sum()),
           "Lệnh độc lập bị lọc chưa đóng":int((filtered&hypothetical.isna()).sum()),
           "Lệnh mua đối chứng bị lọc":int(actual.sum()),
           "Lệnh thắng đối chứng bị lọc":int((actual&(net>0)).sum()),
           "Lệnh thua đối chứng bị lọc":int((actual&(net<0)).sum()),
           "Lệnh đối chứng bị lọc chưa đóng":int((actual&net.isna()).sum()),
           "P&L đối chứng của lệnh thắng bị lọc (VND)":float(out.loc[actual&(net>0),"Đối chứng P&L (VND)"].sum()),
           "P&L đối chứng của lệnh thua bị lọc (VND)":float(out.loc[actual&(net<0),"Đối chứng P&L (VND)"].sum()),
           "Lệnh mua mới do thay đổi phân bổ":int(newly_bought.sum())}
    return out,stats

def evaluate_entry_filters(histories,code="S0P0",policy=Policy()):
    """All eight cases share same signals, costs, R1 and calendar."""
    signals=prepare_signals(histories,code)
    base,base_curve,base_ledger,base_orders,base_windows=simulate_portfolio(signals,code,"R1",policy)
    catalog=signal_catalog(signals)
    rows,curves,trades,orders,windows,diagnostics,errors=[],[],[],[],[],[],[]
    for config in FILTERS:
        try:
            if config.code==BASELINE:
                result=(base,base_curve,base_ledger,base_orders,base_windows)
                # Verify optional hook with all-pass function is inert.
                check=simulate_portfolio(signals,code,"R1",policy,entry_gate=lambda s,row:"")
                for expected,actual in zip(result[1:],check[1:]):
                    pd.testing.assert_frame_equal(expected,actual)
            else:
                result=simulate_portfolio(signals,code,"R1",policy,
                      entry_gate=lambda s,row:reject_reason(row,config))
            summary,curve,ledger,audit,window=result
            diag,stats=compare_entries(catalog,base_ledger,base_orders,ledger,audit,config)
            ret=summary["Lợi nhuận (%)"]
            exposure=summary["Exposure TB (%)"]
            rows.append({**summary,"Bộ lọc":config.code,"Quy tắc":config.label,
                         "Chênh LN so đối chứng (đpt)":ret-base["Lợi nhuận (%)"],
                         "Cải thiện MDD (đpt)":summary["MDD (%)"]-base["MDD (%)"],
                         "Chênh Exposure (đpt)":exposure-base["Exposure TB (%)"],
                         "LN toàn kỳ/Exposure TB (tham chiếu)":ret/exposure if exposure>0 else None,
                         **stats})
            for frame,target in ((curve.reset_index(),curves),(ledger,trades),(audit,orders),(window,windows),(diag,diagnostics)):
                if not frame.empty:
                    target.append(frame.assign(**{"Cấu hình":code,"Sizing":"R1","Bộ lọc":config.code}))
        except Exception as exc:
            if config.code==BASELINE:
                raise ValueError("Đối chứng không khớp KT06/KT07") from exc
            errors.append({"Cấu hình":code,"Bộ lọc":config.code,"Lỗi":str(exc)[:150] if isinstance(exc,ValueError) else type(exc).__name__})
    def join(frames):
        return pd.concat(frames,ignore_index=True) if frames else pd.DataFrame()
    return {"summary":pd.DataFrame(rows),"equity":join(curves),"trades":join(trades),
            "orders":join(orders),"windows":join(windows),"diagnostics":join(diagnostics),
            "errors":pd.DataFrame(errors)}
