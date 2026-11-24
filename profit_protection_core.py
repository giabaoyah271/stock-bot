"""KT13 isolated profit protection. No mutation of KT03 or live strategies."""
from dataclasses import dataclass
import numpy as np
import pandas as pd

from initial_stop_core import BY_CODE, COLS, REASON_INITIAL, REASON_TRAILING, REASON_SCORE, replay_stop, verify_baseline, winner_comparison
from risk_equity import calculate_equity_risk, BUY_FEE, SELL_FEE, SELL_TAX, SLIPPAGE
from strategy_policy import RESEARCH
from multi_backtest_core import trade_metrics, RETURN, BUY_DATE
from backtesting import tao_bang_giao_dich
from trade_diagnostics import _validate
from walk_forward_core import evaluate_windows_from_curve

BASE_CODES=("S0","S2","S5")
REASON_PROFIT="KT13: Profit Protection"

@dataclass(frozen=True)
class ProfitConfig:
    code: str
    label: str
    levels: tuple=()
    adaptive: bool=False

PROFITS=(
    ProfitConfig("P0","Không bảo vệ bổ sung"),
    ProfitConfig("P1","Lãi 2% → hòa vốn",((2,0),)),
    ProfitConfig("P2","Lãi 3% → hòa vốn",((3,0),)),
    ProfitConfig("P3","Lãi 5% → hòa vốn",((5,0),)),
    ProfitConfig("P4","Lãi 5% → bảo vệ 2%",((5,2),)),
    ProfitConfig("P5","Lãi 3/5/10% → bảo vệ 0/2/5%",((3,0),(5,2),(10,5))),
    ProfitConfig("P6","Lãi 5% → trailing 1,5 ATR",adaptive=True),
)

def replay_profit(df, strategy, config, profit):
    """Replay close decisions; use only known entry open and close returns."""
    if strategy not in RESEARCH or config.code not in BASE_CODES or config != BY_CODE[config.code] or profit not in PROFITS:
        raise ValueError("Chiến lược/cấu hình không hợp lệ")
    needed = ["open","close","SMA50","SMA200","Senkou_Span_B","ATR","ADX",
              "Buy_Pct","Sell_Pct","Plus_DI","Minus_DI","MACD","Signal_Line"]
    if not set(needed).issubset(df.columns):
        raise ValueError("Thiếu chỉ báo cần thiết")
    a = df[needed].apply(pd.to_numeric,errors="coerce").to_numpy(dtype=float)
    opens,closes,sma50,sma200,cloud,atr,adx,buy,sell,plus,minus,macd,line = a.T
    # Warmup may be NaN. Once strategy is ready, all inputs must be finite.
    ready = np.isfinite(sma200) & np.isfinite(cloud)
    if ready.any():
        first = int(np.flatnonzero(ready)[0])
        if not ready[first:].all() or not np.isfinite(a[first:]).all() or (atr[first:]<0).any():
            raise ValueError("Chỉ báo không hợp lệ sau warmup")
    trend, pending, entry_bar = -1,0,-1
    trailing, initial = np.nan,np.nan
    factor, protected, peak = np.nan,np.nan,np.nan
    states, reasons, initial_values, trail_values = [],[],[],[]
    protected_values, peak_values = [],[]
    for i in range(len(df)):
        reason = ""
        if not ready[i]:
            states.append(-1); reasons.append("Chưa đủ dữ liệu")
            initial_values.append(np.nan); trail_values.append(np.nan)
            protected_values.append(np.nan); peak_values.append(np.nan)
            continue
        if adx[i]>=27:
            buy_limit,sell_limit=55,35
        elif adx[i]>=21:
            buy_limit,sell_limit=60,40
        else:
            buy_limit,sell_limit=65,45
        if trend==1:
            if i==entry_bar+1:
                factor = (1-SLIPPAGE)*(1-SELL_FEE-SELL_TAX)/(opens[i]*(1+SLIPPAGE)*(1+BUY_FEE))
                if config.fixed_pct:
                    initial=opens[i]*(1-config.fixed_pct)
                elif config.atr_multiple:
                    initial=opens[i]-config.atr_multiple*atr[entry_bar]
            trailing=max(trailing,closes[i]-2*atr[i])
            net = (closes[i]*factor-1)*100
            peak = max(peak,net) if np.isfinite(peak) else net
            for trigger,lock in profit.levels:
                if peak >= trigger-1e-10:
                    candidate = (1+lock/100)/factor
                    protected = max(protected,candidate) if np.isfinite(protected) else candidate
            if profit.adaptive and peak >= 5-1e-10:
                candidate = closes[i]-1.5*atr[i]
                protected = max(protected,candidate) if np.isfinite(protected) else candidate
            if np.isfinite(initial) and closes[i]<=initial:
                reason=REASON_INITIAL
            elif np.isfinite(protected) and closes[i]<=protected:
                reason=REASON_PROFIT
            elif i-entry_bar>=config.min_trailing_age and closes[i]<=trailing:
                reason=REASON_TRAILING
            elif sell[i]>=sell_limit or (sell[i]>=35 and adx[i]>30 and minus[i]>plus[i]):
                reason=REASON_SCORE
            if reason:
                trend,pending=-1,0
            else:
                pending=0
        else:
            eligible=True
            if strategy==RESEARCH[1]:
                eligible=closes[i]>sma200[i] and sma50[i]>sma200[i]
            elif strategy==RESEARCH[2]:
                eligible=adx[i]>=25 and plus[i]>minus[i] and macd[i]>line[i]
            pending=pending+1 if buy[i]>=buy_limit and eligible else 0
            if pending>=(1 if adx[i]>=30 else 2):
                trend,entry_bar,pending=1,i,0
                trailing=closes[i]-2*atr[i]
                initial=np.nan
                factor,protected,peak=np.nan,np.nan,np.nan
        states.append(trend); reasons.append(reason)
        initial_values.append(initial if trend==1 or reason else np.nan)
        trail_values.append(trailing if trend==1 or reason else np.nan)
        protected_values.append(protected if trend==1 or reason else np.nan)
        peak_values.append(peak if trend==1 or reason else np.nan)
        if trend==-1:
            initial,trailing,factor,protected,peak=np.nan,np.nan,np.nan,np.nan,np.nan
    trial=df.copy()
    trial["Trend"]=states
    trial["Reason"]=reasons
    trial["KT03_Initial"]=initial_values
    trial["KT03_Trailing"]=trail_values
    trial["KT13_Protected"]=protected_values
    trial["KT13_Peak_Net_Close"]=peak_values
    return trial

