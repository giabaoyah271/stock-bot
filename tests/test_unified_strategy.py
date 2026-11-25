import unittest
import copy
import pandas as pd
from signal_engine_core import history_digest,state,END
from unified_strategy_core import validate_chart,resolve_daily,reference_stop,transition_history,supplemental
from full_universe_core import SHA_B
from workspace_acceptance import run_workspace_acceptance

def fixture():
    ix=pd.bdate_range(end=END,periods=250,name="Ngày")
    d=pd.DataFrame({"open":25.,"high":26.,"low":24.,"close":25.,"volume":1000.,"ATR":.75,
                    "Buy_Pct":70.,"Sell_Pct":10.,"Trend":-1,"Reason":"","RS60 (đpt)":4.,"GTGD proxy 20 (VND)":25e6},index=ix)
    d.loc[ix[-1],"Trend"]=1
    row={"Mã":"HPG","Kỹ thuật":"Khớp mẫu KT18","Phiên cuối":str(END.date()),"Trend trước":-1,"Trend":1,
         "Tín hiệu":state(-1,1),"Lý do":"","Open (nghìn VND)":25.,"Close (nghìn VND)":25.,"ATR (nghìn VND)":.75,
         "Buy Score (%)":70.,"Sell Score (%)":10.,"RS60 (đpt)":4.,"GTGD proxy 20 (VND)":25e6,
         "SHA lịch sử":history_digest(d),"SHA lịch sử trước phiên":history_digest(d.iloc[:-1])}
    return d,row

class UnifiedTests(unittest.TestCase):
    def test_shared_snapshot(self):
        d,row=fixture()
        report={"identity":(str(END.date()),"x"*64,SHA_B,"LIVE"),"rows":{"HPG":row},"charts":{"HPG":d}}
        f,r,source,rank=resolve_daily(report,"HPG")
        self.assertIs(f,d);self.assertIs(r,row);self.assertEqual(rank,1)
        self.assertEqual(reference_stop(d),23.5)
        self.assertEqual(transition_history(d).index.tolist(),[d.index[-1]])
    def test_fail_closed(self):
        d,row=fixture()
        for k,value in (("Trend", -1),("RS60 (đpt)",5.),("SHA lịch sử","wrong"),("Phiên cuối","2026-11-24")):
            bad={**row,k:value}
            with self.assertRaises(ValueError): validate_chart("HPG",d,bad,str(END.date()))
        other=d.copy();other.iloc[0,other.columns.get_loc("close")]=24.
        with self.assertRaises(ValueError): validate_chart("HPG",other,row,str(END.date()))
        report={"identity":(str(END.date()),"x"*64,SHA_B,"LIVE"),"rows":{"HPG":{"Kỹ thuật":"Chưa đạt"}}}
        single={"identity":report["identity"],"row":row,"frame":d}
        with self.assertRaises(ValueError): resolve_daily(report,"HPG",single)
    def test_auxiliary_no_signals(self):
        d,row=fixture();d["V1_Trailing_Stop"]=23.;d["KT03_Trailing"]=22.
        a=supplemental(d)
        self.assertTrue({"Trend","Reason","Buy_Pct","Sell_Pct","V1_Trailing_Stop","KT03_Trailing","RS60 (đpt)"}.isdisjoint(a.columns))
        self.assertIn("ATR",a)
    def test_standalone_no_rank_and_identity_conflict(self):
        d,row=fixture();identity=(str(END.date()),"x"*64,SHA_B,"LIVE")
        single={"identity":identity,"row":row,"frame":d}
        self.assertTrue(pd.isna(resolve_daily(None,"HPG",single)[3]))
        report={"identity":(str(END.date()),"y"*64,SHA_B,"LIVE"),"rows":{}}
        with self.assertRaises(ValueError): resolve_daily(report,"HPG",single)
    def test_previous_acceptance(self):
        self.assertEqual(len(run_workspace_acceptance()["checks"]),21)
if __name__=="__main__": unittest.main()
