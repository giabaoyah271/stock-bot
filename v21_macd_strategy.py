"""V2.1: V2 scores with MACD-only buy confirmation (experimental).

Uses the same independently recalculated signal/exit state machine as V2.
Never modifies the original input or the existing V1/V2 strategy paths.
"""
from scoring_v2 import tinh_diem_v2
from strategy_experiments import chay_backtest_thu_nghiem


def chay_backtest_diem_v21_macd(df):
    """Backtest V2 scores, allowing new entries only if MACD > Signal_Line.

    The MACD gate is checked on the signal candle, so fills still occur
    at the next session's open. It never forces exits.
    """
    trial = tinh_diem_v2(df).copy()
    trial["Buy_Pct"] = trial["V2_Buy_Pct"].fillna(0)
    trial["Sell_Pct"] = trial["V2_Sell_Pct"].fillna(0)
    return chay_backtest_thu_nghiem(trial, bo_loc="macd")
