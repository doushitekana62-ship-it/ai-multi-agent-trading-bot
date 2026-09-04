import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routes.auth import router as auth_router
from backend.routes.dashboard import router as dashboard_router
from backend.routes.exchange import router as exchange_router
from backend.routes.market import router as market_router
from backend.routes.paper_control import router as paper_control_router
from backend.routes.reports import router as reports_router

APP_VERSION = "2.0.0"
APP_ENTRYPOINT = "backend.api:app"

app = FastAPI(title="AI Multi-Agent Trading Bot API", version=APP_VERSION)


def _cors_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "")
    defaults = {
        "http://localhost:3000",
        "http://localhost:5173",
        "https://doushitekana62-ship-it.github.io",
    }
    configured = {origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip()}
    return sorted(defaults | configured)


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "Cache-Control"],
)

app.include_router(auth_router, prefix="/api/auth", tags=["Authentication"])
app.include_router(dashboard_router, prefix="/api/dashboard", tags=["Dashboard"])
app.include_router(market_router, prefix="/api/market", tags=["Market Data"])
app.include_router(paper_control_router, prefix="/api/dashboard/paper", tags=["Paper Trading"])
app.include_router(exchange_router, prefix="/api/exchange", tags=["Exchange"])
app.include_router(reports_router, prefix="/api/reports", tags=["Reports"])


@app.get("/")
async def root():
    return {
        "status": "online",
        "service": "AI Multi-Agent Trading Bot API",
        "runtime": "fastapi",
        "version": APP_VERSION,
        "entrypoint": APP_ENTRYPOINT,
    }


@app.get("/health")
async def health():
    # Deployment identity is intentionally part of the health contract so a stale
    # FastAPI Cloud deployment cannot be mistaken for the current backend.
    return {
        "status": "healthy",
        "service": "ai-multi-agent-trading-bot-api",
        "version": APP_VERSION,
        "entrypoint": APP_ENTRYPOINT,
        "paper_mode": True,
        "real_trading_locked": True,
    }


@app.get("/ready")
async def ready():
    from backend.core.database import db
    return {
        "status": "ready" if db.is_connected() else "degraded",
        "supabase": db.is_connected(),
        "paper_mode": True,
        "real_trading_locked": True,
        "entrypoint": APP_ENTRYPOINT,
    }
