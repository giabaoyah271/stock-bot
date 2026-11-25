import ast
import unittest
from pathlib import Path
from trading_dashboard_core import (
    PAGES,HOME,DETAIL,SCAN,RESEARCH_PAGE,HISTORY_PREFIX,HISTORY_ZERO,HISTORY_SHORT,HISTORY_ERROR,
    watchlist_frame,filter_watchlist,candidate_parameters
)
from universe_u5 import U5

class TradingDashboardTests(unittest.TestCase):
    def test_scope_and_clearance(self):
        d=watchlist_frame()
        self.assertEqual(tuple(d["Mã"]),U5)
        self.assertEqual(len(d),120)
        self.assertEqual((d["Phạm vi KT18"]=="Trong mẫu U5-B").sum(),115)
        self.assertEqual(set(d.loc[d["Phạm vi KT18"]=="Ngoài mẫu","Mã"]),{"CC1","NAB","VBB","DMX","GEL"})
        self.assertTrue((d["Điều kiện mua"]=="Chưa phê duyệt").all())
        self.assertTrue((d["Dữ liệu hiện tại"]=="Chưa kiểm tra").all())
    def test_history_labels(self):
        counts=watchlist_frame()["Dữ liệu hồi cứu"].value_counts()
        self.assertEqual(counts[HISTORY_PREFIX],10)
        self.assertEqual(counts[HISTORY_ZERO],4)
        self.assertEqual(counts[HISTORY_SHORT],2)
        self.assertEqual(counts[HISTORY_ERROR],3)
    def test_search_filters_and_literal_input(self):
        self.assertEqual(filter_watchlist(" hpg ")["Mã"].tolist(),["HPG"])
        self.assertTrue(filter_watchlist(".*").empty)
        self.assertEqual(set(filter_watchlist(statuses=(HISTORY_SHORT,))["Mã"]),{"DMX","GEL"})
        self.assertTrue(filter_watchlist("HPG",statuses=(HISTORY_ERROR,)).empty)
    def test_pages_and_policy(self):
        self.assertEqual(PAGES[0],HOME)
        self.assertEqual(len(set(PAGES)),8)
        self.assertTrue({DETAIL,SCAN,RESEARCH_PAGE}.issubset(PAGES))
        d=candidate_parameters().set_index("Thông số ứng viên")["Thiết lập nghiên cứu"]
        self.assertEqual(d["Vị thế tối đa"],"5")
        self.assertEqual(d["Rủi ro dự kiến/lệnh"],"0.50%")
        self.assertEqual(d["Portfolio Heat ban đầu"],"2.5%")
    def test_read_only_dashboard(self):
        p=Path(__file__).resolve().parents[1]/"trading_dashboard_ui.py"
        tree=ast.parse(p.read_text(encoding="utf-8"))
        calls={n.func.id for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)}
        self.assertTrue({"Market","get_data","simulate_portfolio","size_order"}.isdisjoint(calls))

if __name__=="__main__": unittest.main()
