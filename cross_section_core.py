"""KT15: fixed cross-sectional universes, no optimization."""
from dataclasses import replace
import numpy as np
import pandas as pd
from portfolio_core import Policy,SECTORS,simulate_portfolio
from initial_stop_core import BY_CODE,verify_baseline
from profit_protection_core import PROFITS,replay_profit,verify_p0
from strategy_policy import RESEARCH
from trade_diagnostics import _validate
from entry_filter_core import BY_FILTER,reject_reason,signal_catalog
from robustness_core import HISTORY_END,COSTS,BLOCKS,N_SIM,block_bootstrap,stats_equity,historical_slice
from market_research_core import market_context

U0=("HPG","MBB","FPT","TCB","MWG","VNM","ACB","DGC","GAS","GMD","PNJ","REE")
U1=("VIC","VHM","VCB","CTG","BID","VPB","VGI","HPG","MCH","VPL","GAS","MBB","TCB","HDB","STB","ACV","BSR","ACB","GVR","VNM")
U2=tuple(s for s in U1 if s not in U0)
U3=("VCB","CTG","BID","SSI","BVH","VIC","VHM","HPG","FPT","VGI","GAS","BSR","PLX","MCH","VNM","MWG","VJC","ACV","POW","GVR")
GROUPS={"U0":U0,"U1":U1,"U2":U2,"U3":U3}
ALL=tuple(sorted(set().union(*GROUPS.values())))
EXT_SECTORS={**SECTORS,"VIC":"Đa ngành","VHM":"Bất động sản","VPL":"Du lịch",
    **{s:"Ngân hàng" for s in ("VCB","CTG","BID","VPB","HDB","STB")},
    "VGI":"Viễn thông","MCH":"Thực phẩm","ACV":"Hàng không/hạ tầng","VJC":"Hàng không/hạ tầng",
    "BSR":"Dầu khí","PLX":"Dầu khí","GVR":"Cao su/KCN","SSI":"Chứng khoán","BVH":"Bảo hiểm","POW":"Điện/hạ tầng"}
STARTS={"VPL":pd.Timestamp("2025-05-13")}
PAUSES={"BSR":("2025-01-07","2025-01-16"),"MCH":("2025-12-18","2025-12-24")}
ECOSYSTEM={"VIC","VHM","VPL"}

def local_index(index):
    if not isinstance(index,pd.DatetimeIndex) or index.hasnans or index.has_duplicates or not index.is_monotonic_increasing:
        raise ValueError("Lịch thời gian không hợp lệ")
    local=index.tz_convert("Asia/Ho_Chi_Minh").tz_localize(None) if index.tz is not None else index
    local=local.normalize()
    if local.has_duplicates: raise ValueError("Trùng ngày VN")
    return local

def expected_dates(symbol,calendar):
    dates=calendar[calendar>=STARTS.get(symbol,calendar[0])]
    if symbol in PAUSES:
        a,b=map(pd.Timestamp,PAUSES[symbol])
        dates=dates[~((dates>=a)&(dates<=b))]
    return dates

def prepare_one(symbol,df,calendar):
    if symbol not in EXT_SECTORS: raise ValueError("Mã ngoài danh sách")
    if df is None or df.empty: raise ValueError("Không có dữ liệu TCBS")
    d=historical_slice(df)
    _validate(d)
    d.index=local_index(d.index)
    exp=expected_dates(symbol,calendar)
    missing=exp.difference(d.index)
    extra=d.index.difference(exp)
    if len(missing) or len(extra):
        raise ValueError(f"Thiếu {len(missing)}, thừa {len(extra)} phiên; thiếu đầu: {', '.join(str(x.date()) for x in missing[:5])}; thừa đầu: {', '.join(str(x.date()) for x in extra[:5])}")
    if len(d)<200: raise ValueError("Chưa đủ 200 nến thực")
    strategy=RESEARCH[1]
    verify_baseline(d,strategy)
    base=BY_CODE["S0"]
    verify_p0(d,strategy,base)
    return replay_profit(d,strategy,base,next(p for p in PROFITS if p.code=="P0"))

def run_case(signals,calendar,policy,variant):
    entry=None if variant=="A0" else lambda s,r:reject_reason(r,BY_FILTER["A4"])
    return simulate_portfolio(signals,"S0P0","R1",policy,entry_gate=entry,session_calendar=calendar,sector_map=EXT_SECTORS)

