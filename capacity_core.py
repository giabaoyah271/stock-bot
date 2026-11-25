"""KT18: prespecified capacity and concentration sensitivity; never changes live rules."""
from dataclasses import replace
import numpy as np
import pandas as pd
from full_universe_core import check_zip,load_inputs,enrich_causal,stock_rows,SECTORS
from concentration_core import compare_frame
from portfolio_core import simulate_portfolio
from robustness_core import COSTS,stats_equity,block_bootstrap,BLOCKS,N_SIM
from market_research_core import rank_rs

SHA17="8b88545ee77eb9054a90e69d14dbc0b278a161da00d43727d35d09de8a31a6d3"
GROUPS=("U5-A","U5-B")
# Baseline first, no search beyond the predeclared 3 x 2 design.
CAPACITY=((5,.005),(5,.0025),(8,.005),(8,.0025),(10,.005),(10,.0025))
PARTS=("MAIN","LOO1","LOO2","LOO3","LOO4","LOO5")
KEYS=("tong_hop","equity","giao_dich","lenh","cua_so","theo_ma","theo_nganh","monte_carlo","monte_carlo_mau","walk_forward","loi")

def capacity_id(n,risk):
    return f"P{n}-R{int(round(risk*10000)):03d}"

def split_loo(symbols):
    s=sorted(symbols)
    if len(s)!=115 or len(set(s))!=115: raise ValueError("LOO cần đúng 115 mã")
    return {f"LOO{i+1}":tuple(s[i*23:(i+1)*23]) for i in range(5)}

def read_kt17(data):
    with check_zip(data,SHA17) as z:
        f={k:pd.read_csv(z.open("stock_bot_kt17_"+k+".csv"),float_precision="round_trip") for k in ("tong_hop","equity","giao_dich","lenh","cua_so","theo_ma","pham_vi","loi")}
    meta=f["pham_vi"]
    if len(meta)!=1 or int(meta.iloc[0]["Kịch bản đạt"])!=40 or len(f["tong_hop"])!=40 or len(f["loi"]) or f["tong_hop"]["Kịch bản"].duplicated().any():
        raise ValueError("Báo cáo KT17 không đủ 40 kịch bản")
    return f

def run(signals,calendar,policy,rank="RS60"):
    if rank not in ("BUY","RS60"): raise ValueError("Xếp hạng không hợp lệ")
    return simulate_portfolio(signals,"S0P0","R1",policy,entry_rank=rank_rs if rank=="RS60" else None,session_calendar=calendar,sector_map=SECTORS)

def verify_kt17(result,archive,group,rank):
    case=f"{group}-FULL-A0-C0-{rank}-L0"
    su,eq,l,o,w=result
    for df,key in ((pd.DataFrame([su]),"tong_hop"),(eq.reset_index(),"equity"),(l,"giao_dich"),(o,"lenh"),(w,"cua_so")):
        compare_frame(df,archive[key],case)

def drop_two(archive,group):
    case=f"{group}-FULL-A0-C0-RS60-L0"
    rows=archive["theo_ma"].loc[archive["theo_ma"]["Kịch bản"]==case]
    if len(rows)!=(106 if group=="U5-A" else 115) or rows["Mã"].duplicated().any():
        raise ValueError("Thiếu P&L đối chứng")
    return tuple(rows.sort_values(["P&L tổng (VND)","Mã"],ascending=[False,True]).head(2)["Mã"])

