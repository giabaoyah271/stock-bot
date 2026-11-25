"""PT02: daily frozen-cohort technical scan, no orders."""
import hashlib,json
import numpy as np
import pandas as pd
from universe_u5 import U5,BATCHES
from full_universe_core import SHA_B,UNAVAILABLE,check_zip,enrich_causal
from universe_prepare_core import SECTORS,dates_for,COMPARE,ZERO_COUNTS
from daily_data_quality import OHLCV,prepare_daily_data,slice_raw_history,MARKET_TZ
from research_indicators import calculate_indicators
from initial_stop_core import BY_CODE,verify_baseline
from profit_protection_core import PROFITS,verify_p0,replay_profit
from strategy_policy import RESEARCH
from trade_diagnostics import _validate
END=pd.Timestamp("2026-11-23")
SCOPE=("ALL",*BATCHES)
STATES={(-1,1):"Mua mới (tín hiệu)",(1,1):"Duy trì xu hướng",(1,-1):"Thoát xu hướng (tín hiệu)",(-1,-1):"Đứng ngoài"}

def local_now(now=None):
    t=pd.Timestamp.now(tz=MARKET_TZ) if now is None else pd.Timestamp(now)
    return t.tz_localize(MARKET_TZ) if t.tzinfo is None else t.tz_convert(MARKET_TZ)

def local_days(idx):
    if not isinstance(idx,pd.DatetimeIndex): raise ValueError("Thiếu lịch thời gian")
    d=idx.tz_convert(MARKET_TZ).tz_localize(None) if idx.tz is not None else idx
    d=d.normalize().rename("Ngày")
    if d.hasnans or d.has_duplicates or not d.is_monotonic_increasing: raise ValueError("Lịch không hợp lệ")
    return d

def state(prev,cur):
    if (prev,cur) not in STATES: raise ValueError("Trend không hợp lệ")
    return STATES[prev,cur]

def read_reference(data):
    with check_zip(data,SHA_B) as z:
        def read(k): return pd.read_csv(z.open("stock_bot_kt170prep_"+k+".csv"),float_precision="round_trip")
        src=read("tin_hieu");idx=read("vnindex");omit=read("ngay_loai")
        meta=json.loads(z.read("stock_bot_kt170prep_manifest.json"))
    if set(src["Mã"])!=set(U5)-set(UNAVAILABLE) or meta["Đơn vị giá"]!=1000 or meta["Mã đạt"]!=115: raise ValueError("ZIP không đúng mẫu 115 mã")
    cal=local_days(pd.DatetimeIndex(pd.to_datetime(idx["Ngày"])))
    if len(cal)!=1217 or cal[-1]!=END: raise ValueError("Lịch tham chiếu sai")
    old={};zeros={}
    for s,x in src.groupby("Mã"):
        d=x.drop(columns="Mã").copy();d.index=local_days(pd.DatetimeIndex(pd.to_datetime(d.pop("Ngày"))))
        _validate(d);old[s]=d
        zeros[s]=pd.DatetimeIndex(pd.to_datetime(omit.loc[(omit["Mã"]==s)&(omit["Lý do"]=="Không có giao dịch"),"Ngày"]))
        if len(zeros[s])!=ZERO_COUNTS.get(s,0): raise ValueError("Ngoại lệ volume không khớp")
    return old,zeros,pd.Series(idx["VNINDEX Close"].to_numpy(),index=cal)

def validate_index(index,reference,target,now=None):
    t=local_now(now);day=pd.Timestamp(t.date());target=pd.Timestamp(target).normalize()
    if target<=END or target>day or (day-target).days>7 or (target==day and (t.hour,t.minute)<(15,15)):
        raise ValueError("Chọn phiên gần nhất đã hoàn tất, sau mốc nghiên cứu, không quá 7 ngày; hôm nay sau 15:15")
    _validate(index)
    d=index.copy();d.index=local_days(d.index)
    if d.index[-1]!=target: raise ValueError(f"Phiên yêu cầu {target.date()}, TCBS VN-Index trả về phiên cuối {d.index[-1].date()}. Kiểm tra lịch nghỉ hoặc độ trễ dữ liệu; không tự coi phiên cũ là phiên mới.")
    past=d.loc[:END,"close"]
    if not past.index.equals(reference.index): raise ValueError("Lịch VN-Index lịch sử thay đổi")
    np.testing.assert_allclose(past,reference,rtol=1e-9,atol=1e-8,err_msg="VN-Index lịch sử thay đổi")
    out=d["close"]
    return out,hashlib.sha256(out.to_csv(float_format="%.17g").encode()).hexdigest()

