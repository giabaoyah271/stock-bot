"""KT06/07: shared-cash, daily, long-only research simulation."""
from dataclasses import dataclass
import math
import numpy as np
import pandas as pd
from risk_equity import BUY_FEE, SELL_FEE, SELL_TAX, SLIPPAGE
from initial_stop_core import BY_CODE, verify_baseline
from profit_protection_core import PROFITS, replay_profit, verify_p0
from strategy_policy import RESEARCH
from trade_diagnostics import _validate

CANDIDATES=("S0P0","S2P0","S5P0","S2P6","S5P6")
SECTORS={"HPG":"Thép","MBB":"Ngân hàng","TCB":"Ngân hàng","ACB":"Ngân hàng",
         "FPT":"Công nghệ","MWG":"Bán lẻ","PNJ":"Bán lẻ","VNM":"Thực phẩm",
         "DGC":"Hóa chất","GAS":"Dầu khí","GMD":"Logistics","REE":"Điện/hạ tầng"}
MODES={"R0":"Tỷ trọng cố định","R1":"Theo rủi ro","R2":"Theo rủi ro + DD"}
BUY_MULT=(1+SLIPPAGE)*(1+BUY_FEE)
SELL_MULT=(1-SLIPPAGE)*(1-SELL_FEE-SELL_TAX)

@dataclass(frozen=True)
class Policy:
    capital: float=100_000_000
    price_scale: int=1000
    risk: float=.005
    stock_cap: float=.15
    sector_cap: float=.25
    heat_cap: float=.025
    max_positions: int=5
    lot: int=100
    def validate(self):
        if not math.isfinite(self.capital) or self.capital<=0 or self.price_scale not in (1,1000):
            raise ValueError("Vốn hoặc đơn vị giá không hợp lệ")
        if not all(math.isfinite(x) and 0<x<=1 for x in (self.risk,self.stock_cap,self.sector_cap,self.heat_cap)):
            raise ValueError("Giới hạn rủi ro/tỷ trọng không hợp lệ")
        if self.lot!=100 or not isinstance(self.max_positions,int) or not 1<=self.max_positions<=12:
            raise ValueError("Lô hoặc số vị thế không hợp lệ")

def dd_multiplier(dd):
    """dd is positive drawdown fraction at previous completed close."""
    if dd>=.09: return 0.
    if dd>=.07: return .25
    if dd>=.05: return .5
    if dd>=.03: return .75
    return 1.

def size_order(equity,cash,price,reference,sector_used,heat,policy,mode,dd=0.):
    """Price and reference in VND; cost includes slippage and fees."""
    if mode not in MODES:
        raise ValueError("Chế độ sizing không hợp lệ")
    if not all(math.isfinite(x) for x in (equity,cash,price,reference,sector_used,heat,dd)) or equity<=0 or price<=0:
        return 0,0.,"Giá/vốn không hợp lệ"
    if reference<=0 or reference>=price:
        return 0,0.,"Stop tham chiếu không hợp lệ/gap qua Stop"
    cost=price*BUY_MULT
    unit_risk=cost-reference*SELL_MULT
    if unit_risk<=0:
        return 0,0.,"Rủi ro đơn vị không hợp lệ"
    limits=[(cash/cost,"Tiền mặt"),
            (equity*policy.stock_cap/cost,"Tỷ trọng mã"),
            ((equity*policy.sector_cap-sector_used)/cost,"Tỷ trọng ngành")]
    if mode!="R0":
        rate=policy.risk*(dd_multiplier(dd) if mode=="R2" else 1)
        if rate<=0:
            return 0,unit_risk,"DD >= 9%: dừng mua mới"
        limits.extend([(equity*rate/unit_risk,"Rủi ro/lệnh"),
                       ((equity*policy.heat_cap-heat)/unit_risk,"Portfolio heat")])
    max_qty,reason=min(limits,key=lambda x:x[0])
    qty=max(0,math.floor(max_qty/policy.lot)*policy.lot)
    return qty,unit_risk,reason if qty==0 else ""

