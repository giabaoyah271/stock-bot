"""Vietnam trading-day and timezone regression tests for Walk-Forward."""
import sys
import types
import unittest
from unittest.mock import Mock, patch
from pathlib import Path
import pandas as pd
import plotly.graph_objects as go

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from walk_forward_core import (
    _market_time, _local_reporting_curve, half_year_windows,
    evaluate_windows_from_curve, evaluate_walk_forward_case,
)


def sample():
    d = pd.DataFrame({
        "Equity": [100, 100, 120, 118, 125, 125, 125, 100, 100],
        "Tiền mặt": [100, 0, 0, 0, 125, 125, 0, 100, 100],
        "Số cổ phiếu quy ước": [0, 1, 1, 1, 0, 0, 1, 0, 0],
        "Trạng thái": ["Giữ tiền mặt", "Mua tại mở cửa", "Đang nắm giữ",
                       "Đang nắm giữ", "Bán tại mở cửa", "Giữ tiền mặt",
                       "Mua tại mở cửa", "Bán tại mở cửa", "Giữ tiền mặt"],
    }, index=pd.to_datetime([
        "2023-12-29", "2024-01-02", "2024-06-27", "2024-07-01",
        "2024-07-02", "2024-12-30", "2025-01-02", "2025-07-01", "2025-07-02",
    ]))
    d["Drawdown (%)"] = (d["Equity"] / d["Equity"].cummax() - 1) * 100
    return d


