"""Offline tests; never connects to real Supabase or TCBS."""
import unittest
from unittest.mock import patch
import pandas as pd
import numpy as np
from storage_ds01 import Repository,StorageError,Missing,Conflict,sha,Config
from storage_codec_ds01 import frame_pack,frame_unpack,encode_report,decode_report,encode_single,decode_single
from paper_trading_core import new_account,export_account,import_account,replay
from signal_engine_core import END,history_digest
from full_universe_core import SHA_B
from test_unified_strategy import fixture

class Fake:
    def __init__(self):
        self.objects={};self.heads={};self.versions={};self.uploads=0
        self.fail_commit=False;self.timeout_commit=False;self.race=False
    def head(self,k): return self.heads.get(k,0)
    def version(self,k,v): return self.versions[k,v]
    def download(self,k,d):
        if (k,d) not in self.objects: raise Missing("missing")
        return self.objects[k,d]
    def upload(self,k,d,data):
        self.objects[k,d]=data;self.uploads+=1
    def commit(self,k,v,d,n):
        if self.fail_commit: raise StorageError("offline")
        if self.race: return -1
        if self.head(k)!=v: return -1
        self.versions[k,v+1]={"sha":d,"size_bytes":n}
        self.heads[k]=v+1
        if self.timeout_commit: raise StorageError("timeout")
        return v+1

class StorageTests(unittest.TestCase):
    def setUp(self): self.b=Fake();self.r=Repository(self.b)
    def test_missing(self): self.assertEqual(self.r.load("paper"),(0,None))
    def test_roundtrip_new_repository(self):
        self.assertEqual(self.r.save("reference",b"zip",0),1)
        self.assertEqual(Repository(self.b).load("reference"),(1,b"zip"))
    def test_dedup_idempotent(self):
        self.r.save("reference",b"zip",0)
        self.assertEqual(self.r.save("reference",b"zip",0),1)
        self.assertEqual(self.b.uploads,1)
    def test_checksum_reject(self):
        self.r.save("reference",b"zip",0)
        self.b.objects["reference",sha(b"zip")]=b"bad"
        with self.assertRaises(StorageError): self.r.load("reference")
    def test_race(self):
        self.r.save("paper",b"old",0)
        self.r.save("paper",b"new",1)
        with self.assertRaises(Conflict): self.r.save("paper",b"stale",1)
        self.assertEqual(self.r.load("paper"),(2,b"new"))
    def test_race_after_upload(self):
        self.b.race=True
        with self.assertRaises(Conflict): self.r.save("paper",b"candidate",0)
        self.assertEqual(self.r.load("paper"),(0,None))
    def test_orphan_after_failed_commit(self):
        self.b.fail_commit=True
        with self.assertRaises(StorageError): self.r.save("paper",b"candidate",0)
        self.assertEqual(self.r.load("paper"),(0,None))
        self.b.fail_commit=False
        self.assertEqual(self.r.save("paper",b"candidate",0),1)
        self.assertEqual(self.b.uploads,1)
    def test_timeout_after_commit(self):
        self.b.timeout_commit=True
        self.assertEqual(self.r.save("paper",b"candidate",0),1)
        self.assertEqual(self.r.load("paper"),(1,b"candidate"))
    def test_paper_schema_replay(self):
        now=pd.Timestamp("2026-11-25T18:00:00+07:00")
        a=new_account(now=now)
        self.r.save("paper",export_account(a),0)
        b=import_account(self.r.load("paper")[1],now=now)
        self.assertEqual(a,b)
        self.assertEqual(replay(a),replay(b))
    def test_test_account_rejected(self):
        a=new_account(mode="TEST",now=pd.Timestamp("2026-11-25T18:00:00+07:00"))
        with self.assertRaises(ValueError): import_account(export_account(a))
    def test_config_host_and_namespace(self):
        owner="b6b13111-39ba-43bb-b999-25810aa111aa"
        c=Config("https://abcd.supabase.co","anon","server",owner,"ds01-test")
        self.assertNotIn("server",repr(c))
        with self.assertRaises(StorageError): Config("https://evil.example","anon","server",owner,"ds01-test")
        with self.assertRaises(StorageError): Config("https://abcd.supabase.co","anon","server",owner,"../prod")

