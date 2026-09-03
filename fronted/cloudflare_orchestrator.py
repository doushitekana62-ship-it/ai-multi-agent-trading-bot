"""Cloudflare adapter for the canonical Indodax scalping decision path."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict
from js import fetch
from pyodide.ffi import to_js
from core.indodax_scalping_strategy import SOURCE, STRATEGY_VERSION, analyze as analyze_indodax

class CloudflareOrchestrator:
    def __init__(self, config: Dict[str, Any] | None = None, env: Any = None):
        self.config=config or {}; self.env=env
    @staticmethod
    def _number(value, default=0.0):
        try:return float(value)
        except (TypeError,ValueError):return default
    @staticmethod
    def _timestamp(value):
        try:return datetime.fromisoformat(str(value).replace("Z","+00:00"))
        except (TypeError,ValueError):return datetime.now(timezone.utc)
    @staticmethod
    def _namespace(result: Dict[str,Any]):
        agents=result.get("agents") or {}; number=CloudflareOrchestrator._number; exit_plan=result.get("exit_plan") or {}
        return SimpleNamespace(timestamp=datetime.now(timezone.utc),symbol=result.get("symbol",""),current_price=result.get("price",0.0),final_action=result.get("action","HOLD"),final_confidence=result.get("confidence",0.0),consensus_action=result.get("candidate_action","HOLD"),consensus_score=result.get("score",0.0),agent_votes={k:str(v.get("direction","NEUTRAL")).replace("BULLISH","BUY").replace("BEARISH","SELL") for k,v in agents.items()},market_scores={k:number(v.get("score")) for k,v in agents.items()},confidence_components={"net_edge_pct":number(result.get("net_edge_pct")),"confirmations":number(result.get("confirmations")),"expected_move_pct":number(result.get("expected_move_pct")),"friction_pct":number(result.get("friction_pct"))},position_size=number(result.get("position_size")),stop_loss=None,take_profit=result.get("take_profit") or result.get("take_profit_pct"),execution_reason=exit_plan.get("exit_reason") or result.get("reason"),hold_reason=result.get("reason") if result.get("action")=="HOLD" else None,summary=result.get("summary",""),engine_source="indodax_native",engine_warning=None,hold_agents=[k for k,v in agents.items() if v.get("direction")=="NEUTRAL"],opposing_agents=[],hold_analysis={"reason":result.get("reason"),"net_edge_pct":result.get("net_edge_pct"),"confirmations":result.get("confirmations"),"exit_plan":exit_plan},knowledge_topics=["1m micro-momentum","5m confirmation","30m regime","volume impulse","Indodax tape","dynamic TP continuation"],candle_analysis={"pulse":result.get("pulse")},library_alerts=[],library_version=STRATEGY_VERSION,agent_details=agents,cycle_status="ANALYZED",sentiment=SimpleNamespace(**(agents.get("sentiment") or {})),technical=SimpleNamespace(**(agents.get("technical") or {})),decision=SimpleNamespace(**(agents.get("decision") or {})),forecast=SimpleNamespace(**(agents.get("forecast") or {})),reflection=SimpleNamespace(**(agents.get("reflection") or {})),mimic_analysis=None,exit_plan=exit_plan,take_profit_pct=result.get("take_profit_pct"),stop_loss_pct=result.get("stop_loss_pct"))
    async def _fastapi(self,symbol,market_data):
        base=str(getattr(self.env,"AI_ENGINE_URL","") or "").strip().rstrip("/") if self.env is not None else "";secret=str(getattr(self.env,"AI_ENGINE_SHARED_SECRET","") or "").strip() if self.env is not None else ""
        if not base or len(secret)<32:return None
        response=await fetch(f"{base}/engine/analyze",to_js({"method":"POST","headers":{"Content-Type":"application/json","Accept":"application/json","X-AI-Engine-Key":secret},"body":json.dumps({"symbol":str(symbol).upper(),"market_data":market_data},separators=(",",":"))}));status=int(response.status);text=await response.text()
        if status<200 or status>=300:raise RuntimeError(f"AI engine HTTP {status}: {text[:200]}")
        data=json.loads(text)
        if data.get("ok") is not True:raise RuntimeError(data.get("detail") or "AI engine rejected analysis")
        return data
    async def analyze(self,symbol:str,market_data:Dict[str,Any]|None=None):
        market_data=dict(market_data or {})
        try:
            data=await self._fastapi(symbol,market_data)
            if data:data["engine_source"]="fastapi_cloud";data["data_source"]=SOURCE;return self._from_fastapi(data,symbol)
        except Exception:pass
        result=analyze_indodax(symbol,market_data,fee_rate=float(self.config.get("fee_rate",.0015)),slippage_rate=float(self.config.get("slippage_rate",.0002)),min_edge_pct=float(self.config.get("min_edge_pct",.45)),position=market_data.get("position"))
        return self._namespace(result)
    @classmethod
    def _from_fastapi(cls,data,symbol):
        agents=dict(data.get("agent_details") or {});exit_plan=dict(data.get("exit_plan") or data.get("hold_analysis",{}).get("exit_plan") or {})
        obj=SimpleNamespace(**{"timestamp":cls._timestamp(data.get("timestamp")),"symbol":str(data.get("symbol") or symbol).upper(),"current_price":cls._number(data.get("current_price")),"final_action":str(data.get("final_action") or "HOLD"),"final_confidence":cls._number(data.get("final_confidence")),"consensus_action":data.get("consensus_action") or "HOLD","consensus_score":cls._number(data.get("consensus_score")),"agent_votes":dict(data.get("agent_votes") or {}),"market_scores":dict(data.get("market_scores") or {}),"confidence_components":dict(data.get("confidence_components") or {}),"position_size":cls._number(data.get("position_size")),"stop_loss":data.get("stop_loss"),"take_profit":data.get("take_profit"),"execution_reason":exit_plan.get("exit_reason") or data.get("execution_reason"),"hold_reason":data.get("hold_reason"),"summary":data.get("summary") or "AI engine completed analysis.","engine_source":"fastapi_cloud","engine_warning":None,"hold_agents":list(data.get("hold_analysis",{}).get("hold_agents") or []),"opposing_agents":list(data.get("hold_analysis",{}).get("opposing_agents") or []),"hold_analysis":dict(data.get("hold_analysis") or {}),"knowledge_topics":list(data.get("knowledge_topics") or []),"candle_analysis":dict(data.get("candle_analysis") or {}),"library_alerts":list(data.get("library_alerts") or [])[:4],"library_version":str(data.get("library_version") or STRATEGY_VERSION),"agent_details":agents,"cycle_status":"ANALYZED","sentiment":SimpleNamespace(**(agents.get("sentiment") or {})),"technical":SimpleNamespace(**(agents.get("technical") or {})),"decision":SimpleNamespace(**(agents.get("decision") or {})),"forecast":SimpleNamespace(**(agents.get("forecast") or {})),"reflection":SimpleNamespace(**(agents.get("reflection") or {})),"mimic_analysis":SimpleNamespace(**(agents.get("mimic_trader") or {})),"exit_plan":exit_plan,"take_profit_pct":data.get("take_profit_pct"),"stop_loss_pct":data.get("stop_loss_pct")})
        return obj
__all__=["CloudflareOrchestrator"]
