import base64
import hashlib
import hmac
import json
import time
from urllib.parse import urlparse, parse_qs

import asgi
from workers import WorkerEntrypoint
from js import fetch
from pyodide.ffi import to_js

JSON_HEADERS = [(b"content-type", b"application/json; charset=utf-8")]
PAPER_INITIAL_BALANCE = 10_000_000.0
MAX_OPEN_POSITIONS = 5
INDODAX_PUBLIC_BASE = "https://indodax.com/api"
SCALPING_PAIRS = {
    "btc_idr", "eth_idr", "usdt_idr", "xrp_idr", "doge_idr", "sol_idr",
    "beat_idr", "hype_idr", "ada_idr", "trx_idr", "shib_idr", "pepe_idr",
}


def _json_bytes(value):
    return json.dumps(value, separators=(",", ":")).encode("utf-8")

def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")

def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))

def _env(scope, name, default=""):
    return str(getattr(scope.get("env"), name, default) or default)

def _secret(scope) -> str:
    secret = _env(scope, "JWT_SECRET_KEY").strip()
    if len(secret) < 32: raise RuntimeError("JWT_SECRET_KEY must be at least 32 characters")
    return secret

def _hmac_sha256(secret: str, message: str) -> bytes:
    return hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).digest()

def _make_token(scope, username: str) -> str:
    now = int(time.time()); header = _b64url(_json_bytes({"alg":"HS256","typ":"JWT"})); payload = _b64url(_json_bytes({"sub":username,"iat":now,"exp":now+1800,"type":"access"})); signing_input=f"{header}.{payload}"; return f"{signing_input}.{_b64url(_hmac_sha256(_secret(scope),signing_input))}"

def _verify_token(scope, token: str):
    try:
        header,payload,signature=token.split(".",2); data=json.loads(_b64url_decode(payload))
        if json.loads(_b64url_decode(header)).get("alg")!="HS256" or int(data.get("exp",0))<=int(time.time()): return None
        if not hmac.compare_digest(_hmac_sha256(_secret(scope),f"{header}.{payload}"),_b64url_decode(signature)): return None
        return data
    except Exception: return None

def _authorization(scope) -> str:
    for key,value in scope.get("headers",[]):
        key_text=key.decode("latin-1") if isinstance(key,(bytes,bytearray)) else str(key)
        if key_text.lower()=="authorization": return value.decode("latin-1") if isinstance(value,(bytes,bytearray)) else str(value)
    return ""

async def _read_body(receive):
    chunks=[]
    while True:
        message=await receive()
        if message.get("type")!="http.request": break
        chunks.append(message.get("body",b""))
        if not message.get("more_body",False): break
    return b"".join(chunks)

async def _send(send,status,headers,body):
    await send({"type":"http.response.start","status":status,"headers":headers}); await send({"type":"http.response.body","body":body})

async def _json_response(send,status,payload): await _send(send,status,JSON_HEADERS,_json_bytes(payload))

async def _require_user(scope):
    value=_authorization(scope)
    return _verify_token(scope,value[7:].strip()) if value.lower().startswith("bearer ") else None

