"""Canonical fast paper cycle: Indodax -> observation -> strategy -> risk -> Supabase."""
from __future__ import annotations
import json, uuid
from datetime import datetime, timezone
from js import fetch
from pyodide.ffi import to_js
import cf_worker
from cloudflare_orchestrator import CloudflareOrchestrator

MARKET_HISTORY_LIMIT=1440
PULSE_MINUTES=30
LIBRARY_ALERT_MARKER="LIBRARY_ALERTS_JSON="


def _num(v,d=0.0):
    try:return float(v)
    except (TypeError,ValueError):return d

def _ts(p):
    v=_num(p.get("timestamp") or p.get("date"))
    return v/1000 if v>1_000_000_000_000 else v

def _safe(v):
    if v is None or isinstance(v,(str,int,float,bool)):return v
    if isinstance(v,datetime):return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()
    if isinstance(v,dict):return {str(k):_safe(x) for k,x in v.items()}
    if isinstance(v,(list,tuple)):return [_safe(x) for x in v]
    return str(v)

async def _supabase(env,table,method="POST",query="",payload=None):
    base=str(getattr(env,"SUPABASE_URL","") or "").strip().rstrip("/"); key=str(getattr(env,"SUPABASE_SERVICE_ROLE_KEY","") or "").strip()
    if not base or not key:return {"ok":False,"saved":False,"reason":"supabase_credentials_missing"}
    try:
        opts={"method":method,"headers":{"apikey":key,"Authorization":f"Bearer {key}","Accept":"application/json","Content-Type":"application/json"}}
        if method.upper()=="POST":opts["headers"]["Prefer"]="return=representation"
        if payload is not None:opts["body"]=json.dumps(_safe(payload),separators=(",",":"))
        response=await fetch(f"{base}/rest/v1/{table}{query}",to_js(opts));text=await response.text();code=int(response.status)
        if code<200 or code>=300:return {"ok":False,"saved":False,"reason":f"supabase_http_{code}: {text[:500]}"}
        try:rows=json.loads(text) if text else []
        except Exception:rows=[]
        return {"ok":True,"saved":True,"rows":rows if isinstance(rows,list) else [rows] if isinstance(rows,dict) else []}
    except Exception as exc:return {"ok":False,"saved":False,"reason":f"{type(exc).__name__}: {exc}"}

async def _persist_market_observation(env,payload):
    base=str(getattr(env,"SUPABASE_URL","") or "").strip().rstrip("/");key=str(getattr(env,"SUPABASE_SERVICE_ROLE_KEY","") or "").strip()
    if not base or not key:return {"ok":False,"saved":False,"reason":"supabase_credentials_missing"}
    try:
        rpc_payload={"p_payload":_safe(payload)}
        opts={"method":"POST","headers":{"apikey":key,"Authorization":f"Bearer {key}","Accept":"application/json","Content-Type":"application/json"},"body":json.dumps(rpc_payload,separators=(",",":"))}
        response=await fetch(f"{base}/rest/v1/rpc/upsert_market_observation",to_js(opts));text=await response.text();code=int(response.status)
        if code<200 or code>=300:return {"ok":False,"saved":False,"reason":f"market_observation_rpc_http_{code}: {text[:500]}"}
        return {"ok":True,"saved":True,"row":json.loads(text) if text else None}
    except Exception as exc:return {"ok":False,"saved":False,"reason":f"{type(exc).__name__}: {exc}"}

def _merge(old,current):
    out=[];seen=set()
    for p in list(old or [])+list(current or []):
        if not isinstance(p,dict):continue
        key=(str(p.get("tid","")),str(p.get("timestamp","")),str(p.get("price","")),str(p.get("observation_type",p.get("type",""))))
        if key not in seen:seen.add(key);out.append(p)
    out.sort(key=_ts);return out[-MARKET_HISTORY_LIMIT:]

def _latest_move(history,minutes,anchor):
    cutoff=anchor-minutes*60;rows=[p for p in history if cutoff<=_ts(p)<=anchor and _num(p.get("price"))>0];rows.sort(key=_ts)
    if len(rows)<2:return None
    return (_num(rows[-1]["price"])/_num(rows[0]["price"])-1)*100

