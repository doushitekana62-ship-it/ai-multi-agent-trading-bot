"""Cloudflare Python Workers ASGI compatibility shim.

The current Workers runtime exposes the ASGI adapter as ``workers.asgi``.
Some legacy code in this repository imports the historical top-level ``asgi``
module, so keep that import stable without changing the trading pipeline.
"""

from workers import asgi as _asgi

fetch = _asgi.fetch
entrypoint = _asgi.entrypoint

__all__ = ["fetch", "entrypoint"]
