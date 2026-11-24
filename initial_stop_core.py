"""KT03: isolated historical exit experiments; no live signal changes."""
from dataclasses import dataclass
import numpy as np
import pandas as pd

from backtesting import tao_bang_giao_dich
from risk_equity import calculate_equity_risk, _signals_and_original_ledger
from strategy_policy import RESEARCH
from multi_backtest_core import trade_metrics, RETURN, BUY_DATE, SELL_DATE
from walk_forward_core import evaluate_windows_from_curve
from trade_diagnostics import _validate

@dataclass(frozen=True)
class StopConfig:
    code: str
    label: str
    min_trailing_age: int = 3
    fixed_pct: float = 0.0
    atr_multiple: float = 0.0

CONFIGS = (
    StopConfig("S0","Đối chứng"),
    StopConfig("S1","Trailing từ phiên khớp mua",1),
    StopConfig("S2","Initial Stop 3%",fixed_pct=0.03),
    StopConfig("S3","Initial Stop 4%",fixed_pct=0.04),
    StopConfig("S4","Initial Stop 5%",fixed_pct=0.05),
    StopConfig("S5","Initial Stop 1,5 ATR",atr_multiple=1.5),
    StopConfig("S6","Initial Stop 2 ATR",atr_multiple=2.0),
    StopConfig("S7","Initial 2 ATR + Trailing sớm",1,atr_multiple=2.0),
)
BY_CODE = {c.code:c for c in CONFIGS}
COLS = ("Ngày tín hiệu mua", BUY_DATE, "Giá mua mô phỏng",
        "Ngày tín hiệu bán", SELL_DATE, "Giá bán mô phỏng", RETURN)
REASON_INITIAL = "KT03: Initial Stop"
REASON_TRAILING = "KT03: Trailing Stop ATR"
REASON_SCORE = "KT03: Điểm bán"

def replay_stop(df, strategy, config):
    """Signal state at close; initial stop anchored to actual next raw open.

    ATR for initial stop is frozen at BUY SIGNAL close. Read fill open only
    when reaching that session. Keep original 2 ATR trailing (signal-close
    anchored), technical sell rules and fresh entry confirmation after exit.
    No intraday fill; no sell on the same open used for entry.
    """
    if strategy not in RESEARCH or config not in CONFIGS:
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
    states, reasons, initial_values, trail_values = [],[],[],[]
    for i in range(len(df)):
        reason = ""
        if not ready[i]:
            states.append(-1); reasons.append("Chưa đủ dữ liệu")
            initial_values.append(np.nan); trail_values.append(np.nan)
            continue
        if adx[i]>=27:
            buy_limit,sell_limit=55,35
        elif adx[i]>=21:
            buy_limit,sell_limit=60,40
        else:
            buy_limit,sell_limit=65,45
        if trend==1:
            if i==entry_bar+1:
                if config.fixed_pct:
                    initial=opens[i]*(1-config.fixed_pct)
                elif config.atr_multiple:
                    initial=opens[i]-config.atr_multiple*atr[entry_bar]
            trailing=max(trailing,closes[i]-2*atr[i])
            if np.isfinite(initial) and closes[i]<=initial:
                reason=REASON_INITIAL
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
        states.append(trend); reasons.append(reason)
        initial_values.append(initial if trend==1 or reason else np.nan)
        trail_values.append(trailing if trend==1 or reason else np.nan)
        if trend==-1:
            initial,trailing=np.nan,np.nan
    trial=df.copy()
    trial["Trend"]=states
    trial["Reason"]=reasons
    trial["KT03_Initial"]=initial_values
    trial["KT03_Trailing"]=trail_values
    return trial

def verify_baseline(df,strategy):
    """S0 must reproduce exact legacy state and closed executions."""
    original_state, original_ledger = _signals_and_original_ledger(df,strategy)
    s0=replay_stop(df,strategy,CONFIGS[0])
    pd.testing.assert_series_equal(s0["Trend"], original_state,check_dtype=False,check_names=False)
    pd.testing.assert_frame_equal(tao_bang_giao_dich(s0)[list(COLS)].reset_index(drop=True),
                                  original_ledger[list(COLS)].reset_index(drop=True))
    return original_ledger

def winner_comparison(baseline, variant):
    """Match by entry date; do not equate unmatched/unfinished trades to losses."""
    base=baseline.set_index(BUY_DATE)[RETURN]
    trial=variant.set_index(BUY_DATE)[RETURN]
    if base.index.has_duplicates or trial.index.has_duplicates:
        raise ValueError("Trùng ngày mua ledger")
    winners=base[base>0]
    big=winners[winners>=10]
    same=winners.index.intersection(trial.index)
    same_big=big.index.intersection(trial.index)
    return {
        "Lệnh thắng S0":len(winners),
        "Lệnh thắng S0 khớp ngày mua":len(same),
        "Lệnh thắng S0 không có lệnh đóng cùng ngày mua":len(winners)-len(same),
        "Lệnh thắng S0 thành lỗ (cùng ngày mua)":int((trial.loc[same]<0).sum()),
        "Chênh LN TB lệnh thắng S0 khớp (đpt)":float((trial.loc[same]-winners.loc[same]).mean()) if len(same) else None,
        "Lệnh S0 lãi >=10%":len(big),
        "Lệnh S0 lãi >=10% khớp ngày mua":len(same_big),
        "Lệnh S0 lãi >=10% còn lãi >=10%":int((trial.loc[same_big]>=10).sum()),
        "Chênh LN TB lệnh S0 lãi >=10% khớp (đpt)":float((trial.loc[same_big]-big.loc[same_big]).mean()) if len(same_big) else None,
    }

