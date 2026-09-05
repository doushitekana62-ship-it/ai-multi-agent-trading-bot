from fastapi import APIRouter, Depends, HTTPException
from ..auth import current_user
from ..freqtrade_client import FreqtradeClient
router=APIRouter(tags=['trading'])
async def call(fn):
    try: return await fn()
    except Exception as exc: raise HTTPException(status_code=502,detail='Freqtrade request failed') from exc
@router.get('/freqtrade/ping')
async def ping(): return await call(FreqtradeClient().ping)
@router.get('/freqtrade/status')
async def status(user=Depends(current_user)): return await call(FreqtradeClient().status)
@router.get('/freqtrade/balance')
async def balance(user=Depends(current_user)): return await call(FreqtradeClient().balance)
@router.get('/freqtrade/trades')
async def trades(user=Depends(current_user)): return await call(FreqtradeClient().trades)
@router.post('/freqtrade/start')
async def start(user=Depends(current_user)): return await call(FreqtradeClient().start)
@router.post('/freqtrade/stop')
async def stop(user=Depends(current_user)): return await call(FreqtradeClient().stop)
