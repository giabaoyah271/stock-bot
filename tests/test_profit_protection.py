import unittest
import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal
from test_initial_stop import fixture
from initial_stop_core import BY_CODE,replay_stop,REASON_INITIAL
from profit_protection_core import BASE_CODES,PROFITS,replay_profit,verify_p0,evaluate_profit_cases,REASON_PROFIT,matched_losses
from strategy_policy import RESEARCH
from risk_equity import _test_trend
from backtesting import tao_bang_giao_dich

def rising(n=400):
    df=fixture(n)
    df.loc[df.index[201:206],"ATR"]=10.0
    for i,p in [(201,103),(202,106),(203,111),(204,108),(205,101),(206,96),(207,96)]:
        df.loc[df.index[i],["open","high","low","close"]]=[p,p+1,p-1,p]
    df.loc[df.index[201],"open"]=100.0
    df.loc[df.index[201],"low"]=99.0
    df["Trend"]=_test_trend(df,"goc")
    return df

class ProfitTests(unittest.TestCase):
    def test_p0_parity_all_bases(self):
        df=rising()
        for code in BASE_CODES:
            verify_p0(df,RESEARCH[1],BY_CODE[code])
    def test_break_even_exact_costs(self):
        df=rising()
        t=replay_profit(df,RESEARCH[1],BY_CODE["S0"],PROFITS[1])
        expected=100*1.001*1.0015/(.999*.9975)
        self.assertAlmostEqual(t["KT13_Protected"].iloc[201],expected)
        self.assertAlmostEqual((expected*.999*.9975/(100*1.001*1.0015)-1)*100,0)
    def test_no_activation_on_high_only(self):
        df=rising()
        df.loc[df.index[201],["close","high"]]=[100,150]
        t=replay_profit(df,RESEARCH[1],BY_CODE["S0"],PROFITS[1])
        self.assertTrue(pd.isna(t["KT13_Protected"].iloc[201]))
    def test_multilevel_non_decreasing(self):
        df=rising()
        t=replay_profit(df,RESEARCH[1],BY_CODE["S0"],PROFITS[5])
        self.assertTrue(pd.isna(t["KT13_Protected"].iloc[201]))
        factor=.999*.9975/(100*1.001*1.0015)
        self.assertAlmostEqual(t["KT13_Protected"].iloc[202],1.02/factor)
        self.assertAlmostEqual(t["KT13_Protected"].iloc[203],1.05/factor)
        self.assertAlmostEqual(t["KT13_Protected"].iloc[204],1.05/factor)
        self.assertEqual(t["Reason"].iloc[205],REASON_PROFIT)
    def test_gap_can_turn_protection_into_loss(self):
        df=rising()
        t=replay_profit(df,RESEARCH[1],BY_CODE["S0"],PROFITS[5])
        ledger=tao_bang_giao_dich(t)
        self.assertEqual(ledger.iloc[0]["Ngày bán mô phỏng"],df.index[206])
        self.assertLess(ledger.iloc[0]["Lợi nhuận sau chi phí (%)"],0)
    def test_adaptive_uses_close_and_ratchet(self):
        df=rising()
        t=replay_profit(df,RESEARCH[1],BY_CODE["S0"],PROFITS[6])
        self.assertTrue(pd.isna(t["KT13_Protected"].iloc[201]))
        self.assertAlmostEqual(t["KT13_Protected"].iloc[202],106-15)
        self.assertAlmostEqual(t["KT13_Protected"].iloc[203],111-15)
        self.assertAlmostEqual(t["KT13_Protected"].iloc[204],111-15)
    def test_prefix_and_input_immutable(self):
        df=rising()
        original=df.copy(deep=True)
        for p in PROFITS:
            t=replay_profit(df,RESEARCH[1],BY_CODE["S2"],p)
            assert_frame_equal(t.iloc[:206],replay_profit(df.iloc[:206],RESEARCH[1],BY_CODE["S2"],p))
        assert_frame_equal(df,original)
    def test_reset_after_exit_and_reentry(self):
        df=rising()
        df.loc[df.index[206],"Buy_Pct"]=70
        t=replay_profit(df,RESEARCH[1],BY_CODE["S0"],PROFITS[5])
        self.assertEqual(t["Trend"].iloc[206],1)
        self.assertTrue(pd.isna(t["KT13_Protected"].iloc[206]))
        self.assertTrue(pd.isna(t["KT13_Protected"].iloc[207]))
    def test_initial_stop_still_works(self):
        df=fixture()
        t=replay_profit(df,RESEARCH[1],BY_CODE["S2"],PROFITS[5])
        self.assertEqual(t["Reason"].iloc[201],REASON_INITIAL)
    def test_final_pending_exit_not_fabricated(self):
        df=rising().iloc[:206]
        t=replay_profit(df,RESEARCH[1],BY_CODE["S0"],PROFITS[5])
        self.assertEqual(t["Reason"].iloc[-1],REASON_PROFIT)
        self.assertTrue(tao_bang_giao_dich(t).empty)
    def test_summary_all_21(self):
        df=rising()
        rows,ledgers,windows,errors,curves=evaluate_profit_cases("HPG",df)
        self.assertEqual(len(rows),21)
        self.assertEqual(len(ledgers),21)
        self.assertTrue(windows)
        self.assertFalse(errors)
        self.assertEqual(len(curves),21)
        for row in rows:
            if row["Profit"]=="P0":
                self.assertEqual(row["Chênh LN so P0 cùng nền (đpt)"],0)
                self.assertEqual(row["Cải thiện MDD so P0 cùng nền (đpt)"],0)
    def test_unmatched_losses_not_assumed_saved(self):
        a=pd.DataFrame({"Ngày mua mô phỏng":pd.to_datetime(["2024-01-01","2024-02-01"]),"Lợi nhuận sau chi phí (%)":[-5,-3]})
        b=a.iloc[:1].copy();b["Lợi nhuận sau chi phí (%)"]=1
        out=matched_losses(a,b)
        self.assertEqual(out["Lệnh lỗ P0 chuyển lãi"],1)
        self.assertEqual(out["Lệnh lỗ P0 không có lệnh đóng cùng ngày mua"],1)

if __name__=="__main__":
    unittest.main()
