"""Independent deterministic checks for historical window slicing.

Run: python -m unittest discover -s tests -p 'test_*.py' -v
"""
import sys
import unittest
from unittest.mock import patch
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from walk_forward_core import (
    half_year_windows, evaluate_windows_from_curve, evaluate_walk_forward_case,
    _closed_metrics, _realized_sales, _validate_curve,
)


def mk(dates, actions, equity, cash, shares):
    frame = pd.DataFrame({
        "Equity": equity, "Tiền mặt": cash,
        "Số cổ phiếu quy ước": shares, "Trạng thái": actions,
    }, index=pd.to_datetime(dates))
    frame["Drawdown (%)"] = (frame["Equity"] / frame["Equity"].cummax() - 1) * 100
    return frame


def sample():
    # Two sales, one from a position purchased in WF1 and sold in WF2;
    # the second is bought in WF3 and sold in WF4. Selling changes only cash.
    return mk(
        ["2023-12-29", "2024-01-02", "2024-06-27", "2024-07-01",
         "2024-07-02", "2024-12-30", "2025-01-02", "2025-07-01", "2025-07-02"],
        ["Giữ tiền mặt", "Mua tại mở cửa", "Đang nắm giữ", "Đang nắm giữ",
         "Bán tại mở cửa", "Giữ tiền mặt", "Mua tại mở cửa", "Bán tại mở cửa", "Giữ tiền mặt"],
        [100., 100., 120., 118., 125., 125., 125., 100., 100.],
        [100., 0., 0., 0., 125., 125., 0., 100., 100.],
        [0., 1., 1., 1., 0., 0., 1., 0., 0.],
    )


