import unittest
import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal
from test_portfolio import bars
from test_initial_stop import fixture
from portfolio_core import Policy,simulate_portfolio
from cross_section_core import GROUPS,ALL,U0,U1,U2,U3,EXT_SECTORS,expected_dates,prepare_one,run_case,stock_breakdown,evaluate_cross_section

class CrossSectionTests(unittest.TestCase):
    def test_universe(self):
        self.assertEqual([len(GROUPS[g]) for g in GROUPS],[12,20,14,20])
        self.assertEqual(len(ALL),31)
        self.assertFalse(set(U0)&set(U2))
        self.assertEqual(set(U2),set(U1)-set(U0))
        self.assertTrue(set(ALL).issubset(EXT_SECTORS))
    def test_dates(self):
        cal=pd.bdate_range("2022-01-04","2026-11-23")
        self.assertEqual(expected_dates("VPL",cal)[0],pd.Timestamp("2025-05-13"))
        self.assertNotIn(pd.Timestamp("2025-01-09"),expected_dates("BSR",cal))
        self.assertNotIn(pd.Timestamp("2025-12-22"),expected_dates("MCH",cal))
        self.assertTrue(expected_dates("HPG",cal).equals(cal))
    def test_acv_quarantine_explicit_and_calendar(self):
        cal=pd.bdate_range("2022-01-04","2026-11-23")
        self.assertEqual(expected_dates("ACV",cal)[0],cal[0])
        self.assertEqual(expected_dates("ACV",cal,True)[0],pd.Timestamp("2022-06-17"))
        self.assertTrue(expected_dates("HPG",cal,True).equals(cal))
        d=fixture(400)
        d.attrs["daily_quality"]={"kt15_acv_quarantine":{"date":"2022-06-16","ohlcv":[48.97,49.09,48.85,48.76,37101]}}
        with self.assertRaisesRegex(ValueError,"chưa được cho phép"):
            prepare_one("ACV",d,d.index)
    def test_unknown_gap_rejected(self):
        d=fixture(400)
        with self.assertRaisesRegex(ValueError,"Thiếu 1"):
            prepare_one("HPG",d.drop(d.index[220]),d.index)
    def test_original_parity(self):
        d=bars([-1,1,1,-1,-1],[25,25,25,26,28])
        old=simulate_portfolio({"HPG":d},"S0P0","R1")
        new=run_case({"HPG":d},d.index,Policy(),"A0")
        self.assertEqual(old[0],new[0])
        assert_frame_equal(old[1],new[1][old[1].columns])
        for a,b in zip(old[2:],new[2:]): assert_frame_equal(a,b)
    def test_late_start_no_fake_orders(self):
        cal=pd.bdate_range("2024-01-02",periods=8)
        d=bars([-1,1,1,-1,-1]);d.index=cal[3:]
        r=run_case({"VPL":d},cal,Policy(),"A0")
        self.assertEqual(r[3].iloc[0]["Ngày"],cal[5])
        self.assertTrue((r[1].iloc[:3]["Equity"]==1e8).all())
        self.assertEqual(r[1].iloc[0]["Số mã có nến"],0)
    def test_gap_carry_and_next_real_open(self):
        cal=pd.bdate_range("2024-01-02",periods=7)
        d=bars([-1,1,1,-1,-1],[25,25,25,26,28])
        d.index=cal[[0,1,2,3,6]]
        r=run_case({"BSR":d},cal,Policy(),"A0")
        self.assertEqual(r[2].iloc[0]["Ngày tín hiệu bán"],cal[3])
        self.assertEqual(r[2].iloc[0]["Ngày bán"],cal[6])
        self.assertEqual(r[1].loc[cal[4],"Vị thế định giá Close cũ"],1)
        self.assertEqual(r[1].loc[cal[4],"Equity"],r[1].loc[cal[3],"Equity"])
        self.assertFalse(r[3]["Ngày"].isin(cal[4:6]).any())
    def test_gap_buy_signal_uses_actual_previous(self):
        cal=pd.bdate_range("2024-01-02",periods=7)
        d=bars([-1,1,1,-1,-1]);d.index=cal[[0,1,4,5,6]]
        r=run_case({"MCH":d},cal,Policy(),"A0")
        self.assertEqual(r[2].iloc[0]["Ngày tín hiệu mua"],cal[1])
        self.assertEqual(r[2].iloc[0]["Ngày mua"],cal[4])
    def test_open_pnl_reconciles(self):
        d=bars([-1,1,1,1],[25,25,25,30])
        r=run_case({"HPG":d},d.index,Policy(),"A0")
        detail=stock_breakdown({"HPG":d},r[2],r[3],Policy())
        self.assertAlmostEqual(detail["P&L tổng (VND)"].sum(),r[0]["Vốn cuối"]-1e8)
    def test_sector_cap_across_new_banks(self):
        d=bars([-1,1,1,1],[25]*4)
        r=run_case({s:d for s in ("VCB","CTG","BID","MBB","ACB")},d.index,Policy(),"A0")
        self.assertLessEqual(r[3].loc[r[3]["Lệnh"]=="Mua","Vốn mua (VND)"].sum(),25e6)
    def test_no_trading_after_last_missing(self):
        d=bars([-1,1,1])
        with self.assertRaises(ValueError):
            run_case({"HPG":d},pd.bdate_range(d.index[0],periods=4),Policy(),"A0")
    def test_partial_group_not_silently_run(self):
        d=fixture(400); d["RSI"]=60.;d["SMA20"]=95.
        idx=pd.DataFrame({"close":np.linspace(1000,1100,len(d))},index=d.index)
        r=evaluate_cross_section({"HPG":d},idx,groups=("U0",),n_sim=10,require_reference=False)
        self.assertTrue(r["summary"].empty)
        self.assertEqual(len(r["coverage"]),12)
        self.assertTrue((r["errors"]["Nhóm"]=="U0").any())
    def test_integration_u0(self):
        d=fixture(400); d["RSI"]=60.;d["SMA20"]=95.
        idx=pd.DataFrame({"close":np.linspace(1000,1100,len(d))},index=d.index)
        r=evaluate_cross_section({s:d for s in U0},idx,groups=("U0",),n_sim=10,require_reference=False)
        self.assertEqual(len(r["summary"]),5,r["errors"].to_string())
        self.assertEqual(len(r["mc"]),6)
        self.assertEqual(len(r["stocks"]),60)
        self.assertTrue(r["errors"].empty)

if __name__=="__main__": unittest.main()
