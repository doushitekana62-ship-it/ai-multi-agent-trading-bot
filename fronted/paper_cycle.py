"""Canonical compounding paper cycle: real Indodax data -> agents -> risk -> execution -> Supabase."""
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

def _now(): return datetime.now(timezone.utc).isoformat()
def _num(v,d=0.0):
    try:return float(v)
    except (TypeError,ValueError):return d
def _ts(p):
    v=(p.get("timestamp") or p.get("date")) if isinstance(p,dict) else 0
    if isinstance(v,str):
        try:return datetime.fromisoformat(v.replace("Z","+00:00")).timestamp()
        except ValueError:return 0.0
    v=_num(v);return v/1000.0 if v>1_000_000_000_000 else v
def _safe(v):
    if v is None or isinstance(v,(str,int,float,bool)):return v
    if isinstance(v,datetime):return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()
    if isinstance(v,dict):return {str(k):_safe(x) for k,x in v.items()}
    if isinstance(v,(list,tuple)):return [_safe(x) for x in v]
    return str(v)

async def _supabase(env,table,method="POST",query="",payload=None):
    base=str(getattr(env,"SUPABASE_URL","") or "").strip().rstrip("/")
    key=str(getattr(env,"SUPABASE_SECRET_KEY","") or getattr(env,"SUPABASE_SERVICE_ROLE_KEY","") or "").strip()
    if not base or not key:return {"ok":False,"saved":False,"reason":"supabase_credentials_missing"}
    try:
        headers={"apikey":key,"Authorization":f"Bearer {key}","Accept":"application/json","Content-Type":"application/json"}
        if method.upper()=="POST":headers["Prefer"]="return=representation"
        opts={"method":method,"headers":headers}
        if payload is not None:opts["body"]=json.dumps(_safe(payload),separators=(",",":"))
        r=await fetch(f"{base}/rest/v1/{table}{query}",to_js(opts));text=await r.text();code=int(r.status)
        if code<200 or code>=300:return {"ok":False,"saved":False,"reason":f"supabase_http_{code}: {text[:500]}"}
        try:data=json.loads(text) if text else []
        except Exception:data=[]
        return {"ok":True,"saved":True,"rows":data if isinstance(data,list) else [data] if isinstance(data,dict) else []}
    except Exception as exc:return {"ok":False,"saved":False,"reason":f"{type(exc).__name__}: {exc}"}

async def _persist_market_observation(env,payload):
    result=await _supabase(env,"rpc/upsert_market_observation",payload={"p_payload":_safe(payload)})
    if not result.get("saved"):return result
    return {"ok":True,"saved":True,"row":(result.get("rows") or [None])[0]}

def _merge(old,current):
    out=[];seen=set()
    for p in list(old or [])+list(current or []):
        if not isinstance(p,dict):continue
        key=(str(p.get("tid","")),str(p.get("timestamp",p.get("date",""))),str(p.get("price","")),str(p.get("observation_type",p.get("type",""))))
        if key not in seen:seen.add(key);out.append(p)
    out.sort(key=_ts);return out[-MARKET_HISTORY_LIMIT:]
def _latest_move(history,minutes,anchor):
    rows=[p for p in history if anchor-minutes*60<=_ts(p)<=anchor and _num(p.get("price"))>0];rows.sort(key=_ts)
    return None if len(rows)<2 else (_num(rows[-1]["price"])/_num(rows[0]["price"])-1)*100
def _reasoning(text,alerts=None):
    clean=str(text or "").split(LIBRARY_ALERT_MARKER,1)[0].strip()
    return f"{clean} {LIBRARY_ALERT_MARKER}{json.dumps(alerts[:4],separators=(',',':'))}".strip() if alerts else clean

