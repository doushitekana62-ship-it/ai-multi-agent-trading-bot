"""Ensure the vendored Freqtrade source is importable in deployments."""

from pathlib import Path
import sys

_PROJECT_ROOT = Path(__file__).resolve().parent
_VENDORED_FREQTRADE = _PROJECT_ROOT / "vendor" / "freqtrade"

if _VENDORED_FREQTRADE.is_dir():
    vendored_path = str(_VENDORED_FREQTRADE)
    if vendored_path not in sys.path:
        sys.path.insert(0, vendored_path)
