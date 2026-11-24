import ast
from pathlib import Path
import unittest
import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal, assert_series_equal
from daily_data_quality import prepare_daily_data, DataQualityError, slice_raw_history
from backtesting import tao_bang_giao_dich

ROOT = Path(__file__).resolve().parents[1]
NOW = pd.Timestamp("2025-11-01 14:00", tz="Asia/Ho_Chi_Minh")

def raw_history(n=240):
    idx = pd.bdate_range(end="2025-10-31", periods=n)
    close = 100.0 + np.arange(n)*0.25
    return pd.DataFrame({"time":idx,"open":close,"high":close+1,
                         "low":close-1,"close":close,"volume":100000.0})

def calculate():
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8-sig"))
    node = next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=="calculate_indicators")
    ns = {"np":np,"pd":pd}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),"app.py","exec"),ns)
    return ns["calculate_indicators"]

class DailyGateTests(unittest.TestCase):
    def test_valid_data_and_no_mutation(self):
        raw=raw_history()
        copy=raw.copy(deep=True)
        out,report=prepare_daily_data(raw,NOW)
        assert_frame_equal(raw,copy)
        self.assertEqual(report["bars"],240)
        self.assertEqual(report["last_date"],"2025-10-31")
        self.assertFalse(report["trimmed"])
        self.assertTrue(out.index.is_monotonic_increasing)
        assert_series_equal(out["close"].reset_index(drop=True),raw["close"])
    def test_cutoff_vietnam_utc(self):
        raw=raw_history()
        raw["time"]=raw["time"].dt.tz_localize("Asia/Ho_Chi_Minh").dt.tz_convert("UTC")
        a,info=prepare_daily_data(raw,"2025-10-31 14:00")
        self.assertTrue(info["trimmed"])
        self.assertEqual(len(a),239)
        b,info=prepare_daily_data(raw,"2025-10-31 15:15")
        self.assertFalse(info["trimmed"])
        self.assertEqual(len(b),240)
    def test_short_history_after_trim(self):
        with self.assertRaises(DataQualityError):
            prepare_daily_data(raw_history(200),"2025-10-31 14:00")
    def test_missing_columns(self):
        with self.assertRaises(DataQualityError):
            prepare_daily_data(raw_history().drop(columns="high"),NOW)
    def test_nan_inf_zero_negative(self):
        for col,val in [("open",np.nan),("high",np.inf),("close",0),("volume",-1),("low",-1)]:
            with self.subTest(col=col,val=val):
                raw=raw_history()
                raw.loc[5,col]=val
                with self.assertRaises(DataQualityError):
                    prepare_daily_data(raw,NOW)
    def test_ohlc_range(self):
        raw=raw_history()
        raw.loc[5,"high"]=raw.loc[5,"close"]-1
        with self.assertRaises(DataQualityError):
            prepare_daily_data(raw,NOW)
    def test_ohlc_error_has_exact_date_and_values(self):
        raw=raw_history()
        raw.loc[5,"high"]=raw.loc[5,"close"]-1
        with self.assertRaises(DataQualityError) as caught:
            prepare_daily_data(raw,NOW)
        msg=str(caught.exception)
        self.assertIn(str(raw.loc[5,"time"].date()),msg)
        self.assertIn("O=",msg)
        self.assertIn("H=",msg)
        self.assertIn("L=",msg)
        self.assertIn("C=",msg)
    def test_frozen_slice_excludes_only_later_bars(self):
        raw=raw_history()
        raw.loc[239,"high"]=0.1
        cutoff=raw.loc[238,"time"].date().isoformat()
        saved=raw.copy(deep=True)
        sliced=slice_raw_history(raw,cutoff)
        assert_frame_equal(sliced,raw.iloc[:239])
        assert_frame_equal(raw,saved)
        self.assertEqual(len(prepare_daily_data(sliced,NOW)[0]),239)
        raw.loc[5,"high"]=0.1
        with self.assertRaises(DataQualityError):
            prepare_daily_data(slice_raw_history(raw,cutoff),NOW)
    def test_duplicate_and_unsorted(self):
        raw=raw_history()
        with self.assertRaises(DataQualityError):
            prepare_daily_data(raw.iloc[::-1],NOW)
        raw.loc[5,"time"]=raw.loc[4,"time"]
        with self.assertRaises(DataQualityError):
            prepare_daily_data(raw,NOW)
    def test_duplicate_local_day(self):
        raw=raw_history()
        raw.loc[5,"time"]=raw.loc[4,"time"]+pd.Timedelta(hours=1)
        with self.assertRaises(DataQualityError):
            prepare_daily_data(raw,NOW)
    def test_future_and_nat(self):
        raw=raw_history()
        raw.loc[239,"time"]=pd.Timestamp("2025-11-03")
        with self.assertRaises(DataQualityError):
            prepare_daily_data(raw,NOW)
        raw.loc[239,"time"]=pd.NaT
        with self.assertRaises(DataQualityError):
            prepare_daily_data(raw,NOW)
    def test_zero_volume_warning_not_rejection(self):
        raw=raw_history()
        raw.loc[5,"volume"]=0
        out,info=prepare_daily_data(raw,NOW)
        self.assertEqual(info["zero_volume"],1)
        self.assertEqual(out["volume"].iloc[5],0)
    def test_numeric_strings_no_price_changes(self):
        raw=raw_history()
        raw["open"]=raw["open"].astype(str)
        out,_=prepare_daily_data(raw,NOW)
        np.testing.assert_allclose(out["open"],raw["close"])

