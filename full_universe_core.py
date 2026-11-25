"""KT17: frozen archive replay, independent portfolio accounts, no live trades."""
import io,hashlib,json,zipfile
from dataclasses import replace
import numpy as np
import pandas as pd
from concentration_core import read_archive,validate_archive,compare_frame,verify_base
from cross_section_core import U0,ALL,EXT_SECTORS
from universe_u5 import U5
from universe_prepare_core import SECTORS,dates_for,COMPARE,ZERO_COUNTS,U5_SHA,KT15_SHA
from portfolio_core import Policy,simulate_portfolio
from robustness_core import COSTS,stats_equity,block_bootstrap,BLOCKS,N_SIM
from entry_filter_core import BY_FILTER,reject_reason,signal_catalog
from market_research_core import rank_rs
from trade_diagnostics import _validate

SHA_A="2fa25ab77642baa6f4f75bdf7676aa2e1a308f40aec2ce5f243c3cbe52df396d"
SHA_B="61972c07080bad830d66636319d34625bb97c9863ae10fe460805c55ca22cdf5"
SHA_16="cdad7e568d4a04c6a360d810381286cb8b38f79277f95da06334ccce8b28a5a7"
ADDITIONS=("CEO","IDC","LAS","MBS","PVS","QNS","SHS","VEA","VGS")
UNAVAILABLE=("CC1","DMX","GEL","NAB","VBB")
GROUPS=("U0","U4","U5-A","U5-B")
FULL_CASES=(("A0","C0","BUY","L0"),("A4","C0","BUY","L0"),("A0","C0","RS60","L0"),("A4","C0","RS60","L0"),
            ("A4","C1","BUY","L0"),("A4","C2","BUY","L0"),("A4","C3","BUY","L0"),("A4","C0","BUY","L10"))
MAX_BYTES=40*1024*1024
LIQ_LIMIT=10_000_000_000

def check_zip(data,sha):
    if not data or len(data)>MAX_BYTES or hashlib.sha256(data).hexdigest()!=sha:
        raise ValueError("ZIP không đúng bản gốc đã nghiệm thu (SHA256)")
    z=zipfile.ZipFile(io.BytesIO(data))
    if len(set(z.namelist()))!=len(z.namelist()) or sum(x.file_size for x in z.infolist())>MAX_BYTES:
        z.close();raise ValueError("ZIP trùng tên hoặc quá lớn")
    return z

def read_prep(data,sha,calendar,index,old,extended):
    with check_zip(data,sha) as z:
        def frame(k): return pd.read_csv(z.open("stock_bot_kt170prep_"+k+".csv"),float_precision="round_trip")
        cov=frame("chat_luong").set_index("Mã");src=frame("tin_hieu");ix=frame("vnindex");om=frame("ngay_loai")
        m=json.loads(z.read("stock_bot_kt170prep_manifest.json"))
    expected=set(U5)-set(UNAVAILABLE)-(set() if extended else set(ADDITIONS))
    if (m["U5_SHA256"],m["KT15_SHA256"],m["Đơn vị giá"],m["Nến thực"],m["Cho phép prefix"],m["Mã đạt"])!=(U5_SHA,KT15_SHA,1000,True,extended,len(expected)):
        raise ValueError("Manifest KT17.0a-e khác hồ sơ")
    if cov.index.has_duplicates or set(cov.index)!=set(U5) or set(cov.index[cov["Trạng thái"]=="Đạt nghiên cứu"])!=expected or set(src["Mã"])!=expected:
        raise ValueError("Tập mã không khớp hồ sơ")
    if not pd.DatetimeIndex(pd.to_datetime(ix["Ngày"])).equals(calendar):
        raise ValueError("Lịch VNINDEX khác KT15")
    np.testing.assert_allclose(ix["VNINDEX Close"],index.to_numpy(),rtol=0,atol=1e-10)
    out={}
    for s,x in src.groupby("Mã",sort=False):
        d=x.drop(columns="Mã").copy()
        d.index=pd.DatetimeIndex(pd.to_datetime(d.pop("Ngày")),name="Ngày")
        _validate(d)
        p=cov.at[s,"Prefix OHLC đến"];p=None if pd.isna(p) else str(p)
        if bool(p)!=(extended and s in ADDITIONS): raise ValueError(s+": prefix khác hồ sơ")
        z=pd.DatetimeIndex(pd.to_datetime(om.loc[(om["Mã"]==s)&(om["Lý do"]=="Không có giao dịch"),"Ngày"]))
        exp=dates_for(s,calendar,p)
        if len(z)!=ZERO_COUNTS.get(s,0) or z.has_duplicates or not z.isin(exp).all() or not d.index.equals(exp.difference(z)):
            raise ValueError(s+": lịch không khớp")
        if len(d)<200 or len(d)!=cov.at[s,"Nến"] or d.index[199]!=pd.Timestamp(cov.at[s,"Nến thứ 200"]) or d.index[-1]!=calendar[-1]:
            raise ValueError(s+": warmup/phạm vi khác")
        if (d["volume"]<=0).any() or not d["Trend"].isin([-1,1]).all() or not (d["Trend"].iloc[:199]==-1).all():
            raise ValueError(s+": volume/Trend sai")
        for n in (50,200): np.testing.assert_allclose(d[f"SMA{n}"],d["close"].rolling(n).mean(),rtol=1e-9,atol=1e-8,equal_nan=True)
        if not np.isfinite(d[["ATR","Buy_Pct"]].iloc[199:].to_numpy()).all() or (d["ATR"].iloc[199:]<0).any(): raise ValueError(s+": chỉ báo sai")
        d["Reason"]=d["Reason"].fillna("")
        if s in old: pd.testing.assert_frame_equal(d[old[s].columns],old[s],check_dtype=False,check_exact=True)
        if cov.at[s,"Ngành đề xuất"]!=SECTORS[s]: raise ValueError(s+": ngành khác")
        out[s]=d
    if len(set(out)&set(old))!=29: raise ValueError("Thiếu 29 mã đối chứng")
    return out,cov

