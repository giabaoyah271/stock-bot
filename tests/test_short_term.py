import unittest
import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal
from test_initial_stop import fixture
from short_term_core import EXITS,INITIAL,TIME,entry_conditions,replay_short,excursions,evaluate_short_term
from portfolio_core import simulate_portfolio

def sample(n=400):
    d=fixture(n)
    d["SMA20"]=95.
    d["RSI"]=60.
    return d

def feature(d,at=200):
    f=pd.DataFrame({"ST1":False,"ST2":False,"ST3":False},index=d.index)
    f.loc[d.index[at],"ST1"]=True
    return f

class ShortTermTests(unittest.TestCase):
    def test_time_stop_exact_held_sessions(self):
        d=sample()
        d.loc[d.index[201:211],["open","close","high","low"]]=[100.,100.,101.,99.]
        for e in EXITS:
            t=replay_short(d,"ST1",e,feature(d))
            self.assertEqual(t["Reason"].iloc[200+e.sessions],TIME)
            # Use scale=1 only in this test to make one lot affordable at 100 VND.
            from portfolio_core import Policy
            out=simulate_portfolio({"HPG":t},e.sizing_code,"R1",Policy(price_scale=1))[2]
            self.assertEqual(out.iloc[0]["Số phiên giữ"],e.sessions)
    def test_initial_stop_signal_close_next_open(self):
        d=sample()
        t=replay_short(d,"ST1",EXITS[0],feature(d))
        self.assertEqual(t["Reason"].iloc[201],INITIAL)
        self.assertAlmostEqual(t["ST_Stop"].iloc[201],97.)
        self.assertEqual(t["Trend"].iloc[202],-1)
    def test_atr_frozen_at_signal(self):
        d=sample()
        d.loc[d.index[201],"ATR"]=30.
        t=replay_short(d,"ST1",EXITS[2],feature(d))
        self.assertAlmostEqual(t["ST_Stop"].iloc[201],97.)
        self.assertEqual(t["Reason"].iloc[201],INITIAL)
    def test_no_intraday_stop(self):
        d=sample()
        d.loc[d.index[201],["close","low"]]=[100.,50.]
        t=replay_short(d,"ST1",EXITS[0],feature(d))
        self.assertEqual(t["Trend"].iloc[201],1)
    def test_sell_day_extremes_excluded(self):
        d=sample()
        d.loc[d.index[202],["high","low"]]=[1000.,1.]
        e=excursions(d,d.index[201],d.index[202])
        self.assertAlmostEqual(e["MAE giá (%)"],-10.)
        self.assertAlmostEqual(e["MFE giá (%)"],1.)
    def test_breakout_excludes_current_high_and_volume(self):
        d=sample()
        d.loc[d.index[200],["open","close","high","low","volume"]]=[100,103,104,99,150000]
        f=entry_conditions(d)
        self.assertEqual(f["ST_High20Prev"].iloc[200],101.)
        self.assertEqual(f["ST_Vol20Prev"].iloc[200],100000.)
        self.assertTrue(f["ST2"].iloc[200])
    def test_mean_reversion_cross(self):
        d=sample()
        d.loc[:d.index[199],["open","close","high","low"]]=[90.,90.,91.,89.]
        d.loc[d.index[150:200],["open","close","high","low"]]=[99.,99.,100.,98.]
        d.loc[d.index[199:201],"RSI"]=[34.,36.]
        self.assertTrue(entry_conditions(d)["ST3"].iloc[200])
    def test_prefix_no_future(self):
        d=sample()
        f=entry_conditions(d)
        assert_frame_equal(f.iloc[:205],entry_conditions(d.iloc[:205]))
        x=replay_short(d,"ST1",EXITS[0],feature(d))
        y=replay_short(d.iloc[:205],"ST1",EXITS[0],feature(d).iloc[:205])
        assert_frame_equal(x.iloc[:205],y)
    def test_no_same_cycle_chase(self):
        d=sample()
        f=feature(d)
        f.loc[d.index[200:210],"ST1"]=True
        t=replay_short(d,"ST1",EXITS[0],f)
        self.assertTrue((t["Trend"].iloc[201:210]==-1).all())
    def test_warmup(self):
        d=sample()
        self.assertFalse(entry_conditions(d).iloc[:199][["ST1","ST2","ST3"]].any().any())
    def test_all_cases_and_immutability(self):
        d=sample()
        original=d.copy(deep=True)
        report=evaluate_short_term({"HPG":d})
        self.assertEqual(len(report["summary"]),13)
        self.assertTrue(report["errors"].empty)
        self.assertEqual(len(report["stocks"]),13)
        assert_frame_equal(d,original)
    def test_pending_exit_not_fabricated(self):
        from portfolio_core import Policy
        d=sample().iloc[:202]
        t=replay_short(d,"ST1",EXITS[0],feature(d))
        result=simulate_portfolio({"HPG":t},"S2P0","R1",Policy(price_scale=1))
        self.assertTrue(result[2].empty)
        self.assertEqual(result[0]["Vị thế cuối"],1)

if __name__=="__main__": unittest.main()
