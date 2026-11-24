"""KT12 retrospective robustness; frozen history, explicit cost scenarios."""
from dataclasses import replace
import math
import numpy as np
import pandas as pd
from portfolio_core import Costs,Policy,prepare_signals,simulate_portfolio
from entry_filter_core import BY_FILTER,reject_reason,signal_features
from market_research_core import CASES,enrich,gate

HISTORY_END=pd.Timestamp("2026-11-23")
CANDIDATE="A4"
CANDIDATES=("A4","A0","A4-M1","A4-RS1")
COSTS={"C0":Costs(),"C1":Costs(.002,.002,.001,.002),
       "C2":Costs(.0025,.0025,.001,.003),"C3":Costs(.003,.003,.001,.005)}
BLOCKS=(5,10,20)
SEED=20261124
N_SIM=2000

def historical_slice(d):
    local=d.index.tz_convert("Asia/Ho_Chi_Minh").tz_localize(None) if d.index.tz is not None else d.index
    return d.loc[local.normalize()<=HISTORY_END].copy()

def stats_equity(values):
    x=np.asarray(values,dtype=float)
    if len(x)<1 or not np.isfinite(x).all() or (x<=0).any():
        raise ValueError("Equity không hợp lệ")
    r=x[1:]/x[:-1]-1
    dd=1-x/np.maximum.accumulate(x)
    sd=float(np.std(r,ddof=1)) if len(r)>1 else 0.
    downside=float(np.sqrt(np.mean(np.minimum(r,0)**2))) if len(r) else 0.
    mdd=float(dd.max())
    return {"Lợi nhuận (%)":100*(x[-1]/x[0]-1),"MDD (%)":-100*mdd,
            "Sharpe (rf=0)":float(r.mean()/sd*np.sqrt(252)) if sd>0 else None,
            "Sortino (MAR=0)":float(r.mean()/downside*np.sqrt(252)) if downside>0 else None}

def gate_limit(limit):
    if limit==15:
        return lambda s,r:reject_reason(r,BY_FILTER["A4"])
    def fn(s,r):
        value=signal_features(r)["Cách SMA50 (%)"]
        return "" if math.isfinite(value) and value<=limit+1e-10 else "Bộ lọc SMA50: không đạt/thiếu"
    return fn

def candidates(signals):
    mapping={c.code:c for c in CASES}
    return {"A4":gate_limit(15),"A0":None,"A4-M1":gate("A4",mapping["M1"]),
            "A4-RS1":gate("A4",mapping["RS1"])}

def sensitivity(policy):
    return [("BASE",policy,15,"Đối chứng"),
            ("R025",replace(policy,risk=.0025),15,"Rủi ro 0,25%"),
            ("R075",replace(policy,risk=.0075),15,"Rủi ro 0,75%"),
            ("A10",policy,10,"SMA50 10%"),("A20",policy,20,"SMA50 20%"),
            ("W10",replace(policy,stock_cap=.10),15,"Tỷ trọng mã 10%"),
            ("W20",replace(policy,stock_cap=.20),15,"Tỷ trọng mã 20%")]

def block_bootstrap(returns,block,n_sim=N_SIM,seed=SEED):
    """Moving blocks, non-circular, resampled portfolio DAILY returns.
    Includes start capital 1 in drawdown peak. Not simulated trade execution.
    """
    r=np.asarray(returns,dtype=float)
    if r.ndim!=1 or not np.isfinite(r).all() or (r<=-1).any() or not 1<=block<=len(r) or not 1<=n_sim<=10000:
        raise ValueError("Dữ liệu bootstrap không hợp lệ")
    rng=np.random.default_rng(seed)
    starts=rng.integers(0,len(r)-block+1,size=(n_sim,int(np.ceil(len(r)/block))))
    idx=(starts[:,:,None]+np.arange(block)).reshape(n_sim,-1)[:,:len(r)]
    paths=np.concatenate([np.ones((n_sim,1)),np.cumprod(1+r[idx],axis=1)],axis=1)
    ret=100*(paths[:,-1]-1)
    dd=100*np.max(1-paths/np.maximum.accumulate(paths,axis=1),axis=1)
    samples=pd.DataFrame({"Lần mô phỏng":np.arange(1,n_sim+1),"Lợi nhuận (%)":ret,"MDD độ lớn (%)":dd})
    stats={"Block":block,"Số mô phỏng":n_sim,"Số lợi nhuận phiên":len(r),"Seed":seed,
           "LN P05 (%)":float(np.quantile(ret,.05)),"LN P50 (%)":float(np.median(ret)),"LN P95 (%)":float(np.quantile(ret,.95)),
           "MDD P50 (%)":float(np.median(dd)),"MDD P95 (%)":float(np.quantile(dd,.95)),
           "Tỷ lệ LN âm (%)":100*float(np.mean(ret<0)),"Tỷ lệ MDD >10% (%)":100*float(np.mean(dd>10))}
    return stats,samples