def report_fixture():
    d,row=fixture()
    d.index=d.index+pd.offsets.BDay(1)
    d["SMA20"]=np.nan
    d.iloc[0,d.columns.get_loc("open")]=np.nextafter(25.,26.)
    row.update({"Phiên cuối":str(d.index[-1].date()),"SHA lịch sử":history_digest(d),"SHA lịch sử trước phiên":history_digest(d.iloc[:-1])})
    return {"identity":(row["Phiên cuối"],"a"*64,SHA_B,"LIVE"),"rows":{"HPG":row},"charts":{"HPG":d},
            "updated":"2026-11-24T16:00:00+07:00","previous_session":str(END.date()),"previous_index_sha":"b"*64}
class CodecTests(unittest.TestCase):
    def test_report_roundtrip(self):
        r=report_fixture();out=decode_report(encode_report(r))
        self.assertEqual(out["identity"],r["identity"])
        self.assertEqual(out["rows"],r["rows"])
        pd.testing.assert_frame_equal(out["charts"]["HPG"],r["charts"]["HPG"],check_freq=False)
    def test_tamper(self):
        r=report_fixture();r["rows"]["HPG"]["RS60 (đpt)"]=999.
        with self.assertRaises(ValueError): encode_report(r)
    def test_test_mode_rejected(self):
        r=report_fixture();r["identity"]=(*r["identity"][:3],"TEST")
        with self.assertRaises(StorageError): encode_report(r)
    def test_single_roundtrip(self):
        r=report_fixture()
        single={"identity":r["identity"],"row":r["rows"]["HPG"],"frame":r["charts"]["HPG"],"observed_at":r["updated"]}
        out=decode_single(encode_single(single))
        pd.testing.assert_frame_equal(out["frame"],single["frame"],check_freq=False)
    def test_timezone_and_nullable(self):
        d=pd.DataFrame({"f":[np.nan,1.2345678901234567],"i":pd.array([1,pd.NA],dtype="Int64"),"s":["a","b"]},index=pd.date_range("2026-11-24",periods=2,tz="Asia/Ho_Chi_Minh"))
        pd.testing.assert_frame_equal(frame_unpack(frame_pack(d)),d,check_freq=False)
    def test_corrupt_gzip(self):
        with self.assertRaises(StorageError): decode_report(b"not gzip")

class AdapterTests(unittest.TestCase):
    def test_preferences_allowlist(self):
        from storage_ui_ds01 import safe_pref
        self.assertTrue(safe_pref("pt10_detail_tf","Ngày"))
        self.assertFalse(safe_pref("tcbs_otp","1234"))
        self.assertFalse(safe_pref("pt09_scan_confirm",True))
        self.assertFalse(safe_pref("pt10_detail_tf","invalid"))
    def test_paper_failed_save_does_not_replace_session(self):
        import storage_ui_ds01 as ui
        a=new_account()
        with patch.object(ui.st,"session_state",{}),patch.object(ui,"enabled",return_value=True),patch.object(ui,"save",side_effect=StorageError("fail")):
            with self.assertRaises(StorageError): ui.persist_account(a)
            self.assertNotIn(ui.ACCOUNT,ui.st.session_state)
    def test_restore_report_marked_not_fresh(self):
        import storage_ui_ds01 as ui
        b=Fake();r=Repository(b);r.save("scan",encode_report(report_fixture()),0)
        with patch.object(ui.st,"session_state",{ui.REF:b"mock verified"}):
            ui.restore_one(r,"scan")
            self.assertTrue(ui.restored_scan())
            self.assertEqual(ui.versions()["scan"],1)
            self.assertEqual(ui.st.session_state[ui.REPORT]["identity"],report_fixture()["identity"])
    def test_new_session_restores_paper(self):
        import storage_ui_ds01 as ui
        b=Fake();r=Repository(b);a=new_account();r.save("paper",export_account(a),0)
        with patch.object(ui.st,"session_state",{}):
            ui.restore_one(r,"paper")
            self.assertEqual(ui.st.session_state[ui.ACCOUNT],a)
            self.assertEqual(ui.versions()["paper"],1)

if __name__=="__main__": unittest.main()
