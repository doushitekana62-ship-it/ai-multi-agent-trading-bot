# Mirei Android-First Migration Plan

## Audit finding

The current repository is server-first: FastAPI owns the runtime and starts an embedded Freqtrade worker; the existing dashboard is a static web frontend. The current configuration is Indodax-only, defaults to one open trade, and contains server-side exchange credentials.

## Required architectural change

Move orchestration and primary state to Android while preserving the proven strategy/risk components where feasible.

Target layers:

1. Android UI
2. Android foreground runtime/service
3. Mirei orchestration and decision engine
4. Market/data adapters
5. Forecast/sentiment/candle agents
6. Risk and position-sizing engine
7. Exchange adapters/execution
8. Local persistence
9. Optional manual Google Drive backup

## Migration principles

- Do not expose exchange secrets to a remote server.
- Do not make Supabase a runtime dependency.
- Do not retain FastAPI solely for architectural consistency if Android can execute the required function locally.
- Keep Freqtrade only where its execution/strategy compatibility is demonstrably useful on the target Android runtime.
- Introduce an exchange abstraction before adding a second exchange.
- Keep paper and live decisions identical; only execution differs.
- Keep live trading disabled until paper/reconciliation/recovery tests pass.

## Existing reusable components

The repository already contains:

- forecast agent
- regime engine
- risk engine
- scalping theory library
- signal engine
- market snapshot handling
- Freqtrade strategy
- runtime monitor
- automated Python tests
- Freqtrade vendoring workflow

These should be audited and adapted rather than rewritten blindly.

## Known mismatches to resolve

1. Current config hard-codes Indodax.
2. Current default max open trades is 1; Mirei requires 3 by default.
3. Current default stake is 100,000 IDR; Mirei requires 50,000 IDR per slot by default.
4. Current strategy has fixed legacy entry gates and fixed ROI/stoploss values that do not yet represent Mirei's adaptive TP/SL requirements.
5. Current server configuration contains dashboard/FastAPI assumptions that are no longer the target architecture.
6. Current repository documentation describes a GitHub Pages -> FastAPI -> Freqtrade architecture and must be updated as migration proceeds.
7. Android foreground execution, local database, secure credential storage, multi-exchange adapters, notifications, and paper execution are not yet present in the audited tree.

## Safe implementation order

1. Freeze and document requirements.
2. Separate exchange interfaces from strategy decisions.
3. Make risk/position sizing configurable and testable.
4. Define Mirei runtime state machine.
5. Implement local persistence model.
6. Implement paper execution.
7. Implement Android service/runtime.
8. Integrate one exchange adapter.
9. Add notifications and recovery.
10. Add second exchange adapter.
11. Add Mirei Take Over with explicit warning/audit.
12. Run paper trading and seven-day evaluation.
13. Enable live trading only after explicit user approval.