def walk_forward(results,capital):
    """Expanding selection on shadow portfolios; test slices carry original
    positions. The stitched return is diagnostic, not a tradable switching account.
    """
    calendar=results["A4"][1].index
    rows,selection=[],[]
    for year in (2024,2025,2026):
        for month in (1,7):
            start=pd.Timestamp(year,month,1)
            end=start+pd.DateOffset(months=6)
            train=calendar<start
            test=(calendar>=start)&(calendar<end)
            if not train.any() or not test.any(): continue
            first=int(np.flatnonzero(test)[0])
            last=int(np.flatnonzero(test)[-1])
            elig=[]
            local=[]
            for name in CANDIDATES:
                _,curve,ledger,_,_=results[name]
                train_eq=np.r_[capital,curve.loc[train,"Equity"].to_numpy()]
                train_stats=stats_equity(train_eq)
                n=int((ledger["Ngày bán"]<start).sum()) if len(ledger) else 0
                sharpe=train_stats["Sharpe (rf=0)"]
                allowed=n>=10 and train_stats["MDD (%)"]>=-10 and sharpe is not None
                if allowed: elig.append((float(sharpe),name))
                seq=np.r_[curve["Equity"].iloc[first-1],curve["Equity"].iloc[first:last+1].to_numpy()]
                test_stats=stats_equity(seq)
                local.append({"Cấu hình":name,"Train từ":calendar[0],"Train đến":calendar[first-1],
                              "Test từ":calendar[first],"Test đến":calendar[last],"Số phiên test":last-first+1,
                              "Lệnh đóng train":n,"Sharpe train":sharpe,"MDD train (%)":train_stats["MDD (%)"],
                              "Đủ điều kiện chọn":allowed,"LN test (%)":test_stats["Lợi nhuận (%)"],
                              "MDD test cục bộ (%)":test_stats["MDD (%)"],"Sharpe test":test_stats["Sharpe (rf=0)"]})
            chosen=sorted(elig,key=lambda p:(-p[0],CANDIDATES.index(p[1])))[0][1] if elig else "A4"
            for row in local:
                row["Được chọn từ train"]=row["Cấu hình"]==chosen
                rows.append(row)
                if row["Được chọn từ train"]:
                    selection.append(dict(row))
    return pd.DataFrame(rows),pd.DataFrame(selection)

def benchmarks(signals,context,curve,capital):
    c=context["VNINDEX Close"]
    index_return=c.pct_change().fillna(0.)
    exposure=curve["Exposure (%)"].shift(1).fillna(0.)/100
    if not exposure.between(0,1+1e-10).all(): raise ValueError("Exposure không hợp lệ")
    # Fractional, frictionless price-only references. Lagged exposure known at prior close.
    equal=pd.DataFrame({s:d["close"]/d["close"].iloc[0] for s,d in signals.items()}).mean(axis=1)
    values=pd.DataFrame({"A4":curve["Equity"]/capital*100,
        "VNINDEX":100*c/c.iloc[0],f"BuyHold {len(signals)} mã (giá)":100*equal,"Tiền mặt":100.,
        "VNINDEX lag Exposure":100*(1+exposure*index_return).cumprod(),
        "Exposure trễ (%)":100*exposure},index=curve.index)
    rows=[]
    years=(values.index[-1]-values.index[0]).days/365.25
    for col in values.columns[:-1]:
        s=stats_equity(values[col])
        cagr=100*((values[col].iloc[-1]/values[col].iloc[0])**(1/years)-1) if years>0 else None
        mdd=abs(s["MDD (%)"])
        rows.append({"Đối chứng":col,**s,"CAGR (%)":cagr,
                     "Calmar":cagr/mdd if mdd>0 and cagr is not None else None})
    return pd.DataFrame(rows),values.rename_axis("Ngày").reset_index()

