# Stock Bot Professional Terminal v1
Baseline: 21a3db9f32129daac5cf2060aa166e915d56d7e8 (cloud-dev). Branch: ui-ux/professional-terminal-v1.

## Design system
80% TradingView (chart-first, symbol/timeframe controls), 20% Bloomberg (dense research tables).
Local UI UX Pro Max search: financial dashboard trading investment. Dark OLED, IBM Plex Sans, dark financial palette. Enterprise Gateway layout rejected. Streamlit theme uses native sans serif fallback to avoid remote font dependency; Plotly requests IBM Plex Sans where available.
Tokens: background #020617, surface #0F172A, elevated #1E293B, border #334155, interaction #3B82F6, positive #22C55E, negative #EF4444, warning #F59E0B, text #F8FAFC, secondary #94A3B8. Labels distinguish states without relying on color. Native widgets first; limited DOM CSS for responsive stacking and focus.

## Inventory / migration
- Trading: main V1 Trend, entry, latest price, price variation, ATR reference, T1–T3, candlesticks, volume, RSI, existing SMA/MACD/ADX/ATR, signal events and optional history.
- Scanner: original universe, formulas and 1.1s delay; result retained per session for latest scanned timeframe, filters/sort do not refetch; failures counted.
- Research: original V1/V2 scoring comparison, single backtest, 5 strategies, V2.1 trade audit, SMA filter, closed-trade equity, multi-stock, risk batch, single equity and Walk-Forward; existing CSVs preserved.
- System: original TCBS form and authentication, original OHLCV checks; auth status is last authentication outcome, not live connectivity.
- No algorithm changes: calculate_indicators/get_data and universe copied verbatim; backtesting/risk/scoring modules untouched. Existing date warning copied, including weekly behavior. No change to next-open fills/T+2. Displayed ATR reference is not internal trailing stop. No live prices or orders added.
- UI-only decisions: scanner skips incomplete records and reports failures; dark theme native font fallback; mobile CSS is best effort; no claim of full WCAG.

## Acceptance
Run python -m unittest discover -s tests -p 'test_*.py' -v and python -m compileall -q app.py terminal_ui.py multi_backtest_ui.py.
Open a separate Streamlit Cloud test app using this branch, entrypoint app.py, same secrets privately. Do not change production. Authenticate and compare HPG/MBB/FPT and all 12 accepted tickers on identical inputs, all timeframes; verify prices, signals, trades, win rate, PF, drawdown, CSV and API error states. Check widths 375/390/768/1024/1280/1440/1920. Confirm no extra API calls on scanner filters. Verify focus and contrast, chart labels and touch targets.
Rollback: production cloud-dev never modified; discard test app or select baseline branch. Merge only after approval.
Runtime, TCBS and browser verification are not implied by source checks.
