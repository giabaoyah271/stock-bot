"""Small independent-oracle and causal-prefix checks for the frozen Stock Bot.

These tests do not query TCBS, modify any trading strategy, or import the
Streamlit app. Independently computed expectations are hard-coded below.
Run: python -m unittest discover -s tests -p 'test_*.py' -v
"""
import ast
from pathlib import Path
import unittest

import numpy as np
import pandas as pd

from backtesting import tao_bang_giao_dich
from performance_metrics import profit_factor_money
from scoring_v2 import tinh_diem_v2

ROOT = Path(__file__).resolve().parents[1]


def _signal_prices(states, opens):
    return pd.DataFrame(
        {"Trend": states, "open": opens, "Reason": [""] * len(states)},
        index=pd.bdate_range("2026-02-02", periods=len(states)),
    )


def _known_score_features(n=90):
    """Synthetic known-at-close features, not future target labels."""
    i = np.arange(n, dtype=float)
    price = 95.0 + 0.09 * i + 5.0 * np.sin(i / 5.0)
    close = pd.Series(price)
    columns = {
        "open": price * 1.001,
        "close": price,
        "volume": 200000 + 1000 * (i % 9),
        "SMA20": close.rolling(20, min_periods=1).mean(),
        "SMA50": close.rolling(50, min_periods=1).mean(),
        "SMA200": close.rolling(70, min_periods=1).mean(),
        "Senkou_Span_A": price - 2,
        "Senkou_Span_B": price - 3,
        "Tenkan_Sen": price - 1,
        "Kijun_Sen": price - 2,
        "ADX": 23.0 + 8.0 * np.sin(i / 12),
        "Plus_DI": 25 + 3 * np.sin(i / 9),
        "Minus_DI": 20 + 2 * np.cos(i / 9),
        "RSI": 50 + 15 * np.sin(i / 7),
        "MACD": np.sin(i / 6),
        "Signal_Line": np.sin((i - 2) / 6),
        "MFI": 52 + 11 * np.cos(i / 8),
        "Vol_Avg": 203500 + np.zeros(n),
        "BB_lower": price - 4,
        "BB_upper": price + 4,
        "Price_Min_10": price - 5,
        "Prev_Price_Min": price - 6,
        "RSI_Min_10": 35 + np.zeros(n),
        "Prev_RSI_Min": 34 + np.zeros(n),
        "Price_Max_10": price + 5,
        "Prev_Price_Max": price + 6,
        "RSI_Max_10": 65 + np.zeros(n),
        "Prev_RSI_Max": 66 + np.zeros(n),
    }
    return pd.DataFrame(columns, index=pd.bdate_range("2026-01-05", periods=n))


def _price_history(n=280):
    """Complete nonconstant OHLCV for the actual app indicators."""
    i = np.arange(n, dtype=float)
    close = 90 + 0.05 * i + 5 * np.sin(i / 8) + 1.2 * np.cos(i / 3)
    opening = close * (1 + 0.003 * np.sin(i / 4))
    return pd.DataFrame({
        "open": opening, "close": close,
        "high": np.maximum(close, opening) * 1.012,
        "low": np.minimum(close, opening) * 0.988,
        "volume": 200_000 + 15_000 * (i % 11),
    }, index=pd.bdate_range("2025-01-02", periods=n))


def _isolated_app_indicators():
    """Compile only the real calculate_indicators AST; do not run Streamlit/TCBS."""
    source = (ROOT / "app.py").read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    matches = [node for node in tree.body if isinstance(node, ast.FunctionDef)
               and node.name == "calculate_indicators"]
    if len(matches) != 1:
        raise AssertionError("Expected one app.calculate_indicators implementation")
    module = ast.Module(body=[matches[0]], type_ignores=[])
    namespace = {"np": np, "pd": pd}
    exec(compile(ast.fix_missing_locations(module), str(ROOT / "app.py"), "exec"), namespace)
    return namespace["calculate_indicators"]


