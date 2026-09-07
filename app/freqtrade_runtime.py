from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import sqlite3
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import httpx

from .config import DEFAULT_FREQTRADE_DB_PATH, settings

logger = logging.getLogger(__name__)
_PROJECT_DIR = Path(__file__).resolve().parent.parent
_VENDOR_FREQTRADE = _PROJECT_DIR / "vendor" / "freqtrade"
if _VENDOR_FREQTRADE.is_dir() and str(_VENDOR_FREQTRADE) not in sys.path:
    sys.path.insert(0, str(_VENDOR_FREQTRADE))

_RUNTIME_DIR = Path(os.getenv("FREQTRADE_RUNTIME_DIR", str(_PROJECT_DIR / "runtime"))).resolve()
_USER_DATA_DIR = Path(os.getenv("FREQTRADE_USER_DATA_DIR", str(_PROJECT_DIR / "user_data"))).resolve()
_STRATEGY_DIR = _USER_DATA_DIR / "strategies"
_LOG_PATH = Path(os.getenv("FREQTRADE_LOG_PATH", str(_PROJECT_DIR / "logs" / "freqtrade.log"))).resolve()


def _writable_sqlite_path() -> Path:
    configured = Path(settings.freqtrade_db_path).expanduser()
    fallback = Path(DEFAULT_FREQTRADE_DB_PATH)
    for path in (configured, fallback):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(path, timeout=2) as conn:
                conn.execute("select 1")
            return path
        except (OSError, sqlite3.Error) as exc:
            logger.warning("SQLite path unavailable %s: %s", path, exc)
    raise RuntimeError("No writable SQLite path is available")


def _internal_api_password() -> str:
    if not settings.dashboard_token:
        raise RuntimeError("DASHBOARD_TOKEN must be configured before starting Freqtrade")
    return hashlib.sha256(f"{settings.dashboard_token}:freqtrade-api".encode("utf-8")).hexdigest()


def _build_freqtrade_config() -> dict[str, Any]:
    pairs = [item.strip() for item in settings.trading_pairs.split(",") if item.strip()]
    if not pairs:
        raise RuntimeError("TRADING_PAIRS must contain at least one pair")
    api_password = _internal_api_password()
    if not _STRATEGY_DIR.is_dir():
        raise RuntimeError(f"Freqtrade strategy directory not found: {_STRATEGY_DIR}")

    exchange_config: dict[str, Any] = {
        "name": settings.exchange_name,
        "ccxt_config": {},
        "ccxt_async_config": {},
        "pair_whitelist": pairs,
        "pair_blacklist": [],
        "enable_ws": False,
    }
    if settings.live_ready:
        exchange_config["key"] = settings.indodax_api_key
        exchange_config["secret"] = settings.indodax_api_secret

    # Development/paper mode is intentionally started automatically. This is
    # safe because live_ready is false unless live mode, the explicit live
    # switch, and both Indodax credentials are present.
    initial_state = "running" if settings.should_auto_start else "stopped"

    return {
        "bot_name": settings.bot_name,
        "dry_run": not settings.live_ready,
        "dry_run_wallet": settings.paper_initial_balance,
        "db_url": f"sqlite:///{_writable_sqlite_path()}",
        "exchange": exchange_config,
        "pairlists": [{"method": "StaticPairList"}],
        "stake_currency": settings.stake_currency,
        "stake_amount": settings.stake_amount,
        "tradable_balance_ratio": 0.99,
        "max_open_trades": settings.max_open_trades,
        "fiat_display_currency": "USD",
        "timeframe": settings.timeframe,
        "strategy": settings.strategy_name,
        "strategy_path": str(_STRATEGY_DIR),
        "user_data_dir": str(_USER_DATA_DIR),
        "entry_pricing": {"price_side": "same", "use_order_book": False},
        "exit_pricing": {"price_side": "same", "use_order_book": False},
        "order_types": {
            "entry": "market",
            "exit": "market",
            "force_entry": "market",
            "force_exit": "market",
            "emergency_exit": "market",
            "stoploss": "market",
            "stoploss_on_exchange": False,
        },
        "initial_state": initial_state,
        "force_entry_enable": True,
        "internals": {
            "process_throttle_secs": settings.process_throttle_secs,
            "heartbeat_interval": settings.heartbeat_interval,
            "sd_notify": False,
        },
        "logfile": str(_LOG_PATH),
        "verbosity": 0,
        "cancel_open_orders_on_exit": True,
        "api_server": {
            "enabled": True,
            "listen_ip_address": "127.0.0.1",
            "listen_port": settings.freqtrade_api_port,
            "verbosity": "error",
            "enable_openapi": False,
            "jwt_secret_key": settings.effective_freqtrade_jwt_secret,
            "CORS_origins": [],
            "username": settings.freqtrade_api_username,
            "password": api_password,
            "ws_token": api_password,
        },
    }


def _write_config() -> Path:
    _RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, path = tempfile.mkstemp(prefix="freqtrade-", suffix=".json", dir=_RUNTIME_DIR)
    os.close(fd)
    config_path = Path(path)
    config_path.write_text(json.dumps(_build_freqtrade_config(), indent=2), encoding="utf-8")
    return config_path


