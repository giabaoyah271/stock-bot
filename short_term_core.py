"""KT11: independent short-horizon entry rules, shared exit grid and R1 sizing."""
from dataclasses import dataclass
import numpy as np
import pandas as pd
from portfolio_core import Policy,prepare_signals,simulate_portfolio,BUY_MULT,SELL_MULT
from entry_filter_core import BY_FILTER,reject_reason,signal_catalog

STRATEGIES=("ST1","ST2","ST3")
BASELINE="S0P0-R1-A4"
INITIAL="KT11: Initial Stop"
TIME="KT11: Time Stop"
@dataclass(frozen=True)
class Exit:
    label: str
    sizing_code: str
    sessions: int

EXITS=(Exit("F3-T5","S2P0",5),Exit("F3-T10","S2P0",10),
       Exit("ATR15-T5","S5P0",5),Exit("ATR15-T10","S5P0",10))
CASE_IDS=(BASELINE,)+tuple(s+"-"+e.label for s in STRATEGIES for e in EXITS)

def entry_conditions(df):
    """All inputs known by signal close; previous 20 excludes current candle."""
    need=("open","high","low","close","volume","ATR","RSI","Buy_Pct")
    if not set(need).issubset(df.columns):
        raise ValueError("Thiếu OHLCV/ATR/RSI/điểm mua")
    c=df["close"].astype(float)
    v=df["volume"].astype(float)
    sma10=c.rolling(10,min_periods=10).mean()
    sma20=c.rolling(20,min_periods=20).mean()
    sma50=c.rolling(50,min_periods=50).mean()
    sma200=c.rolling(200,min_periods=200).mean()
    high20=df["high"].astype(float).shift(1).rolling(20,min_periods=20).max()
    vol20=v.shift(1).rolling(20,min_periods=20).mean()
    rsi=pd.to_numeric(df["RSI"],errors="coerce")
    atr=pd.to_numeric(df["ATR"],errors="coerce")
    score=pd.to_numeric(df["Buy_Pct"],errors="coerce")
    ready=(sma200.notna() & np.isfinite(atr) & (atr>0) & np.isfinite(score) & (v>0))
    st1=(sma20>sma50)&(c>sma50)&(df["low"].shift(1)<=sma20.shift(1))&(c>sma10)&(c.shift(1)<=sma10.shift(1))&(c>c.shift(1))
    st2=(c>sma50)&(c>high20)&(c<=1.05*high20)&(vol20>0)&(v>=1.5*vol20)
    st3=(c>sma200)&(sma50>sma200)&(rsi.shift(1)<=35)&(rsi>35)&(c>c.shift(1))&rsi.between(0,100)&rsi.shift(1).between(0,100)
    return pd.DataFrame({"ST1":ready&st1,"ST2":ready&st2,"ST3":ready&st3,
                         "ST_SMA10":sma10,"ST_SMA20":sma20,"ST_SMA50":sma50,"ST_SMA200":sma200,
                         "ST_High20Prev":high20,"ST_Vol20Prev":vol20},index=df.index)

def replay_short(df,strategy,exit_config,features=None):
    """Virtual single-symbol cycle. After rejected buy, do not chase.
    Buy signal at i, fill i+1, time exit signal at i+N, sell i+N+1.
    Initial Stop from raw fill open and signal ATR; no intraday fills.
    """
    if strategy not in STRATEGIES or exit_config not in EXITS:
        raise ValueError("Cấu hình KT11 không hợp lệ")
    f=entry_conditions(df) if features is None else features
    if not f.index.equals(df.index):
        raise ValueError("Lịch feature không khớp")
    eligible=f[strategy].fillna(False).to_numpy(dtype=bool)
    opens=df["open"].to_numpy(dtype=float)
    closes=df["close"].to_numpy(dtype=float)
    atr=df["ATR"].to_numpy(dtype=float)
    state,entry=-1,-1
    stop=np.nan
    trends,reasons,stops,ages=[],[],[],[]
    for i in range(len(df)):
        reason=""
        age=np.nan
        if state==1:
            age=i-entry
            if age==1:
                stop=opens[i]*.97 if exit_config.sizing_code=="S2P0" else opens[i]-1.5*atr[entry]
            if np.isfinite(stop) and closes[i]<=stop:
                state,reason=-1,INITIAL
            elif age>=exit_config.sessions:
                state,reason=-1,TIME
        # Require a fresh edge; no same-close reentry on exit.
        elif i>=1 and eligible[i] and not eligible[i-1]:
            state,entry,stop,age=1,i,np.nan,0
        trends.append(state)
        reasons.append(reason)
        stops.append(stop if state==1 or reason else np.nan)
        ages.append(age)
        if state==-1: stop=np.nan
    out=df.copy()
    out["Trend"]=trends
    out["Reason"]=reasons
    out["ST_Stop"]=stops
    out["ST_Age"]=ages
    out["ST_Eligible"]=eligible
    return out

