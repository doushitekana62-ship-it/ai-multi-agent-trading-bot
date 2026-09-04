from app.config import settings

def get_supabase():
    from supabase import create_client
    key = settings.supabase_secret_key or settings.supabase_service_role_key
    if not settings.supabase_url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SECRET_KEY are required")
    return create_client(settings.supabase_url, key)