def load_inputs(kt15,kt16,a,b):
    with check_zip(kt15,KT15_SHA): pass
    f,_=read_archive(kt15)
    old,cal,policy,shortened=validate_archive(f)
    if not shortened or policy.price_scale!=1000: raise ValueError("KT15 không đúng cấu hình")
    with check_zip(kt16,SHA_16) as z:
        f16={k:pd.read_csv(z.open("stock_bot_kt16_"+k+".csv"),float_precision="round_trip") for k in ("tong_hop","equity","giao_dich","lenh","cua_so")}
    index=pd.Series(f["vnindex"]["VNINDEX Close"].to_numpy(),index=cal)
    sa,ca=read_prep(a,SHA_A,cal,index,old,False)
    sb,cb=read_prep(b,SHA_B,cal,index,old,True)
    for s in sa: pd.testing.assert_frame_equal(sa[s],sb[s],check_dtype=False,check_exact=True)
    return {"U0":{s:old[s] for s in U0},"U4":old,"U5-A":sa,"U5-B":sb},cal,index,policy,f,f16,ca,cb

def enrich_causal(signals,index,scale):
    out={}
    for s,d in signals.items():
        x=d.copy()
        m=index.reindex(d.index)
        # Same start/end dates for stock and index; 60 actual stock candles,
        # not necessarily 60 market sessions for newly listed/paused symbols.
        x["RS60 (đpt)"]=100*(x["close"]/x["close"].shift(60)-m/m.shift(60))
        x["GTGD proxy 20 (VND)"]=(x["close"]*x["volume"]*scale).rolling(20,min_periods=20).mean()
        out[s]=x
    return out

def make_gate(variant,liq):
    def check(s,row):
        if variant=="A4":
            r=reject_reason(row,BY_FILTER["A4"])
            if r: return r
        if liq=="L10":
            v=float(row.get("GTGD proxy 20 (VND)",np.nan))
            if not np.isfinite(v) or v<LIQ_LIMIT: return "Thanh khoản proxy 20 nến dưới 10 tỷ/thiếu"
        return ""
    return None if variant=="A0" and liq=="L0" else check

