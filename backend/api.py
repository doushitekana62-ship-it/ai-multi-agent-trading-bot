import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routes.auth import router as auth_router
from backend.routes.dashboard import router as dashboard_router
from backend.routes.exchange import router as exchange_router
from backend.routes.reports import router as reports_router

app = FastAPI(title="AI Multi-Agent Trading Bot API", version="1.0.0")


def _cors_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "")
    if not raw:
        return ["http://localhost:3000"]
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth_router, prefix="/api/auth", tags=["Authentication"])
app.include_router(dashboard_router, prefix="/api/dashboard", tags=["Dashboard"])
app.include_router(exchange_router, prefix="/api/exchange", tags=["Exchange"])
app.include_router(reports_router, prefix="/api/reports", tags=["Reports"])


@app.get("/")
async def root():
    return {"status": "online", "service": "AI Multi-Agent Trading Bot API"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/ready")
async def ready():
    from backend.core.database import db
    return {
        "status": "ready" if db.is_connected() else "degraded",
        "supabase": db.is_connected(),
    }
