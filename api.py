from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routes.auth import router as auth_router

app = FastAPI(
    title="AI Multi-Agent Trading Bot API",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Authentication
app.include_router(
    auth_router,
    prefix="/api/auth",
    tags=["Authentication"]
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