class WalkForwardTests(unittest.TestCase):
    def setUp(self):
        self.curve = sample()
        self.rows, self.summary, self.missing, self.sales = evaluate_windows_from_curve(
            self.curve, "HPG", "Chiến lược gốc")
        self.by = {r["Cửa sổ"]: r for r in self.rows}

    def test_01_6_windows_for_2026_november(self):
        w = half_year_windows("2026-11-23")
        self.assertEqual(len(w), 6)
        self.assertEqual(w[-1].end, pd.Timestamp("2026-11-23"))

    def test_02_no_windows_before_2024(self):
        self.assertEqual(half_year_windows("2023-12-29"), [])

    def test_03_first_window_includes_first_session_movement(self):
        self.assertEqual(self.by["WF1"]["Lợi nhuận cửa sổ (%)"], 20.)
        self.assertEqual(self.by["WF1"]["Equity tại ranh giới đầu"], 100.)
        self.assertEqual(self.by["WF1"]["Phiên đầu có dữ liệu"], "02/01/2024")

    def test_04_window_second_uses_prior_close_not_fresh_100(self):
        self.assertEqual(self.by["WF2"]["Equity tại ranh giới đầu"], 120.)
        self.assertEqual(self.by["WF2"]["Lợi nhuận cửa sổ (%)"], 4.17)

    def test_05_local_drawdown_includes_base_before_first_session(self):
        self.assertEqual(self.by["WF2"]["Max Drawdown cục bộ (%)"], -1.67)

    def test_06_closed_trade_allocated_by_sell_execution_session(self):
        self.assertEqual(self.by["WF1"]["Số lệnh đóng"], 0)
        self.assertEqual(self.by["WF2"]["Số lệnh đóng"], 1)
        self.assertEqual(self.by["WF2"]["Lệnh đóng có ngày mua trước cửa sổ"], 1)
        self.assertEqual(self.by["WF4"]["Lệnh đóng có ngày mua trước cửa sổ"], 1)
        self.assertEqual(len(self.sales), 2)

    def test_07_open_position_at_boundary_is_carried(self):
        self.assertEqual(self.by["WF1"]["Trạng thái cuối cửa sổ"], "Đang nắm giữ")
        self.assertEqual(self.by["WF3"]["Trạng thái cuối cửa sổ"], "Đang nắm giữ")
        self.assertEqual(self.by["WF2"]["Trạng thái cuối cửa sổ"], "Tiền mặt")

    def test_08_profit_factor_uses_real_monetary_gain_and_loss(self):
        self.assertEqual(self.by["WF2"]["Profit Factor (theo tiền)"], None)
        self.assertEqual(self.by["WF4"]["Profit Factor (theo tiền)"], 0.)
        self.assertEqual(_closed_metrics(self.sales)["Profit Factor (theo tiền)"], 1.0)

    def test_09_no_closed_trades_undefined_pf_and_winrate(self):
        self.assertIsNone(self.by["WF1"]["Win Rate (%)"])
        self.assertIsNone(self.by["WF1"]["Profit Factor (theo tiền)"])

    def test_10_global_cumulative_does_not_reset(self):
        self.assertEqual(self.summary["Lợi nhuận giai đoạn đánh giá (%)"], 0)
        self.assertEqual(self.summary["Lợi nhuận TOÀN lịch sử (%)"], 0)
        self.assertEqual(self.summary["Đối chiếu Equity qua cửa sổ"], "ĐẠT")

    def test_11_flat_after_sale_does_not_lose_more_on_price_crash(self):
        c = self.curve.copy()
        c.loc[pd.Timestamp("2025-07-03")] = [100., 100., 0., "Giữ tiền mặt", -20.]
        rows, summary, _, _ = evaluate_windows_from_curve(c.sort_index(), "HPG", "Chiến lược gốc")
        self.assertEqual(summary["Lợi nhuận TOÀN lịch sử (%)"], 0.)
        self.assertEqual(rows[-1]["Lợi nhuận cửa sổ (%)"], -20.)

    def test_12_window_empty_but_no_fake_trade(self):
        c = self.curve.loc[pd.to_datetime(["2023-12-29", "2024-01-02", "2025-01-02"])].copy()
        c["Trạng thái"] = ["Giữ tiền mặt", "Giữ tiền mặt", "Giữ tiền mặt"]
        c["Equity"] = 100.
        c["Tiền mặt"] = 100.
        c["Số cổ phiếu quy ước"] = 0.
        c["Drawdown (%)"] = 0.
        rows, summary, missing, trades = evaluate_windows_from_curve(c, "HPG", "Chiến lược gốc")
        self.assertTrue(any(e["Cửa sổ"] == "WF2" for e in missing))
        self.assertEqual(len(trades), 0)
        self.assertEqual(summary["Lợi nhuận giai đoạn đánh giá (%)"], 0.)

    def test_13_no_trade_all_cash_window_return_zero(self):
        c = mk(["2023-12-29", "2024-01-02", "2024-07-01"],
               ["Giữ tiền mặt"] * 3, [100] * 3, [100] * 3, [0] * 3)
        rows, summary, _, _ = evaluate_windows_from_curve(c, "FPT", "Chiến lược gốc")
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row["Lợi nhuận cửa sổ (%)"] == 0 for row in rows))
        self.assertEqual(summary["Số lệnh đóng TOÀN lịch sử"], 0)

    def test_14_no_future_data_contaminates_prior_windows(self):
        c = self.curve.copy()
        c.loc[pd.Timestamp("2026-01-02")] = [100., 100., 0., "Giữ tiền mặt", -20.]
        rows, _, _, _ = evaluate_windows_from_curve(c.sort_index(), "HPG", "Chiến lược gốc")
        self.assertEqual(self.by["WF1"], rows[0])
        self.assertEqual(self.by["WF2"], rows[1])

    def test_15_drawdown_must_match_full_history_equity(self):
        c = self.curve.copy()
        c.iloc[4, c.columns.get_loc("Drawdown (%)")] = -100.
        with self.assertRaises(ValueError):
            _validate_curve(c)

    def test_16_sale_without_purchase_is_rejected(self):
        c = mk(["2024-01-02", "2024-07-01"], ["Bán tại mở cửa", "Giữ tiền mặt"],
               [100, 100], [100, 100], [0, 0])
        with self.assertRaises(ValueError):
            _realized_sales(c, 100.)

    def test_17_sale_must_go_to_cash_only(self):
        c = self.curve.copy()
        c.loc[pd.Timestamp("2024-07-02"), "Số cổ phiếu quy ước"] = 1
        with self.assertRaises(ValueError):
            _validate_curve(c)

    def test_18_no_fake_close_on_end_of_data_open_position(self):
        c = self.curve.iloc[:4].copy()
        rows, summary, _, sales = evaluate_windows_from_curve(c, "HPG", "Chiến lược gốc")
        self.assertEqual(len(sales), 0)
        self.assertEqual(rows[-1]["Trạng thái cuối cửa sổ"], "Đang nắm giữ")
        self.assertLess(rows[-1]["Max Drawdown cục bộ (%)"], 0.)

    def test_19_missing_all_evaluation_dates_fails(self):
        c = self.curve.iloc[:1].copy()
        with self.assertRaises(ValueError):
            evaluate_windows_from_curve(c, "HPG", "Chiến lược gốc")

    def test_20_half_year_holidays_not_assumed_trading_days(self):
        w = self.by["WF1"]
        self.assertEqual(w["Số phiên"], 2)
        self.assertEqual(w["Phiên cuối có dữ liệu"], "27/06/2024")

    def test_21_duplicate_sessions_rejected(self):
        c = pd.concat([self.curve.iloc[:1], self.curve])
        with self.assertRaises(ValueError):
            _validate_curve(c)

    def test_22_monetary_profit_factor_rounding_parity(self):
        c = mk(["2023-12-29", "2024-01-02", "2024-01-03", "2024-07-01", "2024-07-02"],
               ["Mua tại mở cửa", "Bán tại mở cửa", "Mua tại mở cửa", "Bán tại mở cửa", "Giữ tiền mặt"],
               [100, 150, 150, 90, 90], [0, 150, 0, 90, 90], [1, 0, 1, 0, 0])
        # The first purchase might predate the evaluation window; PF is 50/60.
        rows, summary, _, sales = evaluate_windows_from_curve(c, "HPG", "Chiến lược gốc")
        self.assertEqual(round(_closed_metrics(sales)["Profit Factor (theo tiền)"],2), .83)
        self.assertEqual(rows[0]["Số lệnh đóng"], 1)
        self.assertEqual(rows[1]["Số lệnh đóng"], 1)

    def test_23_held_position_within_window_no_close(self):
        c = mk(["2023-12-29", "2024-01-02", "2024-06-28"],
               ["Giữ tiền mặt", "Mua tại mở cửa", "Đang nắm giữ"],
               [100, 99, 85], [100, 0, 0], [0, 1, 1])
        rows, summary, _, sales = evaluate_windows_from_curve(c, "HPG", "Chiến lược gốc")
        self.assertEqual(len(sales), 0)
        self.assertEqual(rows[0]["Lợi nhuận cửa sổ (%)"], -15.)
        self.assertIsNone(rows[0]["Profit Factor (theo tiền)"])

    def test_24_invalid_start_year_rejected(self):
        with self.assertRaises(ValueError):
            half_year_windows("2026-11-23", 1900)


