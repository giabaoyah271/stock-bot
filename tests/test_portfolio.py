import unittest
import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal
from portfolio_core import Policy,size_order,dd_multiplier,simulate_portfolio,BUY_MULT,SELL_MULT,prepare_signals

def bars(states,opens=None,closes=None,score=70):
    n=len(states)
    return pd.DataFrame({"Trend":states,"open":opens or [25.]*n,"close":closes or opens or [25.]*n,
                         "ATR":[1.]*n,"Buy_Pct":[score]*n,"Reason":[""]*n},
                        index=pd.bdate_range("2024-01-02",periods=n))

class PortfolioTests(unittest.TestCase):
    def test_sizing_lot_and_risk(self):
        p=Policy()
        q,r,_=size_order(1e8,1e8,25000,24250,0,0,p,"R1")
        self.assertEqual(q%100,0)
        self.assertLessEqual(q*r,500000)
        self.assertLessEqual(q*25000*BUY_MULT,15000000)
        self.assertGreater(q,0)
    def test_sector_heat_and_cash_constraints(self):
        p=Policy()
        for cash,sector,heat in [(0,0,0),(1e8,25e6,0),(1e8,0,2.5e6)]:
            q,_,_=size_order(1e8,cash,25000,24250,sector,heat,p,"R1")
            self.assertEqual(q,0)
    def test_drawdown_tiers(self):
        self.assertEqual([dd_multiplier(d) for d in (0,.03,.05,.07,.09)],[1,.75,.5,.25,0])
        self.assertEqual(size_order(1e8,1e8,25000,24250,0,0,Policy(),"R2",.09)[0],0)
    def test_next_open_and_cost_cash_parity(self):
        d=bars([-1,1,1,-1,-1],[25,25,25,26,28])
        s,c,t,o,w=simulate_portfolio({"HPG":d},"S2P0","R1")
        self.assertEqual(len(t),1)
        self.assertEqual(t.iloc[0]["Ngày mua"],d.index[2])
        self.assertEqual(t.iloc[0]["Ngày bán"],d.index[4])
        q=t.iloc[0]["Số CP"]
        self.assertAlmostEqual(s["Vốn cuối"],1e8+q*(28000*SELL_MULT-25000*BUY_MULT))
        self.assertTrue((c["Tiền mặt"]>=0).all())
    def test_sell_before_buy_and_rank(self):
        a=bars([-1,1,1,-1,-1,-1],score=80)
        b=bars([-1,1,1,1,1,1],score=70)
        c=bars([-1,-1,-1,1,1,1],score=60)
        p=Policy(max_positions=1)
        s,curve,t,o,w=simulate_portfolio({"MBB":b,"HPG":a,"FPT":c},"S2P0","R1",p)
        self.assertEqual(o.loc[o["Lệnh"]=="Mua","Mã"].tolist(),["HPG","FPT"])
        self.assertEqual(o.loc[o["Lệnh"]=="Bỏ mua","Mã"].tolist(),["MBB"])
        self.assertEqual(o.loc[o["Ngày"]==a.index[4],"Lệnh"].tolist(),["Bán","Mua"])
        self.assertEqual(s["Số vị thế max"],1)
    def test_no_future_and_open_position(self):
        d=bars([-1,1,1,1,-1,-1],[25,25,25,27,28,30])
        full=simulate_portfolio({"HPG":d},"S2P6","R1")
        partial=simulate_portfolio({"HPG":d.iloc[:4]},"S2P6","R1")
        assert_frame_equal(full[1].iloc[:4],partial[1])
        self.assertEqual(partial[0]["Vị thế cuối"],1)
        self.assertEqual(partial[0]["Số lệnh đóng"],0)
    def test_sector_cap_and_tie(self):
        d=bars([-1,1,1,1])
        s,c,t,o,w=simulate_portfolio({k:d for k in ("MBB","TCB","ACB")},"S2P0","R0")
        self.assertEqual(o.iloc[0]["Mã"],"ACB")
        buys=o[o["Lệnh"]=="Mua"]
        self.assertLessEqual(buys["Vốn mua (VND)"].sum(),25e6)
        self.assertLessEqual(s["Số vị thế max"],2)
    def test_calendar_reject(self):
        a=bars([-1,1,1,1])
        with self.assertRaises(ValueError):
            simulate_portfolio({"HPG":a,"MBB":a.iloc[1:]},"S2P0","R1")
    def test_price_scale_equivalent(self):
        a=bars([-1,1,1,-1,-1])
        b=a.copy()
        b[["open","close","ATR"]]*=1000
        x=simulate_portfolio({"HPG":a},"S5P0","R1",Policy(price_scale=1000))
        y=simulate_portfolio({"HPG":b},"S5P0","R1",Policy(price_scale=1))
        assert_frame_equal(x[1],y[1])
    def test_gap_loss_exceeds_risk(self):
        d=bars([-1,1,1,-1,-1],[25,25,25,24,18])
        s,c,t,o,w=simulate_portfolio({"HPG":d},"S2P0","R1")
        self.assertTrue(t.iloc[0]["Lỗ vượt ngân sách"])
        self.assertEqual(s["Lệnh lỗ vượt rủi ro dự kiến"],1)
    def test_no_trades(self):
        d=bars([-1,-1,-1])
        s,c,t,o,w=simulate_portfolio({"HPG":d},"S2P0","R1")
        self.assertEqual(s["Vốn cuối"],1e8)
        self.assertEqual(s["MDD (%)"],0)
        self.assertIsNone(s["PF tiền thực hiện"])
    def test_no_mutation(self):
        d=bars([-1,1,1,-1,-1])
        original=d.copy(deep=True)
        simulate_portfolio({"HPG":d},"S2P0","R1")
        assert_frame_equal(d,original)

if __name__=="__main__": unittest.main()
