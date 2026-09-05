from __future__ import annotations

import json
import logging
import multiprocessing as mp
import os
import signal
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .config import settings

logger = logging.getLogger(__name__)

_RUNTIME_DIR = Path(os.getenv("FREQTRADE_RUNTIME_DIR", "/tmp/compound-scalping"))


def _supabase_db_url() -> str:
    db_url = settings.supabase_db_url.strip()
    if not db_url:
        raise RuntimeError("SUPABASE_DB_URL is required before starting Freqtrade")

    # Keep Freqtrade persistence in its own non-Data-API schema.
    parts = urlsplit(db_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["options"] = "-csearch_path=freqtrade,public"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _build_freqtrade_config() -> dict[str, Any]:
    pairs = [item.strip() for item in settings.trading_pairs.split(",") if item.strip()]
    if not pairs:
        pairs = ["BTC/IDR"]

    exchange_config: dict[str, Any] = {
        "name": settings.exchange_name,
        "key": settings.indodax_api_key,
        "secret": settings.indodax_api_secret,
        "ccxt_config": {},
        "ccxt_async_config": {},
        "pair_whitelist": pairs,
        "pair_blacklist": [],
    }

    return {
        "bot_name": settings.bot_name,
        "dry_run": not settings.is_live,
        "dry_run_wallet": settings.paper_initial_balance,
        "db_url": _supabase_db_url(),
        "exchange": exchange_config,
        "stake_currency": settings.stake_currency,
        "stake_amount": settings.stake_amount,
        "tradable_balance_ratio": 0.99,
        "max_open_trades": settings.max_open_trades,
        "fiat_display_currency": "IDR",
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
        "logfile": None,
        "verbosity": 0,
        "cancel_open_orders_on_exit": True,
        "force_entry_enable": False,
        "api_server": {"enabled": False},
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

        args: dict[str, Any] = {
            "config": [config_path],
            "command": "trade",
            "runmode": RunMode.OTHER,
        }
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
        logger.info("Starting embedded Freqtrade runtime config=%s mode=%s", self._config_path, settings.trading_mode)
        ctx = mp.get_context("spawn")
        self._process = ctx.Process(
            target=_worker_main,
            args=(str(self._config_path),),
            daemon=True,
            name="freqtrade-engine",
        )
        self._process.start()
        return {"running": True, "pid": self.pid, "message": "started"}

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
        return {
            "running": self._process.is_alive(),
            "pid": self._process.pid,
            "exitcode": self._process.exitcode,
        }

    def shutdown(self) -> None:
        try:
            self.stop()
        except Exception:
            logger.exception("Failed to shut down Freqtrade runtime")


runtime = FreqtradeRuntime()
