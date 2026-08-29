"""Compatibility entrypoint.

Production is served by ``worker_entry_api.py`` as configured in wrangler.jsonc.
Keep this module as a thin compatibility import so the repository has one
routing implementation and cannot drift between two Worker entrypoints.
"""

from worker_entry_api import Default, PaperTradingState

__all__ = ["Default", "PaperTradingState"]