async def _supabase_request(scope,path,method="GET"):
    url=_env(scope,"SUPABASE_URL").rstrip("/"); key=_env(scope,"SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key: return None
    try:
        response=await fetch(f"{url}{path}",to_js({"method":method,"headers":{"apikey":key,"Authorization":f"Bearer {key}","Accept":"application/json"}}))
        if int(response.status)>=400:return None
        return json.loads(await response.text())
    except Exception:return None

async def _supabase_probe(scope): return (await _supabase_request(scope,"/rest/v1/")) is not None

async def _public_indodax(path):
    try:
        response=await fetch(f"{INDODAX_PUBLIC_BASE}{path}",to_js({"method":"GET","headers":{"Accept":"application/json"}}))
        if int(response.status)>=400:return None
        return json.loads(await response.text())
    except Exception:return None

def _query_value(scope,name,default=""):
    raw=scope.get("query_string",b""); query=raw.decode("latin-1") if isinstance(raw,(bytes,bytearray)) else str(raw or ""); return parse_qs(query).get(name,[default])[0]

def _clean_pair(value):
    value=(value or "btc_idr").strip().lower().replace("/","_"); return value if value in SCALPING_PAIRS else "btc_idr"

def _recent_trade_move(points):
    values=[float(p["price"]) for p in points if float(p.get("price",0) or 0)>0]
    return ((values[-1]-values[0])/values[0])*100.0 if len(values)>=2 and values[0] else None

async def _market_overview(scope):
    pair=_clean_pair(_query_value(scope,"pair","btc_idr")); ticker=await _public_indodax(f"/{pair}/ticker"); trades=await _public_indodax(f"/{pair}/trades")
    if not ticker or not isinstance(ticker.get("ticker"),dict): return {"available":False,"pair":pair,"currency":"IDR","currency_symbol":"Rp"}
    t=ticker["ticker"]; points=[]; raw_trades=trades.get("trades",[]) if isinstance(trades,dict) else []
    for item in raw_trades[-30:]:
        try:
            points.append({"price":float(item.get("price") or 0),"timestamp":int(item.get("date") or item.get("trade_time") or 0),"amount":float(item.get("amount") or 0),"type":str(item.get("type") or "").lower(),"side":str(item.get("type") or "").lower()})
        except (TypeError,ValueError): continue
    recent_move=_recent_trade_move(points)
    return {"available":True,"pair":pair,"base_currency":pair.split("_")[0].upper(),"quote_currency":pair.split("_")[1].upper(),"currency":"IDR" if pair.endswith("_idr") else pair.split("_")[1].upper(),"currency_symbol":"Rp" if pair.endswith("_idr") else pair.split("_")[1].upper(),"last":float(t.get("last") or 0),"buy":float(t.get("buy") or 0),"sell":float(t.get("sell") or 0),"high":float(t.get("high") or 0),"low":float(t.get("low") or 0),"volume":float(t.get("vol_idr") or t.get("vol") or 0),"recent_move":recent_move,"recent_move_label":"last 30 public trades","points":points,"source":"INDODAX public market data"}

async def _market_insights(scope):
    data=await _public_indodax("/tickers"); raw=data.get("tickers",{}) if isinstance(data,dict) else {}; items=[]
    for pair,ticker in raw.items():
        if not pair.endswith("_idr") or not isinstance(ticker,dict): continue
        try:
            last=float(ticker.get("last") or 0); high=float(ticker.get("high") or 0); low=float(ticker.get("low") or 0)
            if last<=0: continue
            items.append({"pair":pair,"last":last,"high":high,"low":low,"volume":float(ticker.get("vol_idr") or ticker.get("vol") or 0),"change_pct":((last-low)/(high-low)*100 if high>low else 50)})
        except (TypeError,ValueError): continue
    return {"available":True,"items":items,"source":"INDODAX public market data"}


class Worker(WorkerEntrypoint):
    async def fetch(self, request):
        scope={"headers":request.headers,"query_string":request.url.split("?",1)[1].encode("latin-1") if "?" in request.url else b"","env":self.env}
        path=urlparse(request.url).path
        if path.endswith("/health"): return Response.new(_json_bytes({"ok":True,"mode":"paper"}),status=200)
        if path.endswith("/api/market/overview"): return Response.new(_json_bytes(await _market_overview(scope)),status=200,headers={"Content-Type":"application/json"})
        if path.endswith("/api/market/insights"): return Response.new(_json_bytes(await _market_insights(scope)),status=200,headers={"Content-Type":"application/json"})
        return Response.new(_json_bytes({"ok":False,"error":"not_found"}),status=404,headers={"Content-Type":"application/json"})
