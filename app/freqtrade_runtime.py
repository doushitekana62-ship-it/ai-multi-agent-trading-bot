from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import httpx

from .config import DEFAULT_FREQTRADE_DB_PATH, settings

logger = logging.getLogger(__name__)
_RUNTIME_DIR = Path(os.getenv("FREQTRADE_RUNTIME_DIR", "/tmp/compound-scalping"))


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


def _build_freqtrade_config() -> dict[str, Any]:
    pairs = [item.strip() for item in settings.trading_pairs.split(",") if item.strip()]
    if not pairs:
        raise RuntimeError("TRADING_PAIRS must contain at least one pair")
    if not settings.dashboard_token:
        raise RuntimeError("DASHBOARD_TOKEN must be configured before starting Freqtrade")

    exchange_config: dict[str, Any] = {
        "name": settings.exchange_name,
        "ccxt_config": {},
        "ccxt_async_config": {},
        "pair_whitelist": pairs,
        "pair_blacklist": [],
    }
    if settings.live_ready:
        exchange_config["key"] = settings.indodax_api_key
        exchange_config["secret"] = settings.indodax_api_secret

    return {
        "bot_name": settings.bot_name,
        "dry_run": not settings.live_ready,
        "dry_run_wallet": settings.paper_initial_balance,
        "db_url": f"sqlite:///{_writable_sqlite_path()}",
        "exchange": exchange_config,
        "stake_currency": settings.stake_currency,
        "stake_amount": settings.stake_amount,
        "tradable_balance_ratio": 0.99,
        "max_open_trades": settings.max_open_trades,
        "fiat_display_currency": "USD",
        "timeframe": settings.timeframe,
        "strategy": settings.strategy_name,
        "strategy_path": str(Path("/app/user_data/strategies").resolve()),
        "user_data_dir": "/app/user_data",
        "entry_pricing": {"price_side": "same", "use_order_book": False},
        "exit_pricing": {"price_side": "same", "use_order_book": False},
        "order_types": {"entry": "market", "exit": "market", "stoploss": "market", "stoploss_on_exchange": False},
        "initial_state": "stopped",
        "internals": {"process_throttle_secs": settings.process_throttle_secs, "heartbeat_interval": settings.heartbeat_interval, "sd_notify": False},
        "logfile": "/tmp/compound-scalping/freqtrade.log",
        "verbosity": 0,
        "cancel_open_orders_on_exit": True,
        "force_entry_enable": False,
        "api_server": {
            "enabled": True,
            "listen_ip_address": "127.0.0.1",
            "listen_port": settings.freqtrade_api_port,
            "verbosity": "error",
            "enable_openapi": False,
            "jwt_secret_key": settings.effective_freqtrade_jwt_secret,
            "CORS_origins": [],
            "username": settings.freqtrade_api_username,
            "password": settings.dashboard_token,
            "ws_token": settings.dashboard_token,
        },
    }


def _write_config() -> Path:
    _RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    fd, path = tempfile.mkstemp(prefix="freqtrade-", suffix=".json", dir=_RUNTIME_DIR)
    os.close(fd)
    config_path = Path(path)
    config_path.write_text(json.dumps(_build_freqtrade_config(), indent=2), encoding="utf-8")
    return config_path


def _worker_main(config_path: str) -> None:
    from freqtrade.configuration import Configuration
    from freqtrade.enums import RunMode
    from freqtrade.worker import Worker

    args: dict[str, Any] = {"config": [config_path], "command": "trade", "runmode": RunMode.OTHER}
    config = Configuration(args, RunMode.OTHER).get_config()
    worker = Worker(args, config=config)
    runtime._worker = worker
    worker.run()


class FreqtradeRuntime:
    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._worker: Any | None = None
        self._config_path: Path | None = None
        self._error: str | None = None

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def boot(self) -> dict[str, Any]:
        """Run Freqtrade in-process so FastAPI Cloud can keep its native API alive."""
        if self.running:
            return {"running": True, "message": "already_running"}
        self._error = None
        self._worker = None
        self._config_path = _write_config()
        self._thread = threading.Thread(target=self._thread_entry, args=(str(self._config_path),), daemon=True, name="freqtrade-engine")
        self._thread.start()
        return {"running": True, "message": "booted", "dry_run": not settings.live_ready}

    def _thread_entry(self, config_path: str) -> None:
        try:
            _worker_main(config_path)
        except Exception as exc:
            self._error = str(exc)
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
            response = client.post(url, auth=(settings.freqtrade_api_username, settings.dashboard_token))
        if response.status_code >= 400:
            raise RuntimeError(f"Freqtrade /{command} returned HTTP {response.status_code}: {response.text[:300]}")
        return response.json()

    def start(self) -> dict[str, Any]:
        boot_result = self.boot()
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
        return {"running": self.running, "error": self._error}

    def shutdown(self) -> None:
        # The worker thread is daemonized; the platform terminates it with the FastAPI process.
        self._thread = None
        self._worker = None
        if self._config_path:
            self._config_path.unlink(missing_ok=True)
            self._config_path = None


runtime = FreqtradeRuntime()
