"""Compatibility facade for the canonical Cloudflare compounding strategy.

The implementation lives in fronted/core/indodax_scalping_strategy.py because
that package is the Cloudflare Worker import root. Keeping this module as a
facade prevents a second strategy implementation from drifting.
"""
from fronted.core.indodax_scalping_strategy import *
from fronted.core.indodax_scalping_strategy import _candles, _clip, _move, _num, _pulse, _rsi, _role, _ts
