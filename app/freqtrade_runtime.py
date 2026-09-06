from __future__ import annotations

import json
import logging
import multiprocessing as mp
import os
import signal
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

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
            if path != configured:
                logger.warning("Configured SQLite path is not writable; using fallback %s", path)
            return path
        except (OSError, sqlite3.Error) as exc:
            logger.warning("SQLite path unavailable %s: %s", path, exc)

    raise RuntimeError("No writable SQLite path is available")


def _sqlite_db_url() -> str:
    path = _writable_sqlite_path()
    return f"sqlite:///{path}"


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

    dry_run = not settings.live_ready
    return {
        "bot_name": settings.bot_name,
        "dry_run": dry_run,
        "dry_run_wallet": settings.paper_initial_balance,
        "db_url": _sqlite_db_url(),
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
        "order_types": {
            "entry": "market",
            "exit": "market",
            "stoploss": "market",
            "stoploss_on_exchange": False,
        },
        "initial_state": "running",
        "internals": {
            "process_throttle_secs": settings.process_throttle_secs,
            "heartbeat_interval": settings.heartbeat_interval,
            "sd_notify": False,
        },
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
    try:
        from freqtrade.configuration import Configuration
        from freqtrade.enums import RunMode
        from freqtrade.worker import Worker

        args: dict[str, Any] = {"config": [config_path], "command": "trade", "runmode": RunMode.OTHER}
        config = Configuration(args, RunMode.OTHER).get_config()
        worker = Worker(args, config=config)

        def _stop(_signum: int, _frame: Any) -> None:
            logger.info("Freqtrade child received stop signal")
            raise KeyboardInterrupt()

        signal.signal(signal.SIGTERM, _stop)
        signal.signal(signal.SIGINT, _stop)
        worker.run()
    except KeyboardInterrupt:
        logger.info("Freqtrade child stopped")
    except Exception:
        logger.exception("Freqtrade child crashed")
        raise


class FreqtradeRuntime:
    def __init__(self) -> None:
        self._process: mp.Process | None = None
        self._config_path: Path | None = None

    @property
    def running(self) -> bool:
        return bool(self._process and self._process.is_alive())

    @property
    def pid(self) -> int | None:
        return self._process.pid if self._process else None

    def start(self) -> dict[str, Any]:
        if self.running:
            return {"running": True, "pid": self.pid, "message": "already_running"}
        self._config_path = _write_config()
        logger.info("Starting embedded Freqtrade runtime exchange=%s mode=%s dry_run=%s", settings.exchange_name, settings.trading_mode, not settings.live_ready)
        ctx = mp.get_context("spawn")
        self._process = ctx.Process(target=_worker_main, args=(str(self._config_path),), daemon=True, name="freqtrade-engine")
        self._process.start()
        return {"running": True, "pid": self.pid, "message": "started", "dry_run": not settings.live_ready}

    def stop(self) -> dict[str, Any]:
        if not self._process:
            return {"running": False, "pid": None, "message": "not_running"}
        if self._process.is_alive():
            logger.info("Stopping embedded Freqtrade runtime pid=%s", self._process.pid)
            self._process.terminate()
            self._process.join(timeout=20)
            if self._process.is_alive():
                logger.error("Freqtrade child did not stop gracefully; killing pid=%s", self._process.pid)
                self._process.kill()
                self._process.join(timeout=5)
        pid = self._process.pid
        self._process = None
        if self._config_path:
            self._config_path.unlink(missing_ok=True)
            self._config_path = None
        return {"running": False, "pid": pid, "message": "stopped"}

    def status(self) -> dict[str, Any]:
        if not self._process:
            return {"running": False, "pid": None, "exitcode": None}
        return {"running": self._process.is_alive(), "pid": self._process.pid, "exitcode": self._process.exitcode}

    def shutdown(self) -> None:
        try:
            self.stop()
        except Exception:
            logger.exception("Failed to shut down Freqtrade runtime")


runtime = FreqtradeRuntime()