def scan_symbol(s,raw,index,old,zeros,now=None):
    if s not in U5: raise ValueError("Mã ngoài U5")
    raw=slice_raw_history(raw,index.index[-1])
    if not isinstance(raw,pd.DataFrame) or raw.empty: raise ValueError("Không có dữ liệu TCBS")
    if s not in old:
        d,_=prepare_daily_data(raw,now)
        return {"Mã":s,"Ngành":SECTORS[s],"Kỹ thuật":"Ngoài mẫu KT18 – cần nghiệm thu","Nến":len(d),"Phiên cuối":local_days(d.index)[-1].date().isoformat(),"Lý do":"Cần xác minh lịch và tái lập mẫu riêng"}
    start=old[s].index[0]
    ts=local_days(pd.DatetimeIndex(pd.to_datetime(raw["time"],errors="raise")))
    # Preserve frozen start even if old provider errors have since been repaired.
    d,_=prepare_daily_data(raw.loc[ts>=start].copy(),now)
    d.index=local_days(d.index)
    cal=index.index;exp=dates_for(s,cal);exp=exp[exp>=start]
    if not d.index.equals(exp):
        missing=exp.difference(d.index);extra=d.index.difference(exp)
        raise ValueError(f"Lịch khác mẫu: thiếu {len(missing)}, thừa {len(extra)}; thiếu đầu {','.join(str(x.date()) for x in missing[:4])}")
    if not d.index[d["volume"]==0].equals(zeros[s].rename("Ngày")): raise ValueError("Volume 0 khác ngoại lệ lịch sử")
    d=d.loc[d["volume"]>0,list(OHLCV)].copy()
    if len(d)<200 or d.index[-1]!=cal[-1]: raise ValueError("Thiếu nến hoặc phiên cuối")
    past=d.loc[:END]
    if not past.index.equals(old[s].index): raise ValueError("Lịch khác mẫu đã nghiệm thu")
    for k in OHLCV: np.testing.assert_allclose(past[k],old[s][k],rtol=1e-9,atol=1e-8,err_msg=s+" lịch sử "+k+" thay đổi")
    return replay_row(s,d,index,old[s])

def history_digest(d):
    """Canonical OHLCV fingerprint, including ordered local trading dates."""
    x=d[list(OHLCV)].copy()
    x.index=local_days(x.index)
    return hashlib.sha256(x.to_csv(float_format="%.17g").encode()).hexdigest()

def replay_row(s,d,index,old):
    """Recompute using exact accepted OHLCV; same path for frozen test and new scan."""
    f=calculate_indicators(d,record_stop=True)
    verify_baseline(f,RESEARCH[1]);verify_p0(f,RESEARCH[1],BY_CODE["S0"])
    out=replay_profit(f,RESEARCH[1],BY_CODE["S0"],PROFITS[0])
    if not (out["Trend"].iloc[:199]==-1).all(): raise ValueError("Tín hiệu trước warmup")
    for k in COMPARE: np.testing.assert_allclose(out.loc[:END,k],old[k],rtol=1e-9,atol=1e-8,equal_nan=True,err_msg=s+" chỉ báo "+k+" khác")
    for k in ("Trend","Reason"):
        if not out.loc[:END,k].fillna("").astype(str).equals(old[k].fillna("").astype(str)): raise ValueError(s+" tín hiệu lịch sử khác "+k)
    x=enrich_causal({s:out},index,1000)[s];a,b=x.iloc[-2],x.iloc[-1]
    if not np.isfinite([b["RS60 (đpt)"],b["Buy_Pct"],b["Sell_Pct"],b["ATR"],b["GTGD proxy 20 (VND)"]]).all(): raise ValueError("Chỉ báo phiên cuối không hợp lệ")
    return {"Mã":s,"Ngành":SECTORS[s],"Kỹ thuật":"Khớp mẫu KT18","Nến":len(x),"Phiên cuối":index.index[-1].date().isoformat(),
        "Tín hiệu":state(a["Trend"],b["Trend"]),"Trend trước":int(a["Trend"]),"Trend":int(b["Trend"]),
        "Open (nghìn VND)":float(b["open"]),"Close (nghìn VND)":float(b["close"]),"ATR (nghìn VND)":float(b["ATR"]),
        "SHA lịch sử":history_digest(d),"SHA lịch sử trước phiên":history_digest(d.iloc[:-1]),"Buy Score (%)":float(b["Buy_Pct"]),"Sell Score (%)":float(b["Sell_Pct"]),
        "RS60 (đpt)":float(b["RS60 (đpt)"]),"GTGD proxy 20 (VND)":float(b["GTGD proxy 20 (VND)"]),
        "Cảnh báo thanh khoản":"Dưới 10 tỷ" if b["GTGD proxy 20 (VND)"]<10e9 else "","Lý do":str(b["Reason"])}

