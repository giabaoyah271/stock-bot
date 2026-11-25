import unittest
import pandas as pd
import numpy as np
from universe_u5 import U5,OLD_KEPT,NEW_ADDED,EXCLUDED,BATCHES
from universe_audit_core import audit_one,reference_calendar,manifest
from test_initial_stop import fixture

class UniverseAuditTests(unittest.TestCase):
    def test_fixed_universe(self):
        self.assertEqual((len(U5),len(OLD_KEPT),len(NEW_ADDED),len(EXCLUDED)),(120,100,20,21))
        self.assertEqual(len(set(U5+EXCLUDED)),141)
        self.assertEqual(tuple(s for v in BATCHES.values() for s in v),U5)
        self.assertTrue({"PNJ","FPT","MCH","GEE","DMX","ACV"}.issubset(U5))
        self.assertFalse({"DGC","VPI","NVL","VGI"}.intersection(U5))
    def test_empty_is_not_eligible(self):
        d=pd.DataFrame();d.attrs["daily_quality_error"]="Chỉ có 80 nến"
        row,_,source=audit_one("DMX",d,pd.bdate_range("2022-01-04",periods=200))
        self.assertEqual(row["Lý do"],"Chỉ có 80 nến")
        self.assertEqual(row["Đủ điều kiện mua mới"],"Chưa phê duyệt")
        self.assertTrue(source.empty)
    def test_gap_diagnostics(self):
        d=fixture(400)
        cal=d.index
        x=d.drop(cal[[0,220,399]])
        row,gaps,source=audit_one("HPG",x,cal)
        self.assertEqual((row["Thiếu đầu kỳ"],row["Thiếu giữa kỳ"],row["Thiếu cuối kỳ"]),(1,1,1))
        self.assertEqual(len(gaps),3)
        self.assertEqual(len(source),397)
        self.assertEqual(row["Trạng thái kỹ thuật"],"Chưa đạt")
    def test_invalid_ohlc_no_source(self):
        d=fixture(400)
        d.loc[d.index[2],"high"]=0
        row,_,source=audit_one("HPG",d,d.index)
        self.assertEqual(row["Trạng thái kỹ thuật"],"Chưa đạt")
        self.assertTrue(source.empty)
    def test_reference_digest(self):
        cal=pd.bdate_range("2022-01-04",periods=400)
        ix=pd.DataFrame({"close":np.linspace(1000,1100,len(cal))},index=cal)
        c,ctx=reference_calendar(ix,False)
        m=manifest(c,ctx,1000,False)
        self.assertEqual(m["Số phiên"],400)
        ix.loc[cal[-1],"close"]+=1
        _,ctx2=reference_calendar(ix,False)
        self.assertNotEqual(m["SHA256 lịch VNINDEX"],manifest(c,ctx2,1000,False)["SHA256 lịch VNINDEX"])
        with self.assertRaises(ValueError): reference_calendar(ix)

if __name__=="__main__": unittest.main()
