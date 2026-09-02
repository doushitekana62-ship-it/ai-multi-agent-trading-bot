"""Persistent paper-trading state backed by a Durable Object."""
from __future__ import annotations
from datetime import datetime, timezone
from workers import DurableObject
from paper_cycle import run_market_observation, run_paper_cycle
from risk_engine import apply_slippage, settings_with_defaults, update_protection

# Scheduler polls market observations every 5s; decisions are evaluated every 15s.
# CYCLE_INTERVAL_MS = 60_000
CYCLE_INTERVAL_MS = 5_000
DECISION_INTERVAL_MS = 15_000
MAX_POSITIONS = 3
DEFAULT_POSITION_ALLOCATION = 0.10
STATE_VERSION = 5
MARKET_HISTORY_LIMIT = 1440
DEFAULT_STATE={"state_version":STATE_VERSION,"enabled":False,"mode":"paper","cycle_running":False,"started_at":None,"last_cycle_at":None,"last_cycle_started_at":None,"last_cycle_finished_at":None,"last_cycle_status":"idle","cycles_today":0,"cycle_failures":0,"consecutive_cycle_failures":0,"balance":10_000_000.0,"initial_balance":10_000_000.0,"portfolio_value":10_000_000.0,"daily_pnl":0.0,"total_pnl":0.0,"daily_trades":0,"total_trades":0,"active_positions":0,"max_open_positions":MAX_POSITIONS,"position_allocation":DEFAULT_POSITION_ALLOCATION,"decision_counts":{"BUY":0,"SELL":0,"HOLD":0},"positions":[],"trade_history":[],"last_decision":None,"last_error":None,"paper_pair":"btc_idr","scheduler_active":False,"scheduler_source":"durable_object_alarm","last_scheduler_at":None,"scheduler_invocations":0,"next_cycle_at":None,"risk_settings":settings_with_defaults(),"updated_at":None}

def _now():return datetime.now(timezone.utc).isoformat()
def _iso(ms):return datetime.fromtimestamp(ms/1000,timezone.utc).isoformat()
def _num(v,d=0.0):
    try:return float(v)
    except (TypeError,ValueError):return d

def _copy():
    s=dict(DEFAULT_STATE); s["decision_counts"]={"BUY":0,"SELL":0,"HOLD":0}; s["positions"]=[]; s["trade_history"]=[]; s["risk_settings"]=dict(DEFAULT_STATE["risk_settings"]); return s

def _limit(v):
    try:v=int(v)
    except (TypeError,ValueError):v=MAX_POSITIONS
    return max(1, min(MAX_POSITIONS, v))