def prepare_signals(histories,code):
    """Same calendar for all requested stocks, no silently omitted tickers."""
    if code not in CANDIDATES or not histories or not set(histories).issubset(SECTORS):
        raise ValueError("Chỉ hỗ trợ nhóm 12 mã cố định và 5 tổ hợp")
    out={}
    calendar=None
    for symbol in sorted(histories):
        df=histories[symbol]
        if len(df)<200:
            raise ValueError(f"{symbol}: thiếu 200 phiên")
        _validate(df)
        local=df.index.tz_convert("Asia/Ho_Chi_Minh").tz_localize(None) if df.index.tz is not None else df.index
        local=local.normalize()
        if local.has_duplicates or (calendar is not None and not local.equals(calendar)):
            raise ValueError(f"{symbol}: lịch phiên không đồng nhất; không tự ghép/điền")
        calendar=local
        strategy=RESEARCH[1]
        verify_baseline(df,strategy)
        base=BY_CODE[code[:2]]
        verify_p0(df,strategy,base)
        profit=next(p for p in PROFITS if p.code==code[2:])
        trial=replay_profit(df,strategy,base,profit)
        trial.index=local
        out[symbol]=trial
    return out

def _reference(code,open_price,previous):
    if code.startswith("S2"): return open_price*.97
    if code.startswith("S5"): return open_price-1.5*float(previous["ATR"])
    return float(previous["close"])-2*float(previous["ATR"])

