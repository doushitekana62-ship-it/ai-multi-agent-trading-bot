"""Cloudflare Worker entrypoint with persistent paper-trading control."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import urlparse, parse_qs, urlencode

import asgi
from workers import WorkerEntrypoint, Response
from js import fetch
from pyodide.ffi import to_js

import cf_worker
from paper_cycle import run_paper_cycle


async def _access_only(scope):
    value = cf_worker._authorization(scope)
    if not value.lower().startswith("bearer "): return None
    payload = cf_worker._verify_token(scope, value[7:].strip())
    return payload if payload and payload.get("type") == "access" else None

cf_worker._require_user = _access_only


def _make_refresh_token(env, username):
    secret = str(getattr(env,"JWT_SECRET_KEY","") or "").strip()
    if len(secret) < 32: raise RuntimeError("JWT_SECRET_KEY must be at least 32 characters")
    now=int(time.time()); header=cf_worker._b64url(cf_worker._json_bytes({"alg":"HS256","typ":"JWT"})); payload=cf_worker._b64url(cf_worker._json_bytes({"sub":username,"iat":now,"exp":now+7*24*60*60,"type":"refresh"})); raw=f"{header}.{payload}"; sig=hmac.new(secret.encode(),raw.encode(),hashlib.sha256).digest(); return f"{raw}.{cf_worker._b64url(sig)}"

async def _state_stub(env): return env.PAPER_STATE.getByName("global")

def _runtime_hours(started_at):
    if not started_at: return 0.0
    try:
        started=time.strptime(str(started_at)[:19],"%Y-%m-%dT%H:%M:%S"); return max(0.0,(time.time()-time.mktime(started))/3600.0)
    except Exception: return 0.0

def _state_response(state):
    counts=dict(state.get("decision_counts") or {}); enabled=bool(state.get("enabled")); running=bool(state.get("cycle_running")); positions=list(state.get("positions") or [])
    return {**state,"bot_enabled":enabled,"enabled":enabled,"cycle_running":running,"mode":"paper","currency":"IDR","currency_symbol":"Rp","max_open_positions":max(1,min(3,int(state.get("max_open_positions",3) or 3))),"active_positions":len(positions),"runtime_hours":_runtime_hours(state.get("started_at")) if enabled else 0.0,"decision_counts":{k:int(counts.get(k,0)) for k in ("BUY","SELL","HOLD")},"safety":{"mode":"paper","real_trading_locked":True,"bot_enabled":enabled,"cycle_running":running}}

def _request_pair(request, default="btc_idr"):
    try:
        q=parse_qs(urlparse(request.url).query); return cf_worker._clean_pair(q.get("pair",q.get("symbol",[default]))[0])
    except Exception: return default

def _supabase_config(env): return str(getattr(env,"SUPABASE_URL","") or "").strip().rstrip("/"),str(getattr(env,"SUPABASE_SERVICE_ROLE_KEY","") or "").strip()

async def _supabase_health(env):
    url,key=_supabase_config(env)
    if not url or not key: return {"connected":False,"reason":"credentials_missing"}
    try:
        r=await fetch(f"{url}/rest/v1/decisions?select=id&limit=1",to_js({"method":"GET","headers":{"apikey":key,"Authorization":f"Bearer {key}","Accept":"application/json"}})); code=int(r.status)
        return {"connected":200<=code<300,"reason":"rest_probe_ok" if 200<=code<300 else f"http_{code}"}
    except Exception: return {"connected":False,"reason":"network_or_runtime_error"}

async def _history(env, request):
    url,key=_supabase_config(env)
    if not url or not key: return Response.json({"history":[],"connected":False,"reason":"credentials_missing"},status=503)
    q=parse_qs(urlparse(request.url).query); date=q.get("date",[""])[0].strip(); pair=q.get("pair",[""])[0].strip()
    params=[("select","*"),("order","cycle_at.desc"),("limit","200")]
    if date: params.append(("trading_date",f"eq.{date}"))
    if pair: params.append(("pair",f"eq.{pair.upper()}"))
    try:
        r=await fetch(f"{url}/rest/v1/paper_history?{urlencode(params)}",to_js({"method":"GET","headers":{"apikey":key,"Authorization":f"Bearer {key}","Accept":"application/json"}})); code=int(r.status); text=await r.text()
        if code<200 or code>=300: return Response.json({"history":[],"connected":False,"reason":f"http_{code}","detail":text[:500]},status=502)
        rows=json.loads(text) if text else []; return Response.json({"history":rows if isinstance(rows,list) else [],"count":len(rows) if isinstance(rows,list) else 0,"date":date or None,"pair":pair.upper() if pair else None,"connected":True})
    except Exception as exc: return Response.json({"history":[],"connected":False,"reason":type(exc).__name__},status=502)


class Default(WorkerEntrypoint):
    async def _verify_access(self, request):
        value=request.headers.get("authorization","")
        if not value.lower().startswith("bearer "): return None
        secret=str(getattr(self.env,"JWT_SECRET_KEY","") or "").strip()
        if len(secret)<32: return None
        scope={"headers":[(b"authorization",value.encode("latin-1"))],"env":self.env}; payload=cf_worker._verify_token(scope,value[7:].strip())
        return payload if payload and payload.get("type")=="access" else None

    async def _handle_auth(self,request,path):
        if path=="/api/auth/login" and request.method=="POST":
            user=str(getattr(self.env,"ADMIN_USERNAME","") or "").strip(); configured=str(getattr(self.env,"ADMIN_PASSWORD","") or "")
            if not user or not configured: return Response.json({"detail":"Dashboard authentication is not configured"},status=503)
            try: body=await request.json(); username=str(body.get("username","")); password=str(body.get("password",""))
            except Exception: return Response.json({"detail":"Invalid JSON request body"},status=400)
            secret=str(getattr(self.env,"JWT_SECRET_KEY","") or "").strip()
            if len(secret)<32: return Response.json({"detail":"JWT_SECRET_KEY must be at least 32 characters"},status=503)
            supplied=hmac.new(secret.encode(),password.encode(),hashlib.sha256).digest(); expected=hmac.new(secret.encode(),configured.encode(),hashlib.sha256).digest()
            if username!=user or not hmac.compare_digest(supplied,expected): return Response.json({"detail":"Incorrect username or password"},status=401)
            return Response.json({"access_token":cf_worker._make_token({"env":self.env},user),"refresh_token":_make_refresh_token(self.env,user),"token_type":"bearer","expires_in":1800,"refresh_expires_in":7*24*60,"username":user})
        if path=="/api/auth/refresh" and request.method=="POST":
            try: body=await request.json(); token=str(body.get("refresh_token",""))
            except Exception: return Response.json({"detail":"Invalid JSON request body"},status=400)
            payload=cf_worker._verify_token({"env":self.env},token); user=str(getattr(self.env,"ADMIN_USERNAME","") or "").strip()
            if not payload or payload.get("type")!="refresh" or payload.get("sub")!=user: return Response.json({"detail":"Invalid or expired refresh token"},status=401)
            return Response.json({"access_token":cf_worker._make_token({"env":self.env},user),"token_type":"bearer","expires_in":1800})
        if path=="/api/auth/verify" and request.method=="GET":
            payload=await self._verify_access(request); return Response.json({"username":payload.get("sub"),"is_authenticated":True}) if payload else Response.json({"detail":"Invalid or expired token"},status=401)
        if path=="/api/auth/logout" and request.method=="POST":
            return Response.json({"message":"Logged out successfully","status":"success"}) if await self._verify_access(request) else Response.json({"detail":"Invalid or expired token"},status=401)
        return None

    async def _handle_state_routes(self,request,path):
        if (path.startswith("/api/dashboard/") or path.startswith("/api/bot/")) and not await self._verify_access(request): return Response.json({"detail":"Invalid or expired token"},status=401)
        stub=await _state_stub(self.env)
        if path=="/api/bot/status" and request.method=="GET": return Response.json(_state_response(await stub.get_state()))
        if path in ("/api/bot/start","/api/dashboard/paper/start") and request.method=="POST":
            pair=_request_pair(request); state=await stub.start(pair); cycle=await run_paper_cycle(self.env,stub,pair); return Response.json({**_state_response(cycle.get("state") or state),"message":"Paper trading started and one AI cycle completed.","cycle":cycle})
        if path in ("/api/bot/stop","/api/dashboard/paper/stop") and request.method=="POST":
            state=await stub.stop(); return Response.json({**_state_response(state),"message":"Paper trading stopped. Real trading remains locked."})
        if path in ("/api/bot/cycle","/api/dashboard/paper/cycle") and request.method=="POST":
            cycle=await run_paper_cycle(self.env,stub,_request_pair(request)); return Response.json(cycle,status=200 if cycle.get("ok") else 409)
        if path=="/api/dashboard/analyze" and request.method=="POST":
            if not (await stub.get_state()).get("enabled"): return Response.json({"detail":"Paper trading is OFF. Start the bot first.","bot_enabled":False},status=409)
            cycle=await run_paper_cycle(self.env,stub,_request_pair(request)); return Response.json(cycle,status=200 if cycle.get("ok") else 409)
        if path=="/api/dashboard/paper/settings" and request.method=="POST":
            try: body=await request.json(); value=body.get("max_open_positions")
            except Exception: return Response.json({"detail":"Invalid JSON request body"},status=400)
            return Response.json(_state_response(await stub.set_position_limit(value)))
        if path in ("/api/bot/reset","/api/dashboard/paper/reset") and request.method=="POST": return Response.json({**_state_response(await stub.reset()),"message":"Paper trading state reset."})
        if path=="/api/dashboard/status" and request.method=="GET":
            state=await stub.get_state(); result=_state_response(state); url,key=_supabase_config(self.env); health=await _supabase_health(self.env); pair=state.get("paper_pair") or "btc_idr"; market=await cf_worker._market_overview({"env":self.env,"query_string":f"pair={pair}".encode("latin-1")})
            result.update({"daily_pnl":float(state.get("daily_pnl",0)),"daily_trades":int(state.get("daily_trades",0)),"total_trades":int(state.get("total_trades",0)),"portfolio_value":float(state.get("portfolio_value",0)),"balance":float(state.get("balance",0)),"database":{"configured":bool(url and key),"connected":bool(health.get("connected")),"status":"connected" if health.get("connected") else "unavailable"},"market_data":{"source":"INDODAX public market data","available":bool(market.get("available")),"fresh":bool(market.get("available")),"stale":not bool(market.get("available")),"age_seconds":0 if market.get("available") else None},"system_health":{"database":{"connected":bool(health.get("connected"))},"market_data":{"fresh":bool(market.get("available")),"stale":not bool(market.get("available")),"age_seconds":0 if market.get("available") else None},"mode":"paper","engine":{"running":bool(state.get("cycle_running")),"enabled":bool(state.get("enabled"))}}})
            return Response.json(result)
        if path=="/api/dashboard/positions" and request.method=="GET":
            state=await stub.get_state(); return Response.json({"positions":state.get("positions",[]),"active_positions":len(state.get("positions") or []),"max_open_positions":state.get("max_open_positions",3),"currency":"IDR","currency_symbol":"Rp"})
        if path=="/api/dashboard/performance" and request.method=="GET":
            state=await stub.get_state(); return Response.json({"performance":{"total_pnl":float(state.get("total_pnl",0)),"daily_pnl":float(state.get("daily_pnl",0)),"balance":float(state.get("balance",0)),"portfolio_value":float(state.get("portfolio_value",0)),"closed_trades":sum(1 for t in state.get("trade_history",[]) if t.get("action")=="SELL"),"currency":"IDR","currency_symbol":"Rp"}})
        if path=="/api/dashboard/recent-decision" and request.method=="GET": return Response.json({"decision":(await stub.get_state()).get("last_decision")})
        if path=="/api/dashboard/agents" and request.method=="GET":
            state=await stub.get_state(); status="armed" if state.get("enabled") else "idle"; return Response.json({"agents":[{"name":n,"status":status,"description":"Five-agent paper execution pipeline."} for n in ["Sentiment Agent","Technical Agent","Decision Agent","Forecast Agent","Reflector Agent"]]})
        if path=="/api/dashboard/history" and request.method=="GET": return await _history(self.env,request)
        return None

    async def fetch(self,request):
        path=urlparse(request.url).path
        try:
            auth=await self._handle_auth(request,path)
            if auth is not None: return auth
            routed=await self._handle_state_routes(request,path)
            if routed is not None: return routed
            return await asgi.fetch(cf_worker.app,request,self.env)
        except Exception as exc:
            print(f"[worker:fetch] unhandled request path={path} type={type(exc).__name__}: {exc}")
            return Response.json({"detail":"Worker request failed","error_type":type(exc).__name__},status=500)

    async def scheduled(self,controller,env,ctx):
        try:
            stub=await _state_stub(env); state=await stub.get_state()
            if state.get("enabled"): await run_paper_cycle(env,stub,state.get("paper_pair") or "btc_idr")
        except Exception as exc: print(f"[worker:schedule] error type={type(exc).__name__}: {exc}")


__all__=["Default"]
