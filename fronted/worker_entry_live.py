"""Production Worker entrypoint.

Keep the production entrypoint as a thin compatibility layer over the
validated dashboard API entrypoint. This avoids maintaining two independent
HTTP routing implementations that can drift or fail differently.
"""
from worker_entry_api import Default, PaperTradingState

__all__ = ["Default", "PaperTradingState"]
