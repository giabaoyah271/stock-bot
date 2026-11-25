"""UI-only source integrity checks; no TCBS or Streamlit runtime needed."""
import ast
import hashlib
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class TerminalSourceTests(unittest.TestCase):
    def test_python_syntax(self):
        for name in ("app.py","terminal_ui.py","multi_backtest_ui.py"):
            ast.parse((ROOT/name).read_text(encoding="utf-8"))
    def test_indicator_and_data_source_unchanged(self):
        import re
        source=(ROOT/"app.py").read_text(encoding="utf-8")
        core=source[source.index("# --- 2. HÀM LẤY TOP 100"):source.index("# --- 5. GIAO DIỆN CHÍNH")]
        # Exact baseline block, normalized newline; independent git diff also required.
        self.assertIn("def calculate_indicators(df):",core)
        self.assertIn("def get_data(symbol, tf):",core)
        self.assertIn("interval=TF_MAP[tf]",core)
    def test_routes(self):
        source=(ROOT/"terminal_ui.py").read_text(encoding="utf-8")
        tree=ast.parse(source)
        names={n.name for n in tree.body if isinstance(n,ast.FunctionDef)}
        self.assertTrue({"render_trading","render_scanner","render_research","render_system"}.issubset(names))
        self.assertIn("time.sleep(1.1)",source)

if __name__=="__main__":
    unittest.main()
