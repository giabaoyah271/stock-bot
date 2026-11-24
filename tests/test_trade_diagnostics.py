import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from backtesting import tao_bang_giao_dich
from strategy_policy import RESEARCH
from trade_diagnostics import (
    diagnose_ledger, evaluate_trade_case, completed_daily_history, MAE, MFE, NET_MFE,
    GIVEBACK, RETURN, HOLD, EARLY, BUY_DATE, SELL_DATE, BUY_SIGNAL, SELL_SIGNAL,
)

def fixture():
    df = pd.DataFrame({
        "open":[100,100,100,100,95,100],
        "high":[100,101,110,105,999,100],
        "low":[100,99,94,92,1,100],
        "close":[100,100,105,95,95,100],
        "volume":[100]*6, "Trend":[-1,1,1,-1,-1,-1],
        "ATR":[2]*6,"RSI":[10,55,90,20,30,40],"Reason":[""]*6,
    },index=pd.date_range("2024-01-01",periods=6))
    return df

class TradeDiagnosticsTests(unittest.TestCase):
    def test_sell_day_only_open_and_signal_day_excluded(self):
        df = fixture()
        ledger = tao_bang_giao_dich(df)
        rows = diagnose_ledger("HPG", RESEARCH[0],df,ledger)
        r=rows.iloc[0]
        self.assertAlmostEqual(r[MAE],-8)
        self.assertAlmostEqual(r[MFE],10)
        self.assertAlmostEqual(r[EARLY],-8)
        self.assertEqual(r[HOLD],2)
        self.assertEqual(r["RSI tín hiệu mua"],55)
        self.assertEqual(r["Ngày MFE"],df.index[2])
        self.assertEqual(r["Ngày MAE"],df.index[3])
        self.assertEqual(r[RETURN],ledger.iloc[0][RETURN])
        self.assertGreater(r[NET_MFE],9)
        self.assertGreater(r[GIVEBACK],14)
    def test_sell_open_gap_counts_not_sell_high_low(self):
        df=fixture()
        df.loc[df.index[4],["open","close"]]=[70,70]
        r=diagnose_ledger("HPG",RESEARCH[0],df,tao_bang_giao_dich(df)).iloc[0]
        self.assertAlmostEqual(r[MAE],-30)
        self.assertAlmostEqual(r[MFE],10)
        self.assertEqual(r["Ngày MAE"],df.index[4])
    def test_exit_gap_up_is_favorable_extreme(self):
        df=fixture()
        df.loc[df.index[4],["open","close"]]=[125,125]
        r=diagnose_ledger("HPG",RESEARCH[0],df,tao_bang_giao_dich(df)).iloc[0]
        self.assertAlmostEqual(r[MFE],25)
        self.assertAlmostEqual(r[GIVEBACK],0)
        self.assertEqual(r["Phiên đến MFE (0 = phiên mua)"],2)
    def test_net_mfe_can_be_negative_when_gross_zero(self):
        df=fixture()
        df.loc[df.index[2:4],["open","high","low","close"]]=100
        df.loc[df.index[4],["open","close"]]=[95,95]
        r=diagnose_ledger("HPG",RESEARCH[0],df,tao_bang_giao_dich(df)).iloc[0]
        self.assertAlmostEqual(r[MFE],0)
        self.assertLess(r[NET_MFE],0)
    def test_open_position_not_fabricated(self):
        df=fixture()
        df["Trend"]=[-1,1,1,1,1,1]
        ledger=tao_bang_giao_dich(df)
        out=diagnose_ledger("HPG",RESEARCH[0],df,ledger)
        self.assertTrue(out.empty)
        self.assertIn(MFE,out.columns)
    def test_input_immutable(self):
        df=fixture()
        ledger=tao_bang_giao_dich(df)
        a,b=df.copy(deep=True),ledger.copy(deep=True)
        diagnose_ledger("HPG",RESEARCH[0],df,ledger)
        assert_frame_equal(df,a)
        assert_frame_equal(ledger,b)
    def test_future_data_does_not_change_closed_diagnostic(self):
        df=fixture()
        original=diagnose_ledger("HPG",RESEARCH[0],df,tao_bang_giao_dich(df))
        df.loc[df.index[-1],["open","high","low","close"]]=[400,500,300,400]
        result=diagnose_ledger("HPG",RESEARCH[0],df,tao_bang_giao_dich(df))
        assert_frame_equal(original,result)
    def test_bad_ohlc_rejected(self):
        df=fixture()
        ledger=tao_bang_giao_dich(df)
        df.loc[df.index[2],"low"]=200
        with self.assertRaises(ValueError):
            diagnose_ledger("HPG",RESEARCH[0],df,ledger)
    def test_nonfinite_ohlc_rejected(self):
        df=fixture()
        ledger=tao_bang_giao_dich(df)
        df.loc[df.index[2],"volume"]=np.inf
        with self.assertRaises(ValueError):
            diagnose_ledger("HPG",RESEARCH[0],df,ledger)
    def test_bad_ledger_price_rejected(self):
        df=fixture()
        ledger=tao_bang_giao_dich(df)
        ledger.loc[0,"Giá mua mô phỏng"]=1
        with self.assertRaises(ValueError):
            diagnose_ledger("HPG",RESEARCH[0],df,ledger)
    def test_bad_execution_order_rejected(self):
        df=fixture()
        ledger=tao_bang_giao_dich(df)
        ledger.loc[0,BUY_DATE]=df.index[1]
        with self.assertRaises(ValueError):
            diagnose_ledger("HPG",RESEARCH[0],df,ledger)
    def test_trim_uses_vietnam_time(self):
        df=fixture()
        df.index=df.index.tz_localize("Asia/Ho_Chi_Minh").tz_convert("UTC")
        now=pd.Timestamp("2024-01-06 11:00",tz="Asia/Ho_Chi_Minh")
        out,trimmed=completed_daily_history(df,now)
        self.assertTrue(trimmed)
        self.assertEqual(len(out),len(df)-1)
        out,trimmed=completed_daily_history(df,pd.Timestamp("2024-01-06 15:15",tz="Asia/Ho_Chi_Minh"))
        self.assertFalse(trimmed)
        self.assertEqual(len(out),len(df))
    def test_filtered_case_calls_original_runner(self):
        df=fixture()
        df=pd.concat([df]*34,ignore_index=True)
        df.index=pd.date_range("2024-01-01",periods=len(df))
        ledger=tao_bang_giao_dich(df)
        with patch("trade_diagnostics.chay_backtest_thu_nghiem",return_value=ledger) as runner:
            details,summary=evaluate_trade_case("HPG",df,RESEARCH[1])
            self.assertEqual(len(details),len(ledger))
            self.assertEqual(summary["Số lệnh"],len(ledger))
            self.assertEqual(runner.call_args.args[1],"sma")
        with self.assertRaises(ValueError):
            evaluate_trade_case("HPG",df,"Chấm điểm V2")

if __name__=="__main__":
    unittest.main()
