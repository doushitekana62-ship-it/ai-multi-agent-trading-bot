from fastapi import APIRouter
from ..supabase_client import SupabaseClient
from ..freqtrade_client import FreqtradeClient
router=APIRouter(tags=['health'])
@router.get('/health')
async def health():
    supabase=await SupabaseClient().health()
    try: freqtrade=await FreqtradeClient().ping()
    except Exception as exc: freqtrade={'ok':False,'error':str(exc)}
    return {'ok':True,'supabase':supabase,'freqtrade':freqtrade}
