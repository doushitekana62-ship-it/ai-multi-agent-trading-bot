# Mirei runtime boundary

For the Android 6-hour paper validation, the active trading runtime is the Android foreground-service path under `android/`.

The Python/FastAPI/Freqtrade code under `app/`, `user_data/`, and `vendor/freqtrade/` is retained as legacy/reference code. It is not invoked by the Android lifecycle and must not be treated as a second active trading brain.

The historical Python configuration may still contain legacy settings such as a hard-coded `trading_active` value. This is intentionally not changed as part of the Android validation because changing it would make the legacy server path appear active again. If that backend is ever revived, it needs a separate migration/audit before use.

Live exchange order execution remains disabled. Yahoo Finance is a public market-data paper provider and is not an order-execution venue in this validation scope.
