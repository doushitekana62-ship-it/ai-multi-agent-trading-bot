"""Self-healing wrapper around the canonical Cloudflare Worker entrypoint.

The canonical worker remains the routing authority. This wrapper only repairs a
missing Durable Object alarm when paper mode is already enabled, so a transient
lost alarm cannot leave the paper session silently stale.
"""
from __future__ import annotations

from worker_entry_api import Default as CanonicalDefault, _state_stub


class Default(CanonicalDefault):
    """Keep the canonical routes while re-arming an enabled paper scheduler."""

    async def fetch(self, request):
        try:
            stub = await _state_stub(self.env)
            await stub.ensure_scheduler()
        except Exception as exc:
            print(f"[worker:scheduler-recovery] type={type(exc).__name__}: {exc}")
        return await super().fetch(request)


__all__ = ["Default"]
