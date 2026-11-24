import unittest
import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal
from test_portfolio import bars
from test_initial_stop import fixture
from portfolio_core import simulate_portfolio,Policy
from entry_filter_core import FILTERS,BY_FILTER,BASELINE,reject_reason,signal_catalog,compare_entries,evaluate_entry_filters

def sample():
    d=bars([-1,1,1,-1,-1,1,1,-1,-1],[25,25,25,26,28,25,25,24,22])
    d["SMA20"]=25.
    d["SMA50"]=25.
    d["RSI"]=60.
    d["ATR"]=.5
    d.loc[d.index[1],"RSI"]=75.
    d.loc[d.index[5],"RSI"]=50.
    return d

class EntryFilterTests(unittest.TestCase):
    def test_threshold_inclusive(self):
        r=pd.Series({"close":100.,"ATR":3.,"SMA20":100/1.05,"SMA50":100/1.15,"RSI":70.})
        for code in ("V1","V2","V3","A1","A2","A3","A4"):
            self.assertEqual(reject_reason(r,BY_FILTER[code]),"")
    def test_missing_feature_fails_closed_only_selected(self):
        r=pd.Series({"close":100.,"ATR":2.})
        self.assertEqual(reject_reason(r,BY_FILTER["V1"]),"")
        self.assertTrue(reject_reason(r,BY_FILTER["A3"]))
        self.assertEqual(reject_reason(r,BY_FILTER[BASELINE]),"")
    def test_each_filter_independent(self):
        r=pd.Series({"close":100.,"ATR":4.5,"SMA20":100/1.07,"SMA50":100/1.16,"RSI":71.})
        expected={"V1":True,"V2":True,"V3":False,"A1":True,"A2":False,"A3":True,"A4":True}
        for code,blocked in expected.items():
            self.assertEqual(bool(reject_reason(r,BY_FILTER[code])),blocked)
    def test_legacy_all_pass(self):
        d=sample()
        a=simulate_portfolio({"HPG":d},"S0P0","R1")
        b=simulate_portfolio({"HPG":d},"S0P0","R1",entry_gate=lambda s,r:"")
        self.assertEqual(a[0],b[0])
        for x,y in zip(a[1:],b[1:]): assert_frame_equal(x,y)
    def test_gate_uses_signal_not_fill_and_no_chase(self):
        d=sample()
        d.loc[d.index[2],"RSI"]=40.
        res=simulate_portfolio({"HPG":d},"S0P0","R1",entry_gate=lambda s,r:reject_reason(r,BY_FILTER["A3"]))
        audit=res[3]
        self.assertEqual(audit.loc[audit["Lệnh"]=="Bỏ mua","Ngày"].tolist(),[d.index[2]])
        self.assertEqual(audit.loc[audit["Lệnh"]=="Mua","Ngày"].tolist(),[d.index[6]])
        self.assertEqual(len(res[2]),1)
    def test_prefix_causal(self):
        d=sample()
        def gate(s,r): return reject_reason(r,BY_FILTER["A3"])
        a=simulate_portfolio({"HPG":d},"S0P0","R1",entry_gate=gate)
        b=simulate_portfolio({"HPG":d.iloc[:7]},"S0P0","R1",entry_gate=gate)
        assert_frame_equal(a[1].iloc[:7],b[1])
    def test_rejected_winner_and_pnl(self):
        d=sample()
        # Positive and valid reference for both entries.
        d.loc[d.index[5],"close"]=25.
        base=simulate_portfolio({"HPG":d},"S0P0","R1")
        trial=simulate_portfolio({"HPG":d},"S0P0","R1",entry_gate=lambda s,r:reject_reason(r,BY_FILTER["A3"]))
        out,stats=compare_entries(signal_catalog({"HPG":d}),base[2],base[3],trial[2],trial[3],BY_FILTER["A3"])
        self.assertEqual(stats["Tín hiệu bị lọc"],1)
        self.assertEqual(stats["Lệnh thắng đối chứng bị lọc"],1)
        self.assertGreater(stats["P&L đối chứng của lệnh thắng bị lọc (VND)"],0)
    def test_unbought_baseline_not_counted_as_avoided_loss(self):
        d=sample()
        d.loc[d.index[1],"close"]=30.
        base=simulate_portfolio({"HPG":d},"S0P0","R1")
        trial=simulate_portfolio({"HPG":d},"S0P0","R1",entry_gate=lambda s,r:reject_reason(r,BY_FILTER["A3"]))
        out,stats=compare_entries(signal_catalog({"HPG":d}),base[2],base[3],trial[2],trial[3],BY_FILTER["A3"])
        self.assertEqual(stats["Tín hiệu bị lọc"],1)
        self.assertEqual(stats["Lệnh mua đối chứng bị lọc"],0)
    def test_missing_exit_is_not_loss(self):
        d=sample().iloc[:4]
        base=simulate_portfolio({"HPG":d},"S0P0","R1")
        trial=simulate_portfolio({"HPG":d},"S0P0","R1",entry_gate=lambda s,r:reject_reason(r,BY_FILTER["A3"]))
        out,stats=compare_entries(signal_catalog({"HPG":d}),base[2],base[3],trial[2],trial[3],BY_FILTER["A3"])
        self.assertEqual(stats["Lệnh đối chứng bị lọc chưa đóng"],1)
        self.assertEqual(stats["Lệnh thua đối chứng bị lọc"],0)
    def test_all_cases_integration(self):
        d=fixture(400)
        d["SMA20"]=95.
        d["RSI"]=60.
        original=d.copy(deep=True)
        report=evaluate_entry_filters({"HPG":d})
        self.assertEqual(len(report["summary"]),8)
        self.assertTrue(report["errors"].empty)
        self.assertEqual(report["summary"].iloc[0]["Chênh LN so đối chứng (đpt)"],0)
        assert_frame_equal(d,original)
    def test_empty_signals(self):
        d=fixture(400)
        d["Buy_Pct"]=0.
        d["Trend"]=-1
        d["SMA20"]=95.
        d["RSI"]=60.
        report=evaluate_entry_filters({"HPG":d})
        self.assertEqual(len(report["summary"]),8)
        self.assertTrue(report["errors"].empty)
        self.assertTrue((report["summary"]["Tín hiệu mua"]==0).all())

if __name__=="__main__": unittest.main()