def _worker_main(config_path: str) -> None:
    from freqtrade.configuration import Configuration
    from freqtrade.enums import RunMode
    from freqtrade.worker import Worker

    runmode = RunMode.LIVE if settings.live_ready else RunMode.DRY_RUN
    args: dict[str, Any] = {"config": [config_path], "command": "trade", "runmode": runmode}
    config = Configuration(args, runmode).get_config()
    worker = Worker(args, config=config)
    runtime._worker = worker
    worker.run()


class FreqtradeRuntime:
    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._worker: Any | None = None
        self._config_path: Path | None = None
        self._error: str | None = None
        self._exitcode: int | None = None

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    @property
    def api_password(self) -> str:
        return _internal_api_password()

    def boot(self) -> dict[str, Any]:
        if self.running:
            return {"running": True, "message": "already_running"}
        self._error = None
        self._exitcode = None
        self._worker = None
        self._config_path = _write_config()
        self._thread = threading.Thread(
            target=self._thread_entry,
            args=(str(self._config_path),),
            daemon=True,
            name="freqtrade-engine",
        )
        self._thread.start()
        return {
            "running": True,
            "message": "booted",
            "dry_run": not settings.live_ready,
            "auto_started": settings.should_auto_start,
        }

    def _thread_entry(self, config_path: str) -> None:
        try:
            _worker_main(config_path)
            self._exitcode = 0
        except Exception as exc:
            self._error = f"{type(exc).__name__}: {exc}"
            self._exitcode = 1
            logger.exception("Embedded Freqtrade worker crashed")

    async def wait_for_api(self, timeout: float = 30.0) -> None:
        deadline = time.monotonic() + timeout
        url = f"http://127.0.0.1:{settings.freqtrade_api_port}/api/v1/ping"
        last_error: Exception | None = None
        async with httpx.AsyncClient(timeout=2.0) as client:
            while time.monotonic() < deadline:
                if self._error:
                    raise RuntimeError(f"Freqtrade failed to boot: {self._error}")
                if not self.running:
                    raise RuntimeError("Freqtrade worker exited before its API became ready")
                try:
                    response = await client.get(url)
                    if response.status_code == 200:
                        return
                    last_error = RuntimeError(f"Freqtrade API ping returned HTTP {response.status_code}")
                except Exception as exc:
                    last_error = exc
                await asyncio.sleep(0.5)
        raise RuntimeError("Freqtrade API did not become ready") from last_error

    def _wait_for_api_sync(self, timeout: float = 30.0) -> None:
        deadline = time.monotonic() + timeout
        url = f"http://127.0.0.1:{settings.freqtrade_api_port}/api/v1/ping"
        while time.monotonic() < deadline:
            if self._error:
                raise RuntimeError(f"Freqtrade failed to boot: {self._error}")
            if not self.running:
                raise RuntimeError("Freqtrade worker exited before its API became ready")
            try:
                if httpx.get(url, timeout=2.0).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        raise RuntimeError("Freqtrade API did not become ready")

    def _api_command(self, command: str) -> dict[str, Any]:
        self._wait_for_api_sync()
        url = f"http://127.0.0.1:{settings.freqtrade_api_port}/api/v1/{command}"
        with httpx.Client(timeout=10.0) as client:
            response = client.post(url, auth=(settings.freqtrade_api_username, self.api_password))
        if response.status_code >= 400:
            raise RuntimeError(f"Freqtrade /{command} returned HTTP {response.status_code}: {response.text[:300]}")
        return response.json()

    def start(self) -> dict[str, Any]:
        boot_result = self.boot()
        if settings.should_auto_start:
            return {**boot_result, "message": "started", "trading": True}
        api_result = self._api_command("start")
        return {**boot_result, "message": "started", "trading": True, "api": api_result}

    def stop(self) -> dict[str, Any]:
        if not self.running:
            return {"running": False, "message": "not_running"}
        try:
            result = self._api_command("stop")
            return {"running": True, "message": "trading_stopped", "api": result}
        except Exception as exc:
            logger.exception("Native Freqtrade stop failed")
            return {"running": True, "message": "stop_failed", "error": str(exc)}

    def status(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "error": self._error,
            "exitcode": self._exitcode,
            "auto_start": settings.should_auto_start,
            "mode": settings.trading_mode,
        }

    def diagnostics(self) -> dict[str, Any]:
        tail: list[str] = []
        try:
            if _LOG_PATH.exists():
                tail = _LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()[-80:]
        except OSError as exc:
            tail = [f"log_read_error: {type(exc).__name__}: {exc}"]
        return {
            "runtime": self.status(),
            "api_port": settings.freqtrade_api_port,
            "dry_run": not settings.live_ready,
            "exchange": settings.exchange_name,
            "pairs": [item.strip() for item in settings.trading_pairs.split(",") if item.strip()],
            "strategy": settings.strategy_name,
            "strategy_dir_exists": _STRATEGY_DIR.is_dir(),
            "sqlite_path": str(_writable_sqlite_path()),
            "log_path": str(_LOG_PATH),
            "log_tail": tail,
        }

    def shutdown(self) -> None:
        self._thread = None
        self._worker = None
        if self._config_path:
            self._config_path.unlink(missing_ok=True)
            self._config_path = None


runtime = FreqtradeRuntime()
