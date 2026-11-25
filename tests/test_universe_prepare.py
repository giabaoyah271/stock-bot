import unittest
import pandas as pd
from universe_prepare_core import U5,SECTORS,dates_for,RETRY,SHORT,prepare_one
class PrepareTests(unittest.TestCase):
    def test_scope(self):
        self.assertEqual(set(SECTORS),set(U5))
        self.assertEqual((len(RETRY),len(SHORT)),(12,2))
    def test_dates(self):
        cal=pd.bdate_range("2022-01-04","2026-11-23")
        self.assertEqual(dates_for("TCX",cal)[0],pd.Timestamp("2025-10-21"))
        self.assertNotIn(pd.Timestamp("2022-01-10"),dates_for("HHV",cal))
        self.assertIn(pd.Timestamp("2022-01-20"),dates_for("HHV",cal))
        self.assertEqual(dates_for("ACV",cal)[0],pd.Timestamp("2022-06-17"))
        self.assertEqual(dates_for("CEO",cal,"2025-05-16")[0],pd.Timestamp("2025-05-19"))
    def test_zero_gate(self):
        cal=pd.bdate_range("2022-01-04",periods=300)
        d=pd.DataFrame({"open":10.,"high":11.,"low":9.,"close":10.,"volume":100.},index=cal)
        d.loc[cal[20],"volume"]=0
        with self.assertRaisesRegex(ValueError,"volume 0"): prepare_one("HPG",d,cal)
if __name__=="__main__": unittest.main()