class PaperTradingState(DurableObject):
    def __init__(self,ctx,env):super().__init__(ctx,env);self.ctx=ctx;self.env=env
    async def _get(self):
        state=await self.ctx.storage.get("state")
        if not isinstance(state,dict):state=_copy()
        for k,v in DEFAULT_STATE.items():state.setdefault(k,v.copy() if isinstance(v,dict) else list(v) if isinstance(v,list) else v)
        state["risk_settings"]=settings_with_defaults(state.get("risk_settings")); state["max_open_positions"]=_limit(state.get("max_open_positions")); state["active_positions"]=len(state.get("positions") or []); state["state_version"]=STATE_VERSION
        await self.ctx.storage.put("state",state); return state
    async def get_state(self):return await self._get()
    async def get_settings(self):
        s=await self._get(); return {"max_open_positions":s["max_open_positions"],"position_allocation":s["position_allocation"],"active_positions":s["active_positions"],"hard_max_positions":MAX_POSITIONS,"updated_at":s.get("updated_at")}
    async def get_risk_settings(self):return dict((await self._get())["risk_settings"])
    async def set_risk_settings(self,patch):
        s=await self._get(); merged=dict(s.get("risk_settings") or {}); merged.update({k:v for k,v in (patch or {}).items() if k in merged}); s["risk_settings"]=settings_with_defaults(merged); s["updated_at"]=_now(); await self.ctx.storage.put("state",s); return s
    async def get_paper_market_history(self):
        x=await self.ctx.storage.get("paper_market_history"); return x if isinstance(x,list) else []
    async def set_paper_market_history(self,history):
        x=(history if isinstance(history,list) else [])[-MARKET_HISTORY_LIMIT:]; await self.ctx.storage.put("paper_market_history",x); return x
    async def _arm(self):
        alarm=await self.ctx.storage.getAlarm()
        if alarm is None:
            alarm=int(datetime.now(timezone.utc).timestamp()*1000)+CYCLE_INTERVAL_MS; self.ctx.storage.setAlarm(alarm)
        return _iso(alarm)
    async def ensure_scheduler(self):
        s=await self._get()
        if s.get("enabled") and not s.get("cycle_running"):
            s["scheduler_active"]=True; s["next_cycle_at"]=await self._arm(); await self.ctx.storage.put("state",s)
        return s
    async def enable_paper(self,pair="btc_idr"):
        s=await self._get(); now=_now(); s.update({"enabled":True,"mode":"paper","cycle_running":False,"started_at":now,"last_cycle_status":"waiting","cycle_failures":0,"consecutive_cycle_failures":0,"last_error":None,"paper_pair":str(pair or "btc_idr").strip().lower(),"scheduler_active":True,"scheduler_source":"durable_object_alarm","updated_at":now}); s["next_cycle_at"]=await self._arm(); await self.ctx.storage.put("state",s); return s
    async def start(self,pair="btc_idr"):return await self.enable_paper(pair)
    async def set_position_limit(self,value):
        s=await self._get();s["max_open_positions"]=_limit(value);s["active_positions"]=len(s.get("positions") or []);s["updated_at"]=_now();await self.ctx.storage.put("state",s);return s
    async def stop(self):
        s=await self._get();s.update({"enabled":False,"cycle_running":False,"scheduler_active":False,"next_cycle_at":None,"last_error":None,"last_cycle_status":"stopped","updated_at":_now()});self.ctx.storage.deleteAlarm();await self.ctx.storage.put("state",s);return s
    async def reset(self):
        self.ctx.storage.deleteAlarm();await self.ctx.storage.delete("paper_market_history");s=_copy();s["updated_at"]=_now();await self.ctx.storage.put("state",s);return s
    async def begin_cycle(self):
        s=await self._get()
        if not s.get("enabled"):return {"ok":False,"state":s,"reason":"paper_trading_disabled"}
        if s.get("cycle_running"):return {"ok":False,"state":s,"reason":"cycle_already_running"}
        now=_now();s.update({"cycle_running":True,"last_error":None,"last_cycle_started_at":now,"last_cycle_status":"running","scheduler_active":True,"updated_at":now});await self.ctx.storage.put("state",s);return {"ok":True,"state":s,"reason":None}
    async def finish_cycle(self,error=None):
        s=await self._get();now=_now();s.update({"cycle_running":False,"last_cycle_finished_at":now,"last_cycle_status":"failed" if error else "completed","last_error":str(error) if error else None,"updated_at":now})
        if error:s["cycle_failures"]=int(s.get("cycle_failures",0))+1;s["consecutive_cycle_failures"]=int(s.get("consecutive_cycle_failures",0))+1
        else:s["consecutive_cycle_failures"]=0
        await self.ctx.storage.put("state",s);return s
    async def record_orchestrator(self,metadata):await self.ctx.storage.put("last_orchestrator",metadata if isinstance(metadata,dict) else {});return metadata
    async def preview_risk_exit(self,symbol,price):
        s=await self._get();risk=settings_with_defaults(s.get("risk_settings"));p=next((x for x in s.get("positions") or [] if str(x.get("symbol")).upper()==str(symbol).upper()),None)
        if not risk.get("enabled") or p is None:return {"triggered":False,"reason":None,"symbol":symbol,"price":_num(price),"risk_enabled":bool(risk.get("enabled"))}
        snap=update_protection(p,_num(price),await self.get_paper_market_history(),risk);return {"triggered":bool(snap.get("triggered")),"reason":snap.get("reason"),"symbol":symbol,"price":_num(price),"risk_enabled":True,"snapshot":snap}
    async def record_cycle(self,decision="HOLD",confidence=0.0,symbol="BTC/IDR",price=0.0,reasoning="",analysis=None):
        s=await self._get()
        if not s.get("enabled"):return s
        now=_now();action=str(decision or "HOLD").upper();action=action if action in {"BUY","SELL","HOLD"} else "HOLD";confidence=max(0,min(1,_num(confidence)));price=_num(price);risk=settings_with_defaults(s.get("risk_settings"));points=await self.get_paper_market_history();positions=list(s.get("positions") or []);idx=next((i for i,p in enumerate(positions) if str(p.get("symbol")).upper()==str(symbol).upper()),None);position=positions[idx] if idx is not None else None;risk_exit=None;executed=False;trade=None;realized=0.0;fee=0.0
        if position is not None and risk.get("enabled") and price>0:
            snap=update_protection(position,price,points,risk)
            if snap.get("triggered"):action="SELL";risk_exit=snap.get("reason") or "STOP_LOSS"
        if action=="BUY" and price>0 and idx is None and len(positions)<s["max_open_positions"]:
            equity=float(s.get("balance",0))+sum(_num(p.get("quantity"))*_num(p.get("price",p.get("entry_price"))) for p in positions);allocation=min(equity*s["position_allocation"],float(s.get("balance",0))/(1+risk["fee_rate"]))
            if allocation>0:
                fill=apply_slippage(price,"BUY",risk["slippage_bps"]);qty=allocation/fill;fee=allocation*risk["fee_rate"];levels=update_protection({"entry_price":fill,"created_at":now},fill,points,risk);positions.append({"symbol":symbol,"side":"BUY","quantity":qty,"entry_price":fill,"price":fill,"capital":allocation,"position_size":allocation/equity if equity else 0,"pnl":0,"unrealized_pnl":0,"confidence":confidence,"created_at":now,"entry_fee":fee,"fees":fee,"high_water_mark":fill,"stop_loss":levels.get("stop_loss"),"take_profit":levels.get("take_profit"),"initial_stop_loss":levels.get("stop_loss"),"initial_take_profit":levels.get("take_profit"),"risk_mode":risk["stop_loss_mode"]});s["balance"]=_num(s.get("balance"))-allocation-fee;executed=True;trade={"action":"BUY","symbol":symbol,"quantity":qty,"price":fill,"requested_price":price,"pnl":-fee,"confidence":confidence,"created_at":now,"fee":fee,"exit_reason":None}
        elif action=="SELL" and price>0 and idx is not None:
            p=positions[idx];qty=_num(p.get("quantity"));entry=_num(p.get("entry_price"),price);fill=apply_slippage(price,"SELL",risk["slippage_bps"]);proceeds=qty*fill;fee=proceeds*risk["fee_rate"];realized=proceeds-fee-_num(p.get("capital"),entry*qty)-_num(p.get("entry_fee"));s["balance"]=_num(s.get("balance"))+proceeds-fee;positions.pop(idx);s["daily_pnl"]=_num(s.get("daily_pnl"))+realized;s["total_pnl"]=_num(s.get("total_pnl"))+realized;executed=True;trade={"action":"SELL","symbol":symbol,"quantity":qty,"price":fill,"requested_price":price,"entry_price":entry,"pnl":realized,"confidence":confidence,"created_at":now,"fee":fee,"entry_fee":_num(p.get("entry_fee")),"exit_reason":risk_exit or str((analysis or {}).get("exit_reason") or "AI_EXIT")}
        for p in positions:
            if str(p.get("symbol")).upper()==str(symbol).upper() and price>0:
                p["price"]=price;p["unrealized_pnl"]=(price-_num(p.get("entry_price")))*_num(p.get("quantity"))-price*_num(p.get("quantity"))*risk["fee_rate"];p["pnl"]=p["unrealized_pnl"]
        if trade:s["trade_history"]=([*list(s.get("trade_history") or []),trade])[-100:]
        s["positions"]=positions;s["active_positions"]=len(positions);s["portfolio_value"]=_num(s.get("balance"))+sum(_num(p.get("quantity"))*_num(p.get("price",p.get("entry_price"))) for p in positions);s["cycles_today"]=int(s.get("cycles_today",0))+1;s["last_cycle_at"]=now;s["last_cycle_finished_at"]=now;s["last_cycle_status"]="completed";counts=s.setdefault("decision_counts",{"BUY":0,"SELL":0,"HOLD":0});counts[action]=int(counts.get(action,0))+1
        if executed:s["daily_trades"]=int(s.get("daily_trades",0))+1;s["total_trades"]=int(s.get("total_trades",0))+1
        last={"action":action,"candidate_action":action,"confidence":confidence,"symbol":symbol,"price":price,"executed":executed,"realized_pnl":realized,"fee":fee,"reasoning":reasoning,"created_at":now,"risk_exit_reason":risk_exit}
        if isinstance(analysis,dict):last.update({k:analysis[k] for k in analysis if k in {"votes","market_scores","confidence_components","consensus_action","consensus_score","position_size","stop_loss","take_profit","source","warning","raw_action","summary","execution_gate","cycle_id","cycle_number","market_timestamp","market_source","move_1m_pct","move_5m_pct","move_15m_pct","move_30m_pct","pulse_status","current_pulse_status","pulse_net_move_30m_pct","pulse_segments","hold_analysis","candidate_action","cycle_status"}})
        if trade:last["trade"]=trade
        s["last_decision"]=last;s["cycle_running"]=False;s["last_error"]=None;s["consecutive_cycle_failures"]=0;s["updated_at"]=now;await self.ctx.storage.put("state",s);return s
    async def apply_cycle(self,action="HOLD",price=0.0,confidence=0.0,cycle_id=None,metadata=None):
        m=dict(metadata or {})
        if cycle_id is not None:m.setdefault("cycle_id",str(cycle_id))
        return await self.record_cycle(action,confidence,m.get("symbol","BTC/IDR"),price,m.get("summary",m.get("reasoning","")),m)
    async def record_cycle_payload(self,payload):
        p=payload if isinstance(payload,dict) else {};return await self.record_cycle(p.get("decision","HOLD"),p.get("confidence",0),p.get("symbol","BTC/IDR"),p.get("price",0),p.get("reasoning",""),p.get("analysis"))
    async def alarm(self,alarm_info=None):
        s=await self._get();now_ms=int(datetime.now(timezone.utc).timestamp()*1000);s["last_scheduler_at"]=_now();s["scheduler_invocations"]=int(s.get("scheduler_invocations",0))+1;s["scheduler_active"]=bool(s.get("enabled"));await self.ctx.storage.put("state",s)
        if not s.get("enabled"):self.ctx.storage.deleteAlarm();return
        try:
            last=_num(datetime.fromisoformat(str(s.get("last_cycle_at"))).timestamp()*1000) if s.get("last_cycle_at") else 0;due=(not last) or now_ms-last>=DECISION_INTERVAL_MS
            if due:await run_paper_cycle(self.env,self,s.get("paper_pair") or "btc_idr")
            else:await run_market_observation(self.env,self,s.get("paper_pair") or "btc_idr",s.get("started_at"))
        except Exception as exc:
            s=await self._get();s["last_error"]=f"scheduler_cycle_error: {type(exc).__name__}: {exc}";s["updated_at"]=_now();await self.ctx.storage.put("state",s)
        s=await self._get()
        if not s.get("enabled"):self.ctx.storage.deleteAlarm();s["scheduler_active"]=False;s["next_cycle_at"]=None
        else:s["next_cycle_at"]=await self._arm();s["scheduler_active"]=True
        s["updated_at"]=_now();await self.ctx.storage.put("state",s)
