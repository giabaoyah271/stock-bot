"""V3 UI integration checks. Frozen strategy and operational modules stay unchanged."""
import ast
import importlib.util
from pathlib import Path
import subprocess
import unittest
from types import ModuleType
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
BASE="f1cd923b9ae2ae87000f1d2af3932ec00c375e52"
UI_FILES={"multi_backtest_ui.py","app.py","workspace_ui.py","workspace_detail_ui.py","workspace_portfolio_ui.py","workspace_advanced_ui.py","terminal_v3_ui.py"}

class TerminalV3Integrity(unittest.TestCase):
    def test_ui_syntax(self):
        for p in UI_FILES:
            ast.parse((ROOT/p).read_text(encoding="utf-8-sig"))

    def test_frozen_source(self):
        def git(*args):
            return subprocess.check_output(["git",*args],cwd=ROOT)
        try:
            files=git("ls-tree","-r","--name-only",BASE).decode().splitlines()
        except (OSError,subprocess.CalledProcessError):
            self.skipTest("Baseline Git history unavailable")
        for name in files:
            if name.endswith(".py") and name not in UI_FILES:
                self.assertEqual(git("show",BASE+":"+name),(ROOT/name).read_bytes(),name)
        before=git("show",BASE+":app.py").decode("utf-8-sig").replace("\r\n","\n")
        after=(ROOT/"app.py").read_text(encoding="utf-8-sig")
        start="# --- 2. HÀM LẤY TOP 100"
        end="# --- 5. GIAO DIỆN CHÍNH"
        def core(s):
            return s[s.index(start):s.index(end)]
        self.assertEqual(core(before),core(after))
        marker="elif mode == DETAIL:"
        self.assertEqual(before[before.index(marker):],after[after.index(marker):])
        for name in ("build_report","record_preview","resolve_daily","single_snapshot","reference_stop"):
            self.assertTrue(any(name in (ROOT/p).read_text(encoding="utf-8") for p in UI_FILES))
        self.assertIn("elif days_old>5:",(ROOT/"workspace_detail_ui.py").read_text(encoding="utf-8"))
        self.assertEqual(git("show",BASE+":requirements.txt"),(ROOT/"requirements.txt").read_bytes())
        previous=git("show",BASE+":multi_backtest_ui.py").decode("utf-8-sig").replace("\r\n","\n")
        current=(ROOT/"multi_backtest_ui.py").read_text(encoding="utf-8-sig")
        anchor="    st.caption(RESEARCH_NOTE)"
        self.assertEqual(previous[previous.index(anchor):],current[current.index(anchor):])
        def imported_renderers(s):
            return sorted((n.module,a.name) for n in ast.walk(ast.parse(s)) if isinstance(n,ast.ImportFrom) for a in n.names if a.name.startswith("render_"))
        self.assertEqual(imported_renderers(previous),imported_renderers(current))

@unittest.skipUnless(importlib.util.find_spec("streamlit"),"Streamlit not installed")
class TerminalV3Navigation(unittest.TestCase):
    def test_menu_mapping(self):
        from terminal_v3_ui import MENU,menu_for_page,page_for_menu,RESEARCH_IDS,SYSTEM_IDS
        from workspace_core import PAGES,ADVANCED
        for i in range(4):
            self.assertEqual(page_for_menu(MENU[i],PAGES),PAGES[i])
            self.assertEqual(menu_for_page(PAGES[i],PAGES,MENU[5]),MENU[i])
        self.assertEqual(page_for_menu(MENU[4],PAGES),PAGES[4])
        self.assertEqual(menu_for_page(PAGES[4],PAGES,MENU[4]),MENU[4])
        self.assertEqual(sorted(RESEARCH_IDS+SYSTEM_IDS),list(range(len(ADVANCED))))

    def test_offline_navigation(self):
        from streamlit.testing.v1 import AppTest
        fake=ModuleType("vnstock")
        def no_api(*args,**kw):
            raise AssertionError("unexpected market call")
        fake.Market=no_api
        fake.sources=object()
        with patch.dict("sys.modules",{"vnstock":fake}):
            at=AppTest.from_file(str(ROOT/"app.py"),default_timeout=30).run()
            self.assertEqual(len(at.exception),0)
            self.assertEqual(at.radio(key="v3_terminal_menu").value,"Tổng quan")
            next(b for b in at.button if b.label=="Mở bộ quét cơ hội").click().run()
            self.assertEqual(len(at.exception),0)
            self.assertEqual(at.radio(key="v3_terminal_menu").value,"Cơ hội giao dịch")
            self.assertTrue(at.button(key="pt09_scan").disabled)
            for name in ("Phân tích cổ phiếu","Danh mục","Hệ thống","Nghiên cứu","Tổng quan"):
                at.radio(key="v3_terminal_menu").set_value(name).run()
                self.assertEqual(len(at.exception),0,name)

if __name__=="__main__":
    unittest.main()
