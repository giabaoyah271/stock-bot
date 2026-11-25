"""KT17.0a-e: deterministic preparation of the exact archived U5 cohort."""
import io,zipfile,hashlib,json,re
import numpy as np
import pandas as pd
from universe_u5 import U5
from cross_section_core import expected_dates,EXT_SECTORS
from daily_data_quality import OHLCV,prepare_daily_data,slice_raw_history,DataQualityError
from trade_diagnostics import _validate
from research_indicators import calculate_indicators
from initial_stop_core import BY_CODE,verify_baseline
from profit_protection_core import PROFITS,verify_p0,replay_profit
from strategy_policy import RESEARCH
from concentration_core import read_archive,validate_archive

U5_SHA="a686d6a3997b550e7411ee3328081c57b05b99752832224bfb6cc75b48db56a0"
KT15_SHA="747654bafd7d957991587d96f5ae6302574d07b1d0f5ebd0f157e71f1a212b92"
RETRY=tuple("CC1 CEO IDC LAS MBS NAB PVS QNS SHS VBB VEA VGS".split())
SHORT=("DMX","GEL")
STARTS={"GEE":"2022-03-08","TAL":"2024-01-09","TCX":"2025-10-21","VPX":"2025-12-11","VCK":"2025-12-16"}
PAUSES={"GEE":("2024-07-19","2024-08-13"),"HHV":("2022-01-07","2022-01-19"),"PGV":("2022-01-24","2022-02-09"),"PHP":("2022-08-31","2022-09-13"),"TAL":("2025-07-22","2025-07-31")}
ZERO_COUNTS={"GEE":13,"PGV":3,"PHP":1,"TAL":3}
SECTOR_GROUPS={
    "Ngân hàng": "ABB ACB BID CTG EIB HDB LPB MBB MSB NAB OCB SHB SSB STB TCB TPB VBB VCB VIB VPB",
    "Chứng khoán": "AGR BSI CTS FTS HCM MBS SHS SSI TCX VCI VCK VIX VND VPX",
    "Bất động sản": "CEO DIG DXG HDC KDH NLG PDR TAL TCH VHM VRE",
    "Khu công nghiệp": "BCM IDC KBC SZC",
    "Thép": "HPG HSG NKG VGS",
    "Dầu khí": "BSR GAS PLX PVD PVS PVT",
    "Logistics": "GMD HAH PHP",
    "Hàng không/hạ tầng": "ACV VJC",
    "Bảo hiểm": "BVH PVI",
    "Điện/hạ tầng": "GEG NT2 PC1 PGV POW REE",
    "Xây dựng": "CC1 CII CTD FCN HHV HUT LCG VCG",
    "Bán lẻ": "DGW DMX FRT MWG PNJ",
    "Công nghệ": "FPT",
    "Viễn thông": "FOX",
    "Hóa chất": "CSV",
    "Phân bón": "BFC DCM DPM LAS",
    "Cao su/KCN": "DPR GVR PHR",
    "Thực phẩm": "BAF DBC HAG KDC MCH MSN PAN QNS SAB SBT VNM",
    "Thủy sản": "ANV VHC",
    "Dệt may": "MSH TCM TNG",
    "Công nghiệp": "GEE GEL GEX VEA",
    "Khai khoáng": "MSR",
    "Đa ngành": "VIC",
    "Du lịch": "VPL",
    "Vật liệu xây dựng": "VGC",
    "Kỹ thuật": "TV2"
}
SECTORS={s:k for k,v in SECTOR_GROUPS.items() for s in v.split()}
assert set(SECTORS)==set(U5)
# Preserve KT15 classifications for every overlapping ticker; draft groupings elsewhere.
SECTORS.update({s:v for s,v in EXT_SECTORS.items() if s in U5})
COMPARE=["open","high","low","close","volume","ATR","SMA50","SMA200","Buy_Pct"]
SIGNAL_COLS=COMPARE+["Trend","Reason"]

