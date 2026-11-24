# KT03 – Initial Stop experiments

S0 reproduces original strategy and equity, otherwise reject all cases.
S1: original 2 ATR trailing, eligible from close of buy-fill day (signal age 1).
S2/S3/S4: fixed 3/4/5% stop below raw buy open, plus original trailing age 3.
S5/S6: 1.5/2 ATR below raw buy open, ATR frozen at signal close, plus original trailing age 3.
S7: S6 + early trailing (S1). No stop fill at stop price. Every sell decision
uses close and fills next open, original fee/tax/slippage, including gap.
Initial stop has priority if both initial/trailing trigger; then trailing;
then original technical exit. Recompute entry confirmation from flat state
after exit. No synthetic liquidation of open positions at end.
S0 must match full legacy signal state, closed ledger and daily equity.
One stock at a time, full reinvestment, fractional shares. No portfolio MDD.
Use same historical input for all variants, no automatic parameter selection.
Compare trade count, exposure, monetary PF, expectancy, daily equity MDD,
matched winning trades and six-month retrospective windows. Unmatched
winners may reflect different entry dates or still-open positions.
All history is research, not pristine OOS; do not promote based only on
win rate or lower exposure. Next step: analyze CSVs, stress costs and OOS.
Default SMA50/SMA200 with HPG/MBB; 16 cases. All 12 and all 3 = 288 cases.
Run only on button; no new data source; no changes to live signals or baseline.
