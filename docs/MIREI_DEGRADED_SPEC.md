# Mirei Degraded Specification

This is the active specification for the reduced Android-first Mirei build.

## Decision owner

There is exactly one decision owner: Mirei.

Mirei maintains positions while neither SL nor TP is reached, sells automatically at SL or TP, and performs re-entry after a completed SL/TP cycle using the original cycle capital.

There are no secondary analysis agents, agent votes, forecast agents, sentiment agents, learning agents, or suggestion feeds.

## Risk model

There are no AGGRESSIVE, BALANCED, or SAFETY modes.

The active contract is manual SL/TP:

- SL is a percentage.
- TP is a net Rupiah target.
- The reference is either HARGA ENTRY or MODAL BELI PERTAMA.
- Default session capital is Rp150,000.
- Default allocation is Rp50,000 per position.

## Position capacity

Maximum simultaneous positions: 10.

The user may use fewer than 10.

## Dashboard

Exactly one Android dashboard exists.

Primary controls:

- MULAI
- STOP
- LANJUTKAN
- TUTUP SEMUA POSISI
- ATUR SL/TP
- RESET

History is a local trade-ledger table.

There are no secondary dashboards, charts, market scanners, suggestion panels, or web/FreqUI dashboards.

## Paper market

Paper mode supports:

- saham
- forex
- kripto
- komoditas/emas

The UI is not coupled to a future broker choice. Provider-specific market-data adapters remain below the paper runtime boundary.

## TP enforcement

The stored manual net-Rupiah TP is authoritative.

When the executable market price reaches the stored TP threshold, the position is closed with reason take_profit.

No agent vote, strategy mode, suggestion, or warmup rule may suppress that TP close.

After the close, re-entry uses the original cycle capital stored for that instrument rather than adding realized TP profit to the next stake.

## HOLD

HOLD is not a prediction. It means the position remains open because neither SL nor TP has been reached and the user has not requested CLOSE ALL.

## Removed layers

The legacy Python/FastAPI runtime, Freqtrade vendor tree, web dashboard, multi-agent package, suggestion persistence, strategy modes, runtime compatibility layer, unused credential/live-exchange stub, and obsolete pre-degradation Android tests are removed.
