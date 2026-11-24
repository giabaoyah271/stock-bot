import unittest
import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal
from backtesting import tao_bang_giao_dich
from initial_stop_core import replay_stop,CONFIGS,REASON_INITIAL,REASON_TRAILING,verify_baseline,winner_comparison,evaluate_stop_cases
from strategy_policy import RESEARCH
from risk_equity import _test_trend

def fixture(n=240):
    # Ready only after warmup; one entry at 200, fill at 201.
    df=pd.DataFrame(index=pd.bdate_range("2023-01-02",periods=n))
    for col,value in {"open":100.0,"close":100.0,"high":101.0,"low":99.0,"volume":100000.0,
                      "ATR":2.0,"ADX":32.0,"Buy_Pct":0.0,"Sell_Pct":0.0,
                      "SMA50":95.0,"SMA200":90.0,"Senkou_Span_B":90.0,
                      "Plus_DI":30.0,"Minus_DI":10.0,"MACD":2.0,"Signal_Line":1.0}.items():
        df[col]=value
    df.iloc[:199,df.columns.get_loc("SMA200")]=np.nan
    df.loc[df.index[200],"Buy_Pct"]=70
    df.loc[df.index[201],["open","close","high","low"]]=[100,95,101,94]
    df.loc[df.index[202],["open","close","high","low"]]=[90,90,91,89]
    df.loc[df.index[203],["open","close","high","low"]]=[88,88,89,87]
    df.loc[df.index[204],["open","close","high","low"]]=[80,80,81,79]
    df["Reason"]=""
    df["Trend"]=_test_trend(df,"goc")
    return df

class InitialStopTests(unittest.TestCase):
    def test_all_baselines_match(self):
        df=fixture()
        for strategy in RESEARCH:
            self.assertEqual(len(verify_baseline(df,strategy)),1)
    def test_initial_stop_executes_next_open_with_gap(self):
        df=fixture()
        t=replay_stop(df,RESEARCH[1],CONFIGS[3])
        self.assertEqual(t["Reason"].iloc[201],REASON_INITIAL)
        ledger=tao_bang_giao_dich(t)
        self.assertEqual(ledger.iloc[0]["Ngày bán mô phỏng"],df.index[202])
        self.assertEqual(ledger.iloc[0]["Giá bán mô phỏng"],89.91)
        self.assertLess(ledger.iloc[0]["Lợi nhuận sau chi phí (%)"],-10)
    def test_early_trailing_and_old_delay(self):
        df=fixture()
        early=replay_stop(df,RESEARCH[0],CONFIGS[1])
        old=replay_stop(df,RESEARCH[0],CONFIGS[0])
        self.assertEqual(early["Reason"].iloc[201],REASON_TRAILING)
        self.assertEqual(old["Trend"].iloc[201],1)
        self.assertEqual(old["Reason"].iloc[203],REASON_TRAILING)
    def test_atr_at_buy_signal_not_fill_close(self):
        df=fixture()
        df.loc[df.index[201],"ATR"]=40
        t=replay_stop(df,RESEARCH[1],CONFIGS[5])
        self.assertAlmostEqual(t["KT03_Initial"].iloc[201],97)
        self.assertEqual(t["Reason"].iloc[201],REASON_INITIAL)
    def test_not_triggered_by_intraday_low(self):
        df=fixture()
        df.loc[df.index[201],["close","low"]]=[100,50]
        t=replay_stop(df,RESEARCH[1],CONFIGS[2])
        self.assertEqual(t["Trend"].iloc[201],1)
    def test_prefix_and_input_immutable(self):
        df=fixture()
        original=df.copy(deep=True)
        for c in CONFIGS:
            full=replay_stop(df,RESEARCH[1],c)
            short=replay_stop(df.iloc[:202],RESEARCH[1],c)
            assert_frame_equal(full.iloc[:202],short)
        assert_frame_equal(df,original)
    def test_reentry_requires_fresh_signal(self):
        df=fixture()
        df.loc[df.index[202],"Buy_Pct"]=70
        # Fresh buy also needs close strictly above SMA200.
        df.loc[df.index[202],"SMA200"]=85.0
        t=replay_stop(df,RESEARCH[1],CONFIGS[2])
        self.assertEqual(t["Trend"].iloc[201],-1)
        self.assertEqual(t["Trend"].iloc[202],1)
        self.assertEqual(t["KT03_Initial"].iloc[203],88*0.97)
    def test_final_signal_no_fabricated_exit(self):
        df=fixture().iloc[:202].copy()
        t=replay_stop(df,RESEARCH[1],CONFIGS[2])
        self.assertEqual(t["Trend"].iloc[-1],-1)
        self.assertTrue(tao_bang_giao_dich(t).empty)
    def test_baseline_mismatch_rejects(self):
        df=fixture()
        df["Trend"]=-1
        with self.assertRaises(AssertionError):
            verify_baseline(df,RESEARCH[0])
    def test_winner_match_does_not_count_missing_as_loss(self):
        base=pd.DataFrame({"Ngày mua mô phỏng":pd.to_datetime(["2024-01-01","2024-02-01"]),
                           "Lợi nhuận sau chi phí (%)":[12,5]})
        variant=base.iloc[:1].copy()
        variant["Lợi nhuận sau chi phí (%)"]=-1
        s=winner_comparison(base,variant)
        self.assertEqual(s["Lệnh thắng S0 không có lệnh đóng cùng ngày mua"],1)
        self.assertEqual(s["Lệnh thắng S0 thành lỗ (cùng ngày mua)"],1)
    def test_summary_and_equity_parity(self):
        df=fixture(400)
        rows,ledgers,windows,errors,curves=evaluate_stop_cases("HPG",df,RESEARCH[1])
        self.assertEqual(len(rows),8)
        self.assertEqual(len(ledgers),8)
        self.assertEqual(len(curves),8)
        self.assertEqual(rows[0]["Chênh LN so S0 (đpt)"],0)
        self.assertEqual(rows[0]["Cải thiện MDD so S0 (đpt)"],0)
        self.assertTrue(windows)
        self.assertFalse(errors)

if __name__=="__main__":
    unittest.main()
