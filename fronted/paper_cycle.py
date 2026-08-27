"""Lightweight paper-only cycle for Cloudflare Python Workers.

This module intentionally avoids numpy, pandas, scipy, sklearn, ccxt and other
native/heavy dependencies. It is the first Cloudflare-native validation path.
It consumes public Indodax market data and calculates small deterministic
indicators. It never places a live order and does not fake an execution.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from js import fetch
from pyodide.ffi import to_js

INDODAX_PUBLIC_BASE = "https://indodax.com/api"


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_pair(value: str) -> str:
    raw = str(value or "BTC/IDR").strip().upper().replace("-", "/")
    if "/" not in raw:
        raw = f"{raw}/IDR"
    base, quote = raw.split("/", 1)
    allowed = {"BTC", "ETH", "USDT", "XRP", "DOGE", "SOL", "HYPE", "FARTCOIN", "1INCH", "AAVE", "ARB"}
    if base not in allowed or quote != "IDR":
        return "BTC/IDR"
    return f"{base}/IDR"


def _api_pair(pair: str) -> str:
    return normalize_pair(pair).replace("/", "_").lower()


async def _indodax(path: str):
    try:
        response = await fetch(
            f"{INDODAX_PUBLIC_BASE}{path}",
            to_js({"method": "GET", "headers": {"Accept": "application/json"}}),
        )
        if int(response.status) >= 400:
            return None
        return json.loads(await response.text())
    except Exception:
        return None


def _prices(trades):
    values = []
    for row in trades or []:
        price = _safe_float(row.get("price")) if isinstance(row, dict) else 0.0
        if price > 0:
            values.append(price)
    return values[-60:]


def _rsi(values, period=14):
    if len(values) <= period:
        return 50.0
    gains = []
    losses = []
    for i in range(len(values) - period, len(values)):
        change = values[i] - values[i - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    return 100.0 - (100.0 / (1.0 + (avg_gain / avg_loss)))


def _ema(values, period):
    if not values:
        return 0.0
    alpha = 2.0 / (period + 1.0)
    ema = values[0]
    for value in values[1:]:
        ema = (value * alpha) + (ema * (1.0 - alpha))
    return ema


def _macd(values):
    if len(values) < 26:
        return 0.0, 0.0, 0.0
    fast = _ema(values, 12)
    slow = _ema(values, 26)
    macd = fast - slow
    signal = macd * 0.7
    return macd, signal, macd - signal


def _score(rsi, histogram, momentum):
    score = 0.0
    if rsi <= 30:
        score += 0.45
    elif rsi >= 70:
        score -= 0.45
    else:
        score += (50.0 - rsi) / 100.0
    score += max(-0.30, min(0.30, histogram / max(abs(histogram), 1.0) * 0.30))
    score += max(-0.25, min(0.25, momentum / 2.0))
    return max(-1.0, min(1.0, score))


def _decision(score, confidence):
    if confidence < 0.60:
        return "HOLD"
    if score >= 0.55:
        return "BUY"
    if score <= -0.55:
        return "SELL"
    return "HOLD"


async def run_lightweight_paper_cycle(pair: str = "BTC/IDR"):
    symbol = normalize_pair(pair)
    api_pair = _api_pair(symbol)
    ticker_response = await _indodax(f"/{api_pair}/ticker")
    trades_response = await _indodax(f"/{api_pair}/trades")

    ticker = ticker_response.get("ticker", {}) if isinstance(ticker_response, dict) else {}
    trades = trades_response.get("trades", []) if isinstance(trades_response, dict) else []
    prices = _prices(trades)
    current_price = _safe_float(ticker.get("last"))
    if current_price <= 0 and prices:
        current_price = prices[-1]
    if current_price <= 0:
        raise RuntimeError("Indodax market data unavailable")

    rsi = _rsi(prices)
    macd, signal, histogram = _macd(prices)
    momentum = 0.0
    if len(prices) >= 10 and prices[-10] > 0:
        momentum = ((prices[-1] - prices[-10]) / prices[-10]) * 100.0

    score = _score(rsi, histogram, momentum)
    confidence = min(0.95, max(0.35, 0.50 + abs(score) * 0.45))
    action = _decision(score, confidence)

    now = datetime.now(timezone.utc).isoformat()
    trend = "BULLISH" if score >= 0.25 else "BEARISH" if score <= -0.25 else "NEUTRAL"
    return {
        "status": "completed",
        "stage": "cloudflare_lightweight_paper",
        "symbol": symbol,
        "mode": "paper",
        "action": action,
        "confidence": round(confidence, 4),
        "score": round(score, 4),
        "current_price": current_price,
        "indicators": {
            "rsi": round(rsi, 3),
            "macd": round(macd, 8),
            "macd_signal": round(signal, 8),
            "macd_histogram": round(histogram, 8),
            "momentum_percent": round(momentum, 5),
            "trend": trend,
        },
        "market": {
            "high": _safe_float(ticker.get("high")),
            "low": _safe_float(ticker.get("low")),
            "buy": _safe_float(ticker.get("buy")),
            "sell": _safe_float(ticker.get("sell")),
            "volume_idr": _safe_float(ticker.get("vol_idr")),
            "samples": len(prices),
            "source": "INDODAX public market data",
        },
        "paper_execution": {
            "executed": False,
            "live_order": False,
            "reason": "Decision-only validation cycle; paper order execution remains disabled until the shared paper engine is wired.",
        },
        "created_at": now,
    }
