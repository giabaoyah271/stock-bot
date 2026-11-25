# Stock Bot V3 — Professional Terminal
Baseline: f1cd923b9ae2ae87000f1d2af3932ec00c375e52 (research-v3 ONLY). UI branch: ui-ux/research-v3-terminal.
Baseline CI: 261 passed, run 45586303726.
## Design
User-approved 80% TradingView / 20% Bloomberg, desktop-first, responsive mobile. UI UX Pro Max local search `financial dashboard trading investment --design-system`: Dark Mode (OLED), financial palette, IBM Plex Sans. Rejected Enterprise Gateway as irrelevant. Native sans-serif fallback avoids remote font fetching; Plotly requests IBM Plex Sans if installed.
Tokens: #020617 background, #0F172A surface, #1E293B elevated, #334155 border, #F8FAFC text, #94A3B8 secondary, #3B82F6 interaction, #22C55E positive, #EF4444 negative, #F59E0B warning. Chart labels and text distinguish states; limited responsive DOM CSS with focus and reduced-motion rules.
## Inventory / UI01–UI08
- UI01 baseline and frozen source comparison: no core, data, ranking, journal, old test, or research module modifications.
- UI02 theme, consistent chart styles and metrics.
- UI03 six navigation destinations, mapping to original five workspace routes and all seven advanced tools; preserves PT09 NAV callback, sidebar OTP.
- UI04 overview readiness, VN-Index, paper metrics, PT10 price chart with right-side risk panel (S0P0 vs R1), indicators and original transition history; auxiliary 1H/week indicator-only.
- UI05 original 120/115 U5 scanner, reference/confirmation/rank/report/record unchanged; grouped workflow, pinned ticker, better labels, native sort (no reranking).
- UI06 original five portfolio subsections and all KT01–KT18 research tools retained; themed equity/drawdown, paper account backup/restore schema intact.
- UI07 system setup, acceptance, forward readiness, globally accessible OTP; secrets remain external; responsive styling.
- UI08 source integrity and AppTest offline navigation plus original suite.
## Safeguards
Original PT10 U5-A0-RS60-P5-R050 only. No new data fetch, orders, signals, targets or changes to TEST/LIVE, frozen reference, 115/120 gate, RS60, S0P0, R1, record guards, journal. All legacy V1 code unchanged and reachable only in Research. Auth status reports last result, not a live check. Native UI controls and labels are retained.
## Acceptance and rollout
Separate private Streamlit test app using this branch and app.py. Copy existing secrets privately. Before moving apps, download original Paper JSON and preserve exact U5-B ZIP; restore only by explicit action. No automatic migration or persistent cloud storage. Open all six screens, upload U5-B, run PT10 115-symbol TEST acceptance, compare scan/detail with same validated LIVE identity, test 1H/week, verify Paper restoration and report CSV/ZIP. Do not record a duplicate or historical session. Check desktop 1024/1280/1440/1920 and mobile 375/390/768, focus, touch, contrast, and chart/table overflow. Test actual TCBS separately. Unit tests and AppTest are not visual/browser or live-provider validation. No merge/deploy until approval. Rollback: keep research-v3 unchanged; discard test app or switch to baseline. No change to dependencies.
