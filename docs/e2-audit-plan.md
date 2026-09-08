# Mirei E2 audit plan

The E2 paper execution milestone is gated on:

1. Atomic execution/ledger lifecycle: persistence must succeed before in-memory balance/position state is committed, with no partial state on ledger failure.
2. Entry fee accuracy: the OPEN ledger record stores the actual entry fee charged by the execution engine.
3. Limit-order capital reservation: pending limit orders reserve stake plus entry fee so accepted orders cannot over-commit paper balance; cancel/fill release or consume the reservation correctly.
4. End-to-end scenario: start at Rp150,000, allow up to 3 positions, execute entries and TP/SL closes, verify fees/PnL, balance recovery, position limits, and ledger lifecycle.
5. CI is the merge gate. Android build/tests must pass before merge; emulator validation remains a later milestone.
