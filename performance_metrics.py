"""Profit Factor from realized monetary cash flows on reinvested capital.

Trade percentages come from backtesting.py and are rounded there to 0.01%.
No trades or no losing trades => undefined (None), not infinity.
"""
import math


def profit_factor_money(returns_pct, initial_capital=100.0):
    """Gross realized cash gains divided by absolute realized cash losses.

    Each closed trade reinvests the entire prior post-trade capital.  Return
    values are percent points (10 means +10%), already net of trade costs.
    Open positions are not included. The initial capital only scales amounts
    and does not affect the Profit Factor ratio.
    """
    capital = float(initial_capital)
    if not math.isfinite(capital) or capital <= 0:
        raise ValueError("Initial capital must be positive and finite")
    gross_gain = 0.0
    gross_loss = 0.0
    any_trades = False
    for value in returns_pct:
        rate = float(value)
        if not math.isfinite(rate) or rate <= -100.0:
            raise ValueError("Invalid trade return percentage")
        any_trades = True
        pnl = capital * (rate / 100.0)
        if pnl > 0:
            gross_gain += pnl
        elif pnl < 0:
            gross_loss -= pnl
        capital += pnl
    if not any_trades or gross_loss == 0:
        return None
    return gross_gain / gross_loss
