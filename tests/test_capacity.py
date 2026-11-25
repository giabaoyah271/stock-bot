import unittest
import pandas as pd
from capacity_core import CAPACITY,capacity_id,split_loo,loo_symbols,drop_two,diagnostic_walk_forward,read_kt17

class CapacityTests(unittest.TestCase):
    def test_prespecified_grid(self):
        self.assertEqual(len(CAPACITY),6)
        self.assertEqual(len({capacity_id(n,r) for n,r in CAPACITY}),6)
        self.assertEqual(CAPACITY[0],(5,.005))
        self.assertEqual(2*(len(CAPACITY)+1+3+1),22)
    def test_loo(self):
        s=[f"T{i:03d}" for i in range(115)]
        parts=split_loo(s)
        self.assertEqual([len(v) for v in parts.values()],[23]*5)
        self.assertEqual([x for v in parts.values() for x in v],s)
        with self.assertRaises(ValueError): split_loo(s[:-1])
    def test_loo_all_matches_existing_batches(self):
        symbols=[f"T{i:03d}" for i in range(115)][::-1]
        batches=tuple(s for i in range(1,6) for s in loo_symbols(symbols,f"LOO{i}"))
        self.assertEqual(loo_symbols(symbols,"LOO_ALL"),batches)
        self.assertEqual(len(batches),115)
        self.assertEqual(len(set(batches)),115)
        with self.assertRaises(ValueError): loo_symbols(symbols,"MAIN")
        with self.assertRaises(ValueError): loo_symbols(symbols[:-1],"LOO_ALL")
    def test_drop_two_ties(self):
        f=pd.DataFrame({"Mã":[f"T{i:03d}" for i in range(115)],"P&L tổng (VND)":[1.]*115,"Kịch bản":"U5-B-FULL-A0-C0-RS60-L0"})
        self.assertEqual(drop_two({"theo_ma":f},"U5-B"),("T000","T001"))
    def test_walk_forward_no_eligible(self):
        cal=pd.bdate_range("2022-01-04","2026-11-23")
        eq=pd.DataFrame({"Equity":100.},index=cal)
        r={capacity_id(n,x):({},eq,pd.DataFrame(),None,None) for n,x in CAPACITY}
        out=diagnostic_walk_forward(r,100.,"U5-B")
        self.assertEqual(len(out),36)
        self.assertFalse(out["Được chọn từ train"].any())
        self.assertTrue(out["Không có ứng viên đạt train"].all())
    def test_bad_archive(self):
        with self.assertRaises(ValueError): read_kt17(b"wrong")
if __name__=="__main__": unittest.main()