async def run_market_observation(env,state_api,pair="btc_idr",session_id=None):
    pair=cf_worker._clean_pair(pair);market=await cf_worker._market_overview({"env":env,"query_string":f"pair={pair}".encode("latin-1")});price=_num(market.get("last"))
    if not market.get("available") or price<=0:return {"ok":False,"reason":"market_data_unavailable"}
    history=_merge(await state_api.get_paper_market_history(),list(market.get("points") or []));await state_api.set_paper_market_history(history);anchor=max([_ts(x) for x in history if _ts(x)>0] or [datetime.now(timezone.utc).timestamp()]);rows=sorted([x for x in history if int(_ts(x)//60)==int(anchor//60)],key=_ts)
    o=_num(rows[0].get("price")) if rows else price;c=_num(rows[-1].get("price")) if rows else price;changed=any(_num(rows[i].get("price"))!=_num(rows[i-1].get("price")) for i in range(1,len(rows)));direction=None
    for i in range(len(rows)-1,0,-1):
        if _num(rows[i].get("price"))!=_num(rows[i-1].get("price")):direction="GREEN" if _num(rows[i].get("price"))>_num(rows[i-1].get("price")) else "RED";break
    pulse="GREEN" if c>o else "RED" if c<o else direction or "GRAY";symbol=market["pair"].upper().replace("_","/");minute=datetime.fromtimestamp(int(anchor//60)*60,timezone.utc).isoformat()
    payload={"cycle_id":f"OBS-{uuid.uuid4()}","session_id":session_id or _now(),"symbol":symbol,"observed_at":datetime.fromtimestamp(anchor,timezone.utc).isoformat(),"minute_bucket":minute,"price":price,"source":str((history[-1] if history else {}).get("source") or "INDODAX public market data"),"observation_type":str((history[-1] if history else {}).get("observation_type") or "TICKER").upper(),"trade_count":sum(1 for x in rows if str(x.get("observation_type","TRADE")).upper()=="TRADE"),"move_from_previous_pct":_latest_move(history,1,anchor),"pulse_status":pulse,"changed":changed,"last_direction":direction,"raw_observation":{"price":price,"timestamp":anchor,"source":market.get("source"),"points_in_minute":len(rows),"changed":changed,"last_direction":direction}}
    saved=await _persist_market_observation(env,payload)
    return {"ok":bool(saved.get("saved")),"observation_id":((saved.get("row") or {}).get("id") if isinstance(saved.get("row"),dict) else None),"persistence":saved,"price":price,"current_pulse_status":pulse}

def _result_fields(result):
    return getattr(result,"agent_details",{}) or {},getattr(result,"agent_votes",{}) or {},getattr(result,"market_scores",{}) or {}
async def _record_integrity(env,cycle_id,session_id,symbol,reason,details):
    return await _supabase(env,"paper_integrity_events",payload={"severity":"ERROR","event_type":"PAPER_LEDGER_PERSISTENCE_FAILURE","cycle_id":cycle_id,"session_id":session_id,"symbol":symbol,"details":{"reason":reason,**(_safe(details) if isinstance(details,dict) else {})}})

async def _persist_execution_trade(env,trade,decision_id,cycle_id,session_id):
    if not isinstance(trade,dict) or not trade.get("action"):return {"ok":True,"trade_id":None,"status":"NOT_EXECUTED"}
    symbol=str(trade.get("symbol"));action=str(trade.get("action")).upper();now=_now()
    if action=="BUY":
        saved=await _supabase(env,"trades",payload={"decision_id":decision_id,"symbol":symbol,"action":"BUY","entry_price":_num(trade.get("entry_price",trade.get("price"))),"price":_num(trade.get("price")),"quantity":_num(trade.get("quantity")),"pnl":_num(trade.get("pnl")),"confidence":_num(trade.get("confidence"))*100,"status":"OPEN","cycle_id":cycle_id,"session_id":session_id,"order_id":f"PAPER-{cycle_id}"})
    else:
        lookup=await _supabase(env,"trades","GET",f"?select=id&symbol=eq.{symbol}&status=eq.OPEN&order=created_at.desc&limit=1")
        rows=lookup.get("rows") or []
        if not lookup.get("ok") or not rows:return {"ok":False,"reason":"open_trade_not_found_for_sell","trade_id":None}
        trade_id=rows[0].get("id");saved=await _supabase(env,"trades","PATCH",f"?id=eq.{trade_id}",{"exit_price":_num(trade.get("exit_price",trade.get("price"))),"price":_num(trade.get("price")),"pnl":_num(trade.get("pnl")),"status":"CLOSED","closed_at":now,"exit_decision_id":decision_id,"reconciled":True,"reconciliation_reason":str(trade.get("exit_reason") or "PAPER_EXIT"),"reconciled_at":now});saved["rows"]=[rows[0]] if saved.get("ok") else []
    if not saved.get("ok"):return {"ok":False,"reason":saved.get("reason","trade_persistence_failed"),"trade_id":None}
    rows=saved.get("rows") or [];trade_id=rows[0].get("id") if rows and isinstance(rows[0],dict) else None
    return {"ok":bool(trade_id),"reason":None if trade_id else "trade_id_missing_after_persistence","trade_id":trade_id,"status":"FILLED"}

async def run_paper_cycle(env,state_api,pair="btc_idr",state_response=None):
    begin=await state_api.begin_cycle()
    if not begin.get("ok"):return begin
    session_id=begin["state"].get("started_at") or _now();cycle_id=f"CYCLE-{uuid.uuid4()}"
    try:
        pair=cf_worker._clean_pair(pair);market=await cf_worker._market_overview({"env":env,"query_string":f"pair={pair}".encode("latin-1")});price=_num(market.get("last"))
        if not market.get("available") or price<=0:raise RuntimeError("market_data_unavailable")
        history=_merge(await state_api.get_paper_market_history(),list(market.get("points") or []));await state_api.set_paper_market_history(history);anchor=max([_ts(x) for x in history if _ts(x)>0] or [datetime.now(timezone.utc).timestamp()])
        observation=await run_market_observation(env,state_api,pair,session_id)
        if not observation.get("ok"):raise RuntimeError(f"market_observation_persistence_failed: {observation.get('persistence',observation.get('reason'))}")
        symbol=market["pair"].upper().replace("_","/");market_data={"current_price":price,"unified_price":price,"timestamp":datetime.fromtimestamp(anchor,timezone.utc).isoformat(),"timeframe":"1m","recent_trades":history[-1440:],"high_24h":_num(market.get("high")),"low_24h":_num(market.get("low")),"volume_24h":_num(market.get("volume")),"data_quality_score":1.0,"source":"INDODAX public market data","market_source":"INDODAX public market data"}
        result=await CloudflareOrchestrator({"fee_rate":0.0015,"slippage_rate":0.0002,"min_edge_pct":0.45},env=env).analyze(symbol,market_data);agents,votes,scores=_result_fields(result);state=await state_api.get_state();candidate=str(getattr(result,"final_action","HOLD") or "HOLD").upper();confidence=max(0,min(1,_num(getattr(result,"final_confidence",0))));ca=getattr(result,"candle_analysis",{});pulse=(ca.get("pulse") or {}) if isinstance(ca,dict) else {}
        analysis={"votes":votes,"market_scores":scores,"confidence_components":getattr(result,"confidence_components",{}),"consensus_action":getattr(result,"consensus_action",candidate),"consensus_score":getattr(result,"consensus_score",0),"position_size":getattr(result,"position_size",0),"source":getattr(result,"engine_source","indodax_native"),"warning":getattr(result,"engine_warning",None),"raw_action":candidate,"summary":getattr(result,"summary",""),"cycle_id":cycle_id,"cycle_number":int(state.get("cycles_today",0))+1,"market_timestamp":datetime.fromtimestamp(anchor,timezone.utc).isoformat(),"market_source":"INDODAX public market data","move_1m_pct":_latest_move(history,1,anchor),"move_5m_pct":_latest_move(history,5,anchor),"move_15m_pct":_latest_move(history,15,anchor),"move_30m_pct":_latest_move(history,PULSE_MINUTES,anchor),"pulse_status":pulse.get("overall","GRAY"),"current_pulse_status":observation.get("current_pulse_status","GRAY"),"pulse_net_move_30m_pct":pulse.get("net_move_pct"),"pulse_segments":pulse.get("segments",[]),"candidate_action":candidate,"cycle_status":getattr(result,"cycle_status","ANALYZED"),"hold_analysis":getattr(result,"hold_analysis",{}) or {},"symbol":symbol,"net_edge_pct":getattr(result,"net_edge_pct",0),"expected_move_pct":getattr(result,"expected_move_pct",0),"friction_pct":getattr(result,"friction_pct",0),"data_quality_status":"OK","library_version":getattr(result,"library_version",None),"library_alerts":getattr(result,"library_alerts",[]),"agent_details":agents}
        state=await state_api.record_cycle(candidate,confidence,symbol,price,getattr(result,"summary","") or "",analysis);last=state.get("last_decision") or {};trade=last.get("trade") if isinstance(last.get("trade"),dict) else None;execution_status="FILLED" if trade and last.get("executed") else "NOT_EXECUTED";risk_gate=last.get("risk_gate") or {};risk_rejection=risk_gate.get("reason") if candidate=="BUY" and not trade else None
        payload={"symbol":symbol,"pair":symbol,"action":last.get("action",candidate),"candidate_action":candidate,"raw_action":candidate,"confidence":confidence*100,"reasoning":_reasoning(getattr(result,"summary",""),getattr(result,"library_alerts",[])),"agent_votes":votes,"market_scores":scores,"confidence_components":getattr(result,"confidence_components",{}),"consensus_action":getattr(result,"consensus_action",candidate),"consensus_score":_num(getattr(result,"consensus_score",0)),"position_size":_num(getattr(result,"position_size",0)),"engine_source":getattr(result,"engine_source","indodax_native"),"engine_warning":getattr(result,"engine_warning",None),"cycle_id":cycle_id,"session_id":session_id,"cycle_number":int(state.get("cycles_today",0)),"market_timestamp":datetime.fromtimestamp(anchor,timezone.utc).isoformat(),"market_source":"INDODAX public market data","move_1m_pct":analysis["move_1m_pct"],"move_5m_pct":analysis["move_5m_pct"],"move_15m_pct":analysis["move_15m_pct"],"move_30m_pct":analysis["move_30m_pct"],"pulse_status":analysis["pulse_status"],"current_pulse_status":analysis["current_pulse_status"],"pulse_net_move_30m_pct":analysis["pulse_net_move_30m_pct"],"pulse_segments":analysis["pulse_segments"],"data_quality_status":"OK","execution_status":execution_status,"risk_rejection_reason":risk_rejection,"agent_run_count":len(agents),"cycle_at":_now(),"trading_date":datetime.now(timezone.utc).date().isoformat(),"price":price,"balance":_num(state.get("balance")),"portfolio_value":_num(state.get("portfolio_value")),"daily_pnl":_num(state.get("daily_pnl")),"total_pnl":_num(state.get("total_pnl")),"active_positions":int(state.get("active_positions",0)),"positions":state.get("positions") or [],"fees":_num((trade or {}).get("fee")),"realized_pnl":_num((trade or {}).get("pnl")) if execution_status=="FILLED" else 0,"execution_result":{"executed":execution_status=="FILLED","trade":trade,"risk_gate":risk_gate},"trade_id":None,"stop_loss":getattr(result,"stop_loss",None),"take_profit":getattr(result,"take_profit",None),"exit_reason":last.get("risk_exit_reason") or getattr(result,"execution_reason",None),"hold_analysis":getattr(result,"hold_analysis",{}) or {},"agent_details":agents,"library_version":getattr(result,"library_version",None),"library_alerts":getattr(result,"library_alerts",[]) or []}
        saved=await _supabase(env,"decisions",payload=payload)
        if not saved.get("saved"):raise RuntimeError(f"decision_persistence_failed: {saved.get('reason')}")
        decision_rows=saved.get("rows") or [];decision_id=decision_rows[0].get("id") if decision_rows and isinstance(decision_rows[0],dict) else None
        ledger=await _persist_execution_trade(env,trade,decision_id,cycle_id,session_id)
        if not ledger.get("ok"):
            await _record_integrity(env,cycle_id,session_id,symbol,ledger.get("reason","trade_persistence_failed"),{"decision_id":decision_id,"trade":trade,"execution_status":execution_status})
            if decision_id:await _supabase(env,"decisions","PATCH",f"?id=eq.{decision_id}",{"persistence_status":"FAILED","execution_status":execution_status,"risk_rejection_reason":ledger.get("reason")})
            raise RuntimeError(f"trade_ledger_persistence_failed: {ledger.get('reason')}")
        trade_id=ledger.get("trade_id")
        if decision_id and trade_id:
            linked=await _supabase(env,"decisions","PATCH",f"?id=eq.{decision_id}",{"trade_id":trade_id,"persistence_status":"saved"})
            if not linked.get("ok"):raise RuntimeError(f"decision_trade_link_failed: {linked.get('reason')}")
        payload["decision_id"]=decision_id;payload["trade_id"]=trade_id;payload["persistence_status"]="saved";payload["execution_result"]["trade_id"]=trade_id
        history_payload={k:payload.get(k) for k in ("cycle_at","trading_date","pair","action","raw_action","confidence","price","balance","portfolio_value","daily_pnl","total_pnl","active_positions","positions","agent_votes","market_scores","confidence_components","consensus_action","consensus_score","position_size","stop_loss","take_profit","reasoning","engine_source","engine_warning","cycle_id","session_id","cycle_number","decision_id","trade_id","market_timestamp","market_source","move_1m_pct","move_5m_pct","move_15m_pct","move_30m_pct","pulse_status","current_pulse_status","pulse_net_move_30m_pct","pulse_segments","data_quality_status","execution_status","execution_result","realized_pnl","fees","risk_rejection_reason","candidate_action","library_version","library_alerts","hold_analysis","agent_details")};history_payload["execution_gate"]={"status":execution_status,"eligible":execution_status=="FILLED","risk_gate":risk_gate};history_payload["market_snapshot"]={"symbol":symbol,"price":price,"source":"INDODAX public market data","observed_at":datetime.fromtimestamp(anchor,timezone.utc).isoformat()}
        hist=await _supabase(env,"paper_history",payload=history_payload)
        if not hist.get("saved"):raise RuntimeError(f"paper_history_persistence_failed: {hist.get('reason')}")
        await state_api.record_orchestrator({"cycle_id":cycle_id,"session_id":session_id,"engine_source":getattr(result,"engine_source","indodax_native"),"engine_warning":getattr(result,"engine_warning",None),"agent_run_count":len(agents),"decision_id":decision_id,"trade_id":trade_id,"execution_status":execution_status})
        await state_api.finish_cycle(None)
        return {"ok":True,"state":state,"decision_id":decision_id,"trade_id":trade_id,"execution_status":execution_status,"risk_gate":risk_gate,"market_observation":observation,"persistence":{"decision":True,"trade":bool(trade_id),"paper_history":True}}
    except Exception as exc:
        await state_api.finish_cycle(exc)
        return {"ok":False,"state":await state_api.get_state(),"reason":type(exc).__name__,"error":str(exc),"cycle_id":cycle_id,"session_id":session_id}
