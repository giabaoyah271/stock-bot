import unittest
import pandas as pd
from signal_engine_core import state,report_rows,validate_index,SCOPE,U5
class SignalEngineTests(unittest.TestCase):
    def test_states(self):
        self.assertEqual(state(-1,1),"Mua mới (tín hiệu)")
        self.assertEqual(state(1,-1),"Thoát xu hướng (tín hiệu)")
        self.assertEqual(state(1,1),"Duy trì xu hướng")
        self.assertEqual(state(-1,-1),"Đứng ngoài")
        with self.assertRaises(ValueError): state(0,1)
    def test_ranking_only_new_verified(self):
        rows=[{"Mã":s,"Kỹ thuật":status,"Tín hiệu":signal,"RS60 (đpt)":rs,"Buy Score (%)":buy}
            for s,status,signal,rs,buy in [("HPG","Khớp mẫu KT18",state(-1,1),3,65),("ACB","Khớp mẫu KT18",state(-1,1),3,65),("FPT","Khớp mẫu KT18",state(1,1),20,90),("MBB","Chưa đạt",state(-1,1),30,100),("TCB","Khớp mẫu KT18",state(-1,1),3,70)]]
        d=report_rows(rows)
        self.assertEqual(d["Mã"].tolist()[:3],["TCB","ACB","HPG"])
        self.assertEqual(d["Hạng mua mới (kỹ thuật)"].notna().sum(),3)
        self.assertEqual(len(SCOPE),5)
        self.assertEqual(len(U5),120)
    def test_index_session(self):
        cal=pd.DatetimeIndex(["2026-11-23","2026-11-24"],name="Ngày")
        d=pd.DataFrame({"open":[100.,101.],"high":[101.,102.],"low":[99.,100.],"close":[100.,101.],"volume":[1,1]},index=cal)
        old=d["close"].iloc[:1]
        x,h=validate_index(d,old,"2026-11-24","2026-11-25 09:00")
        self.assertEqual(x.index[-1],cal[-1]);self.assertEqual(len(h),64)
        with self.assertRaises(ValueError): validate_index(d,old,"2026-11-25","2026-11-25 09:00")
        with self.assertRaises(ValueError): validate_index(d,old,"2026-11-25","2026-11-25 16:00")
        with self.assertRaises(AssertionError): validate_index(d,old+1,"2026-11-24","2026-11-25 09:00")
    def test_empty_error_only_and_duplicates(self):
        self.assertTrue(report_rows([]).empty)
        d=report_rows([{"Mã":"HPG","Kỹ thuật":"Chưa đạt"}])
        self.assertTrue(d["Hạng mua mới (kỹ thuật)"].isna().all())
        with self.assertRaises(ValueError): report_rows([{"Mã":"HPG"},{"Mã":"HPG"}])
if __name__=="__main__": unittest.main()
