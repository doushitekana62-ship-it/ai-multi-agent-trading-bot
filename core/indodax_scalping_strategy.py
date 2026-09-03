"""Canonical Indodax compounding-scalping strategy."""
from __future__ import annotations
from typing import Any, Dict
from fronted.core.indodax_scalping_strategy import analyze as _analyze

def analyze(symbol: str, market_data: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
    return _analyze(symbol, market_data, **kwargs)
