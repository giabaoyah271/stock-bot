"""Offline UI regression tests. Runtime tests use synthetic fixtures only."""
import ast
from pathlib import Path
import subprocess
import unittest
import importlib.util
from unittest.mock import patch
from types import ModuleType, SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
BASE="21a3db9f32129daac5cf2060aa166e915d56d7e8"

class TerminalSourceTests(unittest.TestCase):
    def test_python_syntax(self):
        for name in ("app.py","terminal_ui.py","multi_backtest_ui.py"):
            ast.parse((ROOT/name).read_text(encoding="utf-8"))

    def test_indicator_and_data_source_unchanged(self):
        try:
            before=subprocess.check_output(["git","show",BASE+":app.py"],cwd=ROOT,stderr=subprocess.DEVNULL).decode("utf-8-sig")
        except (OSError,subprocess.CalledProcessError):
            self.skipTest("Baseline commit not available in local Git history")
        after=(ROOT/"app.py").read_text(encoding="utf-8-sig")
        def core(s):
            s=s.replace("\r\n","\n")
            return s[s.index("# --- 2. HÀM LẤY TOP 100"):s.index("# --- 5. GIAO DIỆN CHÍNH")].rstrip()
        self.assertEqual(core(before),core(after))
        self.assertIn('TF_MAP = {"1 Giờ": "1H", "Ngày": "1D", "Tuần": "1W"}',after)
        for name in ("backtesting.py","scoring_v2.py","v21_macd_strategy.py","strategy_experiments.py","risk_equity.py","risk_batch.py","walk_forward_core.py","multi_backtest_core.py","performance_metrics.py"):
            original=subprocess.check_output(["git","show",BASE+":"+name],cwd=ROOT)
            self.assertEqual(original,(ROOT/name).read_bytes(),name)

    def test_routes(self):
        source=(ROOT/"terminal_ui.py").read_text(encoding="utf-8")
        tree=ast.parse(source)
        names={n.name for n in tree.body if isinstance(n,ast.FunctionDef)}
        self.assertTrue({"render_trading","render_scanner","render_research","render_system"}.issubset(names))
        self.assertIn("time.sleep(1.1)",source)
        self.assertIn("elif days_old > 5:",source)

@unittest.skipUnless(importlib.util.find_spec("streamlit"),"Streamlit runtime not installed")
class TerminalRuntimeTests(unittest.TestCase):
    def test_full_app_navigation_offline(self):
        import numpy as np
        import pandas as pd
        from streamlit.testing.v1 import AppTest
        i=np.arange(300,dtype=float)
        close=90+.05*i+5*np.sin(i/8)+1.2*np.cos(i/3)
        opening=close*(1+.003*np.sin(i/4))
        frame=pd.DataFrame({"time":pd.bdate_range("2024-01-02",periods=300),"open":opening,"close":close,
             "high":np.maximum(close,opening)*1.012,"low":np.minimum(close,opening)*.988,"volume":200000+15000*(i%11)})
        fake=ModuleType("vnstock")
        fake.Market=lambda src: SimpleNamespace(equity=lambda symbol:SimpleNamespace(ohlcv=lambda **kw:frame.copy()))
        fake.sources=SimpleNamespace(authenticate=lambda *args,**kwargs:None)
        with patch.dict("sys.modules",{"vnstock":fake}):
            at=AppTest.from_file(str(ROOT/"app.py"),default_timeout=30).run()
            self.assertEqual(len(at.exception),0)
            self.assertEqual(at.radio(key="terminal_page").value,"Giao dịch")
            self.assertGreaterEqual(len(at.metric),3)
            at.text_input(key="terminal_symbol_input").set_value("MBB").run()
            self.assertEqual(len(at.exception),0)
            at.radio(key="terminal_tf_input").set_value("1 Giờ").run()
            self.assertEqual(len(at.exception),0)
            at.radio(key="terminal_page").set_value("Quét tín hiệu").run()
            self.assertEqual(len(at.exception),0)
            self.assertEqual(at.radio(key="terminal_tf_input").value,"1 Giờ")
            at.radio(key="terminal_page").set_value("Nghiên cứu").run()
            self.assertEqual(len(at.exception),0)
            at.radio(key="terminal_page").set_value("Hệ thống").run()
            self.assertEqual(len(at.exception),0)
            at.radio(key="terminal_page").set_value("Giao dịch").run()
            self.assertEqual(len(at.exception),0)
            self.assertEqual(at.text_input(key="terminal_symbol_input").value,"MBB")

    def test_scanner_filters_do_not_call_loader(self):
        from streamlit.testing.v1 import AppTest
        code="""
import streamlit as st
import pandas as pd
from terminal_ui import shell, render_scanner
def load(symbol,tf):
    st.session_state["calls"]=st.session_state.get("calls",0)+1
    return pd.DataFrame({"Trend":[-1,1],"Buy_Pct":[10,80],"Sell_Pct":[80,10],"Reason":["a","b"],
        "ATR":[1,1],"close":[20,21],"open":[20,20],"high":[21,22],"low":[19,19],
        "volume":[1000,2000],"SMA20":[20,20],"RSI":[40,60]},index=pd.date_range("2025-01-01",periods=2))
page,_=shell()
render_scanner(load,["HPG","MBB"])
"""
        at=AppTest.from_string(code,default_timeout=30).run()
        self.assertEqual(len(at.exception),0)
        next(b for b in at.button if b.label=="Bắt đầu quét").click().run()
        self.assertEqual(len(at.exception),0)
        self.assertEqual(at.session_state["calls"],2)
        at.text_input(key="terminal_scan_search").set_value("HPG").run()
        self.assertEqual(len(at.exception),0)
        self.assertEqual(at.session_state["calls"],2)
        at.radio(key="terminal_scan_filter").set_value("Vùng Xanh").run()
        self.assertEqual(at.session_state["calls"],2)
        at.selectbox(key="terminal_scan_sort").set_value("Điểm mua giảm dần").run()
        self.assertEqual(at.session_state["calls"],2)
        self.assertEqual(len(at.exception),0)

if __name__=="__main__":
    unittest.main()