def dates_for(s,calendar,prefix=None):
    d=expected_dates(s,calendar,s=="ACV")
    if s in STARTS: d=d[d>=pd.Timestamp(STARTS[s])]
    if s in PAUSES:
        a,b=map(pd.Timestamp,PAUSES[s]);d=d[~((d>=a)&(d<=b))]
    if prefix is not None: d=d[d>pd.Timestamp(prefix)]
    return d

def read_u5(data,kt15_data):
    if hashlib.sha256(data).hexdigest()!=U5_SHA or hashlib.sha256(kt15_data).hexdigest()!=KT15_SHA:
        raise ValueError("Cần đúng hai ZIP gốc đã nghiệm thu; không đổi tên/nội dung CSV")
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        def frame(k): return pd.read_csv(z.open("stock_bot_kt170_"+k+".csv"),float_precision="round_trip")
        cov=frame("chat_luong").set_index("Mã");src=frame("du_lieu_nguon");idx=frame("vnindex")
        meta=json.loads(z.read("stock_bot_kt170_manifest.json"))
    f,_=read_archive(kt15_data);old,cal,policy,shortened=validate_archive(f)
    if not shortened or policy.price_scale!=1000 or meta["Đơn vị giá"]!=1000 or len(cov)!=120 or set(cov.index)!=set(U5):
        raise ValueError("Metadata không khớp")
    if not pd.DatetimeIndex(pd.to_datetime(idx["Ngày"])).equals(cal):
        raise ValueError("Lịch VNINDEX không khớp")
    np.testing.assert_allclose(idx["VNINDEX Close"],f["vnindex"]["VNINDEX Close"],rtol=0,atol=1e-10)
    raw={}
    for sym,x in src.groupby("Mã",sort=False):
        d=x.drop(columns="Mã").copy()
        d.index=pd.DatetimeIndex(pd.to_datetime(d.pop("Ngày")),name="Ngày")
        _validate(d);raw[sym]=d
    if set(raw)!=set(U5)-set(RETRY)-set(SHORT): raise ValueError("Phạm vi nguồn không khớp 106 mã")
    return raw,cov,cal,old,idx

def retry_raw(raw,s,old_reason,calendar,allow_prefix=False):
    if s not in RETRY: raise ValueError("Không thuộc lô OHLC")
    raw=slice_raw_history(raw,"2026-11-23")
    prefix=None
    try: d,_=prepare_daily_data(raw)
    except DataQualityError as exc:
        # Exact archived error string, including dates and OHLCV signatures; never repair prices.
        if not allow_prefix or str(exc)!=old_reason or "OHLC không nhất quán" not in old_reason: raise
        dates=re.findall(r"(\d{4}-\d{2}-\d{2}): O=",old_reason)
        if not dates or len(dates)!=int(old_reason.split()[0]): raise ValueError("Không xác nhận được toàn bộ nến lỗi")
        prefix=max(dates)
        t=pd.DatetimeIndex(pd.to_datetime(raw["time"]))
        t=t.tz_convert("Asia/Ho_Chi_Minh").tz_localize(None) if t.tz is not None else t
        d,_=prepare_daily_data(raw.loc[t.normalize()>pd.Timestamp(prefix)].copy())
    d.index=pd.DatetimeIndex(d.index.tz_convert("Asia/Ho_Chi_Minh").tz_localize(None) if d.index.tz is not None else d.index,name="Ngày").normalize()
    if not d.index.equals(dates_for(s,calendar,prefix)): raise ValueError("Lịch tải lại không khớp")
    return d,prefix

