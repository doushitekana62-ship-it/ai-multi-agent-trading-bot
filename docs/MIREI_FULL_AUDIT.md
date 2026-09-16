# Mirei Full Audit

## Runtime control invariants

- MULAI with initial allocations creates a new portfolio session only when the previous session is stopped.
- LANJUTKAN sends no initial allocations and only resumes the persisted session.
- MULAI is rejected while RUNNING or HOLD to prevent replacing a live session accidentally.
- JEDA/HOLD only pauses the runtime loop; it does not clear session state.
- BERHENTI stops the runtime loop but preserves the persisted session for LANJUTKAN.
- RESET SESI clears the persisted portfolio session but does not delete audit history.
- HAPUS RIWAYAT deletes history only; it does not mutate the live portfolio session.
- TERAPKAN PERUBAHAN RISIKO updates the active runtime risk configuration; it does not replace session capital or position count.
- VERIFIKASI MANUAL / RE-ENTRY is an execution confirmation path only and is not an alternate decision engine.
- RESET JAM changes display/session timing metadata only.
- TUTUP SEMUA POSISI closes positions and does not silently create a new session.

## Engine invariants

- MireiDecisionEngine remains the sole entry/risk gate.
- Runtime configuration changes are propagated into the decision engine rather than leaving it bound to construction-time configuration.
- Python/Freqtrade remains reference/legacy code and is not invoked by the Android runtime.
- Live exchange execution remains disabled; the Android runtime uses paper execution.
