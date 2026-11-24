"""KT16: frozen KT15 signal replay, no new indicators or optimization."""
import hashlib
import io
import json
import zipfile
import numpy as np
import pandas as pd
from cross_section_core import GROUPS as KT15_GROUPS,ALL,EXT_SECTORS,expected_dates,run_case,stock_breakdown
from daily_data_quality import ACV_BAD_DAY,ACV_BAD_OHLCV
from trade_diagnostics import _validate
from portfolio_core import Policy
from robustness_core import HISTORY_END,stats_equity,block_bootstrap,BLOCKS,N_SIM

GROUPS={**KT15_GROUPS,"U4":ALL}
VARIANTS=("A0","A4")
REQUIRED=("du_lieu_nguon","vnindex","chat_luong","tong_hop","equity","giao_dich","lenh","cua_so")
MAX_BYTES=40*1024*1024

def read_archive(data):
    if not data or len(data)>MAX_BYTES:
        raise ValueError("ZIP trống hoặc vượt giới hạn 40 MB")
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names=z.namelist()
        if len(set(names))!=len(names) or sum(x.file_size for x in z.infolist())>MAX_BYTES:
            raise ValueError("ZIP trùng tên hoặc quá lớn")
        frames={}
        for k in REQUIRED:
            name=f"stock_bot_kt15_{k}.csv"
            if name not in names: raise ValueError("Thiếu "+name)
            frames[k]=pd.read_csv(io.BytesIO(z.read(name)),float_precision="round_trip")
    return frames,hashlib.sha256(data).hexdigest()

def validate_archive(frames):
    """Check actual data coverage and metadata; never substitute missing tickers."""
    source=frames["du_lieu_nguon"].copy()
    ix=frames["vnindex"].copy()
    cal=pd.DatetimeIndex(pd.to_datetime(ix["Ngày"],format="%Y-%m-%d",errors="raise"),name="Ngày")
    if len(cal)!=1217 or cal[0]!=pd.Timestamp("2022-01-04") or cal[-1]!=HISTORY_END or cal.hasnans or cal.has_duplicates or not cal.is_monotonic_increasing:
        raise ValueError("Lịch KT15 không khớp 1.217 phiên")
    v=pd.to_numeric(ix["VNINDEX Close"],errors="raise").to_numpy()
    if not np.isfinite(v).all() or (v<=0).any(): raise ValueError("VN-Index không hợp lệ")
    cov=frames["chat_luong"].set_index("Mã")
    if cov.index.has_duplicates or set(cov.index)!=set(ALL) or set(source["Mã"])!=set(ALL):
        raise ValueError("Cần ZIP KT15 đầy đủ đúng 31 mã")
    q=cov.loc["ACV"]
    shortened=q["Trạng thái"]=="Đạt bổ sung (ACV rút ngắn)"
    if shortened:
        try: values=np.asarray(json.loads(q["OHLCV lỗi ACV"]),dtype=float)
        except (ValueError,TypeError): raise ValueError("Metadata ACV không hợp lệ") from None
        if values.shape!=(5,) or not np.allclose(values,ACV_BAD_OHLCV,rtol=0,atol=1e-8) or q["Ngày lỗi ACV"]!="2022-06-16" or q["Phiên loại do ACV rút ngắn"]!=int((cal<=ACV_BAD_DAY).sum()):
            raise ValueError("Metadata ACV không khớp KT15")
    summary=frames["tong_hop"]
    ids={g+"-"+v+"-"+c for g in KT15_GROUPS for v,c in (("A0","C0"),("A4","C0"),("A4","C1"),("A4","C2"),("A4","C3"))}
    if summary["Kịch bản"].duplicated().any() or set(summary["Kịch bản"])!=ids:
        raise ValueError("Cần đầy đủ 20 kịch bản KT15")
    if not (summary["Vốn đầu"]==100000000).all() or not (summary["Sizing"]=="R1").all() or not (summary["Cấu hình"]=="S0P0").all():
        raise ValueError("Cấu hình KT15 không đúng")
    scales=summary["Đơn vị giá"].unique()
    if len(scales)!=1 or scales[0] not in (1,1000): raise ValueError("Đơn vị giá KT15 không hợp lệ")
    signals={}
    for s in ALL:
        d=source.loc[source["Mã"]==s].drop(columns="Mã").copy()
        d.index=pd.DatetimeIndex(pd.to_datetime(d.pop("Ngày"),format="%Y-%m-%d",errors="raise"),name="Ngày")
        _validate(d)
        exp=expected_dates(s,cal,shortened and s=="ACV")
        if not d.index.equals(exp) or len(d)<200 or not d["Trend"].isin([-1,1]).all():
            raise ValueError(s+": lịch hoặc Trend không hợp lệ")
        if cov.at[s,"Trạng thái"]!=("Đạt bổ sung (ACV rút ngắn)" if s=="ACV" and shortened else "Đạt") or cov.at[s,"Phiên nguồn"]!=len(d) or cov.at[s,"Thiếu"]!=0 or cov.at[s,"Thừa"]!=0 or cov.at[s,"Nến thứ 200"]!=d.index[199].date().isoformat():
            raise ValueError(s+": báo cáo chất lượng không khớp")
        if not (d["Trend"].iloc[:199]==-1).all(): raise ValueError(s+": tín hiệu trước warmup")
        d["Reason"]=d["Reason"].fillna("")
        # Indicator values are archived, not recalculated. Verify the gate input.
        np.testing.assert_allclose(d["SMA50"].to_numpy(),d["close"].rolling(50).mean().to_numpy(),rtol=1e-9,atol=1e-8,equal_nan=True)
        signals[s]=d
    return signals,cal,Policy(price_scale=int(scales[0])),shortened

