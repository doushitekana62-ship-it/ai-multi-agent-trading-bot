from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .freqtrade_runtime import runtime
from .logging_config import configure_logging
from .market_snapshot import collector
from .routers import dashboard, freqtrade_ui, health, trading
from .runtime_monitor import monitor

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    logger.info("FastAPI runtime booting version=%s mode=%s", settings.app_version, settings.trading_mode)
    boot_error = None
    try:
        runtime.boot()
    except Exception as exc:
        boot_error = f"{type(exc).__name__}: {exc}"
        logger.exception("Embedded Freqtrade API boot failed")
    await collector.start()
    await monitor.start()
    if boot_error:
        logger.error("FastAPI remains available for diagnostics; engine is unhealthy: %s", boot_error)
    yield
    logger.info("FastAPI runtime shutting down")
    await monitor.stop()
    await collector.stop()
    runtime.shutdown()


app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)

origins = [item.strip() for item in settings.cors_origins.split(",") if item.strip()]
if origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )


@app.middleware("http")
async def request_logging(request: Request, call_next):
    started = time.perf_counter()
    try:
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.info("request method=%s path=%s status=%s duration_ms=%.2f", request.method, request.url.path, response.status_code, elapsed_ms)
        return response
    except Exception:
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.exception("request_failed method=%s path=%s duration_ms=%.2f", request.method, request.url.path, elapsed_ms)
        raise


app.include_router(health.router, prefix="/api")
app.include_router(trading.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(freqtrade_ui.router)


@app.get("/")
async def root():
    runtime_status = runtime.status()
    return {
        "name": "compound-scalping",
        "engine": "freqtrade-embedded",
        "api": "fastapi",
        "database": "local-sqlite",
        "frontend": "github-pages",
        "status": "ready" if runtime_status["running"] and not runtime_status["error"] else "degraded",
        "trading_mode": settings.trading_mode,
        "live_ready": settings.live_ready,
        "engine_runtime": runtime_status,
    }
