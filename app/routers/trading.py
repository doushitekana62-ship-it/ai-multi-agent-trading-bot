from fastapi import APIRouter, HTTPException
from ..freqtrade_client import FreqtradeClient

router = APIRouter(tags=["trading"])

async def call(fn):
    try:
        return await fn()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

@router.get("/freqtrade/status")
async def status():
    return await call(FreqtradeClient().status)

@router.get("/freqtrade/balance")
async def balance():
    return await call(FreqtradeClient().balance)

@router.get("/freqtrade/trades")
async def trades():
    return await call(FreqtradeClient().trades)

@router.post("/freqtrade/start")
async def start():
    return await call(FreqtradeClient().start)

@router.post("/freqtrade/stop")
async def stop():
    return await call(FreqtradeClient().stop)
