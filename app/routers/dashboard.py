from fastapi import APIRouter, Depends
from ..auth import current_token, current_user, supabase
from ..freqtrade_client import FreqtradeClient

router = APIRouter(tags=["dashboard"])

@router.get('/me')
async def me(user=Depends(current_user)): return {'user': user}

@router.get('/dashboard')
async def dashboard(token: str = Depends(current_token)):
    result={'freqtrade':None,'positions':[],'signals':[],'health':'ok'}
    try: result['freqtrade']=await FreqtradeClient().status()
    except Exception as exc: result['freqtrade']={'error':str(exc)}
    try: result['positions']=await supabase.select('positions',token,{'select':'*','order':'opened_at.desc','limit':'20'})
    except Exception: pass
    try: result['signals']=await supabase.select('signal_decisions',token,{'select':'*','order':'created_at.desc','limit':'20'})
    except Exception: pass
    return result
