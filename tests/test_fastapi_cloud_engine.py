from datetime import datetime,timedelta,timezone
from fastapi.testclient import TestClient
from fastapi_cloud_app import app

def _market_data():
    prices=[100_000_000+i*10_000+((i%7)-3)*5_000 for i in range(100)];now=datetime.now(timezone.utc);ohlcv=[{"timestamp":(now-timedelta(minutes=99-i)).isoformat(),"open":float(p),"high":float(p*1.001),"low":float(p*.999),"close":float(p),"volume":1000.0+i} for i,p in enumerate(prices)]
    trades=[{"price":float(p),"timestamp":int((now-timedelta(minutes=99-i)).timestamp()),"amount":1.0,"type":"buy" if i%3 else "sell","observation_type":"TRADE"} for i,p in enumerate(prices)]
    return {"current_price":float(prices[-1]),"unified_price":float(prices[-1]),"timestamp":now.isoformat(),"timeframe":"1m","ohlcv":ohlcv,"high_24h":float(max(prices)),"low_24h":float(min(prices)),"volume_24h":5_000_000.0,"change_percent_24h":.5,"short_term_move_percent":.5,"data_quality_score":.9,"recent_trades":trades}

def test_health_and_ready():
    with TestClient(app) as client:
        assert client.get('/health').json()['status']=='healthy';assert client.get('/ready').json()['real_trading']=='locked'

def test_analyze_requires_shared_secret(monkeypatch):
    secret='x'*32;monkeypatch.setenv('AI_ENGINE_SHARED_SECRET',secret)
    with TestClient(app) as client:assert client.post('/engine/analyze',json={'symbol':'BTC/IDR','market_data':_market_data()}).status_code==401

def test_analyze_runs_indodax_native_multi_agent_orchestrator(monkeypatch):
    secret='x'*32;monkeypatch.setenv('AI_ENGINE_SHARED_SECRET',secret)
    with TestClient(app) as client:
        r=client.post('/engine/analyze',headers={'X-AI-Engine-Key':secret},json={'symbol':'BTC/IDR','market_data':_market_data()});assert r.status_code==200,r.text;p=r.json();assert p['ok'] is True;assert p['symbol']=='BTC/IDR';assert p['final_action'] in {'BUY','SELL','HOLD'};assert set(p['agent_votes']).issuperset({'technical','forecast','sentiment'});assert p['hold_analysis']['diagnostic']

def test_real_trading_bypass_is_not_accepted(monkeypatch):
    secret='x'*32;monkeypatch.setenv('AI_ENGINE_SHARED_SECRET',secret);data=_market_data();data['_force_action']='BUY'
    with TestClient(app) as client:
        r=client.post('/engine/analyze',headers={'X-AI-Engine-Key':secret},json={'symbol':'BTC/IDR','market_data':data});assert r.status_code==200;p=r.json();assert p['final_action'] in {'BUY','SELL','HOLD'};assert p['final_action']!='STRONG_BUY'