def diagnostic_walk_forward(results,capital,group):
    """Fixed shadow accounts; choose on expanding train only. No stitched tradable equity."""
    if set(results)!={capacity_id(n,r) for n,r in CAPACITY}: raise ValueError("Thiếu cấu hình capacity")
    cal=next(iter(results.values()))[1].index
    rows=[]
    for year in (2024,2025,2026):
        for month in (1,7):
            start=pd.Timestamp(year,month,1);end=start+pd.DateOffset(months=6)
            tr=cal<start;te=(cal>=start)&(cal<end)
            if not tr.any() or not te.any(): continue
            first=int(np.flatnonzero(te)[0]);last=int(np.flatnonzero(te)[-1])
            local=[];eligible=[]
            for i,(n,r) in enumerate(CAPACITY):
                name=capacity_id(n,r);_,curve,ledger,_,_=results[name]
                eq=curve["Equity"].to_numpy()
                a=stats_equity(np.r_[capital,eq[tr]])
                b=stats_equity(eq[first-1:last+1])
                count=int((ledger["Ngày bán"]<start).sum()) if len(ledger) else 0
                sharpe=a["Sharpe (rf=0)"]
                ok=count>=10 and a["MDD (%)"]>=-10 and sharpe is not None
                if ok: eligible.append((-sharpe,i,name))
                local.append({"Nhóm":group,"Cấu hình capacity":name,"Train từ":cal[0],"Train đến":cal[first-1],
                    "Test từ":cal[first],"Test đến":cal[last],"Số phiên test":last-first+1,"Lệnh đóng train":count,
                    "Sharpe train":sharpe,"MDD train (%)":a["MDD (%)"],"Đủ điều kiện chọn":ok,
                    "LN test (%)":b["Lợi nhuận (%)"],"MDD test cục bộ (%)":b["MDD (%)"],"Sharpe test":b["Sharpe (rf=0)"]})
            chosen=min(eligible)[2] if eligible else None
            for row in local:
                row["Được chọn từ train"]=row["Cấu hình capacity"]==chosen
                row["Không có ứng viên đạt train"]=chosen is None
                rows.append(row)
    return pd.DataFrame(rows)

