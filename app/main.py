from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import settings
from .routers import health, trading

@asynccontextmanager
async def lifespan(_: FastAPI):
    yield

app = FastAPI(title="Compound Scalping API", version="1.0.0", lifespan=lifespan)
origins = [x.strip() for x in settings.cors_origins.split(",") if x.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health.router, prefix="/api")
app.include_router(trading.router, prefix="/api")

@app.get("/")
async def root():
    return {"name": "compound-scalping", "engine": "freqtrade", "api": "fastapi"}