class IndependentTradingOracles(unittest.TestCase):
    def test_next_open_dates_and_costs_with_large_gap(self):
        # Signals on 03/02 and 05/02 fill 04/02 (125) and 06/02 (90).
        d = _signal_prices([-1, 1, 1, -1, -1, -1], [100, 99, 125, 110, 90, 80])
        ledger = tao_bang_giao_dich(d)
        self.assertEqual(len(ledger), 1)
        t = ledger.iloc[0]
        self.assertEqual(t["Ngày tín hiệu mua"], d.index[1])
        self.assertEqual(t["Ngày mua mô phỏng"], d.index[2])
        self.assertEqual(t["Ngày tín hiệu bán"], d.index[3])
        self.assertEqual(t["Ngày bán mô phỏng"], d.index[4])
        # Decimal reference: buy fill 125.125; cost 125.3126875;
        # sell fill 89.910; proceeds 89.6852250; net -28.4308502%.
        self.assertEqual(t["Giá mua mô phỏng"], 125.125)
        self.assertEqual(t["Giá bán mô phỏng"], 89.910)
        self.assertEqual(t["Lợi nhuận sau chi phí (%)"], -28.43)

    def test_last_bar_signal_cannot_fill_from_unavailable_future_open(self):
        d = _signal_prices([-1, -1, -1, -1, 1], [100, 100, 100, 100, 200])
        self.assertTrue(tao_bang_giao_dich(d).empty)
        d2 = _signal_prices([-1, 1, 1, 1, -1], [100, 100, 95, 90, 80])
        self.assertTrue(tao_bang_giao_dich(d2).empty)

    def test_future_open_change_cannot_reprice_past_closed_trade(self):
        original = _signal_prices([-1, 1, 1, -1, -1, -1, -1],
                                  [100, 110, 125, 110, 90, 90, 80])
        manipulated = original.copy()
        manipulated.iloc[-1, manipulated.columns.get_loc("open")] = 1_000_000
        pd.testing.assert_frame_equal(
            tao_bang_giao_dich(original), tao_bang_giao_dich(manipulated))

    def test_independently_computed_reinvestment_profit_factor(self):
        # 100 ->120 (+20); ->108 (-12); ->102.6 (-5.4); ->117.99 (+15.39).
        # Gross gain 35.39, loss 17.40, PF = 2.033908...
        self.assertAlmostEqual(profit_factor_money([20, -10, -5, 15]),
                               35.39 / 17.4, places=12)

    def test_open_legs_are_not_realized_profit_factor(self):
        self.assertIsNone(profit_factor_money([]))
        self.assertIsNone(profit_factor_money([15]))


class IndependentCausalityChecks(unittest.TestCase):
    def test_v2_scores_do_not_change_when_future_rows_append(self):
        feature = _known_score_features()
        truncated = tinh_diem_v2(feature.iloc[:65].copy())
        full = tinh_diem_v2(feature.copy())
        for col in ("V2_Buy_Pct", "V2_Sell_Pct", "V2_Ready"):
            pd.testing.assert_series_equal(truncated[col], full[col].iloc[:65])

    def test_actual_app_indicators_are_prefix_causal(self):
        if not (ROOT / "app.py").exists():
            self.skipTest("Full app.py unavailable in isolated local staging")
        calculate = _isolated_app_indicators()
        inputs = _price_history()
        past = calculate(inputs.iloc[:255].copy())
        full = calculate(inputs.copy()).iloc[:255]
        fields = ["SMA20", "SMA50", "SMA200", "RSI", "MACD", "Signal_Line",
                  "Senkou_Span_A", "Senkou_Span_B", "ATR", "ADX",
                  "Trend", "Buy_Pct", "Sell_Pct", "Reason"]
        pd.testing.assert_frame_equal(past[fields], full[fields],
                                      check_exact=False, rtol=1e-12, atol=1e-12)

    def test_actual_v2_with_app_indicators_is_prefix_causal(self):
        if not (ROOT / "app.py").exists():
            self.skipTest("Full app.py unavailable in isolated local staging")
        calculate = _isolated_app_indicators()
        inputs = _price_history()
        past = tinh_diem_v2(calculate(inputs.iloc[:255].copy()))
        full = tinh_diem_v2(calculate(inputs.copy())).iloc[:255]
        pd.testing.assert_frame_equal(
            past[["V2_Buy_Pct", "V2_Sell_Pct", "V2_Ready"]],
            full[["V2_Buy_Pct", "V2_Sell_Pct", "V2_Ready"]],
            check_exact=False, rtol=1e-12, atol=1e-12)

    def test_indicators_use_no_explicit_negative_shift_or_centered_rolling(self):
        if not (ROOT / "app.py").exists():
            self.skipTest("Full app.py unavailable in isolated local staging")
        tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8-sig"))
        indicators = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                          and node.name == "calculate_indicators")
        for node in ast.walk(indicators):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr == "shift" and node.args:
                amount = node.args[0]
                if (isinstance(amount, ast.UnaryOp) and isinstance(amount.op, ast.USub)
                        and isinstance(amount.operand, ast.Constant)
                        and isinstance(amount.operand.value, (int, float))):
                    self.fail("Negative shift would expose future observations")
            if node.func.attr == "rolling":
                for kw in node.keywords:
                    if kw.arg == "center" and isinstance(kw.value, ast.Constant):
                        self.assertNotEqual(kw.value.value, True)
            self.assertNotIn(node.func.attr, ("bfill", "backfill"),
                             "Backward fill might leak future observations")


if __name__ == "__main__":
    unittest.main()
