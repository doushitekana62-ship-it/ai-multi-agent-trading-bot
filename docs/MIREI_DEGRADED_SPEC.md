# Mirei Degraded Specification

This document replaces the previous multi-agent and multi-dashboard requirements.

## 1. Decision owner

There is exactly one decision owner: Mirei.

Mirei is responsible for maintaining an open position while neither SL nor TP is reached, automatic SELL at SL, automatic SELL at TP, automatic RE-ENTRY after a completed SL/TP cycle, and preserving the original cycle capital for re-entry.

There are no separate candle, momentum, forecast, sentiment, risk, learning, or suggestion agents.

## 2. Risk model

The application exposes no AGGRESSIVE, BALANCED, or SAFETY mode.

The active contract is manual SL/TP.

SL is configured as a percentage.

TP is configured as a net Rupiah target.

The reference can be HARGA ENTRY or MODAL BELI PERTAMA.

The default session capital is Rp150,000 and the default position allocation is Rp50,000.

## 3. Position capacity

The maximum is 10 simultaneous positions. The user may use fewer than 10.

## 4. Dashboard

There is exactly one Android dashboard.

The only primary controls are:

- MULAI
- STOP
- LANJUTKAN
- TUTUP SEMUA POSISI
- ATUR SL/TP
- RESET

History remains a real table backed by the local trade ledger.

No secondary dashboard, tabbed market dashboard, scanner, chart, suggestion view, or FreqUI/web dashboard is part of the application.

## 5. Paper market

Paper mode supports saham, forex, kripto, and komoditas/emas.

The dashboard does not depend on a specific future broker choice.

## 6. TP enforcement

A manual net-Rupiah TP is authoritative.

When the observed executable price reaches the stored TP price, the position is closed with reason take_profit.

There is no AI veto, suggestion veto, warmup rule, agent vote, or strategy mode that can suppress the TP close.

After the position is closed, the re-entry cycle uses the original capital reference stored for that position rather than compounding the TP profit into the next stake.

## 7. HOLD

HOLD is not a prediction.

It is simply the state in which Mirei keeps the existing position open because neither SL nor TP has been reached and the user has not requested CLOSE ALL.

## 8. Removed layers

The following legacy layers are intentionally removed:

- Python/FastAPI application
- Freqtrade vendor tree
- web/static dashboard
- FreqUI deployment
- multi-agent package
- agent evidence library
- suggestion persistence
- strategy-mode configuration
- runtime compatibility aliases
- unused credential/live-exchange stubs
- obsolete pre-degradation Android tests

The remaining repository is Android-first and paper-runtime focused.
