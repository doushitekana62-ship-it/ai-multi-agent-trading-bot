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
    try: yield
    finally:
        scheduler.stop(); task.cancel()
        try: await task
        except asyncio.CancelledError: pass

app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)
origins = [x.strip() for x in settings.cors_origins.split(",")] if settings.cors_origins != "*" else ["*"]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(auth_router, prefix=settings.api_prefix)
app.include_router(dashboard_router, prefix=settings.api_prefix)
app.include_router(coins_router, prefix=settings.api_prefix)
app.include_router(positions_router, prefix=settings.api_prefix)

@app.get("/health")
def health(): return {"status": "ok", "mode": settings.trading_mode}
