import ast
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class FrozenIndicatorTests(unittest.TestCase):
    def test_same_indicator_ast(self):
        def node(path):
            tree=ast.parse((ROOT/path).read_text(encoding="utf-8-sig"))
            return next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="calculate_indicators")
        self.assertEqual(ast.dump(node("app.py"),include_attributes=False),ast.dump(node("research_indicators.py"),include_attributes=False))
if __name__=="__main__": unittest.main()
