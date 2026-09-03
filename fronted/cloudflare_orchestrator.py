from __future__ import annotations

from typing import Any, Dict

from core.indodax_scalping_strategy import analyze as analyze_indodax


class CloudflareOrchestrator:
    """Single Cloudflare-side analysis adapter; execution remains in paper state."""

    def __init__(self, env: Any):
        self.env = env

    @staticmethod
    def _number(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _namespace(env: Any) -> Any:
        return getattr(env, "PAPER_STATE", None)

    def analyze(self, symbol: str, market_data: Dict[str, Any]) -> Dict[str, Any]:
        result = analyze_indodax(symbol, market_data)
        if not isinstance(result, dict):
            return {
                "action": "HOLD",
                "confidence": 0.0,
                "reason": "INVALID_ANALYSIS_RESULT",
                "data_source": "INDODAX public market data",
            }
        return result

    async def get_state(self, pair: str = "btc_idr") -> Dict[str, Any]:
        namespace = self._namespace(self.env)
        if namespace is None:
            return {}
        return {}