def _reasoning(text,alerts=None):
    clean=str(text or "").split(LIBRARY_ALERT_MARKER,1)[0].strip()
    if alerts:return f"{clean} {LIBRARY_ALERT_MARKER}{json.dumps(alerts[:4],separators=(',',':'))}".strip()
    return clean

async def run_market_observation(env,state_api,pair="btc_idr",session_id=None):
    pair=cf_worker._clean_pair(pair);market=await cf_worker._market_overview({"env":env,"query_string":f"pair={pair}".encode("latin-1")})
    if not market.get("available") or _num(market.get("last"))<=0:return {"ok":False,"reason":"market_data_unavailable"}
    points=list(market.get("points") or []);history=_merge(await state_api.get_paper_market_history(),points);await state_api.set_paper_market_history(history)
    anchor=max([_ts(x) for x in history if _ts(x)>0] or [datetime.now(timezone.utc).timestamp()]);latest=history[-1] if history else {};previous=history[-2] if len(history)>1 else None;price=_num(market.get("last"));prev_price=_num(previous.get("price")) if previous else 0;mprev=((price-prev_price)/prev_price*100) if prev_price else None
    minute=datetime.fromtimestamp(int(anchor//60)*60,timezone.utc).isoformat();pulse_status="GRAY";current_rows=[x for x in history if int(_ts(x)//60)==int(anchor//60)]
    if len(current_rows)>=2:
        o,c=_num(current_rows[0].get("price")),_num(current_rows[-1].get("price"));pulse_status="GREEN" if c>o else "RED" if c<o else "GRAY"
    payload={"cycle_id":f"OBS-{uuid.uuid4()}","session_id":session_id or _now(),"symbol":market["pair"].upper().replace("_","/"),"observed_at":datetime.fromtimestamp(anchor,timezone.utc).isoformat(),"minute_bucket":minute,"price":price,"source":str(latest.get("source") or "INDODAX public market data"),"observation_type":str(latest.get("observation_type") or "TRADE").upper(),"trade_count":sum(1 for x in current_rows if str(x.get("observation_type","TRADE")).upper()=="TRADE"),"move_from_previous_pct":mprev,"pulse_status":pulse_status,"raw_observation":{"price":price,"timestamp":anchor,"source":market.get("source"),"points_in_minute":len(current_rows)}}
    saved=await _persist_market_observation(env,payload)
    return {"ok":bool(saved.get("saved")),"observation_id":((saved.get("row") or {}).get("id") if isinstance(saved.get("row"),dict) else None),"persistence":saved,"price":price,"current_pulse_status":pulse_status}

def _agent_payload(result):
    agents=getattr(result,"agent_details",{}) or {};votes=getattr(result,"agent_votes",{}) or {};scores=getattr(result,"market_scores",{}) or {}
    return agents,votes,scores

async def run_paper_cycle(env,state_api,pair="btc_idr",state_response=None):
    begin=await state_api.begin_cycle()
    if not begin.get("ok"):return begin
    session_id=begin["state"].get("started_at") or _now();cycle_id=f"CYCLE-{uuid.uuid4()}"
    try:
        pair=cf_worker._clean_pair(pair);market=await cf_worker._market_overview({"env":env,"query_string":f"pair={pair}".encode("latin-1")})
        if not market.get("available") or _num(market.get("last"))<=0:raise RuntimeError("market_data_unavailable")
        points=list(market.get("points") or []);history=_merge(await state_api.get_paper_market_history(),points);await state_api.set_paper_market_history(history);anchor=max([_ts(x) for x in history if _ts(x)>0] or [datetime.now(timezone.utc).timestamp()])
        observation=await run_market_observation(env,state_api,pair,session_id)
        if not observation.get("ok"):raise RuntimeError(f"market_observation_persistence_failed: {observation.get('persistence',observation.get('reason'))}")
        market_data={"current_price":_num(market.get("last")),"unified_price":_num(market.get("last")),"timestamp":datetime.fromtimestamp(anchor,timezone.utc).isoformat(),"timeframe":"1m","recent_trades":history[-1440:],"high_24h":_num(market.get("high")),"low_24h":_num(market.get("low")),"volume_24h":_num(market.get("volume")),"data_quality_score":1.0,"source":"INDODAX public market data","market_source":"INDODAX public market data"}
        orchestrator=CloudflareOrchestrator({"fee_rate":0.0015,"slippage_rate":0.0002,"min_edge_pct":0.45},env=env);result=await orchestrator.analyze(market["pair"].upper().replace("_","/"),market_data);state=await state_api.get_state();agents,votes,scores=_agent_payload(result)
        symbol=market["pair"].upper().replace("_","/");action=str(getattr(result,"final_action","HOLD") or "HOLD").upper();confidence=max(0,min(1,_num(getattr(result,"final_confidence",0))));price=_num(market.get("last"));pulse=getattr(result,"candle_analysis",{}).get("pulse",{}) if isinstance(getattr(result,"candle_analysis",{}),dict) else {};pulse_segments=pulse.get("segments") or []
        execution_status="NOT_EXECUTED";risk_rejection=None;trade_id=None
        before=len(state.get("trade_history") or []);state=await state_api.record_cycle(action,confidence,symbol,price,getattr(result,"summary","") or "",{"votes":votes,"market_scores":scores,"confidence_components":getattr(result,"confidence_components",{}),"consensus_action":getattr(result,"consensus_action","HOLD"),"consensus_score":getattr(result,"consensus_score",0),"position_size":getattr(result,"position_size",0),"source":getattr(result,"engine_source","indodax_native"),"warning":getattr(result,"engine_warning",None),"raw_action":action,"summary":getattr(result,"summary","") ,"cycle_id":cycle_id,"cycle_number":int(state.get("cycles_today",0))+1,"market_timestamp":datetime.fromtimestamp(anchor,timezone.utc).isoformat(),"market_source":"INDODAX public market data","move_1m_pct":_latest_move(history,1,anchor),"move_5m_pct":_latest_move(history,5,anchor),"move_15m_pct":_latest_move(history,15,anchor),"move_30m_pct":_latest_move(history,PULSE_MINUTES,anchor),"pulse_status":pulse.get("overall") or "GRAY","current_pulse_status":pulse.get("current") or "GRAY","pulse_net_move_30m_pct":pulse.get("net_move_pct"),"pulse_segments":pulse_segments,"candidate_action":getattr(result,"consensus_action",action),"cycle_status":"ANALYZED","hold_analysis":getattr(result,"hold_analysis",{}),"symbol":symbol})
        after=len(state.get("trade_history") or []);execution_status="FILLED" if after>before else "NOT_EXECUTED";last=state.get("last_decision") or {};trade=last.get("trade") or {};trade_id=trade.get("id")
        if action in {"BUY","SELL"} and not trade and action=="BUY":risk_rejection="POSITION_ALREADY_OPEN" if state.get("active_positions",0)>=state.get("max_open_positions",3) else None
        payload={"symbol":symbol,"pair":symbol,"action":action if execution_status=="FILLED" else "HOLD" if action in {"BUY","SELL"} and risk_rejection else action,"confidence":confidence*100,"reasoning":_reasoning(getattr(result,"summary",""),getattr(result,"library_alerts",[])),"agent_votes":votes,"market_scores":scores,"confidence_components":getattr(result,"confidence_components",{}),"consensus_action":getattr(result,"consensus_action","HOLD"),"consensus_score":_num(getattr(result,"consensus_score",0)),"position_size":_num(getattr(result,"position_size",0)),"engine_source":getattr(result,"engine_source","indodax_native"),"engine_warning":getattr(result,"engine_warning",None),"cycle_id":cycle_id,"session_id":session_id,"cycle_number":int(state.get("cycles_today",0)),"market_timestamp":datetime.fromtimestamp(anchor,timezone.utc).isoformat(),"market_source":"INDODAX public market data","move_1m_pct":_latest_move(history,1,anchor),"move_5m_pct":_latest_move(history,5,anchor),"move_15m_pct":_latest_move(history,15,anchor),"move_30m_pct":_latest_move(history,PULSE_MINUTES,anchor),"pulse_status":pulse.get("overall") or "GRAY","current_pulse_status":pulse.get("current") or "GRAY","pulse_net_move_30m_pct":pulse.get("net_move_pct"),"data_quality_status":"OK","candidate_action":action,"execution_status":execution_status,"risk_rejection_reason":risk_rejection,"agent_run_count":len(agents),"raw_action":action,"pulse_segments":pulse_segments,"cycle_at":datetime.now(timezone.utc).isoformat(),"trading_date":datetime.now(timezone.utc).date().isoformat(),"price":price,"balance":_num(state.get("balance")),"portfolio_value":_num(state.get("portfolio_value")),"daily_pnl":_num(state.get("daily_pnl")),"total_pnl":_num(state.get("total_pnl")),"active_positions":int(state.get("active_positions",0)),"positions":state.get("positions") or [],"fees":_num(trade.get("fee")),"realized_pnl":_num(trade.get("pnl")) if execution_status=="FILLED" else 0,"execution_result":{"executed":execution_status=="FILLED","trade":trade or None},"trade_id":trade_id,"stop_loss":getattr(result,"stop_loss",None),"take_profit":getattr(result,"take_profit",None),"exit_reason":risk_rejection or getattr(result,"execution_reason",None)}
        saved=await _supabase(env,"decisions",payload=payload)
        if not saved.get("saved"):raise RuntimeError(f"decision_persistence_failed: {saved.get('reason')}")
        decision_rows=saved.get("rows") or [];decision_id=decision_rows[0].get("id") if isinstance(decision_rows[0],dict) else None
        paper_history={k:payload.get(k) for k in ("cycle_at","trading_date","pair","action","raw_action","confidence","execution_status","price","balance","portfolio_value","daily_pnl","total_pnl","active_positions","positions","agent_votes","market_scores","confidence_components","consensus_action","consensus_score","position_size","stop_loss","take_profit","reasoning","engine_source","engine_warning","cycle_id","session_id","cycle_number","decision_id","trade_id","market_timestamp","market_source","move_1m_pct","move_5m_pct","move_15m_pct","move_30m_pct","pulse_status","current_pulse_status","pulse_net_move_30m_pct","pulse_segments","hold_analysis","data_quality_status","execution_result","realized_pnl","unrealized_pnl","fees")}
        paper_history["agent_details"]=agents
        paper_history["execution_gate"]={"status":execution_status,"risk_rejection_reason":risk_rejection,"eligible":execution_status=="FILLED"}
        paper_history["market_snapshot"]={"symbol":symbol,"price":price,"timestamp":datetime.fromtimestamp(anchor,timezone.utc).isoformat(),"source":"INDODAX public market data","move_1m_pct":paper_history.get("move_1m_pct"),"move_5m_pct":paper_history.get("move_5m_pct"),"move_15m_pct":paper_history.get("move_15m_pct"),"move_30m_pct":paper_history.get("move_30m_pct")}
        paper_history["persistence_status"]="PENDING"
        paper_history["library_alerts"]=getattr(result,"library_alerts",[]) or []
        paper_history["candle_analysis"]=getattr(result,"candle_analysis",{}) or {}
        paper_history["knowledge_topics"]=getattr(result,"knowledge_topics",[]) or []
        paper_history["unrealized_pnl"]=_num(paper_history.get("unrealized_pnl"),0)
        history_saved=await _supabase(env,"paper_history",payload=paper_history)
        if not history_saved.get("saved"):raise RuntimeError(f"paper_history_persistence_failed: {history_saved.get('reason')}")
        await state_api.finish_cycle(None)
        return {"ok":True,"cycle_id":cycle_id,"state":state_response(await state_api.get_state()) if state_response else await state_api.get_state(),"decision":payload,"observation":observation,"execution":{"executed":execution_status=="FILLED","status":execution_status,"risk_rejection_reason":risk_rejection}}
    except Exception as exc:
        await state_api.finish_cycle(f"{type(exc).__name__}: {exc}")
        return {"ok":False,"cycle_id":cycle_id,"state":state_response(await state_api.get_state()) if state_response else await state_api.get_state(),"error":f"{type(exc).__name__}: {exc}"}

def _now():return datetime.now(timezone.utc).isoformat()
