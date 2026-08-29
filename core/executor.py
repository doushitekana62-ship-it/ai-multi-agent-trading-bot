"""Deterministic execution adapter with one paper ledger."""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional
from exchange_integration.alpaca_bridge import AlpacaBridge
from exchange_integration.paper_trading import PaperTrading
from exchange_integration.indodax_bridge import IndodaxBridge
logger=logging.getLogger(__name__)
class OrderStatus(Enum):
    PENDING="PENDING"; FILLED="FILLED"; PARTIALLY_FILLED="PARTIALLY_FILLED"; CANCELLED="CANCELLED"; REJECTED="REJECTED"; EXPIRED="EXPIRED"
@dataclass
class Order:
    order_id:str; symbol:str; side:str; quantity:float; price:float; status:str; created_at:datetime; filled_at:Optional[datetime]; filled_quantity:float; filled_price:float; stop_loss:Optional[float]; take_profit:Optional[float]; metadata:Dict[str,Any]
class Executor:
    def __init__(self,config:Optional[Dict[str,Any]]=None):
        self.config=config or {}; self.exchange_mode=str(self.config.get("exchange_mode","paper")).lower(); self.paper_trading=PaperTrading(self.config.get("paper",{})); self.alpaca_bridge=AlpacaBridge(self.config.get("alpaca",{})); self.indodax_bridge=None; self.active_orders={}; self.order_history=[]; self.active_positions={}; self.max_open_positions=min(3,max(1,int(self.config.get("max_open_positions",3)))); self.daily_loss_limit=float(self.config.get("daily_loss_limit",0.05)); self.daily_starting_equity=0.0; self.daily_realized_pnl=0.0; self.daily_pnl=0.0; self.daily_trades=0; self.order_id_counter=0
    def configure_exchange(self,exchange_mode:str,credentials:Optional[Dict[str,Any]]=None):
        self.exchange_mode=exchange_mode.lower(); credentials=credentials or {}
        if self.exchange_mode=="indodax": self.indodax_bridge=IndodaxBridge({"api_key":credentials.get("api_key"),"secret":credentials.get("api_secret") or credentials.get("secret"),"enable_trading":credentials.get("enable_trading",False)})
    def _ensure_daily_baseline(self):
        if self.daily_starting_equity<=0:self.daily_starting_equity=max(self._get_portfolio_value(),1e-9)
    def execute(self,symbol,action,confidence,position_size,stop_loss=None,take_profit=None,market_price=None):
        action=action.upper()
        if action not in {"BUY","SELL","STRONG_BUY","STRONG_SELL"} or not 0<position_size<=1 or confidence<0.75:return None
        self._ensure_daily_baseline()
        if self.daily_pnl<=-self.daily_loss_limit:return None
        side="BUY" if action in {"BUY","STRONG_BUY"} else "SELL"
        if side=="BUY" and (symbol in self.active_positions or len(self.active_positions)>=self.max_open_positions):return None
        if side=="SELL" and symbol not in self.active_positions:return None
        current_price=float(market_price) if market_price is not None else self._get_current_price(symbol)
        if current_price is None or current_price<=0:return None
        if side=="BUY" and (stop_loss is None or take_profit is None or not 0<stop_loss<current_price<take_profit):return None
        if side=="SELL" and stop_loss is not None and take_profit is not None and not take_profit<current_price<stop_loss:return None
        quantity=(self._get_portfolio_value()*position_size/current_price) if side=="BUY" else float(self.active_positions[symbol]["quantity"])
        if quantity<=0:return None
        order=self._create_order(symbol,side,quantity,current_price,stop_loss,take_profit); executed=self._execute_order(order)
        if not executed:return None
        if side=="SELL":self._close_position_record(symbol,self._get_execution_realized_pnl(executed))
        else:self._track_position(executed)
        return executed
    def _create_order(self,symbol,side,quantity,price,stop_loss,take_profit):
        self.order_id_counter+=1; return Order(f"ORD_{self.order_id_counter:06d}",symbol,side,quantity,price,OrderStatus.PENDING.value,datetime.now(timezone.utc),None,0.0,0.0,stop_loss,take_profit,{})
    def _execute_order(self,order):
        try:
            if self.exchange_mode=="paper": result={"paper":True} if self.paper_trading.execute_order(order.symbol,order.side,order.quantity,order.price) else None
            elif self.exchange_mode=="indodax": result=self.indodax_bridge.submit_order(order.symbol,order.side,order.quantity,"market") if self.indodax_bridge else None
            elif self.exchange_mode=="alpaca": result=self.alpaca_bridge.submit_order(order.symbol,order.side,order.quantity,"market")
            else: result=None
            if result is None:order.status=OrderStatus.REJECTED.value;return None
            order.status=OrderStatus.FILLED.value;order.filled_at=datetime.now(timezone.utc);order.filled_quantity=order.quantity;order.filled_price=order.price;order.metadata["exchange_result"]=result;self.order_history.append(order);self.daily_trades+=1;return order
        except Exception: order.status=OrderStatus.REJECTED.value;logger.exception("Order execution failed");return None
    def _get_execution_realized_pnl(self,order):
        if self.exchange_mode=="paper" and self.paper_trading.trade_history:
            t=self.paper_trading.trade_history[-1]
            if t.get("symbol")==order.symbol:return float(t.get("pnl",0.0))
        p=self.active_positions.get(order.symbol); return (order.filled_price-p["entry_price"])*order.filled_quantity if p else 0.0
    def _track_position(self,order):
        self.active_positions[order.symbol]={"symbol":order.symbol,"side":order.side,"entry_price":order.filled_price,"quantity":order.filled_quantity,"stop_loss":order.stop_loss,"take_profit":order.take_profit,"entry_time":datetime.now(timezone.utc),"order_id":order.order_id,"current_pnl":0.0}
    def _close_position_record(self,symbol,realized_pnl=None):
        self.active_positions.pop(symbol,None)
        if realized_pnl is not None:self._record_realized_pnl(realized_pnl)
    def _record_realized_pnl(self,pnl):
        self._ensure_daily_baseline();self.daily_realized_pnl+=pnl;self.daily_pnl=self.daily_realized_pnl/self.daily_starting_equity
    def monitor_positions(self,market_prices=None):
        for symbol,position in list(self.active_positions.items()):
            current_price=(market_prices or {}).get(symbol,self._get_current_price(symbol))
            if current_price is None:continue
            position["current_pnl"]=(current_price-position["entry_price"])/position["entry_price"]
            hit_sl=position["stop_loss"] is not None and current_price<=position["stop_loss"]; hit_tp=position["take_profit"] is not None and current_price>=position["take_profit"]
            if hit_sl or hit_tp:self._close_position(symbol,current_price,"STOP_LOSS" if hit_sl else "TAKE_PROFIT")
    def _close_position(self,symbol,price,reason):
        p=self.active_positions.get(symbol)
        if not p:return None
        order=self._create_order(symbol,"SELL",p["quantity"],price,None,None);order.metadata["close_reason"]=reason;executed=self._execute_order(order)
        if executed:self._close_position_record(symbol,self._get_execution_realized_pnl(executed))
        return executed
    def _get_current_price(self,symbol):
        try:
            if self.exchange_mode=="paper":return self.paper_trading.get_price(symbol)
            if self.exchange_mode=="indodax":return self.indodax_bridge.get_current_price(symbol) if self.indodax_bridge else None
            return self.alpaca_bridge.get_current_price(symbol)
        except Exception:return None
    def _get_portfolio_value(self):
        try:
            if self.exchange_mode=="paper":return float(self.paper_trading.get_portfolio_value())
            if self.exchange_mode=="indodax":return float(self.indodax_bridge.get_account_value()) if self.indodax_bridge else 0.0
            return float(self.alpaca_bridge.get_account_value())
        except Exception:return 0.0
    def get_summary(self):
        return {"active_positions":len(self.active_positions),"total_trades":len(self.order_history),"daily_pnl":self.daily_pnl,"daily_realized_pnl":self.daily_realized_pnl,"daily_trades":self.daily_trades,"positions":self.active_positions,"exchange_mode":self.exchange_mode,"max_open_positions":self.max_open_positions}
    def reset_daily(self):
        self.daily_starting_equity=self._get_portfolio_value();self.daily_realized_pnl=0.0;self.daily_pnl=0.0;self.daily_trades=0
