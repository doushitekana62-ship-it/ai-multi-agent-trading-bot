from app.config import settings


def get_supabase():
    from supabase import create_client
    key = settings.supabase_secret_key or settings.supabase_service_role_key
    if not settings.supabase_url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SECRET_KEY are required")
    return create_client(settings.supabase_url, key)


def response_data(response, default=None):
    """Safely extract data from a Supabase response, including None responses."""
    data = getattr(response, "data", None)
    return default if data is None else data


def execute_data(query, default=None):
    """Execute a Supabase query without assuming the response object exists."""
    return response_data(query.execute(), default)


def execute_one(query):
    """Return zero or one row without relying on maybe_single()."""
    data = execute_data(query.limit(1), [])
    if isinstance(data, list):
        return data[0] if data else None
    return data