def reference_batch(symbols,old,index,progress=None):
    """Offline test at END, not newly observed market data or forward evidence."""
    if index.index[-1]!=END or not symbols or len(set(symbols))!=len(symbols) or not set(symbols).issubset(U5):
        raise ValueError("Phạm vi kiểm thử sai")
    rows=[]
    for i,s in enumerate(symbols):
        if s not in old:
            row={"Mã":s,"Ngành":SECTORS[s],"Kỹ thuật":"Ngoài mẫu KT18 – chưa kiểm tra hiện tại",
                 "Lý do":"Không có dữ liệu đã nghiệm thu trong ZIP U5-B"}
        else:
            try: row=replay_row(s,old[s][list(OHLCV)].copy(),index,old[s])
            except Exception as exc:
                row={"Mã":s,"Ngành":SECTORS[s],"Kỹ thuật":"Chưa đạt / cần kiểm tra","Lý do":str(exc)[:350] if isinstance(exc,(ValueError,AssertionError)) else type(exc).__name__}
        row.update({"Tuân thủ":"Chưa xác minh","Điều kiện mua":"Chưa phê duyệt",
                    "Ghi nhận (VN)":local_now().isoformat(),"Chế độ":"KIỂM THỬ HỒI CỨU"})
        rows.append(row)
        if progress: progress(i+1,len(symbols),s)
    return rows

def scan_batch(symbols,loader,index,old,zeros,now,progress=None):
    if not symbols or len(set(symbols))!=len(symbols) or not set(symbols).issubset(U5): raise ValueError("Lô không hợp lệ")
    rows=[]
    for i,s in enumerate(symbols):
        try: row=scan_symbol(s,loader(s),index,old,zeros,now)
        except Exception as exc:
            row={"Mã":s,"Ngành":SECTORS[s],"Kỹ thuật":"Chưa đạt / cần kiểm tra","Lý do":str(exc)[:350] if isinstance(exc,(ValueError,AssertionError)) else type(exc).__name__}
        row.update({"Tuân thủ":"Chưa xác minh","Điều kiện mua":"Chưa phê duyệt","Ghi nhận (VN)":local_now().isoformat(),"Chế độ":"QUÉT PHIÊN MỚI"})
        rows.append(row)
        if progress: progress(i+1,len(symbols),s)
    return rows

def report_rows(rows):
    d=pd.DataFrame(list(rows))
    if d.empty: return d
    if d["Mã"].duplicated().any() or not set(d["Mã"]).issubset(U5): raise ValueError("Trùng hoặc sai mã")
    d["Hạng mua mới (kỹ thuật)"]=pd.Series(pd.NA,index=d.index,dtype="Int64")
    if "Tín hiệu" in d:
        pick=d.loc[(d["Kỹ thuật"]=="Khớp mẫu KT18")&(d["Tín hiệu"]==STATES[-1,1])].sort_values(["RS60 (đpt)","Buy Score (%)","Mã"],ascending=[False,False,True])
        d.loc[pick.index,"Hạng mua mới (kỹ thuật)"]=range(1,len(pick)+1)
    return d.sort_values(["Hạng mua mới (kỹ thuật)","Mã"],na_position="last").reset_index(drop=True)