def excursions(d,buy,sell):
    """Gross raw price excursions; include only sell open, never sell-day high/low."""
    b=d.index.get_loc(buy)
    s=d.index.get_loc(sell)
    if not isinstance(b,(int,np.integer)) or not isinstance(s,(int,np.integer)) or s<=b:
        raise ValueError("Ngày khớp lệnh không hợp lệ")
    entry=float(d["open"].iloc[b])
    sell_open=float(d["open"].iloc[s])
    high=max(float(d["high"].iloc[b:s].max()),sell_open,entry)
    low=min(float(d["low"].iloc[b:s].min()),sell_open,entry)
    return {"MAE giá (%)":100*(low/entry-1),"MFE giá (%)":100*(high/entry-1),
            "MFE ròng giả định (%)":100*(high*SELL_MULT/(entry*BUY_MULT)-1),
            "Số phiên giữ":s-b}

def independent_audit(signals,orders):
    cat=signal_catalog(signals)
    if not orders.empty:
        buys=orders.loc[orders["Lệnh"].isin(["Mua","Bỏ mua"]),["Mã","Ngày","Lệnh","Lý do"]]
        cat=cat.merge(buys,on=["Mã","Ngày"],how="left",validate="one_to_one")
        if cat["Lệnh"].isna().any(): raise ValueError("Tín hiệu không khớp lệnh")
    else:
        cat["Lệnh"]=pd.Series(index=cat.index,dtype=object)
        cat["Lý do"]=pd.Series(index=cat.index,dtype=object)
        if len(cat): raise ValueError("Thiếu nhật ký lệnh")
    results=[]
    for _,r in cat.iterrows():
        d=signals[r["Mã"]]
        if pd.notna(r["Ngày bán giả định"]):
            e=excursions(d,r["Ngày"],r["Ngày bán giả định"])
            s=d.index.get_loc(r["Ngày bán giả định"])
            e["Lý do thoát độc lập"]=d["Reason"].iloc[s-1]
        else:
            e={"MAE giá (%)":np.nan,"MFE giá (%)":np.nan,"MFE ròng giả định (%)":np.nan,
               "Số phiên giữ":np.nan,"Lý do thoát độc lập":""}
        results.append(e)
    extra=pd.DataFrame(results,index=cat.index,columns=["MAE giá (%)","MFE giá (%)","MFE ròng giả định (%)","Số phiên giữ","Lý do thoát độc lập"])
    return pd.concat([cat,extra],axis=1)

def portfolio_excursions(ledger,signals):
    out=ledger.copy()
    if out.empty: return out
    values=[excursions(signals[r["Mã"]],r["Ngày mua"],r["Ngày bán"]) for _,r in out.iterrows()]
    e=pd.DataFrame(values,index=out.index)
    if not np.array_equal(e["Số phiên giữ"],out["Số phiên giữ"]): raise ValueError("Sai số phiên giữ")
    for col in ("MAE giá (%)","MFE giá (%)","MFE ròng giả định (%)"):
        out[col]=e[col]
    out["Giveback ròng (đpt)"]=out["MFE ròng giả định (%)"]-out["Lợi nhuận ròng (%)"]
    return out

def _stats(values):
    x=pd.to_numeric(values,errors="coerce").dropna()
    loss=x[x<0]
    return {"Lệnh độc lập đóng":len(x),"Lệnh độc lập thắng":int((x>0).sum()),
            "Win Rate độc lập (%)":100*(x>0).mean() if len(x) else None,
            "Expectancy độc lập (%)":float(x.mean()) if len(x) else None,
            "PF tỷ lệ LN độc lập":float(x[x>0].sum()/(-loss.sum())) if len(loss) else None}

