# Persistent trade ledger milestone

The paper execution layer now exposes a TradeLedger contract and a SQLite implementation. Open and close lifecycle events can be persisted in the existing `trades` table without coupling execution code directly to Android storage.
