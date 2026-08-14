from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routes.auth import router as auth_router
from backend.routes.dashboard import router as dashboard_router
from backend.routes.reports import router as reports_router


app = FastAPI(
    title="AI Multi-Agent Trading Bot API",
    version="1.0.0"
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(
    auth_router,
    prefix="/api/auth",
    tags=["Authentication"]
)

app.include_router(
    dashboard_router,
    prefix="/api/dashboard",
    tags=["Dashboard"]
)

app.include_router(
    reports_router,
    prefix="/api/reports",
    tags=["Reports"]
)


@app.get("/")
async def root():

    return {
        "status": "online",
        "service": "AI Multi-Agent Trading Bot API"
    }


@app.get("/health")
async def health():

    return {
        "status": "healthy"
    }