def evaluate_short_term(histories,policy=Policy()):
    # Same validated calendar and unchanged A4 reference as prior KT08/09.
    base=prepare_signals(histories,"S0P0")
    features={s:entry_conditions(d) for s,d in base.items()}
    summary,curves,trades,orders,windows,independent,stocks,errors=[],[],[],[],[],[],[],[]
    ref=None
    cases=[(BASELINE,None,None)]+[(s+"-"+e.label,s,e) for s in STRATEGIES for e in EXITS]
    for case,strategy,e in cases:
        try:
            if strategy is None:
                sig=base
                result=simulate_portfolio(sig,"S0P0","R1",policy,entry_gate=lambda s,r:reject_reason(r,BY_FILTER["A4"]))
            else:
                sig={s:replay_short(d,strategy,e,features[s]) for s,d in base.items()}
                # S2P0/S5P0 select only the same sizing stop formula, NOT legacy entry/exit.
                result=simulate_portfolio(sig,e.sizing_code,"R1",policy)
            row,curve,ledger,audit,window=result
            diag=independent_audit(sig,audit)
            ledger=portfolio_excursions(ledger,sig)
            if strategy is None: ref=row
            if ref is None: raise ValueError("Thiếu đối chứng")
            hold=ledger["Số phiên giữ"] if len(ledger) else pd.Series(dtype=float)
            reasons=ledger["Lý do bán"] if len(ledger) else pd.Series(dtype=str)
            if e is not None and (hold>e.sessions).any(): raise ValueError("Time Stop không khớp")
            stats=_stats(diag["LN lệnh độc lập giả định (%)"])
            case_row={**row,"Cấu hình":case,"Sizing":"R1","Mã sizing gốc":row["Cấu hình"],
                "Nhóm":strategy or "Đối chứng","Time Stop":e.sessions if e else None,
                "Chênh LN so A4 (đpt)":row["Lợi nhuận (%)"]-ref["Lợi nhuận (%)"],
                "Cải thiện MDD so A4 (đpt)":row["MDD (%)"]-ref["MDD (%)"],
                "Tín hiệu mua":len(diag),"Tín hiệu độc lập chưa đóng":int(diag["Ngày bán giả định"].isna().sum()),
                "Giữ TB (phiên)":float(hold.mean()) if len(hold) else None,
                "Giữ trung vị (phiên)":float(hold.median()) if len(hold) else None,
                "Giữ 3–10 phiên":int(hold.between(3,10).sum()),"Giữ dưới 3 phiên":int((hold<3).sum()),
                "Thoát Initial Stop":int((reasons==INITIAL).sum()),"Thoát Time Stop":int((reasons==TIME).sum()),
                "MAE TB (%)":float(ledger["MAE giá (%)"].mean()) if len(ledger) else None,
                "MFE TB (%)":float(ledger["MFE giá (%)"].mean()) if len(ledger) else None,**stats}
            local_stocks=[]
            for symbol in sig:
                a=diag.loc[diag["Mã"]==symbol]
                l=ledger.loc[ledger["Mã"]==symbol] if not ledger.empty else ledger
                local_stocks.append({"Cấu hình":case,"Mã":symbol,"Tín hiệu mua":len(a),
                    "Lệnh độc lập chưa đóng":int(a["Ngày bán giả định"].isna().sum()),
                    **_stats(a["LN lệnh độc lập giả định (%)"]),
                    "Lệnh danh mục đóng":len(l),
                    "P&L danh mục đã đóng (VND)":float(l["Lãi/lỗ (VND)"].sum()) if len(l) else 0.})
            summary.append(case_row)
            stocks.extend(local_stocks)
            for frame,target in ((curve.reset_index(),curves),(ledger,trades),(audit,orders),(window,windows),(diag,independent)):
                if not frame.empty: target.append(frame.assign(**{"Cấu hình":case,"Sizing":"R1"}))
        except Exception as exc:
            if strategy is None: raise ValueError("Đối chứng A4 không hoàn thành") from exc
            errors.append({"Cấu hình":case,"Lỗi":str(exc)[:160] if isinstance(exc,ValueError) else type(exc).__name__})
    def join(frames): return pd.concat(frames,ignore_index=True) if frames else pd.DataFrame()
    return {"summary":pd.DataFrame(summary),"equity":join(curves),"trades":join(trades),
            "orders":join(orders),"windows":join(windows),"independent":join(independent),
            "stocks":pd.DataFrame(stocks),"errors":pd.DataFrame(errors)}