def compare_frame(actual,archived,case):
    """Compare original report columns, tolerant only to CSV float round-trip."""
    a=actual.reset_index(drop=True)
    b=archived.loc[archived["Kịch bản"]==case].reset_index(drop=True)
    if len(a)!=len(b): raise ValueError(case+": số dòng replay không khớp")
    if not len(a): return
    for col in a.columns:
        if col not in b: raise ValueError(case+": thiếu cột "+col)
        x,y=a[col],b[col]
        if pd.api.types.is_numeric_dtype(x) and not pd.api.types.is_bool_dtype(x):
            np.testing.assert_allclose(x.to_numpy(dtype=float),pd.to_numeric(y,errors="raise").to_numpy(dtype=float),rtol=0,atol=1e-5,equal_nan=True,err_msg=case+" "+col)
        else:
            if not x.fillna("").astype(str).equals(y.fillna("").astype(str)):
                raise ValueError(case+": replay khác cột "+col)

def verify_base(result,frames,group,variant):
    case=group+"-"+variant+"-C0"
    su,eq,ledger,orders,windows=result
    compare_frame(pd.DataFrame([su]),frames["tong_hop"],case)
    for a,k in ((eq.reset_index(),"equity"),(ledger,"giao_dich"),(orders,"lenh"),(windows,"cua_so")):
        compare_frame(a,frames[k],case)

def common_period(signals,calendar):
    """Use existing warmed indicators; start fresh flat. No historical holdings."""
    start=max(d.index[199] for d in signals.values())
    cal=calendar[calendar>=start]
    if len(cal)<3: raise ValueError("Giai đoạn chung quá ngắn")
    trimmed={s:d.loc[d.index>=start].copy() for s,d in signals.items()}
    if any(not d.index.equals(cal) for d in trimmed.values()):
        raise ValueError("Lịch sau warmup chung không đồng nhất")
    return trimmed,cal

def top_two(detail):
    # Two largest signed P&L values, not absolute losses. Ties by ticker.
    return tuple(detail.sort_values(["P&L tổng (VND)","Mã"],ascending=[False,True])["Mã"].iloc[:2])

def case_count(groups):
    return sum(2*(len(GROUPS[g])+3) for g in groups)

