# Mirei

Mirei is an Android-first paper-trading runtime.

The application is intentionally reduced to one decision owner: Mirei. There are no secondary analysis agents, suggestion panels, strategy modes, web dashboards, FastAPI runtime, Freqtrade runtime, or broker-specific live execution in this build.

## Runtime contract

- Paper trading only.
- Maximum 10 simultaneous positions.
- Session capital defaults to Rp150,000.
- Default allocation is Rp50,000 per position.
- Mirei opens the initial paper holdings selected by the user.
- After a position closes at SL or TP, Mirei may re-enter using the original cycle capital for that instrument.
- HOLD means keep the position open until SL/TP or an explicit close-all command.
- SELL is automatic when the configured SL or TP threshold is reached.
- Manual TP is a net Rupiah target. The target is not converted into a percentage mode.
- Risk reference can be either HARGA ENTRY or MODAL BELI PERTAMA.
- Paper instruments include saham, forex, kripto, and komoditas/emas.
- The dashboard has one screen only.

## Dashboard

The only dashboard controls are:

1. MULAI
2. STOP
3. LANJUTKAN
4. TUTUP SEMUA POSISI
5. ATUR SL/TP
6. RESET

History is rendered as a table from the local trade ledger.

The dashboard does not expose live market charts, market scanners, suggestion feeds, agent votes, or secondary dashboards.

## Android architecture

The active runtime is:

Android Activity -> Mirei Foreground Service -> Mirei Paper Trading Runtime -> Paper Execution Engine -> Local SQLite ledger.

Market data is used only as the input required to determine whether an existing position has reached SL/TP and whether a re-entry can be executed. It is not rendered as a market-analysis dashboard.

## Paper market catalog

The paper catalog is broker-independent at the UI level and currently contains examples across:

- Crypto
- Stocks
- Forex
- Commodities / Gold

Provider-specific market-data adapters remain below the paper runtime boundary.

## Security and live trading

Live order execution is disabled in this build. No live API credential flow is part of the active runtime.