def prepare_one(s,d,calendar,old=None,prefix=None,drop_zero=False):
    _validate(d)
    if not d.index.equals(dates_for(s,calendar,prefix)): raise ValueError("Lịch không khớp ngoại lệ đã xác minh")
    z=d.index[d["volume"]==0]
    if len(z)!=ZERO_COUNTS.get(s,0): raise ValueError("Số nến volume 0 khác hồ sơ; cần xác minh")
    if len(z) and not drop_zero: raise ValueError("Volume 0: chưa cho phép mẫu nghiên cứu nến thực")
    x=d.loc[d["volume"]>0,list(OHLCV)].copy()
    if len(x)<200: raise ValueError("Thiếu 200 nến giao dịch thực")
    full=calculate_indicators(x,record_stop=True)
    if not len(z) and set(COMPARE).issubset(d.columns):
        for c in COMPARE: np.testing.assert_allclose(full[c],d[c],rtol=1e-9,atol=1e-8,equal_nan=True,err_msg=s+" "+c)
    verify_baseline(full,RESEARCH[1]);verify_p0(full,RESEARCH[1],BY_CODE["S0"])
    out=replay_profit(full,RESEARCH[1],BY_CODE["S0"],PROFITS[0])
    if not (out["Trend"].iloc[:199]==-1).all(): raise ValueError("Trend trước warmup")
    if old is not None:
        if not out.index.equals(old.index): raise ValueError("Lịch KT15 khác")
        for c in COMPARE: np.testing.assert_allclose(out[c],old[c],rtol=1e-9,atol=1e-8,equal_nan=True,err_msg=s+" KT15 "+c)
        for c in ("Trend","Reason"):
            if not out[c].fillna("").astype(str).equals(old[c].fillna("").astype(str)):
                raise ValueError(s+" KT15 khác "+c)
    return out[SIGNAL_COLS],z

def prepare_batch(raw,cov,calendar,old,retries=None,drop_zero=False,progress=None):
    retries=retries or {}
    rows=[];signals=[];omitted=[]
    for i,s in enumerate(U5):
        row={"Mã":s,"Ngành đề xuất":SECTORS[s],"Pháp lý":"Chưa xác minh đầy đủ","Free Float":"Chưa xác minh","BCTC/kiểm toán":"Chưa xác minh","Mua thực tế":"Chưa phê duyệt","Trạng thái":"Chưa đạt","Lý do":"","Đối chiếu KT15":"Không áp dụng"}
        try:
            prefix=None
            if s in raw: d=raw[s]
            elif s in retries: d,prefix=retries[s]
            else: raise ValueError(str(cov.at[s,"Lý do"]))
            out,z=prepare_one(s,d,calendar,old.get(s),prefix,drop_zero)
            row.update({"Trạng thái":"Đạt nghiên cứu","Từ":out.index[0],"Đến":out.index[-1],"Nến":len(out),
                "Nến thứ 200":out.index[199],"Số nến volume 0 bỏ":len(z),"Prefix OHLC đến":prefix or "",
                "ACV rút ngắn":s=="ACV","Đối chiếu KT15":"Khớp" if s in old else "Không áp dụng",
                "Mẫu":"Rút ngắn OHLC" if prefix or s=="ACV" else "Nến giao dịch thực" if len(z) else "Không rút ngắn"})
            signals.append(out.rename_axis("Ngày").reset_index().assign(Mã=s))
            omitted.extend({"Mã":s,"Ngày":t,"Lý do":"Không có giao dịch"} for t in z)
            if prefix: omitted.extend({"Mã":s,"Ngày":t,"Lý do":"Prefix OHLC"} for t in calendar[calendar<=pd.Timestamp(prefix)])
        except Exception as exc:
            row["Lý do"]=str(exc)[:500] if isinstance(exc,(ValueError,AssertionError)) else type(exc).__name__
        rows.append(row)
        if progress: progress(i+1,s)
    return pd.DataFrame(rows),pd.concat(signals,ignore_index=True) if signals else pd.DataFrame(columns=["Ngày","Mã",*SIGNAL_COLS]),pd.DataFrame(omitted,columns=["Mã","Ngày","Lý do"])
