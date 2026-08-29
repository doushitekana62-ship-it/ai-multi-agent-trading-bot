"""Real-market paper cycle.

One cycle uses one unified snapshot, the canonical orchestrator, and the
single deterministic executor. There is no secondary scalping decision path.
"""
from __future__ import annotations
from typing import Any, Dict
from agents.agent_trading_librarian import TradingLibrarianAgent
from core.executor import Executor
from core.orchestrator import Orchestrator
from core.runtime_state import set_last_orchestrator_result


class LivePaperCycle:
    def __init__(self, config: Dict[str, Any] | None = None):
        cfg=config or {}
        self.orchestrator=Orchestrator(cfg.get("orchestrator",{}))
        self.librarian=TradingLibrarianAgent(cfg.get("trading_librarian",{}))
        self.executor=Executor({
            "exchange_mode":"paper",
            "paper":cfg.get("paper",{"initial_balance":10_000_000.0}),
            "daily_loss_limit":cfg.get("daily_loss_limit",0.05),
            "max_open_positions":min(3,int(cfg.get("max_open_positions",3))),
        })

    async def cycle(self,symbol:str="BTC/IDR")->Dict[str,Any]:
        symbol=symbol.upper()
        snapshot=self.orchestrator.market_data_provider.refresh_snapshot(symbol,timeframe="1m",limit=180,force=True)
        if snapshot is None or not snapshot.is_valid():
            return {"action":"HOLD","executed":False,"reason":"DATA_UNAVAILABLE","cycle_status":"DATA_UNAVAILABLE","market_data_valid":False}

        # Mark open positions with the exact same price used by analysis.
        before=len(self.executor.order_history)
        self.executor.monitor_positions({symbol:float(snapshot.current_price)})
        position_event=self.executor.order_history[-1].metadata.get("close_reason") if len(self.executor.order_history)>before else None

        market_data=snapshot.to_dict(); market_data["current_price"]=snapshot.current_price; market_data["unified_price"]=snapshot.current_price; market_data["timeframe"]="1m"
        result=await self.orchestrator.analyze(symbol,market_data); set_last_orchestrator_result(result)
        action=result.final_action
        confidence=result.final_confidence
        if action=="HOLD":
            return {"action":"HOLD","executed":False,"price":snapshot.current_price,"confidence":confidence,"reason":result.hold_reason or result.execution_reason,"cycle_status":result.cycle_status,"position_event":position_event,"active_positions":len(self.executor.active_positions),"market_data_valid":True}

        # Spot-paper scope: Trader may propose SELL only to close an owned long.
        position_size=result.position_size
        if position_size<=0: return {"action":action,"executed":False,"price":snapshot.current_price,"confidence":confidence,"reason":"ZERO_POSITION_SIZE","cycle_status":"RISK_REJECTED","market_data_valid":True}
        price=float(snapshot.current_price)
        if action in {"BUY","STRONG_BUY"}: stop_loss=price*0.995; take_profit=price*1.010
        else: stop_loss=price*1.005; take_profit=price*0.990
        order=self.executor.execute(symbol,action,confidence,position_size,stop_loss,take_profit,market_price=price)
        return {"action":action,"executed":order is not None,"price":price,"confidence":confidence,"reason":"EXECUTED" if order else "RISK_REJECTED","cycle_status":"EXECUTED" if order else "RISK_REJECTED","position_event":position_event,"active_positions":len(self.executor.active_positions),"market_data_valid":True,"order_id":order.order_id if order else None}

    def runtime_summary(self)->Dict[str,Any]:
        return {"executor":self.executor.get_summary(),"paper_performance":self.executor.paper_trading.get_performance(),"trade_history":self.executor.paper_trading.trade_history,"positions":self.executor.paper_trading.get_positions()}