class WalkForwardTimezoneTests(unittest.TestCase):
    def setUp(self):
        self.baseline = sample()
        self.expected = evaluate_windows_from_curve(self.baseline, "HPG", "Chiến lược gốc")

    def assert_same_numbers(self, frame):
        actual = evaluate_windows_from_curve(frame, "HPG", "Chiến lược gốc")
        self.assertEqual(actual[0], self.expected[0])
        self.assertEqual(actual[1], self.expected[1])
        self.assertEqual(actual[2], self.expected[2])
        self.assertEqual(actual[3]["Lợi nhuận lệnh (%)"].tolist(),
                         self.expected[3]["Lợi nhuận lệnh (%)"].tolist())

    def test_01_naive_dates_unchanged(self):
        self.assert_same_numbers(self.baseline)

    def test_02_vietnam_tz_same_results(self):
        frame = self.baseline.tz_localize("Asia/Ho_Chi_Minh")
        self.assert_same_numbers(frame)
        self.assertIsNotNone(frame.index.tz)

    def test_03_utc_tz_same_results(self):
        frame = self.baseline.tz_localize("Asia/Ho_Chi_Minh").tz_convert("UTC")
        self.assert_same_numbers(frame)

    def test_04_utc_crosses_into_next_vietnam_day(self):
        self.assertEqual(_market_time("2024-06-30 20:00+00:00"),
                         pd.Timestamp("2024-07-01 03:00"))

    def test_05_naive_wall_clock_not_shifted(self):
        self.assertEqual(_market_time("2024-07-01 09:30"),
                         pd.Timestamp("2024-07-01 09:30"))

    def test_06_non_midnight_sessions_keep_metrics(self):
        frame = self.baseline.copy()
        frame.index += pd.Timedelta(hours=9)
        self.assert_same_numbers(frame)

    def test_07_final_calendar_day_included(self):
        frame = self.baseline.copy()
        frame.index += pd.Timedelta(hours=9)
        frame.index = frame.index.where(frame.index != pd.Timestamp("2024-06-27 09:00"),
                                        pd.Timestamp("2024-06-30 15:00"))
        rows, *_ = evaluate_windows_from_curve(frame, "HPG", "Chiến lược gốc")
        self.assertEqual(rows[0]["Phiên cuối có dữ liệu"], "30/06/2024")

    def test_08_no_trades_tz_aware_is_not_error(self):
        frame = self.baseline.copy()
        frame.index = frame.index.tz_localize("UTC")
        frame["Equity"] = 100.
        frame["Tiền mặt"] = 100.
        frame["Số cổ phiếu quy ước"] = 0.
        frame["Trạng thái"] = "Giữ tiền mặt"
        frame["Drawdown (%)"] = 0.
        rows, summary, _, trades = evaluate_windows_from_curve(frame, "HPG", "Chiến lược gốc")
        self.assertTrue(rows)
        self.assertEqual(len(trades), 0)
        self.assertIsNone(rows[0]["Profit Factor (theo tiền)"])
        self.assertEqual(summary["Lợi nhuận TOÀN lịch sử (%)"], 0)

    def test_09_duplicate_local_trading_date_rejected(self):
        frame = self.baseline.copy()
        idx = list(frame.index)
        idx[2] = pd.Timestamp("2024-01-02 15:00")
        frame.index = pd.DatetimeIndex(idx)
        with self.assertRaisesRegex(ValueError, "Trùng ngày"):
            evaluate_windows_from_curve(frame, "HPG", "Chiến lược gốc")

    def test_10_unsorted_dates_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_windows_from_curve(self.baseline.iloc[::-1], "HPG", "Chiến lược gốc")

    def test_11_nat_rejected(self):
        frame = self.baseline.copy()
        idx = list(frame.index)
        idx[0] = pd.NaT
        frame.index = pd.DatetimeIndex(idx)
        with self.assertRaises(ValueError):
            evaluate_windows_from_curve(frame, "HPG", "Chiến lược gốc")

    def test_12_no_mutation_of_original_timezone_or_values(self):
        frame = self.baseline.tz_localize("Asia/Ho_Chi_Minh")
        saved = frame.copy(deep=True)
        evaluate_windows_from_curve(frame, "HPG", "Chiến lược gốc")
        pd.testing.assert_frame_equal(frame, saved)

    def test_13_no_reset_or_fake_trades_across_boundary(self):
        frame = self.baseline.tz_localize("Asia/Ho_Chi_Minh")
        rows, summary, _, trades = evaluate_windows_from_curve(frame, "HPG", "Chiến lược gốc")
        by = {r["Cửa sổ"]: r for r in rows}
        self.assertEqual(by["WF1"]["Số lệnh đóng"], 0)
        self.assertEqual(by["WF2"]["Số lệnh đóng"], 1)
        self.assertEqual(by["WF2"]["Lệnh đóng có ngày mua trước cửa sổ"], 1)
        self.assertEqual(len(trades), 2)
        self.assertEqual(summary["Lợi nhuận TOÀN lịch sử (%)"], 0.)

    def test_14_final_day_utc_rollover_window(self):
        idx = pd.to_datetime(["2023-12-29 00:00+00:00", "2024-06-30 20:00+00:00"])
        frame = pd.DataFrame({
            "Equity": [100., 100.], "Tiền mặt": [100., 100.],
            "Số cổ phiếu quy ước": [0., 0.], "Trạng thái": ["Giữ tiền mặt"] * 2,
            "Drawdown (%)": [0., 0.],
        }, index=idx)
        rows, *_ = evaluate_windows_from_curve(frame, "HPG", "Chiến lược gốc")
        self.assertEqual([r["Cửa sổ"] for r in rows], ["WF2"])

    def test_15_drawdown_corruption_still_detected(self):
        frame = self.baseline.tz_localize("UTC").copy()
        frame.iloc[3, frame.columns.get_loc("Drawdown (%)")] = -70.
        with self.assertRaisesRegex(ValueError, "Drawdown"):
            evaluate_windows_from_curve(frame, "HPG", "Chiến lược gốc")

    def test_16_chart_datetime_shape_valid_in_plotly(self):
        frame = _local_reporting_curve(self.baseline.tz_localize("UTC"))
        fig = go.Figure(go.Scatter(x=frame.index, y=frame["Equity"]))
        for window in half_year_windows(frame.index[-1]):
            if frame.index.normalize().min() <= window.start <= frame.index.normalize().max():
                at = window.start.to_pydatetime()
                fig.add_shape(type="line", xref="x", yref="paper", x0=at, x1=at,
                              y0=0, y1=1, line=dict(color="gray", width=1, dash="dot"))
        self.assertGreater(len(fig.layout.shapes), 0)

    def test_17_wrapper_chart_localized_but_equity_unchanged(self):
        curve = self.baseline.tz_localize("UTC")
        fake_risk = types.ModuleType("risk_equity")
        fake_risk.STRATEGIES = ("Chiến lược gốc",)
        fake_risk.calculate_equity_risk = Mock(return_value=(curve, {
            "Số giao dịch đã đóng": 2, "Lợi nhuận theo phiên (%)": 0.,
            "Max Drawdown theo phiên (%)": -20.,
        }))
        fake_batch = types.ModuleType("risk_batch")
        fake_batch._closed_trade_metrics = lambda c, count: ({"Profit Factor": 1.}, [25., -20.])
        with patch.dict(sys.modules, {"risk_equity": fake_risk, "risk_batch": fake_batch}):
            rows, aggregate, errors, chart = evaluate_walk_forward_case(
                "HPG", pd.DataFrame({"dummy": range(200)}), "Chiến lược gốc")
        self.assertEqual(len(rows), 4)
        self.assertIsNone(chart.index.tz)
        self.assertEqual(chart["Equity"].tolist(), curve["Equity"].tolist())
        self.assertIsNotNone(curve.index.tz)

    def test_18_half_years_use_vietnam_date(self):
        windows = half_year_windows(pd.Timestamp("2026-11-23 00:00", tz="UTC"))
        self.assertEqual(len(windows), 6)
        self.assertEqual(windows[-1].end, pd.Timestamp("2026-11-23"))


if __name__ == "__main__":
    unittest.main()