def evaluate_concentration(frames,groups=("U4",),n_sim=N_SIM,progress=None):
    groups=tuple(groups)
    if not groups or len(set(groups))!=len(groups) or not set(groups).issubset(GROUPS):
        raise ValueError("Nhóm KT16 không hợp lệ")
    signals,cal,policy,shortened=validate_archive(frames)
    # Reproduce all eight archived bases before any sensitivity results.
    bases={}
    for g,members in KT15_GROUPS.items():
        sig={s:signals[s] for s in members}
        for v in VARIANTS:
            result=run_case(sig,cal,policy,v)
            verify_base(result,frames,g,v)
            bases[g,v]=result
    common,common_cal=common_period(signals,cal)
    rows,eqs,trades,orders,windows,stocks,mc,draws,errors=[],[],[],[],[],[],[],[],[]
    done=0
    total=case_count(groups)
    for g in groups:
        members=GROUPS[g]
        sig={s:signals[s] for s in members}
        for v in VARIANTS:
            baseline=bases.get((g,v))
            if baseline is None: baseline=run_case(sig,cal,policy,v)
            base=baseline[0]
            ranked=stock_breakdown(sig,baseline[2],baseline[3],policy)
            pair=top_two(ranked)
            cases=[("FULL",(),cal,sig),("DROP2",pair,cal,{s:d for s,d in sig.items() if s not in pair}),
                   ("COMMON",(),common_cal,{s:common[s] for s in members})]
            cases.extend(("LOO",(s,),cal,{t:d for t,d in sig.items() if t!=s}) for s in sorted(members))
            for kind,excluded,calendar,subset in cases:
                code=g+"-"+v+"-"+kind+("-"+",".join(excluded) if excluded else "")
                try:
                    result=baseline if kind=="FULL" else run_case(subset,calendar,policy,v)
                    su,eq,ledger,audit,win=result
                    detail=stock_breakdown(subset,ledger,audit,policy)
                    if not np.isclose(detail["P&L tổng (VND)"].sum(),su["Vốn cuối"]-policy.capital,rtol=0,atol=.001):
                        raise ValueError("P&L theo mã không khớp")
                    tags={"Nhóm":g,"Bộ lọc":v,"Kiểm định":kind,"Kịch bản":code,"Mã loại":",".join(excluded),
                          "Phạm vi ACV":"Rút ngắn (KT15)" if shortened and "ACV" in subset else "Không có rút ngắn ACV"}
                    st=stats_equity(eq["Equity"].to_numpy())
                    # Do not compare raw full vs common-period returns as a delta.
                    same=kind!="COMMON"
                    row={**su,**tags,"Sortino (MAR=0)":st["Sortino (MAR=0)"],
                         "Calmar":su["CAGR (%)"]/abs(su["MDD (%)"]) if su["MDD (%)"]<0 else None,
                         "Chênh LN so FULL (đpt)":su["Lợi nhuận (%)"]-base["Lợi nhuận (%)"] if same else None,
                         "Chênh MDD so FULL (đpt)":su["MDD (%)"]-base["MDD (%)"] if same else None}
                    local_mc,local_draws=[],[]
                    if kind=="FULL":
                        for b in BLOCKS:
                            metrics,sample=block_bootstrap(eq["Equity"].pct_change().dropna(),b,n_sim)
                            local_mc.append({**metrics,**tags})
                            local_draws.append(sample.assign(**tags,Block=b))
                    rows.append(row)
                    # Keep all LOO summaries/windows/stock details, but export
                    # full daily and execution ledgers only for FULL/DROP2/COMMON.
                    for f,target in ((win,windows),(detail,stocks)):
                        if len(f): target.append(f.assign(**tags))
                    if kind!="LOO":
                        for f,target in ((eq.reset_index(),eqs),(ledger,trades),(audit,orders)):
                            if len(f): target.append(f.assign(**tags))
                    mc.extend(local_mc)
                    draws.extend(local_draws)
                except Exception as exc:
                    errors.append({"Kịch bản":code,"Lỗi":str(exc)[:250] if isinstance(exc,(ValueError,AssertionError)) else type(exc).__name__})
                finally:
                    done+=1
                    if progress: progress(done,total,code)
    def join(xs): return pd.concat(xs,ignore_index=True) if xs else pd.DataFrame()
    return {"summary":pd.DataFrame(rows),"equity":join(eqs),"trades":join(trades),"orders":join(orders),
            "windows":join(windows),"stocks":join(stocks),"mc":pd.DataFrame(mc),"mc_samples":join(draws),
            "errors":pd.DataFrame(errors,columns=["Kịch bản","Lỗi"]),
            "metadata":pd.DataFrame([{"Nhóm":",".join(groups),"Số kịch bản dự kiến":total,"Đối chứng KT15 khớp":8,
               "Ngày bắt đầu chung":common_cal[0],"Ngày cuối":common_cal[-1],"Số phiên chung":len(common_cal),
               "ACV rút ngắn":shortened,"Đơn vị giá":policy.price_scale,"Phí mua (%)":100*policy.costs.buy_fee,
               "Phí bán (%)":100*policy.costs.sell_fee,"Thuế (%)":100*policy.costs.sell_tax,"Trượt giá mỗi chiều (%)":100*policy.costs.slippage}])}
