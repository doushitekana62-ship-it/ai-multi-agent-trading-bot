import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routes.auth import router as auth_router
from backend.routes.dashboard import router as dashboard_router
from backend.routes.exchange import router as exchange_router
from backend.routes.reports import router as reports_router

app = FastAPI(title="AI Multi-Agent Trading Bot API", version="1.0.0")

cors_setting = os.getenv("CORS_ORIGINS", "*")
cors_origins = [
    origin.strip()
    for origin in cors_setting.split(",")
    if origin.strip()
]
allow_all_origins = "*" in cors_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if allow_all_origins else cors_origins,
    allow_credentials=not allow_all_origins,
    allow_methods=["*"],
    allow_headers=["*"],
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