def evaluate_robustness(histories,index,policy=Policy(),n_sim=N_SIM,require_reference_calendar=False):
    if policy.costs!=Costs() or policy.risk!=.005 or policy.stock_cap!=.15:
        raise ValueError("KT12 yêu cầu R1 cơ sở")
    histories={s:historical_slice(d) for s,d in histories.items()}
    index=historical_slice(index)
    signals=prepare_signals(histories,"S0P0")
    signals,context=enrich(signals,index)
    calendar=context.index
    if require_reference_calendar and (len(calendar)!=1217 or calendar[0]!=pd.Timestamp("2022-01-04") or calendar[-1]!=HISTORY_END):
        raise ValueError("Lịch hồi cứu khác báo cáo tham chiếu 1.217 phiên (04/01/2022–23/11/2026); kiểm tra dữ liệu nguồn.")
    # KT12 uses frozen historical date even if source already includes later bars.
    results={name:simulate_portfolio(signals,"S0P0","R1",policy,entry_gate=fn)
             for name,fn in candidates(signals).items()}
    base=results["A4"]
    # Exact legacy gate parity (same context, no cost overrides).
    check=simulate_portfolio(signals,"S0P0","R1",policy,entry_gate=lambda s,r:reject_reason(r,BY_FILTER["A4"]))
    for a,b in zip(base[1:],check[1:]): pd.testing.assert_frame_equal(a,b)
    rows,eqs,trades,orders,windows=[],[],[],[],[]
    def add(group,name,result,p,limit,label):
        s,c,l,o,w=result
        st=stats_equity(np.r_[p.capital,c["Equity"].to_numpy()])
        rows.append({**s,"Nhóm":group,"Kịch bản":name,"Quy tắc":label,"Rủi ro/lệnh (%)":100*p.risk,
             "Trần mã (%)":100*p.stock_cap,"SMA50 tối đa (%)":limit,
             "Phí mua (%)":100*p.costs.buy_fee,"Phí bán (%)":100*p.costs.sell_fee,
             "Thuế bán (%)":100*p.costs.sell_tax,"Trượt mỗi chiều (%)":100*p.costs.slippage,
             "Sortino (MAR=0)":st["Sortino (MAR=0)"],
             "Calmar":s["CAGR (%)"]/abs(s["MDD (%)"]) if s["CAGR (%)"] is not None and s["MDD (%)"]<0 else None,
             "Chênh LN so A4 (đpt)":s["Lợi nhuận (%)"]-base[0]["Lợi nhuận (%)"],
             "Cải thiện MDD so A4 (đpt)":s["MDD (%)"]-base[0]["MDD (%)"]})
        for f,target in ((c.reset_index(),eqs),(l,trades),(o,orders),(w,windows)):
            if not f.empty: target.append(f.assign(**{"Nhóm":group,"Kịch bản":name}))
    for name,r in results.items(): add("Ứng viên",name,r,policy, None if name=="A0" else 15,name)
    for name,cost in COSTS.items():
        p=replace(policy,costs=cost)
        r=base if name=="C0" else simulate_portfolio(signals,"S0P0","R1",p,entry_gate=gate_limit(15))
        add("Chi phí",name,r,p,15,name)
    for name,p,limit,label in sensitivity(policy):
        r=base if name=="BASE" else simulate_portfolio(signals,"S0P0","R1",p,entry_gate=gate_limit(limit))
        add("Độ nhạy",name,r,p,limit,label)
    wf,selected=walk_forward(results,policy.capital)
    mc,mc_samples=[],[]
    daily=base[1]["Equity"].pct_change().dropna()
    for sample,ret in (("Toàn kỳ",daily),("Sau warmup 200",daily.iloc[199:])):
        for b in BLOCKS:
            if len(ret)<b: continue
            st,draws=block_bootstrap(ret,b,n_sim)
            mc.append(dict(st,**{"Mẫu":sample}))
            mc_samples.append(draws.assign(**{"Mẫu":sample,"Block":b}))
    bm,bm_eq=benchmarks(signals,context,base[1],policy.capital)
    def join(frames): return pd.concat(frames,ignore_index=True) if frames else pd.DataFrame()
    return {"summary":pd.DataFrame(rows),"equity":join(eqs),"trades":join(trades),"orders":join(orders),"windows":join(windows),
            "wf":wf,"selection":selected,"mc":pd.DataFrame(mc),"mc_samples":join(mc_samples),"benchmark":bm,"benchmark_equity":bm_eq}