def simulate_portfolio(signals,code,mode,policy=Policy(),entry_gate=None,entry_rank=None):
    """Open exits first, then ranked new entries; close marks equity.
    Rejected buy is ignored until a later fresh -1→1 signal.
    All quotes and orders are hypothetical; no real orders are sent.
    """
    policy.validate()
    if code not in CANDIDATES or mode not in MODES or not signals or not set(signals).issubset(SECTORS):
        raise ValueError("Danh mục/cấu hình không hợp lệ")
    symbols=sorted(signals)
    calendar=signals[symbols[0]].index
    if not isinstance(calendar,pd.DatetimeIndex) or not calendar.is_monotonic_increasing or calendar.has_duplicates or calendar.hasnans:
        raise ValueError("Lịch phiên không hợp lệ")
    for s in symbols:
        d=signals[s]
        if not d.index.equals(calendar) or not {"Trend","open","close","ATR","Buy_Pct"}.issubset(d.columns):
            raise ValueError("Lịch hoặc tín hiệu không đồng nhất")
        prices=d[["open","close"]].to_numpy(dtype=float)
        if not np.isfinite(prices).all() or (prices<=0).any() or not d["Trend"].isin([-1,1]).all():
            raise ValueError("Giá hoặc trạng thái không hợp lệ")
    cash=float(policy.capital)
    positions={}
    trades,orders,daily=[],[],[]
    peak=previous_equity=cash
    turnover=0.
    scale=policy.price_scale
    for i,date in enumerate(calendar):
        opens={s:float(signals[s]["open"].iloc[i])*scale for s in symbols}
        closes={s:float(signals[s]["close"].iloc[i])*scale for s in symbols}
        prev_dd=max(0.,1-previous_equity/peak)
        def equity_at_open():
            return cash+sum(p["qty"]*opens[s] for s,p in positions.items())
        if i>=2:
            for s in list(positions):
                d=signals[s]
                if d["Trend"].iloc[i-2]==1 and d["Trend"].iloc[i-1]==-1:
                    p=positions.pop(s)
                    proceeds=p["qty"]*opens[s]*SELL_MULT
                    cash+=proceeds
                    turnover+=proceeds
                    pnl=proceeds-p["cost"]
                    trades.append({"Mã":s,"Ngành":SECTORS[s],"Ngày tín hiệu mua":p["signal"],
                        "Ngày mua":p["date"],"Ngày bán":date,"Ngày tín hiệu bán":calendar[i-1],
                        "Số CP":p["qty"],"Open mua (VND)":p["open"],"Open bán (VND)":opens[s],
                        "Vốn mua (VND)":p["cost"],"Thu bán (VND)":proceeds,"Lãi/lỗ (VND)":pnl,
                        "Lợi nhuận ròng (%)":100*pnl/p["cost"],"Rủi ro ban đầu (VND)":p["risk"],
                        "Lỗ vượt ngân sách":pnl<-p["risk"],"Số phiên giữ":i-p["i"],
                        "Lý do bán":str(d["Reason"].iloc[i-1]) if "Reason" in d else ""})
                    orders.append({"Ngày":date,"Mã":s,"Lệnh":"Bán","Số CP":p["qty"],"Lý do":""})
            candidates=[s for s in symbols if s not in positions and signals[s]["Trend"].iloc[i-2]==-1 and signals[s]["Trend"].iloc[i-1]==1]
            # Rank using ONLY signal-close score, deterministic ticker tie-break.
            if entry_rank is None:
                candidates.sort(key=lambda s:(-float(signals[s]["Buy_Pct"].iloc[i-1]),s))
            else:
                candidates.sort(key=lambda s:entry_rank(s,signals[s].iloc[i-1].copy()))
            for s in candidates:
                # Optional research gate reads only the completed signal row.
                # Keep legacy Trend unchanged: a rejected signal is not chased.
                if entry_gate is not None:
                    rejection = entry_gate(s, signals[s].iloc[i-1].copy())
                    if rejection:
                        orders.append({"Ngày":date,"Mã":s,"Lệnh":"Bỏ mua","Số CP":0,
                                       "Lý do":rejection,"Nhóm từ chối":"Bộ lọc điểm mua"})
                        continue
                if len(positions)>=policy.max_positions:
                    orders.append({"Ngày":date,"Mã":s,"Lệnh":"Bỏ mua","Số CP":0,"Lý do":"Giới hạn vị thế"})
                    continue
                eq=equity_at_open()
                sector_used=sum(p["qty"]*opens[t] for t,p in positions.items() if SECTORS[t]==SECTORS[s])
                heat=sum(p["risk"] for p in positions.values())
                prev=signals[s].iloc[i-1].copy()
                prev["close"]*=scale
                prev["ATR"]*=scale
                reference=_reference(code,opens[s],prev)
                qty,unit_risk,reason=size_order(eq,cash,opens[s],reference,sector_used,heat,policy,mode,prev_dd)
                if qty==0:
                    orders.append({"Ngày":date,"Mã":s,"Lệnh":"Bỏ mua","Số CP":0,"Lý do":reason})
                    continue
                cost=qty*opens[s]*BUY_MULT
                if cost>cash+1e-7: raise ValueError("Vi phạm tiền mặt")
                cash-=cost
                turnover+=cost
                positions[s]={"qty":qty,"cost":cost,"risk":qty*unit_risk,"i":i,"date":date,
                              "signal":calendar[i-1],"open":opens[s]}
                orders.append({"Ngày":date,"Mã":s,"Lệnh":"Mua","Số CP":qty,"Lý do":"",
                    "Vốn mua (VND)":cost,"Rủi ro dự kiến (VND)":qty*unit_risk,
                    "Equity trước mua (VND)":eq,"Stop tham chiếu (VND)":reference,
                    "DD phiên trước (%)":prev_dd*100})
        market_value=sum(p["qty"]*closes[s] for s,p in positions.items())
        equity=cash+market_value
        if not math.isfinite(equity) or equity<=0 or cash<-1e-7:
            raise ValueError("Vi phạm vốn/tiền mặt")
        peak=max(peak,equity)
        sector_values={}
        for s,p in positions.items():
            sector_values[SECTORS[s]]=sector_values.get(SECTORS[s],0.)+p["qty"]*closes[s]
        daily.append({"Ngày":date,"Equity":equity,"Tiền mặt":cash,"Giá trị vị thế":market_value,
                      "Drawdown (%)":100*(equity/peak-1),"Số vị thế":len(positions),
                      "Exposure (%)":100*market_value/equity,
                      "Heat ban đầu còn mở (%)":100*sum(p["risk"] for p in positions.values())/equity,
                      "Tỷ trọng mã lớn nhất (%)":100*max([p["qty"]*closes[s] for s,p in positions.items()] or [0])/equity,
                      "Tỷ trọng ngành lớn nhất (%)":100*max(sector_values.values(),default=0)/equity,
                      "Hệ số DD áp dụng":dd_multiplier(prev_dd) if mode=="R2" else 1.})
        previous_equity=equity
    curve=pd.DataFrame(daily).set_index("Ngày")
    ledger=pd.DataFrame(trades)
    audit=pd.DataFrame(orders)
    pnl=ledger["Lãi/lỗ (VND)"] if len(ledger) else pd.Series(dtype=float)
    rets=ledger["Lợi nhuận ròng (%)"] if len(ledger) else pd.Series(dtype=float)
    losses=pnl[pnl<0]
    wins=pnl[pnl>0]
    returns=curve["Equity"].pct_change().dropna()
    years=(calendar[-1]-calendar[0]).days/365.25
    summary={"Cấu hình":code,"Sizing":mode,"Vốn đầu":policy.capital,"Đơn vị giá":scale,
             "Dữ liệu từ":calendar[0],"Dữ liệu đến":calendar[-1],"Số mã":len(symbols),
             "Vốn cuối":equity,"Lợi nhuận (%)":100*(equity/policy.capital-1),
             "CAGR (%)":100*((equity/policy.capital)**(1/years)-1) if years>0 else None,
             "MDD (%)":float(curve["Drawdown (%)"].min()),
             "Số lệnh đóng":len(ledger),"Số lệnh thắng":len(wins),"Số lệnh thua":len(losses),
             "Win Rate (%)":100*len(wins)/len(ledger) if len(ledger) else None,
             "Expectancy (%)":float(rets.mean()) if len(rets) else None,
             "PF tiền thực hiện":float(wins.sum()/(-losses.sum())) if len(losses) else None,
             "Lỗ lớn nhất (%)":float(rets.min()) if len(losses) else None,
             "Sharpe (rf=0)":float(returns.mean()/returns.std()*np.sqrt(252)) if len(returns)>1 and returns.std()>0 else None,
             "Exposure TB (%)":float(curve["Exposure (%)"].mean()),
             "Exposure max (%)":float(curve["Exposure (%)"].max()),
             "Heat max (%)":float(curve["Heat ban đầu còn mở (%)"].max()),
             "Số vị thế max":int(curve["Số vị thế"].max()),
             "Vị thế cuối":len(positions),"Lệnh bỏ mua":int((audit["Lệnh"]=="Bỏ mua").sum()) if len(audit) else 0,
             "Phiên DD dừng mua":int((curve["Hệ số DD áp dụng"]==0).sum()),
             "Lệnh lỗ vượt rủi ro dự kiến":int(ledger["Lỗ vượt ngân sách"].sum()) if len(ledger) else 0,
             "Tổng giá trị giao dịch/Vốn đầu":turnover/policy.capital,
             "P&L đã đóng (VND)":float(pnl.sum()),
             "P&L vị thế mở (VND)":sum(p["qty"]*closes[s]-p["cost"] for s,p in positions.items())}
    if not math.isclose(equity-policy.capital,summary["P&L đã đóng (VND)"]+summary["P&L vị thế mở (VND)"],abs_tol=.001):
        raise ValueError("Đối chiếu dòng tiền thất bại")
    windows=[]
    for (year,half),part in curve.groupby([curve.index.year,(curve.index.month-1)//6+1]):
        first=curve.index.get_loc(part.index[0])
        base_eq=float(curve["Equity"].iloc[first-1]) if first else policy.capital
        seq=np.r_[base_eq,part["Equity"].to_numpy()]
        windows.append({"Năm":year,"Nửa năm":half,"Từ":part.index[0],"Đến":part.index[-1],
                        "Lợi nhuận (%)":100*(seq[-1]/base_eq-1),
                        "MDD cục bộ (%)":100*float((seq/np.maximum.accumulate(seq)-1).min()),
                        "Exposure TB (%)":float(part["Exposure (%)"].mean())})
    return summary,curve,ledger,audit,pd.DataFrame(windows)
