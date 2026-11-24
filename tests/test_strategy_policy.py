import unittest
import json
from pathlib import Path
from unittest.mock import patch
import pandas as pd

from multi_backtest_core import STRATEGY_NAMES, evaluate_symbol, RETURN, BUY_DATE, SELL_DATE
from strategy_policy import (
    ACTIVE, BENCHMARK, SUPPORTING, ARCHIVED, RESEARCH,
    DEFAULT_GROUP, BASELINE_GROUP, resolve_strategies,
)

class StrategyPolicyTests(unittest.TestCase):
    def test_research_and_archive_partition(self):
        self.assertEqual(RESEARCH, STRATEGY_NAMES[:3])
        self.assertEqual(ACTIVE + BENCHMARK + SUPPORTING, (STRATEGY_NAMES[1], STRATEGY_NAMES[0], STRATEGY_NAMES[2]))
        self.assertEqual(ARCHIVED, STRATEGY_NAMES[3:])
        self.assertEqual(resolve_strategies(DEFAULT_GROUP), RESEARCH)
        self.assertEqual(resolve_strategies(BASELINE_GROUP), STRATEGY_NAMES)
        self.assertEqual(resolve_strategies(ARCHIVED[0]), (ARCHIVED[0],))
        with self.assertRaises(ValueError):
            resolve_strategies("invalid")

    def test_frozen_baseline_keeps_all_five(self):
        baseline = json.loads((Path(__file__).resolve().parents[1] / "prospective" / "baseline.json").read_text(encoding="utf-8"))
        self.assertEqual(tuple(baseline["strategies"]), STRATEGY_NAMES)

    def test_default_research_skips_archived_runners(self):
        history = pd.DataFrame({"open": [10.0] * 200}, index=pd.date_range("2024-01-01", periods=200))
        trades = pd.DataFrame(columns=[BUY_DATE, SELL_DATE, RETURN])
        with patch("backtesting.tao_bang_giao_dich", return_value=trades), patch("strategy_experiments.chay_backtest_thu_nghiem", return_value=trades) as filters, patch("strategy_experiments.chay_backtest_diem_v2", return_value=trades) as v2, patch("v21_macd_strategy.chay_backtest_diem_v21_macd", return_value=trades) as v21:
            rows, errors = evaluate_symbol("HPG", history, "test", strategies=RESEARCH)
            self.assertEqual(errors, [])
            self.assertEqual(tuple(row["Chiến lược"] for row in rows), RESEARCH)
            self.assertEqual(filters.call_count, 2)
            v2.assert_not_called()
            v21.assert_not_called()
            rows, errors = evaluate_symbol("HPG", history, "test", strategies=resolve_strategies(BASELINE_GROUP))
            self.assertEqual(errors, [])
            self.assertEqual(tuple(row["Chiến lược"] for row in rows), STRATEGY_NAMES)
            v2.assert_called_once()
            v21.assert_called_once()

if __name__ == "__main__":
    unittest.main()