def evaluate_capacity(data,archive,part="MAIN",n_sim=N_SIM,progress=None):
    if part not in PARTS: raise ValueError("Phần KT18 không hợp lệ")
    universe,calendar,index,policy,*_=data
    signals={g:enrich_causal(universe[g],index,policy.price_scale) for g in GROUPS}
    base={}
    for g in GROUPS:
        for rank in ("BUY","RS60"):
            result=run(signals[g],calendar,policy,rank)
            verify_kt17(result,archive,g,rank)
            base[g,rank]=result
    # MAIN 22 cases: 12 grid, 2 BUY controls, 6 cost stress, 2 drop-two.
    # LOO: 23 omissions per part, fixed U5-B A0-RS60 baseline policy only.
    jobs=[]
    if part=="MAIN":
        for g in GROUPS:
            jobs.extend((g,"CAPACITY",n,r,"C0","RS60",()) for n,r in CAPACITY)
            jobs.append((g,"CONTROL",5,.005,"C0","BUY",()))
            jobs.extend((g,"COST",5,.005,c,"RS60",()) for c in ("C1","C2","C3"))
            jobs.append((g,"DROP2",5,.005,"C0","RS60",drop_two(archive,g)))
    else:
        jobs.extend(("U5-B","LOO",5,.005,"C0","RS60",(s,)) for s in split_loo(signals["U5-B"])[part])
    report={k:[] for k in KEYS};wf={g:{} for g in GROUPS}
    def add(k,d):
        if len(d): report[k].append(d)
    for i,(g,kind,n,r,c,rank,omit) in enumerate(jobs):
        name=capacity_id(n,r)
        case=f"{g}-{kind}-{name}-{c}-{rank}"+("-"+",".join(omit) if omit else "")
        tags={"Nhóm":g,"Loại":kind,"Kịch bản":case,"Cấu hình capacity":name,"Số vị thế giới hạn":n,"Rủi ro/lệnh (%)":r*100,
              "Chi phí":c,"Xếp hạng":rank,"Mã loại":",".join(omit)}
        try:
            p=replace(policy,max_positions=n,risk=r,costs=COSTS[c])
            sig={s:d for s,d in signals[g].items() if s not in omit}
            result=base[g,rank] if n==5 and r==.005 and c=="C0" and not omit else run(sig,calendar,p,rank)
            su,eq,ledger,orders,windows=result
            if su["Số vị thế max"]>n or (eq["Tiền mặt"]< -1e-7).any(): raise ValueError("Vi phạm giới hạn vốn/vị thế")
            if len(orders):
                buys=orders.loc[orders["Lệnh"]=="Mua"]
                if len(buys) and ((buys["Rủi ro dự kiến (VND)"]>r*buys["Equity trước mua (VND)"]+1e-6).any() or (buys["Vốn mua (VND)"]>p.stock_cap*buys["Equity trước mua (VND)"]+1e-6).any()):
                    raise ValueError("Vi phạm sizing lúc mua")
            detail=stock_rows(sig,ledger,orders,p,SECTORS)
            if not np.isclose(detail["P&L tổng (VND)"].sum(),su["Vốn cuối"]-p.capital,atol=.001,rtol=0): raise ValueError("P&L không khớp")
            st=stats_equity(eq["Equity"].to_numpy())
            baseline=base[g,"RS60"][0]
            reject=orders.loc[orders["Lệnh"]=="Bỏ mua","Lý do"] if len(orders) else pd.Series(dtype=str)
            row={**su,**tags,"Sortino (MAR=0)":st["Sortino (MAR=0)"],"Calmar":su["CAGR (%)"]/abs(su["MDD (%)"]) if su["MDD (%)"]<0 else None,
                 "Chênh LN so RS60 gốc (đpt)":su["Lợi nhuận (%)"]-baseline["Lợi nhuận (%)"],
                 "Chênh MDD so RS60 gốc (đpt)":su["MDD (%)"]-baseline["MDD (%)"],
                 "Bỏ mua giới hạn vị thế":int((reject=="Giới hạn vị thế").sum()),"Bỏ mua portfolio heat":int((reject=="Portfolio heat").sum())}
            mc=[];draws=[]
            # Bootstrap on fixed capacity and cost scenarios plus BUY controls;
            # no repeated bootstrap for ex-post omission diagnostics.
            if kind in ("CAPACITY","COST","CONTROL"):
                for b in BLOCKS:
                    m,s=block_bootstrap(eq["Equity"].pct_change().dropna(),b,n_sim)
                    mc.append({**m,**tags});draws.append(s.assign(**tags,Block=b))
            add("tong_hop",pd.DataFrame([row]))
            add("cua_so",windows.assign(**tags))
            if kind!="LOO":
                agg=detail.groupby("Ngành",as_index=False)[["Lệnh mua","Lệnh đóng","CP cuối","P&L đã đóng (VND)","P&L mở (VND)","P&L tổng (VND)"]].sum()
                for k,d in (("equity",eq.reset_index()),("giao_dich",ledger),("lenh",orders),("theo_ma",detail),("theo_nganh",agg)):
                    add(k,d.assign(**tags))
            if mc: add("monte_carlo",pd.DataFrame(mc));report["monte_carlo_mau"].extend(draws)
            if kind=="CAPACITY": wf[g][name]=result
        except Exception as exc:
            add("loi",pd.DataFrame([{**tags,"Lỗi":str(exc)[:500] if isinstance(exc,(ValueError,AssertionError)) else type(exc).__name__}]))
        if progress: progress(i+1,len(jobs),case)
    if part=="MAIN":
        for g in GROUPS:
            if len(wf[g])==len(CAPACITY): add("walk_forward",diagnostic_walk_forward(wf[g],policy.capital,g))
            else: add("loi",pd.DataFrame([{"Nhóm":g,"Lỗi":"Không đủ 6 cấu hình để Walk-Forward"}]))
    out={k:pd.concat(v,ignore_index=True) if v else pd.DataFrame() for k,v in report.items()}
    if out["loi"].empty: out["loi"]=pd.DataFrame(columns=["Kịch bản","Lỗi"])
    out["pham_vi"]=pd.DataFrame([{"Phần":part,"Kịch bản dự kiến":len(jobs),"Kịch bản đạt":len(out["tong_hop"]),"Đối chứng KT17":4,
        "SHA KT17":SHA17,"Từ":calendar[0],"Đến":calendar[-1],"Số phiên":len(calendar),"U5-A":106,"U5-B":115,"U5 theo dõi":120,
        "Vốn đầu":policy.capital,"Stock cap (%)":100*policy.stock_cap,"Sector cap (%)":100*policy.sector_cap,"Heat cap (%)":100*policy.heat_cap,
        "N_sim/block":n_sim,"Pháp lý":"Chưa xác minh; chỉ nghiên cứu hồi cứu","Walk-forward":"Shadow accounts; không giao dịch chuyển cấu hình"}])
    return out