def evaluate_stop_cases(symbol,df,strategy,codes=None):
    """Return summaries, ledgers, fixed half-year windows, errors, chart curves."""
    if len(df)<200:
        raise ValueError("Cần ít nhất 200 phiên")
    _validate(df)
    codes=tuple(codes) if codes is not None else tuple(BY_CODE)
    if not codes or codes[0]!="S0" or len(set(codes))!=len(codes) or not set(codes).issubset(BY_CODE):
        raise ValueError("Cần S0 và mã cấu hình hợp lệ, không trùng")
    baseline=verify_baseline(df,strategy)
    rows,ledgers,windows,errors,curves=[],[],[],[],{}
    base_ret=base_dd=None
    for code in codes:
        try:
            config=BY_CODE[code]
            trial=replay_stop(df,strategy,config)
            ledger=tao_bang_giao_dich(trial)
            curve,risk=calculate_equity_risk(trial,RESEARCH[0])
            if code=="S0":
                legacy,legacy_metrics=calculate_equity_risk(df,strategy)
                pd.testing.assert_series_equal(curve["Equity"],legacy["Equity"])
                pd.testing.assert_series_equal(curve["Drawdown (%)"],legacy["Drawdown (%)"])
            ret=float(risk["Lợi nhuận theo phiên (%)"])
            dd=float(risk["Max Drawdown theo phiên (%)"])
            if code=="S0":
                base_ret,base_dd=ret,dd
            if base_ret is None:
                raise ValueError("S0 chưa đối chiếu thành công")
            stats=trade_metrics(ledger)
            row={"Mã":symbol,"Chiến lược":strategy,"Cấu hình":code,"Quy tắc":config.label,
                 "Dữ liệu từ":df.index[0],"Dữ liệu đến":df.index[-1],**stats,
                 "Lợi nhuận theo phiên (%)":ret,"Max Drawdown theo phiên (%)":dd,
                 "Chênh LN so S0 (đpt)":round(ret-base_ret,2),
                 "Cải thiện MDD so S0 (đpt)":round(dd-base_dd,2),
                 "Tỷ lệ phiên có vị thế (%)":round(float((curve["Số cổ phiếu quy ước"]>0).mean()*100),2),
                 "Số phiên giữ TB":risk["Số phiên nắm giữ TB (lệnh đã đóng)"],
                 "Lệnh lỗ lớn nhất (%)":risk["Lệnh lỗ lớn nhất (%)"],
                 "Trạng thái cuối":risk["Trạng thái cuối"],
                 "Số lệnh thoát Initial Stop":int((ledger["Lý do bán"]==REASON_INITIAL).sum()),
                 "Số lệnh thoát Trailing":int((ledger["Lý do bán"]==REASON_TRAILING).sum()),
                 **winner_comparison(baseline,ledger)}
            ledger=ledger.copy()
            ledger.insert(0,"Cấu hình",code);ledger.insert(0,"Chiến lược",strategy);ledger.insert(0,"Mã",symbol)
            ledger["Initial Stop tại tín hiệu bán"]=trial["KT03_Initial"].reindex(pd.DatetimeIndex(ledger["Ngày tín hiệu bán"])).to_numpy()
            ledger["Trailing Stop tại tín hiệu bán"]=trial["KT03_Trailing"].reindex(pd.DatetimeIndex(ledger["Ngày tín hiệu bán"])).to_numpy()
            rows.append(row);ledgers.append(ledger)
            curves[code]=curve[["Equity","Drawdown (%)"]].copy()
            try:
                sliced,_,missing,_=evaluate_windows_from_curve(curve,symbol,strategy)
                windows.extend(dict(w,**{"Cấu hình":code}) for w in sliced)
                errors.extend(dict(w,**{"Cấu hình":code}) for w in missing)
            except Exception as exc:
                errors.append({"Mã":symbol,"Chiến lược":strategy,"Cấu hình":code,"Cửa sổ":"WF","Lỗi":type(exc).__name__})
        except Exception as exc:
            if code=="S0":
                raise ValueError("Đối chứng S0 không khớp; dừng toàn bộ cấu hình") from exc
            errors.append({"Mã":symbol,"Chiến lược":strategy,"Cấu hình":code,"Cửa sổ":"Toàn lịch sử","Lỗi":type(exc).__name__})
    return rows,ledgers,windows,errors,curves