if __name__ == "__main__":
    unittest.main()

class IntegrationTests(unittest.TestCase):
    def test_25_wrapper_uses_exactly_one_full_equity_replay(self):
        import types
        from unittest.mock import Mock
        c = sample()
        fake_risk = types.ModuleType('risk_equity')
        fake_risk.STRATEGIES = ("Chiến lược gốc",)
        fake_risk.calculate_equity_risk = Mock(return_value=(c, {
            "Số giao dịch đã đóng": 2,
            "Lợi nhuận theo phiên (%)": 0.0,
            "Max Drawdown theo phiên (%)": -20.0,
        }))
        fake_batch = types.ModuleType('risk_batch')
        fake_batch._closed_trade_metrics = lambda curve, count: ({"Profit Factor": 1.0}, [25, -20])
        with patch.dict(sys.modules, {'risk_equity': fake_risk, 'risk_batch': fake_batch}):
            # Only the data length matters for preflight check.
            data = pd.DataFrame({'x': range(200)})
            rows, agg, issues, chart = evaluate_walk_forward_case("HPG", data, "Chiến lược gốc")
        fake_risk.calculate_equity_risk.assert_called_once()
        self.assertEqual(len(rows), 4)
        self.assertEqual(agg['Đối chiếu Equity qua cửa sổ'], 'ĐẠT')
        self.assertEqual(list(chart.columns), ['Equity', 'Drawdown (%)'])

    def test_26_wrapper_detects_profit_factor_mismatch(self):
        import types
        from unittest.mock import Mock
        c = sample()
        fake_risk = types.ModuleType('risk_equity')
        fake_risk.STRATEGIES = ("Chiến lược gốc",)
        fake_risk.calculate_equity_risk = Mock(return_value=(c, {
            "Số giao dịch đã đóng": 2,
            "Lợi nhuận theo phiên (%)": 0.0,
            "Max Drawdown theo phiên (%)": -20.0,
        }))
        fake_batch = types.ModuleType('risk_batch')
        fake_batch._closed_trade_metrics = lambda curve, count: ({"Profit Factor": 1.5}, [25, -20])
        with patch.dict(sys.modules, {'risk_equity': fake_risk, 'risk_batch': fake_batch}):
            with self.assertRaisesRegex(ValueError, 'Profit Factor'):
                evaluate_walk_forward_case("HPG", pd.DataFrame({'x': range(200)}), "Chiến lược gốc")

    def test_27_wrapper_detects_equity_mismatch(self):
        import types
        from unittest.mock import Mock
        fake_risk = types.ModuleType('risk_equity')
        fake_risk.STRATEGIES = ("Chiến lược gốc",)
        fake_risk.calculate_equity_risk = Mock(return_value=(sample(), {
            "Số giao dịch đã đóng": 2, "Lợi nhuận theo phiên (%)": 9.0,
            "Max Drawdown theo phiên (%)": -20.0,
        }))
        with patch.dict(sys.modules, {'risk_equity': fake_risk}):
            with self.assertRaisesRegex(ValueError, 'Lợi nhuận'):
                evaluate_walk_forward_case("HPG", pd.DataFrame({'x': range(200)}), "Chiến lược gốc")
