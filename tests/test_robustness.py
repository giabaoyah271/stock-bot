import unittest
from dataclasses import replace
import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal
from test_portfolio import bars
from test_initial_stop import fixture
from portfolio_core import Policy,Costs,simulate_portfolio,size_order,BUY_MULT,SELL_MULT
from robustness_core import block_bootstrap,stats_equity,benchmarks,evaluate_robustness,walk_forward,CANDIDATES,historical_slice
from prospective_capture import capture_snapshot

class RobustnessTests(unittest.TestCase):
    def test_default_cost_parity(self):
        d=bars([-1,1,1,-1,-1])
        a=simulate_portfolio({"HPG":d},"S0P0","R1")
        b=simulate_portfolio({"HPG":d},"S0P0","R1",Policy(costs=Costs()))
        self.assertEqual(Costs().buy_mult,BUY_MULT)
        self.assertEqual(Costs().sell_mult,SELL_MULT)
        for x,y in zip(a[1:],b[1:]): assert_frame_equal(x,y)
    def test_stress_costs_sizing_and_accounting(self):
        d=bars([-1,1,1,-1,-1],[25,25,25,25,27])
        p=Policy(costs=Costs(.003,.003,.001,.005))
        q,_,_=size_order(1e8,1e8,25000,23000,0,0,p,"R1")
        s,c,l,o,w=simulate_portfolio({"HPG":d},"S0P0","R1",p)
        t=l.iloc[0]
        self.assertEqual(t["Số CP"],q)
        self.assertAlmostEqual(s["Vốn cuối"],1e8+q*(27000*p.costs.sell_mult-25000*p.costs.buy_mult))
    def test_reject_non_s0_costs(self):
        with self.assertRaises(ValueError):
            simulate_portfolio({"HPG":bars([-1,1,1])},"S2P0","R1",Policy(costs=Costs(.003,.003,.001,.005)))
    def test_bootstrap_deterministic_and_flat(self):
        a,x=block_bootstrap(np.zeros(40),5,20)
        b,y=block_bootstrap(np.zeros(40),5,20)
        self.assertEqual(a,b)
        assert_frame_equal(x,y)
        self.assertEqual(a["MDD P95 (%)"],0)
    def test_bootstrap_initial_drawdown(self):
        a,x=block_bootstrap(np.full(20,-.01),5,20)
        self.assertAlmostEqual(a["MDD P95 (%)"],100*(1-.99**20))
        self.assertEqual(a["Tỷ lệ LN âm (%)"],100)
    def test_stats_initial_peak(self):
        self.assertAlmostEqual(stats_equity([100,90,95])["MDD (%)"],-10)
    def test_lagged_exposure(self):
        dates=pd.date_range("2024-01-01",periods=3)
        d=pd.DataFrame({"close":[100.,110.,121.]},index=dates)
        context=pd.DataFrame({"VNINDEX Close":d.close},index=dates)
        curve=pd.DataFrame({"Equity":[100.,100.,100.],"Exposure (%)":[0.,50.,100.]},index=dates)
        _,b=benchmarks({"HPG":d},context,curve,100)
        np.testing.assert_allclose(b["VNINDEX lag Exposure"],[100,100,105])
    def test_historical_cutoff(self):
        d=pd.DataFrame({"close":[1,2]},index=pd.to_datetime(["2026-11-23","2026-11-24"]))
        self.assertEqual(len(historical_slice(d)),1)
    def test_walk_forward_future_not_selecting(self):
        ix=pd.bdate_range("2023-01-02","2024-07-03")
        results={}
        for name in CANDIDATES:
            equity=np.linspace(100,120,len(ix))
            curve=pd.DataFrame({"Equity":equity},index=ix)
            ledger=pd.DataFrame({"Ngày bán":ix[:10]})
            results[name]=({},curve,ledger,pd.DataFrame(),pd.DataFrame())
        a,_=walk_forward(results,100)
        results["A0"][1].loc["2024-01-02":,"Equity"]*=3
        b,_=walk_forward(results,100)
        first=a["Test từ"].min()
        self.assertEqual(a.loc[a["Test từ"]==first,"Được chọn từ train"].tolist(),b.loc[b["Test từ"]==first,"Được chọn từ train"].tolist())
    def test_all_report_cases(self):
        d=fixture(400)
        d["SMA20"]=95.;d["RSI"]=60.
        index=pd.DataFrame({"close":np.linspace(1000,1200,len(d))},index=d.index)
        r=evaluate_robustness({"HPG":d},index,n_sim=20)
        self.assertEqual(len(r["summary"]),15)
        self.assertEqual(len(r["mc"]),6)
        self.assertEqual(len(r["benchmark"]),5)
    def test_capture_no_backfill(self):
        for now in ("2026-11-24 18:00","2026-11-25 14:00"):
            with self.assertRaises(ValueError): capture_snapshot({},now)
    def test_capture_requires_universe(self):
        with self.assertRaises(ValueError): capture_snapshot({},"2026-11-25 16:00")

if __name__=="__main__": unittest.main()