class LoaderIntegrationTests(unittest.TestCase):
    def loader(self, raw):
        from datetime import datetime
        from types import SimpleNamespace
        from unittest.mock import Mock
        tree=ast.parse((ROOT / "app.py").read_text(encoding="utf-8-sig"))
        node=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=="get_data")
        node.decorator_list=[]
        indicator=Mock(side_effect=lambda df, **kw: df)
        st=SimpleNamespace(warning=Mock())
        def market(src):
            return SimpleNamespace(equity=lambda symbol: SimpleNamespace(ohlcv=lambda **kw:raw.copy()))
        ns={"pd":pd,"datetime":datetime,"Market":market,"st":st,
            "TF_MAP":{"Ngày":"1D","1 Giờ":"1H","Tuần":"1W"},"calculate_indicators":indicator}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),"app.py","exec"),ns)
        return ns["get_data"],indicator,st
    def test_invalid_daily_is_blocked_before_indicators(self):
        raw=raw_history()
        raw.loc[5,"high"]=0
        loader,indicator,st=self.loader(raw)
        self.assertTrue(loader("HPG","Ngày").empty)
        indicator.assert_not_called()
        st.warning.assert_called_once()
    def test_kt15_cutoff_before_indicators(self):
        raw=raw_history()
        raw.loc[239,"high"]=0.1
        loader,indicator,st=self.loader(raw)
        out=loader("ACV","Ngày",history_end=str(raw.loc[238,"time"].date()))
        self.assertEqual(len(out),239)
        indicator.assert_called_once()
        st.warning.assert_not_called()
        raw.loc[5,"high"]=0.1
        loader,indicator,st=self.loader(raw)
        out=loader("ACV","Ngày",history_end=str(raw.loc[238,"time"].date()))
        self.assertTrue(out.empty)
        self.assertIn(str(raw.loc[5,"time"].date()),out.attrs["daily_quality_error"])
        indicator.assert_not_called()
    def test_valid_daily_passes_gate_and_records_stop(self):
        loader,indicator,st=self.loader(raw_history())
        out=loader("HPG","Ngày")
        self.assertEqual(len(out),240)
        self.assertEqual(indicator.call_args.kwargs,{"record_stop":True})
        self.assertEqual(out.attrs["daily_quality"]["bars"],240)
        st.warning.assert_not_called()
    def test_hour_and_week_use_original_loader(self):
        loader,indicator,st=self.loader(raw_history(10))
        for tf in ("1 Giờ","Tuần"):
            out=loader("HPG",tf)
            self.assertEqual(len(out),10)
            self.assertEqual(indicator.call_args.kwargs,{})
            self.assertNotIn("daily_quality",out.attrs)

class StopTraceTests(unittest.TestCase):
    def history(self):
        raw=raw_history(300)
        # Rising segment, pullback and decline to exercise signal exit.
        close=raw["close"].to_numpy().copy()
        close[260:]=close[259]-np.arange(1,41)*0.8
        raw["open"]=close
        raw["close"]=close
        raw["high"]=close+1
        raw["low"]=close-1
        return prepare_daily_data(raw,NOW)[0]
    def test_original_outputs_and_ledger_identical(self):
        calc=calculate()
        hist=self.history()
        old=calc(hist.copy())
        new=calc(hist.copy(),record_stop=True)
        assert_frame_equal(old,new[old.columns])
        assert_frame_equal(tao_bang_giao_dich(old),tao_bang_giao_dich(new))
        self.assertNotIn("V1_Trailing_Stop",old)
        self.assertTrue((new["Trend"]==1).any())
    def test_stop_exact_running_max_and_reset(self):
        out=calculate()(self.history(),record_stop=True)
        entry=None
        running=None
        count=0
        for i,row in enumerate(out.itertuples()):
            if row.Trend==1:
                candidate=row.close-2*row.ATR
                if entry is None:
                    entry=i
                    running=candidate
                else:
                    running=max(running,candidate)
                self.assertAlmostEqual(row.V1_Trailing_Stop,running)
                self.assertEqual(row.V1_Stop_Age,i-entry)
                self.assertEqual(row.V1_Stop_Eligible,i-entry>=3)
                self.assertTrue(pd.isna(row.V1_Stop_Exit))
                count+=1
            else:
                if entry is not None and str(row.Reason).startswith("Thoát do Trailing Stop"):
                    self.assertAlmostEqual(row.V1_Stop_Exit,max(running,row.close-2*row.ATR))
                else:
                    self.assertTrue(pd.isna(row.V1_Stop_Exit))
                self.assertTrue(pd.isna(row.V1_Trailing_Stop))
                self.assertFalse(row.V1_Stop_Eligible)
                entry=running=None
        self.assertGreater(count,3)
    def test_stop_prefix_causal(self):
        calc=calculate()
        hist=self.history()
        full=calc(hist.copy(),record_stop=True)
        partial=calc(hist.iloc[:255].copy(),record_stop=True)
        assert_frame_equal(partial,full.iloc[:255])
    def test_short_history_does_not_generate_signals(self):
        calc=calculate()
        short=raw_history(100).set_index("time")
        out=calc(short.copy(),record_stop=True)
        self.assertNotIn("Trend",out)

if __name__=="__main__":
    unittest.main()