def stock_rows(signals,ledger,orders,policy,sectors):
    rows=[]
    for s,d in sorted(signals.items()):
        l=ledger.loc[ledger["Mã"]==s] if len(ledger) else ledger
        o=orders.loc[orders["Mã"]==s] if len(orders) else orders
        buys=o.loc[o["Lệnh"]=="Mua"] if len(o) else o
        qty=int(buys["Số CP"].sum() if len(buys) else 0)-int(l["Số CP"].sum() if len(l) else 0)
        cost=float(buys["Vốn mua (VND)"].sum() if len(buys) else 0)-float(l["Vốn mua (VND)"].sum() if len(l) else 0)
        realized=float(l["Lãi/lỗ (VND)"].sum()) if len(l) else 0.
        unrealized=qty*float(d["close"].iloc[-1])*policy.price_scale-cost
        rows.append({"Mã":s,"Ngành":sectors[s],"Lệnh mua":len(buys),"Lệnh đóng":len(l),"CP cuối":qty,
                    "P&L đã đóng (VND)":realized,"P&L mở (VND)":unrealized,"P&L tổng (VND)":realized+unrealized})
    return pd.DataFrame(rows)

def common_slice(signals,calendar,start):
    cal=calendar[calendar>=start]
    out={s:d.loc[d.index>=start].copy() for s,d in signals.items()}
    if any(not d.index.equals(cal) for d in out.values()):
        raise ValueError("Giai đoạn chung không khớp lịch")
    return out,cal

def check_reference(result,group,variant,f,f16):
    if group=="U0": verify_base(result,f,"U0",variant)
    elif group=="U4":
        case=f"U4-{variant}-FULL"
        su,eq,l,o,w=result
        for frame,k in ((pd.DataFrame([su]),"tong_hop"),(eq.reset_index(),"equity"),(l,"giao_dich"),(o,"lenh"),(w,"cua_so")):
            compare_frame(frame,f16[k],case)

