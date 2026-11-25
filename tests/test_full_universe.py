import unittest
import pandas as pd
import numpy as np
from full_universe_core import FULL_CASES,GROUPS,enrich_causal,make_gate,common_slice,check_zip,LIQ_LIMIT,stock_rows
from portfolio_core import Policy

class KT17Tests(unittest.TestCase):
    def test_design(self):
        self.assertEqual(len(set(FULL_CASES)),8)
        self.assertEqual(len(GROUPS)*(len(FULL_CASES)+2),40)
    def test_liquidity_and_rank_causal(self):
        cal=pd.bdate_range("2022-01-04",periods=100)
        idx=pd.Series(np.arange(100)+1000.,index=cal)
        d=pd.DataFrame({"close":np.arange(100)+20.,"volume":1000000.},index=cal).drop(cal[20])
        x=enrich_causal({"HPG":d},idx,1000)["HPG"]
        self.assertAlmostEqual(x["RS60 (đpt)"].iloc[60],100*(d["close"].iloc[60]/d["close"].iloc[0]-idx.loc[d.index[60]]/idx.loc[d.index[0]]))
        self.assertAlmostEqual(x["GTGD proxy 20 (VND)"].iloc[19],float((d["close"].iloc[:20]*d["volume"].iloc[:20]*1000).mean()))
        d2=d.copy();d2.loc[d2.index[-1],"close"]*=2
        y=enrich_causal({"HPG":d2},idx,1000)["HPG"]
        pd.testing.assert_frame_equal(x.iloc[:-1],y.iloc[:-1])
    def test_gate(self):
        row=pd.Series({"close":10.,"SMA50":10.,"GTGD proxy 20 (VND)":LIQ_LIMIT})
        self.assertEqual(make_gate("A4","L10")("HPG",row),"")
        row["GTGD proxy 20 (VND)"]=LIQ_LIMIT-1
        self.assertIn("Thanh khoản",make_gate("A4","L10")("HPG",row))
        row["close"]=12.
        self.assertIn("A4",make_gate("A4","L10")("HPG",row))
        self.assertIsNone(make_gate("A0","L0"))
    def test_common(self):
        cal=pd.bdate_range("2026-10-08",periods=33)
        d=pd.DataFrame({"Trend":1},index=cal)
        sig,c=common_slice({"HPG":d},cal,cal[2])
        self.assertEqual(len(c),31)
        self.assertEqual(sig["HPG"]["Trend"].iloc[0],1)
        with self.assertRaises(ValueError): common_slice({"HPG":d.drop(cal[-1])},cal,cal[2])
    def test_wrong_zip(self):
        with self.assertRaises(ValueError): check_zip(b"wrong","bad")
    def test_zero_trades(self):
        d=pd.DataFrame({"close":[10.]})
        r=stock_rows({"HPG":d},pd.DataFrame(),pd.DataFrame(),Policy(),{"HPG":"Thép"})
        self.assertEqual(r["P&L tổng (VND)"].iloc[0],0)

if __name__=="__main__": unittest.main()
