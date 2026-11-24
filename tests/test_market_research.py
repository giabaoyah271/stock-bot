import unittest
from unittest.mock import Mock
import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal
from test_initial_stop import fixture
from test_portfolio import bars
from portfolio_core import simulate_portfolio,Policy
from market_research_core import CASES,BASELINE,load_index,market_context,enrich,market_reason,rank_rs,gate,evaluate_market
CA={c.code:c for c in CASES}

def history():
    d=fixture(400)
    d["SMA20"]=95.
    d["RSI"]=60.
    return d

def idx(d):
    return pd.DataFrame({"close":np.linspace(1000,1200,len(d))},index=d.index)

class MarketTests(unittest.TestCase):
    def test_tcbs_index_route(self):
        d=history()
        raw=d[["open","high","low","close","volume"]].reset_index(names="time")
        factory=Mock()
        factory.return_value.index.return_value.ohlcv.return_value=raw
        out=load_index(factory,now="2026-11-24 16:00")
        factory.assert_called_once_with("tcbs")
        factory.return_value.index.assert_called_once_with("VNINDEX")
        factory.return_value.index.return_value.ohlcv.assert_called_once_with(start="2022-01-01",end="2026-11-24",interval="1D")
        self.assertEqual(len(out),400)
    def test_alignment_fails_closed(self):
        d=history()
        for x in (idx(d).iloc[1:],idx(d).iloc[::-1],idx(d).assign(close=0)):
            with self.assertRaises(ValueError): market_context(x,d.index)
    def test_timezone_normalization(self):
        d=history()
        x=idx(d)
        x.index=x.index.tz_localize("Asia/Ho_Chi_Minh").tz_convert("UTC")
        assert_frame_equal(market_context(x,d.index),market_context(idx(d),d.index))
    def test_relative_return_math(self):
        d=history()
        d["close"]=np.linspace(50,100,len(d))
        s,m=enrich({"HPG":d},idx(d))
        t=80
        expect=100*(d["close"].iloc[t]/d["close"].iloc[t-20]-idx(d)["close"].iloc[t]/idx(d)["close"].iloc[t-20])
        self.assertAlmostEqual(s["HPG"]["RS20 (đpt)"].iloc[t],expect)
        self.assertTrue(pd.isna(s["HPG"]["RS60 (đpt)"].iloc[59]))
    def test_prefix_causality(self):
        d=history()
        full,m=enrich({"HPG":d},idx(d))
        part,n=enrich({"HPG":d.iloc[:250]},idx(d).iloc[:250])
        assert_frame_equal(full["HPG"].iloc[:250],part["HPG"])
        assert_frame_equal(m.iloc[:250],n)
    def test_conditions_and_strict_boundary(self):
        r=pd.Series({"VNINDEX Close":110,"VNINDEX SMA50":105,"VNINDEX SMA200":100,"VNINDEX SMA50 lag20":104,"RS20 (đpt)":1,"RS60 (đpt)":-1})
        for code in ("M1","M2","M3","M4","RS1","RS4"): self.assertEqual(market_reason(r,CA[code]),"")
        for code in ("RS2","RS3"): self.assertTrue(market_reason(r,CA[code]))
        r["VNINDEX Close"]=105
        self.assertTrue(market_reason(r,CA["M1"]))
        r["RS20 (đpt)"]=0
        self.assertTrue(market_reason(r,CA["RS1"]))
        self.assertTrue(market_reason(pd.Series(dtype=float),CA["M1"]))
    def test_a4_first(self):
        r=pd.Series({"close":120,"SMA50":100,"RS20 (đpt)":-1})
        self.assertTrue(gate("A4",CA["RS1"])("HPG",r).startswith("Bộ lọc A4:"))
        self.assertTrue(gate("A0",CA["RS1"])("HPG",r).startswith("Bộ lọc RS1:"))
    def test_rank_changes_order_only(self):
        a=bars([-1,1,1,-1,-1],score=80)
        b=bars([-1,1,1,-1,-1],score=70)
        a["RS60 (đpt)"]=-2
        b["RS60 (đpt)"]=5
        p=Policy(max_positions=1)
        x=simulate_portfolio({"HPG":a,"MBB":b},"S0P0","R1",p)
        y=simulate_portfolio({"HPG":a,"MBB":b},"S0P0","R1",p,entry_rank=rank_rs)
        self.assertEqual(x[3].loc[x[3]["Lệnh"]=="Mua","Mã"].tolist(),["HPG"])
        self.assertEqual(y[3].loc[y[3]["Lệnh"]=="Mua","Mã"].tolist(),["MBB"])
        self.assertEqual(rank_rs("HPG",pd.Series({"RS60 (đpt)":1,"Buy_Pct":60})),(-1.,-60.,"HPG"))
    def test_rank_signal_row_not_fill(self):
        a=bars([-1,1,1,-1,-1],score=80); b=a.copy()
        a["RS60 (đpt)"]=[0,5,-10,0,0]
        b["RS60 (đpt)"]=[0,1,20,0,0]
        y=simulate_portfolio({"HPG":a,"MBB":b},"S0P0","R1",Policy(max_positions=1),entry_rank=rank_rs)
        self.assertEqual(y[3].loc[y[3]["Lệnh"]=="Mua","Mã"].tolist(),["HPG"])
    def test_all_18_and_no_mutation(self):
        d=history()
        original=d.copy(deep=True)
        report=evaluate_market({"HPG":d},idx(d))
        self.assertEqual(len(report["summary"]),18)
        self.assertTrue(report["errors"].empty)
        self.assertEqual(len(report["index"]),400)
        self.assertTrue((report["summary"].loc[report["summary"]["Thử nghiệm"]==BASELINE.code,"Chênh LN so cùng nền (đpt)"]==0).all())
        assert_frame_equal(d,original)
    def test_empty_signals(self):
        d=history();d["Buy_Pct"]=0.;d["Trend"]=-1
        report=evaluate_market({"HPG":d},idx(d))
        self.assertEqual(len(report["summary"]),18)
        self.assertTrue(report["errors"].empty)
        self.assertTrue((report["summary"]["Tín hiệu mua"]==0).all())

if __name__=="__main__": unittest.main()
