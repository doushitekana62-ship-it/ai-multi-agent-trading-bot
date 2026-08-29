"""Production Cloudflare Worker entrypoint.

All HTTP/dashboard routing lives in worker_entry_api.py. This file is only the
production adapter required by Wrangler, preventing duplicate routing logic
from drifting between entrypoints.
"""
from worker_entry_api import Default, PaperTradingState

__all__ = ["Default", "PaperTradingState"]
