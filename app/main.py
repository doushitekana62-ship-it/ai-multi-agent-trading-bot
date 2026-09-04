import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.auth.router import router as auth_router
from app.routers.dashboard import router as dashboard_router
from app.routers.coins import router as coins_router
from app.routers.positions import router as positions_router
from app.scheduler import TradingScheduler

scheduler = TradingScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(scheduler.start())
    try:
        yield
    finally:
        scheduler.stop()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)

# Never use a wildcard origin with credentialed requests. Also protect against
# an old CORS_ORIGINS=* environment variable overriding the code default.
configured_origins = [x.strip() for x in settings.cors_origins.split(",") if x.strip()]
if not configured_origins or "*" in configured_origins:
    configured_origins = ["https://doushitekana62-ship-it.github.io"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=configured_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix=settings.api_prefix)
app.include_router(dashboard_router, prefix=settings.api_prefix)
app.include_router(coins_router, prefix=settings.api_prefix)
app.include_router(positions_router, prefix=settings.api_prefix)

@app.get("/")
def root():
    return {"service": settings.app_name, "status": "ok", "mode": settings.trading_mode}

@app.get("/health")
def health():
    return {"status": "ok", "mode": settings.trading_mode}
