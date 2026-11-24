import io
import zipfile
import unittest
import numpy as np
import pandas as pd
from test_portfolio import bars
from portfolio_core import Policy
from cross_section_core import run_case
from concentration_core import GROUPS,case_count,common_period,top_two,compare_frame,read_archive

class ConcentrationTests(unittest.TestCase):
    def test_counts(self):
        self.assertEqual([len(x) for x in GROUPS.values()],[12,20,14,20,31])
        self.assertEqual(case_count(tuple(GROUPS)),224)
        self.assertEqual(case_count(("U4",)),68)
    def test_top_two_signed_with_tie(self):
        d=pd.DataFrame({"Mã":["HPG","MBB","ACB","FPT"],"P&L tổng (VND)":[-900,3,3,1]})
        self.assertEqual(top_two(d),("ACB","MBB"))
    def test_compare_csv_precision_and_dates(self):
        a=pd.DataFrame({"Ngày":pd.to_datetime(["2022-01-04"]),"Equity":[100000001.1234567],"Lý do":[""],"Flag":[True]})
        b=pd.DataFrame({"Ngày":["2022-01-04"],"Equity":[100000001.12345671],"Lý do":[np.nan],"Flag":[True],"Kịch bản":["X"]})
        compare_frame(a,b,"X")
        b.loc[0,"Equity"]+=1
        with self.assertRaises(AssertionError): compare_frame(a,b,"X")
    def test_archive_missing_member(self):
        buf=io.BytesIO()
        with zipfile.ZipFile(buf,"w") as z: z.writestr("unrelated.csv","x\n1\n")
        with self.assertRaisesRegex(ValueError,"Thiếu"): read_archive(buf.getvalue())
    def test_archive_duplicate_member(self):
        buf=io.BytesIO()
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with zipfile.ZipFile(buf,"w") as z:
                z.writestr("x","a");z.writestr("x","b")
        with self.assertRaisesRegex(ValueError,"trùng"): read_archive(buf.getvalue())
    def test_common_starts_flat_and_ignores_old_signal(self):
        cal=pd.bdate_range("2024-01-02",periods=206)
        a=bars([-1]*198+[1]*4+[-1,1,1,-1]);a.index=cal
        b=bars([-1]*203);b.index=cal[3:]
        trimmed,c=common_period({"HPG":a,"MBB":b},cal)
        self.assertEqual(c[0],cal[202])
        self.assertEqual(len(c),4)
        r=run_case(trimmed,c,Policy(),"A0")
        self.assertEqual(r[1]["Equity"].iloc[0],1e8)
        self.assertEqual(r[1]["Số vị thế"].iloc[0],0)
        self.assertEqual(r[3].loc[r[3]["Lệnh"]=="Mua","Ngày"].tolist(),[cal[204]])
    def test_common_rejects_gap(self):
        cal=pd.bdate_range("2024-01-02",periods=210)
        a=bars([-1]*210);a.index=cal
        b=a.drop(cal[205])
        with self.assertRaisesRegex(ValueError,"không đồng nhất"): common_period({"HPG":a,"MBB":b},cal)
    def test_leave_one_out_reallocates(self):
        a=bars([-1,1,1,-1,-1],[25,25,25,25,27],score=80)
        b=bars([-1,1,1,-1,-1],[25,25,25,25,28],score=70)
        p=Policy(max_positions=1)
        full=run_case({"HPG":a,"MBB":b},a.index,p,"A0")
        omit=run_case({"MBB":b},a.index,p,"A0")
        self.assertEqual(full[2]["Mã"].tolist(),["HPG"])
        self.assertEqual(omit[2]["Mã"].tolist(),["MBB"])
        self.assertGreater(omit[0]["Lợi nhuận (%)"],0)

if __name__=="__main__": unittest.main()