def stock_breakdown(signals,ledger,orders,policy):
    rows=[]
    for s,d in sorted(signals.items()):
        l=ledger.loc[ledger["Mã"]==s] if not ledger.empty else ledger
        o=orders.loc[orders["Mã"]==s] if not orders.empty else orders
        buys=o.loc[o["Lệnh"]=="Mua"] if len(o) else o
        qty=int(buys["Số CP"].sum() if len(buys) else 0)-int(l["Số CP"].sum() if len(l) else 0)
        cost=float(buys["Vốn mua (VND)"].sum() if len(buys) else 0)-float(l["Vốn mua (VND)"].sum() if len(l) else 0)
        realized=float(l["Lãi/lỗ (VND)"].sum()) if len(l) else 0.
        unrealized=qty*float(d["close"].iloc[-1])*policy.price_scale-cost
        rows.append({"Mã":s,"Ngành":EXT_SECTORS[s],"Hệ sinh thái Vingroup":s in ECOSYSTEM,
                     "Lệnh mua":len(buys),"Lệnh đóng":len(l),"CP cuối":qty,
                     "P&L đã đóng (VND)":realized,"P&L mở (VND)":unrealized,"P&L tổng (VND)":realized+unrealized})
    return pd.DataFrame(rows)

def evaluate_cross_section(histories,index,groups=("U0","U1","U2","U3"),policy=Policy(),n_sim=N_SIM,require_reference=True,load_errors=None):
    if not groups or len(set(groups))!=len(groups) or not set(groups).issubset(GROUPS):
        raise ValueError("Nhóm KT15 không hợp lệ")
    if policy!=Policy(price_scale=policy.price_scale): raise ValueError("KT15 chỉ dùng R1 cơ sở 100 triệu")
    if index is None or index.empty: raise ValueError("Thiếu VN-Index")
    idx=historical_slice(index)
    calendar=local_index(idx.index)
    market_context(idx,calendar)
    if require_reference and (len(calendar)!=1217 or calendar[0]!=pd.Timestamp("2022-01-04") or calendar[-1]!=HISTORY_END):
        raise ValueError("VN-Index không khớp phạm vi KT12 1.217 phiên")
    selected=sorted(set().union(*(GROUPS[g] for g in groups)))
    signals,coverage,errors,dates,raw={},[],[],[],[]
    load_errors=load_errors or {}
    for s in selected:
        exp=expected_dates(s,calendar)
        row={"Mã":s,"Ngành":EXT_SECTORS[s],"Nhóm":",".join(g for g in groups if s in GROUPS[g]),
             "Phiên dự kiến":len(exp),"Phiên trước niêm yết":int((calendar<exp[0]).sum()) if len(exp) else len(calendar),
             "Phiên chuyển sàn dự kiến":len(calendar[calendar>=exp[0]])-len(exp) if len(exp) else 0}
        try:
            d=histories.get(s)
            if d is not None and not d.empty:
                d=historical_slice(d)
                local=local_index(d.index)
                row.update({"Phiên nguồn":len(d),"Từ":local[0] if len(local) else None,"Đến":local[-1] if len(local) else None,
                            "Thiếu":len(exp.difference(local)),"Thừa":len(local.difference(exp)),
                            "Nến volume 0":int((d["volume"]==0).sum())})
                for kind,ls in (("Thiếu",exp.difference(local)),("Thừa",local.difference(exp))):
                    dates.extend({"Mã":s,"Ngày":t,"Loại":kind} for t in ls)
            if s in load_errors: raise ValueError(load_errors[s])
            trial=prepare_one(s,d,calendar)
            raw.append(trial[["open","high","low","close","volume","ATR","SMA50","SMA200","Buy_Pct","Trend","Reason"]].rename_axis("Ngày").reset_index().assign(Mã=s))
            signals[s]=trial
            row.update({"Trạng thái":"Đạt","Nến thứ 200":trial.index[199]})
        except Exception as exc:
            msg=str(exc)[:300] if isinstance(exc,ValueError) else type(exc).__name__
            row.update({"Trạng thái":"Lỗi","Lý do":msg})
            errors.append({"Mã":s,"Lỗi":msg})
        coverage.append(row)
    summary,equity,trades,orders,windows,stocks,sectors,mc,samples,catalogs=[],[],[],[],[],[],[],[],[],[]
    for group in groups:
        missing=set(GROUPS[group])-set(signals)
        if missing:
            errors.append({"Nhóm":group,"Lỗi":"Không chạy do mã không đạt: "+", ".join(sorted(missing))})
            continue
        sig={s:signals[s] for s in GROUPS[group]}
        base=None
        for variant,cost_id in (("A0","C0"),("A4","C0"),("A4","C1"),("A4","C2"),("A4","C3")):
            case=group+"-"+variant+"-"+cost_id
            try:
                p=replace(policy,costs=COSTS[cost_id])
                result=run_case(sig,calendar,p,variant)
                su,curve,ledger,audit,window=result
                if group=="U0":
                    legacy=simulate_portfolio(sig,"S0P0","R1",p,entry_gate=None if variant=="A0" else lambda s,r:reject_reason(r,BY_FILTER["A4"]))
                    if su!=legacy[0]: raise ValueError("U0 không khớp engine cũ")
                    pd.testing.assert_frame_equal(curve[legacy[1].columns],legacy[1])
                    for a,b in zip(result[2:],legacy[2:]): pd.testing.assert_frame_equal(a,b)
                detail=stock_breakdown(sig,ledger,audit,p)
                if not np.isclose(detail["P&L tổng (VND)"].sum(),su["Vốn cuối"]-p.capital,atol=.001,rtol=0):
                    raise ValueError("P&L theo mã không khớp")
                agg=detail.groupby("Ngành",as_index=False)[["Lệnh mua","Lệnh đóng","CP cuối","P&L đã đóng (VND)","P&L mở (VND)","P&L tổng (VND)"]].sum()
                cat=signal_catalog(sig) if cost_id=="C0" else pd.DataFrame()
                if len(cat):
                    buy=audit.loc[audit["Lệnh"].isin(["Mua","Bỏ mua"]),["Mã","Ngày","Lệnh","Lý do"]]
                    cat=cat.merge(buy,on=["Mã","Ngày"],how="left",validate="one_to_one")
                    if cat["Lệnh"].isna().any(): raise ValueError("Tín hiệu không khớp lệnh")
                if variant=="A0": base=su
                if base is None: raise ValueError("Thiếu A0 đối chứng")
                st=stats_equity(curve["Equity"].to_numpy())
                eco=float(detail.loc[detail["Hệ sinh thái Vingroup"],"P&L tổng (VND)"].sum())
                tags={"Nhóm":group,"Bộ lọc":variant,"Chi phí":cost_id,"Kịch bản":case}
                local_mc,local_draws=[],[]
                if variant=="A4" and cost_id=="C0":
                    ret=curve["Equity"].pct_change().dropna()
                    for name,r in (("Toàn kỳ",ret),("Sau warmup 200 thị trường",ret.iloc[199:])):
                        for b in BLOCKS:
                            if len(r)<b: continue
                            metrics,draws=block_bootstrap(r,b,n_sim)
                            local_mc.append({**metrics,**tags,"Mẫu":name})
                            local_draws.append(draws.assign(**tags,**{"Mẫu":name,"Block":b}))
                summary.append({**su,**tags,"Sortino (MAR=0)":st["Sortino (MAR=0)"],
                    "Calmar":su["CAGR (%)"]/abs(su["MDD (%)"]) if su["MDD (%)"]<0 else None,
                    "Chênh LN so A0 C0 (đpt)":su["Lợi nhuận (%)"]-base["Lợi nhuận (%)"],
                    "Phí mua (%)":100*p.costs.buy_fee,"Phí bán (%)":100*p.costs.sell_fee,"Thuế (%)":100*p.costs.sell_tax,
                    "Trượt giá (%)":100*p.costs.slippage,"Phiên có vị thế định giá cũ":int((curve["Vị thế định giá Close cũ"]>0).sum()),
                    "P&L hệ sinh thái VIC/VHM/VPL (VND)":eco})
                for f,target in ((curve.reset_index(),equity),(ledger,trades),(audit,orders),(window,windows),(detail,stocks),(agg,sectors),(cat,catalogs)):
                    if len(f): target.append(f.assign(**tags))
                mc.extend(local_mc)
                samples.extend(local_draws)
            except Exception as exc:
                errors.append({"Nhóm":group,"Kịch bản":case,"Lỗi":str(exc)[:300] if isinstance(exc,(ValueError,AssertionError)) else type(exc).__name__})
    def join(frames): return pd.concat(frames,ignore_index=True) if frames else pd.DataFrame()
    return {"summary":pd.DataFrame(summary),"equity":join(equity),"trades":join(trades),"orders":join(orders),
            "windows":join(windows),"stocks":join(stocks),"sectors":join(sectors),"signals":join(catalogs),
            "mc":pd.DataFrame(mc),"mc_samples":join(samples),"coverage":pd.DataFrame(coverage),
            "missing":pd.DataFrame(dates,columns=["Mã","Ngày","Loại"]),"source":join(raw),
            "calendar":pd.DataFrame({"Ngày":calendar,"VNINDEX Close":idx["close"].to_numpy()}),"errors":pd.DataFrame(errors)}