def evaluate(data,groups=GROUPS,include_common=True,n_sim=N_SIM,progress=None):
    universe,calendar,index,policy,f,f16,ca,cb=data
    if not groups or len(set(groups))!=len(groups) or not set(groups).issubset(GROUPS):
        raise ValueError("Nhóm không hợp lệ")
    # Verify all four baseline accounts before any new experiments, even if
    # the user selects only U5-B for the report.
    references={}
    for g in ("U0","U4"):
        for v in ("A0","A4"):
            r=simulate_portfolio(universe[g],"S0P0","R1",policy,entry_gate=make_gate(v,"L0"),session_calendar=calendar,sector_map=EXT_SECTORS)
            check_reference(r,g,v,f,f16);references[g,v]=r
    start=max(d.index[199] for d in universe["U5-B"].values())
    if start!=pd.Timestamp("2026-10-08") or len(calendar[calendar>=start])!=33: raise ValueError("Mốc chung không khớp hồ sơ")
    keys=("tong_hop","equity","giao_dich","lenh","cua_so","theo_ma","theo_nganh","tin_hieu","monte_carlo","monte_carlo_mau","loi")
    report={k:[] for k in keys}
    total=len(groups)*(len(FULL_CASES)+(2 if include_common else 0));count=0
    for group in groups:
        sectors=EXT_SECTORS if group in ("U0","U4") else SECTORS
        signals=enrich_causal(universe[group],index,policy.price_scale)
        horizons=[("FULL",signals,calendar,FULL_CASES)]
        if include_common:
            sub,cal=common_slice(signals,calendar,start);horizons.append(("COMMON",sub,cal,FULL_CASES[:2]))
        for horizon,sig,cal,cases in horizons:
            base=None
            for v,c,r,l in cases:
                case=f"{group}-{horizon}-{v}-{c}-{r}-{l}"
                tags={"Nhóm":group,"Phạm vi":horizon,"Bộ lọc":v,"Chi phí":c,"Xếp hạng":r,"Thanh khoản":l,"Kịch bản":case}
                try:
                    p=replace(policy,costs=COSTS[c])
                    result=references[group,v] if horizon=="FULL" and group in ("U0","U4") and c=="C0" and r=="BUY" and l=="L0" else simulate_portfolio(sig,"S0P0","R1",p,entry_gate=make_gate(v,l),entry_rank=rank_rs if r=="RS60" else None,session_calendar=cal,sector_map=sectors)
                    su,eq,ledger,orders,windows=result
                    detail=stock_rows(sig,ledger,orders,p,sectors)
                    if not np.isclose(detail["P&L tổng (VND)"].sum(),su["Vốn cuối"]-p.capital,atol=.001,rtol=0): raise ValueError("P&L theo mã không khớp")
                    agg=detail.groupby("Ngành",as_index=False)[["Lệnh mua","Lệnh đóng","CP cuối","P&L đã đóng (VND)","P&L mở (VND)","P&L tổng (VND)"]].sum()
                    st=stats_equity(eq["Equity"].to_numpy())
                    if (v,c,r,l)==FULL_CASES[0]: base=su
                    if base is None: raise ValueError("Thiếu A0 đối chứng")
                    cat=pd.DataFrame()
                    if horizon=="FULL" and c=="C0":
                        cat=signal_catalog(sig)
                        if len(cat):
                            for col in ("RS60 (đpt)","GTGD proxy 20 (VND)","Buy_Pct"):
                                cat[col]=[sig[s].at[t,col] for s,t in zip(cat["Mã"],cat["Ngày tín hiệu mua"])]
                            if len(orders):
                                buy=orders.loc[orders["Lệnh"].isin(["Mua","Bỏ mua"]),["Mã","Ngày","Lệnh","Lý do"]]
                                cat=cat.merge(buy,on=["Mã","Ngày"],how="left",validate="one_to_one")
                                if cat["Lệnh"].isna().any(): raise ValueError("Tín hiệu không khớp audit")
                            else: raise ValueError("Thiếu nhật ký lệnh")
                    mc=[];samples=[]
                    if horizon=="FULL" and c=="C0" and r=="BUY" and l=="L0":
                        for block in BLOCKS:
                            m,draws=block_bootstrap(eq["Equity"].pct_change().dropna(),block,n_sim)
                            mc.append({**m,**tags});samples.append(draws.assign(**tags,Block=block))
                    report["tong_hop"].append(pd.DataFrame([{**su,**tags,"Sortino (MAR=0)":st["Sortino (MAR=0)"],"Calmar":su["CAGR (%)"]/abs(su["MDD (%)"]) if su["MDD (%)"]<0 else None,
                        "Chênh LN so A0 (đpt)":su["Lợi nhuận (%)"]-base["Lợi nhuận (%)"],"Chênh MDD so A0 (đpt)":su["MDD (%)"]-base["MDD (%)"],
                        "Phiên định giá cũ":int((eq["Vị thế định giá Close cũ"]>0).sum())}]))
                    for key,frame in (("equity",eq.reset_index()),("giao_dich",ledger),("lenh",orders),("cua_so",windows),("theo_ma",detail),("theo_nganh",agg),("tin_hieu",cat)):
                        if len(frame): report[key].append(frame.assign(**tags))
                    if mc: report["monte_carlo"].append(pd.DataFrame(mc));report["monte_carlo_mau"].extend(samples)
                except Exception as exc:
                    report["loi"].append(pd.DataFrame([{**tags,"Lỗi":str(exc)[:500] if isinstance(exc,(ValueError,AssertionError)) else type(exc).__name__}]))
                count+=1
                if progress: progress(count,total,case)
    out={k:pd.concat(v,ignore_index=True) if v else pd.DataFrame() for k,v in report.items()}
    if out["loi"].empty: out["loi"]=pd.DataFrame(columns=["Kịch bản","Lỗi"])
    out["pham_vi"]=pd.DataFrame([{"Nhóm chọn":",".join(groups),"Kịch bản dự kiến":total,"Kịch bản đạt":len(out["tong_hop"]),"Đối chứng KT15/KT16":4,
        "SHA KT15":KT15_SHA,"SHA KT16":SHA_16,"SHA U5-A":SHA_A,"SHA U5-B":SHA_B,"Từ":calendar[0],"Đến":calendar[-1],"Số phiên":len(calendar),
        "Giai đoạn chung từ":start,"Giai đoạn chung số phiên":33,"U5 ứng viên":120,"U5-A":106,"U5-B":115,"Mã chưa đạt":",".join(UNAVAILABLE),
        "N_sim/block":n_sim,"Pháp lý":"Chưa xác minh; hồi cứu, không giao dịch thật","Thanh khoản":"Proxy close*volume từ nến thực đến tín hiệu; không phải GTGD chính thức"}])
    out["chat_luong"]=cb.reset_index()
    return out