def verify_p0(df,strategy,base):
    legacy=replay_stop(df,strategy,base)
    trial=replay_profit(df,strategy,base,PROFITS[0])
    pd.testing.assert_frame_equal(trial[legacy.columns],legacy)
    ledger=tao_bang_giao_dich(legacy)
    pd.testing.assert_frame_equal(tao_bang_giao_dich(trial),ledger)
    curve,risk=calculate_equity_risk(legacy,RESEARCH[0])
    actual,_=calculate_equity_risk(trial,RESEARCH[0])
    pd.testing.assert_frame_equal(actual,curve)
    return ledger,curve,risk

def matched_losses(baseline,trial):
    old=baseline.set_index(BUY_DATE)[RETURN]
    new=trial.set_index(BUY_DATE)[RETURN]
    losses=old[old<0]
    same=losses.index.intersection(new.index)
    return {"Lệnh lỗ P0":len(losses),
            "Lệnh lỗ P0 khớp ngày mua":len(same),
            "Lệnh lỗ P0 chuyển lãi":int((new.loc[same]>0).sum()),
            "Lệnh lỗ P0 giảm lỗ (cùng ngày mua)":int(((new.loc[same]<0)&(new.loc[same]>losses.loc[same])).sum()),
            "Lệnh lỗ P0 không có lệnh đóng cùng ngày mua":len(losses)-len(same)}

