"""Regression tests for cash-only periods and realized-money Profit Factor.

Run from repository root:
    python -m unittest discover -s tests -p 'test_*.py' -v
No TCBS credentials or remote data are needed.
"""
import unittest
import pandas as pd

from backtesting import tao_bang_giao_dich
from multi_backtest_core import trade_metrics
from performance_metrics import profit_factor_money
from risk_equity import calculate_equity_risk

RETURN = "Lợi nhuận sau chi phí (%)"


def stock(trend, opens=None, closes=None):
    n = len(trend)
    opens = list(opens) if opens is not None else [100.0] * n
    closes = list(closes) if closes is not None else list(opens)
    return pd.DataFrame(
        {"open": opens, "close": closes, "Trend": trend, "Reason": [""] * n},
        index=pd.bdate_range("2026-01-05", periods=n),
    )


class CashAndRiskTests(unittest.TestCase):
    def run_case(self, df):
        return calculate_equity_risk(df, "Chiến lược gốc")

    def test_01_sell_then_price_crashes(self):
        d = stock([-1, 1, 1, -1, -1, -1, -1], [100, 100, 100, 110, 110, 95, 80])
        curve, metrics = self.run_case(d)
        self.assertEqual(metrics["Số giao dịch đã đóng"], 1)
        self.assertEqual(curve["Equity"].iloc[4:].nunique(), 1)
        self.assertTrue((curve["Số cổ phiếu quy ước"].iloc[4:] == 0).all())
        self.assertEqual(curve["Drawdown (%)"].iloc[4:].nunique(), 1)

    def test_02_sell_loss_then_price_crashes(self):
        d = stock([-1, 1, 1, -1, -1, -1, -1], [100, 100, 100, 90, 90, 50, 20])
        curve, metrics = self.run_case(d)
        self.assertLess(metrics["Lợi nhuận theo phiên (%)"], 0)
        self.assertEqual(curve["Equity"].iloc[4:].nunique(), 1)

    def test_03_unsold_position_falls_and_recovers(self):
        d = stock([-1, 1, 1, 1, 1, 1], closes=[100, 100, 100, 75, 95, 105])
        curve, metrics = self.run_case(d)
        self.assertLess(curve["Equity"].iloc[3], curve["Equity"].iloc[2])
        self.assertGreater(curve["Equity"].iloc[-1], curve["Equity"].iloc[3])
        self.assertEqual(metrics["Trạng thái cuối"], "Đang nắm giữ")

    def test_04_cash_ignores_stock_price_crash(self):
        curve, _ = self.run_case(stock([-1] * 8, opens=[100, 100, 100, 50, 40, 20, 10, 1]))
        self.assertTrue((curve["Equity"] == 100).all())

    def test_05_flat_for_100_sessions_after_sale(self):
        d = stock([-1, 1, 1, -1] + [-1] * 101,
                  opens=[100, 100, 100, 95, 95] + [10] * 100)
        curve, _ = self.run_case(d)
        self.assertEqual(curve["Equity"].iloc[4:].nunique(), 1)

    def test_06_reentry_after_sale(self):
        d = stock([-1, 1, 1, -1, -1, 1, 1, -1, -1, -1],
                  opens=[100, 100, 100, 110, 110, 110, 110, 90, 90, 20])
        curve, metrics = self.run_case(d)
        self.assertEqual(metrics["Số giao dịch đã đóng"], 2)
        self.assertEqual(sum(curve["Trạng thái"] == "Mua tại mở cửa"), 2)
        self.assertEqual(curve["Equity"].iloc[8], curve["Equity"].iloc[9])

    def test_07_open_position_is_marked_to_market(self):
        d = stock([-1, 1, 1, 1, 1], closes=[100, 100, 100, 95, 85])
        _, metrics = self.run_case(d)
        self.assertEqual(metrics["Trạng thái cuối"], "Đang nắm giữ")
        self.assertLess(metrics["Lãi/lỗ vị thế mở (%; chưa trừ phí bán)"], 0)
        self.assertIsNone(metrics["Lệnh lỗ lớn nhất (%)"])

    def test_08_no_trades(self):
        curve, metrics = self.run_case(stock([-1] * 5))
        self.assertEqual(metrics["Số giao dịch đã đóng"], 0)
        self.assertIsNone(metrics["Lệnh lỗ lớn nhất (%)"])
        self.assertTrue((curve["Equity"] == 100).all())

    def test_09_gap_before_next_open_sale(self):
        d = stock([-1, 1, 1, -1, -1, -1], opens=[100, 100, 100, 110, 70, 20])
        curve, _ = self.run_case(d)
        self.assertLess(curve["Equity"].iloc[4], curve["Equity"].iloc[3])
        self.assertEqual(curve["Equity"].iloc[4], curve["Equity"].iloc[5])
        self.assertLess(tao_bang_giao_dich(d)[RETURN].iloc[0], -20)

    def test_10_winning_then_losing_trade(self):
        d = stock([-1, 1, 1, -1, -1, 1, 1, -1, -1, -1],
                  opens=[100, 100, 100, 110, 110, 110, 110, 80, 80, 10])
        curve, metrics = self.run_case(d)
        self.assertEqual(metrics["Số giao dịch đã đóng"], 2)
        self.assertGreater(curve["Equity"].iloc[4], 100)
        self.assertLess(curve["Equity"].iloc[-1], 100)

    def test_11_drawdown_persists_but_not_worsens_in_cash(self):
        d = stock([-1, 1, 1, -1, -1, -1, -1], opens=[100, 100, 100, 110, 90, 25, 5])
        curve, metrics = self.run_case(d)
        self.assertEqual(metrics["Trạng thái cuối"], "Tiền mặt")
        self.assertLess(curve["Drawdown (%)"].iloc[4], 0)
        self.assertEqual(curve["Drawdown (%)"].iloc[4:].nunique(), 1)

    def test_12_last_bar_signals_do_not_fill_without_next_session(self):
        for trend, state in [
            ([-1, -1, -1, -1, 1], "Tiền mặt"),
            ([-1, 1, 1, 1, -1], "Đang nắm giữ"),
        ]:
            with self.subTest(trend=trend):
                _, metrics = self.run_case(stock(trend))
                self.assertEqual(metrics["Trạng thái cuối"], state)
                self.assertEqual(metrics["Số giao dịch đã đóng"], 0)

    def test_13_fees_and_slippage_agree_with_trade_ledger(self):
        d = stock([-1, 1, 1, -1, -1, -1])
        curve, _ = self.run_case(d)
        expected = 100 * ((1 - .001) * (1 - .0015 - .001)) / ((1 + .001) * (1 + .0015))
        self.assertAlmostEqual(curve["Equity"].iloc[4], expected)
        self.assertAlmostEqual(
            tao_bang_giao_dich(d)[RETURN].iloc[0],
            round((expected / 100 - 1) * 100, 2),
        )

    def test_14_invalid_price_is_rejected(self):
        d = stock([-1, 1, 1, -1, -1])
        d.iloc[2, d.columns.get_loc("open")] = float("nan")
        with self.assertRaises(ValueError):
            self.run_case(d)

    def test_15_winning_trades_have_no_largest_loss(self):
        d = stock([-1, 1, 1, -1, -1, -1], opens=[100, 100, 100, 110, 110, 110])
        _, metrics = self.run_case(d)
        self.assertEqual(metrics["Số giao dịch đã đóng"], 1)
        self.assertIsNone(metrics["Lệnh lỗ lớn nhất (%)"])

    def test_16_losing_trades_show_negative_biggest_loss(self):
        d = stock([-1, 1, 1, -1, -1, -1], opens=[100, 100, 100, 90, 90, 90])
        _, metrics = self.run_case(d)
        self.assertLess(metrics["Lệnh lỗ lớn nhất (%)"], 0)

    def test_17_money_profit_factor_is_not_percentage_ratio(self):
        metrics = trade_metrics(pd.DataFrame({RETURN: [50.0, -40.0]}))
        self.assertEqual(metrics["Profit Factor"], 0.83)
        self.assertEqual(metrics["Lợi nhuận tích lũy (%)"], -10.0)
        self.assertAlmostEqual(profit_factor_money([50, -40]), 50 / 60)

    def test_18_all_winners_make_pf_undefined(self):
        self.assertIsNone(trade_metrics(pd.DataFrame({RETURN: [10.0, 20.0]}))["Profit Factor"])

    def test_19_all_losers_make_pf_zero(self):
        self.assertEqual(trade_metrics(pd.DataFrame({RETURN: [-10.0, -20.0]}))["Profit Factor"], 0.0)

    def test_20_empty_trade_table(self):
        m = trade_metrics(pd.DataFrame({RETURN: pd.Series(dtype=float)}))
        self.assertEqual(m["Số lệnh"], 0)
        self.assertIsNone(m["Profit Factor"])

    def test_21_breakeven_is_not_a_loss(self):
        m = trade_metrics(pd.DataFrame({RETURN: [0.0, -5.0]}))
        self.assertEqual(m["Số lệnh thua"], 1)
        self.assertEqual(m["Profit Factor"], 0.0)

    def test_22_trade_order_changes_monetary_profit_factor(self):
        self.assertAlmostEqual(profit_factor_money([-40, 50]), 30 / 40)

    def test_23_pf_is_independent_of_capital_unit(self):
        self.assertAlmostEqual(
            profit_factor_money([15, -8, 5, -2]),
            profit_factor_money([15, -8, 5, -2], initial_capital=1_000_000),
        )

    def test_24_invalid_trade_returns_are_rejected(self):
        for bad in (-100, -120, float("nan"), float("inf")):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                profit_factor_money([bad])


if __name__ == "__main__":
    unittest.main()
