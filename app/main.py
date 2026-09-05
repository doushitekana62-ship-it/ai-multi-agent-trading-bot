import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.config import settings
from app.auth.router import router as auth_router
from app.routers.dashboard import router as dashboard_router
from app.routers.coins import router as coins_router
from app.routers.positions import router as positions_router
from app.scheduler import TradingScheduler
from app.supabase_client import execute_data, get_supabase

log = logging.getLogger(__name__)
scheduler = TradingScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(scheduler.start())
    try:
        yield
    finally:
        scheduler.stop(); task.cancel()
        try: await task
        except asyncio.CancelledError: pass

app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)
origins = [x.strip() for x in settings.cors_origins.split(",") if x.strip()]

# Diagnostic mode: CORS_ORIGINS=* is intentionally broad for troubleshooting.
# The API authenticates with Bearer headers, not browser cookies, so credentials
# are disabled in wildcard mode. Restore an explicit origin after diagnosis.
if "*" in origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    if not origins:
        origins = ["https://doushitekana62-ship-it.github.io"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception):
    log.exception("Unhandled API error: %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(status_code=500, content={"error": "Internal server error"})

app.include_router(auth_router, prefix=settings.api_prefix)
app.include_router(dashboard_router, prefix=settings.api_prefix)
app.include_router(coins_router, prefix=settings.api_prefix)
app.include_router(positions_router, prefix=settings.api_prefix)

@app.get("/")
def root():
    return {"service": settings.app_name, "status": "ok", "mode": settings.trading_mode}

@app.get("/health")
def health():
    configured = bool(settings.supabase_url and (settings.supabase_secret_key or settings.supabase_service_role_key))
    db_ok = False
    if configured:
        try:
            execute_data(get_supabase().table("users_settings").select("id").limit(1), [])
            db_ok = True
        except Exception:
            log.exception("health database check failed")
    return {"status": "ok" if db_ok else "degraded", "mode": settings.trading_mode,
            "supabase_configured": configured, "database_healthy": db_ok}