def evaluate_profit_cases(symbol,df,strategy=RESEARCH[1],bases=BASE_CODES):
    if len(df)<200:
        raise ValueError("Cần ít nhất 200 phiên")
    _validate(df)
    bases=tuple(bases)
    if not bases or len(set(bases))!=len(bases) or not set(bases).issubset(BASE_CODES):
        raise ValueError("Cấu hình nền không hợp lệ")
    verify_baseline(df,strategy)
    rows,ledgers,windows,errors,curves=[],[],[],[],{}
    # Always calculate S0P0 for joint comparisons even when only one base selected.
    reference,reference_curve,reference_risk=verify_p0(df,strategy,BY_CODE["S0"])
    for code in bases:
        base=BY_CODE[code]
        try:
            baseline,base_curve,base_risk=verify_p0(df,strategy,base)
        except Exception:
            errors.append({"Mã":symbol,"Nền":code,"Profit":"Tất cả","Lỗi":"P0 không khớp KT03"})
            continue
        for profit in PROFITS:
            try:
                trial=replay_profit(df,strategy,base,profit)
                ledger=tao_bang_giao_dich(trial)
                curve,risk=calculate_equity_risk(trial,RESEARCH[0])
                ret=risk["Lợi nhuận theo phiên (%)"]
                dd=risk["Max Drawdown theo phiên (%)"]
                winners={k.replace("S0","P0"):v for k,v in winner_comparison(baseline,ledger).items()}
                protection_exit=ledger["Lý do bán"]==REASON_PROFIT
                stats=trade_metrics(ledger)
                dates=pd.DatetimeIndex(ledger["Ngày tín hiệu bán"])
                peak=trial["KT13_Peak_Net_Close"].reindex(dates).to_numpy(dtype=float)
                protected=trial["KT13_Protected"].reindex(dates).to_numpy(dtype=float)
                exit_net=ledger[RETURN].to_numpy(dtype=float)
                giveback=peak-exit_net
                row={"Mã":symbol,"Chiến lược":strategy,"Nền":code,"Profit":profit.code,
                    "Cấu hình":code+profit.code,"Quy tắc":profit.label,"Dữ liệu từ":df.index[0],"Dữ liệu đến":df.index[-1],
                    **stats,"Lợi nhuận theo phiên (%)":ret,"Max Drawdown theo phiên (%)":dd,
                    "Chênh LN so P0 cùng nền (đpt)":round(ret-base_risk["Lợi nhuận theo phiên (%)"],2),
                    "Cải thiện MDD so P0 cùng nền (đpt)":round(dd-base_risk["Max Drawdown theo phiên (%)"],2),
                    "Chênh LN so S0P0 (đpt)":round(ret-reference_risk["Lợi nhuận theo phiên (%)"],2),
                    "Cải thiện MDD so S0P0 (đpt)":round(dd-reference_risk["Max Drawdown theo phiên (%)"],2),
                    "Tỷ lệ phiên có vị thế (%)":round(float((curve["Số cổ phiếu quy ước"]>0).mean()*100),2),
                    "Số phiên giữ TB":risk["Số phiên nắm giữ TB (lệnh đã đóng)"],
                    "Lệnh lỗ lớn nhất (%)":risk["Lệnh lỗ lớn nhất (%)"],
                    "Trạng thái cuối":risk["Trạng thái cuối"],
                    "Số lệnh kích hoạt bảo vệ (đã đóng)":int(np.isfinite(protected).sum()),
                    "Số lệnh thoát Profit Protection":int(protection_exit.sum()),
                    "Lệnh thoát Profit Protection vẫn lỗ":int((protection_exit & (ledger[RETURN]<0)).sum()),
                    "Đỉnh LN ròng Close TB (%)":float(np.mean(peak)) if len(peak) else None,
                    "Đỉnh Close trừ LN khớp bán TB (đpt)":float(np.mean(giveback)) if len(giveback) else None,
                    **winners,**matched_losses(baseline,ledger)}
                ledger=ledger.copy()
                for k,v in reversed(list({"Mã":symbol,"Chiến lược":strategy,"Nền":code,"Profit":profit.code,"Cấu hình":code+profit.code}.items())):
                    ledger.insert(0,k,v)
                ledger["Ngưỡng bảo vệ tại tín hiệu bán"]=protected
                ledger["Đỉnh LN ròng Close (%)"]=peak
                ledger["Đỉnh Close trừ LN khớp bán (đpt)"]=giveback
                ledger["Initial Stop tại tín hiệu bán"]=trial["KT03_Initial"].reindex(dates).to_numpy()
                ledger["Trailing Stop tại tín hiệu bán"]=trial["KT03_Trailing"].reindex(dates).to_numpy()
                rows.append(row);ledgers.append(ledger)
                curves[code+profit.code]=curve[["Equity","Drawdown (%)"]].copy()
                try:
                    sliced,_,missing,_=evaluate_windows_from_curve(curve,symbol,strategy)
                    windows.extend(dict(w,**{"Nền":code,"Profit":profit.code,"Cấu hình":code+profit.code}) for w in sliced)
                    errors.extend(dict(w,**{"Nền":code,"Profit":profit.code,"Cấu hình":code+profit.code}) for w in missing)
                except Exception as exc:
                    errors.append({"Mã":symbol,"Nền":code,"Profit":profit.code,"Cửa sổ":"WF","Lỗi":type(exc).__name__})
            except Exception as exc:
                errors.append({"Mã":symbol,"Nền":code,"Profit":profit.code,"Lỗi":type(exc).__name__})
    return rows,ledgers,windows,errors,curves
