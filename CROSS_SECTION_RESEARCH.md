# KT15 cross-sectional robustness

Frozen groups from user-approved proposal (Top 20 reference dated 20/11/2026; U3 diversified large-cap selection, not literal top 20). 31 unique tickers, U0/U1/U2/U3 = 12/20/14/20. Fixed membership ex post, survivorship/selection bias; new ticker sample is cross-sectional only, not pristine temporal OOS. No optimization.

2022-01-04 to 2026-11-23, exact 1217-session VNINDEX reference coverage, 100m VND, original R1 and S0P0, A0/A4, C0 vs A4 C1-C3, 5 cases per group; 20 total. Original U0 sector map preserved. BSR/PLX/GAS share oil bucket, MCH/VNM food, banks shared; ecosystem VIC/VHM/VPL P&L reported not additional cap. Sector classifications research mapping, not official standard.

VPL first trading 2025-05-13. BSR last UPCOM trading 2025-01-06, first HOSE 2025-01-17. MCH last UPCOM 2025-12-17, first HOSE 2025-12-25. No other gaps accepted, including provider missing older UPCOM data; report missing/extra dates and fail affected group, no silent substitutions. No OHLCV padding; indicators on actual trading candles; next actual stock open after completed stock signal, may span market sessions; stale prior close only for held suspended asset mark/sizing other assets, never fill. Holding duration market sessions. Stale count in equity; mark may understate risk. No forced liquidation.

Portfolio engine extended via opt-in calendar and sector map; default path checked in U0 parity and legacy CI. 200 real bars warmup via original SMA rules. MC for A4 C0 each group 2,000 x 3 blocks x 2 samples (full and after market warmup; late listing may still have warmup), no predictive guarantee. Stock and sector breakdown includes open and closed P&L, signal catalog baseline costs only. ZIP includes source prices/indicators, VNINDEX calendar, diagnostic gaps, reports; store privately, not public repository. No live changes, no new T+2 rule. Compare KT12 U0 reports manually as source may revise data. Data revisions, corporate actions, liquidity/price limits/zero-volume actual executability remain limitations.

Sources for dates:
- https://www.bsc.com.vn/tin-tuc/tin-tuc-ma-co-phieu/1308470/vpl-thong-bao-ve-viec-niem-yet-va-ngay-giao-dich-dau-tien/
- https://www.phs.vn/tin-tuc/bsr-an-dinh-ngay-dua-31-ty-cp-len-hose-cong-bo-ke-hoach-2025/6227099
- https://www.phs.vn/tin-tuc/mch-chot-ngay-len-hose-vao-2512-gia-tham-chieu-212800-dongcp/6352774

KT15 requests the existing daily loader with history_end=2026-11-23. Raw timestamps are checked before truncating; bars strictly after the frozen cutoff cannot block the retrospective run or enter indicator calculations. All OHLC checks within the cutoff remain strict. OHLC range failures report the first five offending local dates and full-precision OHLCV values; empty rejected frames retain a safe diagnostic attr for KT15 errors/ZIP. No price repair, no gap exemption, no change to default daily/hour/week calls.
