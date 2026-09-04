def test_fastapi_app_imports():
    from app.main import app
    assert app.title == "AI Multi-Agent Trading Bot"
