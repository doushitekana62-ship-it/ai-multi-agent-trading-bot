"""Compatibility entrypoint.

The production service is now the canonical FastAPI application in backend.api.
This module remains as a compatibility import for existing FastAPI Cloud projects.
"""
from backend.api import app

__all__ = ["app"]
