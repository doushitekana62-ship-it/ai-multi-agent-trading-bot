# Dashboard Contract Amendment — 2026-08-29

This amendment records the approved dashboard presentation changes implemented after the Market Pulse review.

## 1. Market Pulse ownership

Market Pulse status is rendered inside the Market Pulse dashboard card. A second fixed status widget must not be mounted globally. The symbols are interpreted as:

- `UP` / upward marker: price increased during the displayed short-term window;
- `DOWN` / downward marker: price decreased during the displayed short-term window;
- `FLAT` / neutral marker: movement is below the configured significance threshold or data is insufficient.

24-hour high, 24-hour low, and 24-hour volume remain independent market context.

## 2. Trading Library alerts

Trading Library alerts are informational UI events only. They may appear as a left-side popup and must never start, stop, or execute a paper cycle. Duplicate alerts must be suppressed by cycle/alert identity.

## 3. Dashboard analytics

The dashboard may expose Conflict Analyzer, INDODAX Scalping Radar, and Volume Share visualizations. These components are read-only projections of existing decision and market-data contracts. They must not become a second decision or execution engine.

## 4. Market Scanner

The scanner is not hard-capped at five rows. The API may return a bounded larger set, currently twenty IDR markets. The scalping-coin selector must only expose pairs accepted by the paper/AI engine contract. Unsupported pairs must never silently map to another coin.

## 5. Supabase paper history

Paper history is read from the `paper_history` persistence boundary. The dashboard requests ten rows per page. The Worker fetches only eleven rows to determine `has_next`, then returns at most ten. Pagination is read-only and cannot mutate Durable Object paper state.

## 6. Failure containment

Dashboard analytics are optional presentation layers. A failure in scanner, chart, history, or alert polling must not prevent the primary paper-trading controls from rendering. API calls use bounded requests and frontend polling must prevent overlapping requests.

No change in this amendment authorizes live trading or bypasses the central risk/execution boundary.
