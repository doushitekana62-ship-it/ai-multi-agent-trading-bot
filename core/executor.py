"""
Executor: Eksekusi trading berdasarkan keputusan dari Orchestrator

Bertugas:
1. Menerima keputusan dari Orchestrator
2. Menghubungi exchange untuk eksekusi order
3. Memantau posisi yang berjalan
4. Melakukan manajemen risiko (stop loss, take profit)
5. Mencatat semua transaksi
"""

import os
import sys
import logging
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

# Import exchange integration
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from exchange_integration.alpaca_bridge import AlpacaBridge
from exchange_integration.paper_trading import PaperTrading

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OrderStatus(Enum):
    """Status order"""
    PENDING = "PENDING"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"

@dataclass
class Order:
    """Data class untuk order"""
    order_id: str
    symbol: str
    side: str  # BUY or SELL
    quantity: float
    price: float
    status: str
    created_at: datetime
    filled_at: Optional[datetime]
    filled_quantity: float
    filled_price: float
    stop_loss: Optional[float]
    take_profit: Optional[float]
    metadata: Dict[str, Any]

class Executor:
    """
    Executor untuk eksekusi trading
    """
    
    def __init__(self, config: Dict = None):
        """
        Initialize Executor
        
        Args:
            config: Konfigurasi untuk executor
        """
        self.config = config or {}
        
        # Initialize exchange connections
        self.exchange_mode = self.config.get('exchange_mode', 'paper')  # 'paper' or 'live'
        
        # Use paper trading by default
        self.paper_trading = PaperTrading()
        self.alpaca_bridge = AlpacaBridge()
        
        # Order management
        self.active_orders: Dict[str, Order] = {}
        self.order_history: List[Order] = []
        
        # Position management
        self.active_positions: Dict[str, Dict] = {}
        self.max_open_positions = self.config.get('max_open_positions', 5)
        
        # Risk parameters
        self.daily_loss_limit = self.config.get('daily_loss_limit', 0.05)
        self.daily_pnl = 0.0
        self.daily_trades = 0
        
        # Order tracking
        self.order_id_counter = 0
        
        logger.info(f"Executor initialized in {self.exchange_mode} mode")
    
    def execute(self, symbol: str, action: str, confidence: float,
                position_size: float, stop_loss: Optional[float] = None,
                take_profit: Optional[float] = None) -> Optional[Order]:
        """
        Execute trading order
        
        Args:
            symbol: Simbol aset
            action: STRONG_BUY, BUY, SELL, STRONG_SELL, HOLD
            confidence: Confidence level (0-1)
            position_size: Position size (0-1)
            stop_loss: Stop loss price
            take_profit: Take profit price
        
        Returns:
            Order: Order yang dieksekusi, atau None jika HOLD
        """
        logger.info(f"Executing {action} for {symbol}")
        
        # Check if HOLD
        if action in ['HOLD']:
            logger.info("Action is HOLD - no execution")
            return None
        
        # Check daily loss limit
        if abs(self.daily_pnl) > self.daily_loss_limit:
            logger.warning(f"Daily loss limit reached: {self.daily_pnl:.2%}")
            return None
        
        # Check max positions
        if len(self.active_positions) >= self.max_open_positions:
            logger.warning(f"Max open positions reached: {self.max_open_positions}")
            return None
        
        # Determine side (BUY or SELL)
        side = 'BUY' if action in ['BUY', 'STRONG_BUY'] else 'SELL'
        
        # Get current price
        current_price = self._get_current_price(symbol)
        if not current_price:
            logger.error(f"Could not get current price for {symbol}")
            return None
        
        # Calculate quantity based on position size
        portfolio_value = self._get_portfolio_value()
        position_value = portfolio_value * position_size
        quantity = position_value / current_price
        
        # Create order
        order = self._create_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=current_price,
            stop_loss=stop_loss,
            take_profit=take_profit
        )
        
        # Execute order based on mode
        if self.exchange_mode == 'paper':
            executed_order = self._execute_paper_order(order)
        else:
            executed_order = self._execute_live_order(order)
        
        if executed_order:
            # Track position
            self._track_position(executed_order)
            
            # Log order
            logger.info(f"Order executed: {executed_order.order_id} - {side} {quantity} {symbol}")
            
            return executed_order
        
        return None
    
    def _create_order(self, symbol: str, side: str, quantity: float,
                     price: float, stop_loss: Optional[float],
                     take_profit: Optional[float]) -> Order:
        """Create order object"""
        self.order_id_counter += 1
        
        return Order(
            order_id=f"ORD_{self.order_id_counter:06d}",
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            status=OrderStatus.PENDING.value,
            created_at=datetime.now(),
            filled_at=None,
            filled_quantity=0.0,
            filled_price=0.0,
            stop_loss=stop_loss,
            take_profit=take_profit,
            metadata={}
        )
    
    def _execute_paper_order(self, order: Order) -> Optional[Order]:
        """Execute order using paper trading"""
        try:
            # Execute via paper trading
            result = self.paper_trading.execute_order(
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                price=order.price
            )
            
            if result:
                order.status = OrderStatus.FILLED.value
                order.filled_at = datetime.now()
                order.filled_quantity = order.quantity
                order.filled_price = order.price
                self.order_history.append(order)
                
                return order
            
            order.status = OrderStatus.REJECTED.value
            return None
            
        except Exception as e:
            logger.error(f"Error executing paper order: {e}")
            return None
    
    def _execute_live_order(self, order: Order) -> Optional[Order]:
        """Execute order using live Alpaca API"""
        try:
            # Execute via Alpaca bridge
            result = self.alpaca_bridge.submit_order(
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                order_type='market'
            )
            
            if result:
                order.status = OrderStatus.FILLED.value
                order.filled_at = datetime.now()
                order.filled_quantity = order.quantity
                order.filled_price = order.price
                self.order_history.append(order)
                
                return order
            
            order.status = OrderStatus.REJECTED.value
            return None
            
        except Exception as e:
            logger.error(f"Error executing live order: {e}")
            return None
    
    def _track_position(self, order: Order):
        """Track opened position"""
        position = {
            'symbol': order.symbol,
            'side': order.side,
            'entry_price': order.price,
            'quantity': order.quantity,
            'stop_loss': order.stop_loss,
            'take_profit': order.take_profit,
            'entry_time': datetime.now(),
            'order_id': order.order_id,
            'current_pnl': 0.0
        }
        
        self.active_positions[order.symbol] = position
        self.daily_trades += 1
    
    def monitor_positions(self):
        """Monitor open positions for stop loss and take profit"""
        for symbol, position in list(self.active_positions.items()):
            current_price = self._get_current_price(symbol)
            
            if not current_price:
                continue
            
            # Calculate PnL
            if position['side'] == 'BUY':
                pnl_percent = (current_price - position['entry_price']) / position['entry_price']
            else:  # SELL
                pnl_percent = (position['entry_price'] - current_price) / position['entry_price']
            
            position['current_pnl'] = pnl_percent
            
            # Check stop loss
            if position['stop_loss']:
                if position['side'] == 'BUY' and current_price <= position['stop_loss']:
                    self._close_position(symbol, current_price, 'STOP_LOSS')
                
                elif position['side'] == 'SELL' and current_price >= position['stop_loss']:
                    self._close_position(symbol, current_price, 'STOP_LOSS')
            
            # Check take profit
            if position['take_profit']:
                if position['side'] == 'BUY' and current_price >= position['take_profit']:
                    self._close_position(symbol, current_price, 'TAKE_PROFIT')
                
                elif position['side'] == 'SELL' and current_price <= position['take_profit']:
                    self._close_position(symbol, current_price, 'TAKE_PROFIT')
    
    def _close_position(self, symbol: str, price: float, reason: str):
        """Close a position"""
        if symbol not in self.active_positions:
            return
        
        position = self.active_positions[symbol]
        close_side = 'SELL' if position['side'] == 'BUY' else 'BUY'
        
        # Create closing order
        close_order = self._create_order(
            symbol=symbol,
            side=close_side,
            quantity=position['quantity'],
            price=price,
            stop_loss=None,
            take_profit=None
        )
        
        # Execute closing order
        if self.exchange_mode == 'paper':
            executed = self._execute_paper_order(close_order)
        else:
            executed = self._execute_live_order(close_order)
        
        if executed:
            # Calculate PnL
            pnl = 0
            if position['side'] == 'BUY':
                pnl = (price - position['entry_price']) * position['quantity']
            else:
                pnl = (position['entry_price'] - price) * position['quantity']
            
            pnl_percent = pnl / (position['entry_price'] * position['quantity'])
            
            # Update daily PnL
            self.daily_pnl += pnl_percent
            
            # Log
            logger.info(f"Position closed: {symbol} - {reason} - PnL: {pnl_percent:.2%}")
            
            # Remove from active positions
            del self.active_positions[symbol]
    
    def _get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price from exchange"""
        try:
            if self.exchange_mode == 'paper':
                return self.paper_trading.get_price(symbol)
            else:
                return self.alpaca_bridge.get_current_price(symbol)
        except Exception as e:
            logger.error(f"Error getting price for {symbol}: {e}")
            return None
    
    def _get_portfolio_value(self) -> float:
        """Get current portfolio value"""
        try:
            if self.exchange_mode == 'paper':
                return self.paper_trading.get_portfolio_value()
            else:
                return self.alpaca_bridge.get_account_value()
        except Exception as e:
            logger.error(f"Error getting portfolio value: {e}")
            return 10000.0  # Default
    
    def get_summary(self) -> Dict:
        """Get summary of executor status"""
        return {
            'active_positions': len(self.active_positions),
            'total_trades': len(self.order_history),
            'daily_pnl': self.daily_pnl,
            'daily_trades': self.daily_trades,
            'positions': self.active_positions
        }
    
    def reset_daily(self):
        """Reset daily counters"""
        self.daily_pnl = 0.0
        self.daily_trades = 0

# Example usage
if __name__ == "__main__":
    executor = Executor()
    
    # Test execution
    order = executor.execute(
        symbol="BTC-USD",
        action="BUY",
        confidence=0.8,
        position_size=0.1,
        stop_loss=38000,
        take_profit=42000
    )
    
    if order:
        print(f"Order executed: {order.order_id}")
        print(f"Side: {order.side}")
        print(f"Quantity: {order.quantity}")
        print(f"Price: ${order.price:.2f}")
    
    # Monitor positions
    executor.monitor_positions()
    
    print("\nExecutor Summary:")
    print(json.dumps(executor.get_summary(), indent=2))
