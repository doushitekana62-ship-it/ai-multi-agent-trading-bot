"""Cloudflare compatibility router for live market data and health routes."""
from __future__ import annotations
import json,time
from urllib.parse import parse_qs,urlparse
from js import fetch as js_fetch
from pyodide.ffi import to_js
from workers import Response
import cf_worker as _cf_worker

async def _fresh_public_indodax(path):
    try:
        sep="&" if "?" in path else "?"; url=f"https://indodax.com/api{path}{sep}_live={int(time.time()*1000)}"
        r=await js_fetch(url,to_js({"method":"GET","cache":"no-store","headers":{"Accept":"application/json","Cache-Control":"no-cache","Pragma":"no-cache"}}))
        if int(r.status)>=400:return None
        return json.loads(await r.text())
    except Exception:return None

def _clean_pair(value):
    allowed={"btc_idr","eth_idr","usdt_idr","xrp_idr","doge_idr","sol_idr","beat_idr","hype_idr","ada_idr","trx_idr","shib_idr","pepe_idr"};p=(value or "btc_idr").strip().lower().replace("/","_");return p if p in allowed else "btc_idr"

async def _supabase_observations(env,pair):
    base=str(getattr(env,"SUPABASE_URL","") or "").strip().rstrip("/");key=str(getattr(env,"SUPABASE_SERVICE_ROLE_KEY","") or "").strip()
    if not base or not key:return []
    try:
        symbol=pair.upper().replace("_","/");url=f"{base}/rest/v1/market_observations?select=observed_at,minute_bucket,price,source,observation_type,trade_count,move_from_previous_pct,pulse_status,raw_observation&symbol=eq.{symbol}&order=observed_at.desc&limit=360"
        r=await js_fetch(url,to_js({"method":"GET","headers":{"apikey":key,"Authorization":f"Bearer {key}","Accept":"application/json","Cache-Control":"no-cache"}}))
        if int(r.status)>=400:return []
        rows=json.loads(await r.text());return rows if isinstance(rows,list) else []
    except Exception:return []

def _pulse(rows):
    buckets={}
    for row in rows:
        try:
            ts=row.get("observed_at") or row.get("minute_bucket"); price=float(row.get("price") or 0)
            if not ts or price<=0:continue
            minute=ts[:16] if isinstance(ts,str) else str(ts)
            buckets.setdefault(minute,[]).append(price)
        except Exception:continue
    keys=sorted(buckets)[-30:];segments=[]
    for key in keys:
        vals=buckets[key];move=((vals[-1]-vals[0])/vals[0]*100) if len(vals)>=2 and vals[0] else None;status="GREEN" if move is not None and move>0 else "RED" if move is not None and move<0 else "GRAY";segments.append({"timestamp":key,"status":status,"move_pct":move,"observations":len(vals),"open":vals[0],"close":vals[-1]})
    while len(segments)<30:segments.insert(0,{"timestamp":None,"status":"GRAY","move_pct":None,"observations":0,"open":None,"close":None})
    populated=[x for x in segments if x["observations"]>=2 and x["open"]]
    net=((populated[-1]["close"]-populated[0]["open"])/populated[0]["open"]*100) if populated else None
    return segments,"GREEN" if net is not None and net>0 else "RED" if net is not None and net<0 else "GRAY",net

async def _light_market_overview(pair,env):
    pair=_clean_pair(pair);ticker=await _fresh_public_indodax(f"/{pair}/ticker")
    if not ticker or not isinstance(ticker.get("ticker"),dict):return {"available":False,"pair":pair,"currency":"IDR","currency_symbol":"Rp","source":"INDODAX public market data"}
    t=ticker["ticker"];last=float(t.get("last") or 0);rows=await _supabase_observations(env,pair);points=[{"tid":f"supabase:{i}:{r.get('observed_at')}","price":float(r.get("price") or 0),"timestamp":r.get("observed_at"),"amount":0,"source":r.get("source") or "INDODAX public market data","observation_type":r.get("observation_type") or "TICKER"} for i,r in enumerate(reversed(rows)) if float(r.get("price") or 0)>0]
    if last>0 and (not points or points[-1]["price"]!=last):points.append({"tid":f"ticker:{pair}:{time.time()}","price":last,"timestamp":datetime_now(),"amount":0,"source":"INDODAX public ticker","observation_type":"TICKER"})
    segments,overall,net=_pulse(rows)
    return {"available":last>0,"pair":pair,"base_currency":pair.split("_")[0].upper(),"quote_currency":pair.split("_")[1].upper(),"currency":"IDR" if pair.endswith("_idr") else pair.split("_")[1].upper(),"currency_symbol":"Rp" if pair.endswith("_idr") else pair.split("_")[1].upper(),"last":last,"buy":float(t.get("buy") or 0),"sell":float(t.get("sell") or 0),"high":float(t.get("high") or 0),"low":float(t.get("low") or 0),"volume":float(t.get("vol_idr") or t.get("vol") or 0),"recent_move":net,"recent_move_label":"Supabase persisted Indodax observations","points":points[-1440:],"pulse_segments":segments,"pulse_status":overall,"source":"INDODAX public market data","market_data_quality":"SUPABASE_OBSERVATIONS_PLUS_LIVE_TICKER"}

def datetime_now():return __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()

async def fetch(app,request,env):
    parsed=urlparse(request.url);path=parsed.path;query=parse_qs(parsed.query);pair=query.get("pair",["btc_idr"])[0];scope={"env":env,"query_string":f"pair={pair}".encode("latin-1")}
    if request.method=="OPTIONS":return Response("",status=204)
    if request.method=="GET" and path=="/api/health":return Response.json({"status":"healthy","runtime":"cloudflare-python-worker"})
    if request.method=="GET" and path=="/api/ready":
        configured=all(str(getattr(env,n,"") or "").strip() for n in ("SUPABASE_URL","SUPABASE_SERVICE_ROLE_KEY","JWT_SECRET_KEY","ADMIN_USERNAME","ADMIN_PASSWORD"));supabase=await _cf_worker._supabase_probe(scope) if configured else False;return Response.json({"status":"ready" if configured and supabase else "degraded","supabase":bool(supabase),"secrets_configured":configured,"runtime":"cloudflare-python-worker"})
    if request.method=="GET" and path in {"/api/market/overview","/api/market/data"}:return Response.json(await _light_market_overview(pair,env))
    if request.method=="GET" and path=="/api/market/insights":return Response.json(await _cf_worker._market_insights(scope))
    return Response.json({"detail":"API route not found"},status=404)

entrypoint=None
__all__=["fetch","entrypoint"]
