"""
Paper Trading: Simulasi trading tanpa uang sungguhan

Fungsi:
1. Simulasi eksekusi order
2. Track portfolio
3. Simulasi market data
4. PnL tracking
"""

import os
import logging
import json
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import pandas as pd
import numpy as np

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class PaperPosition:
    """Position in paper trading"""
    symbol: str
    side: str
    entry_price: float
    quantity: float
    entry_time: datetime
    current_price: float
    unrealized_pnl: float
    realized_pnl: float

class PaperTrading:
    """
    Paper Trading simulator
    """
    
    def __init__(self, config: Dict = None):
        """
        Initialize Paper Trading
        
        Args:
            config: Konfigurasi untuk paper trading
        """
        self.config = config or {}
        
        # Account settings
        self.initial_balance = self.config.get('initial_balance', 10000.0)
        self.balance = self.initial_balance
        self.portfolio_value = self.initial_balance
        
        # Positions
        self.positions: Dict[str, PaperPosition] = {}
        self.trade_history: List[Dict] = []
        
        # Performance tracking
        self.total_pnl = 0.0
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        
        # Price simulation (for demo)
        self.price_cache = {}
        
        # Load saved data if exists
        self._load_data()
        
        logger.info(f"Paper Trading initialized with ${self.initial_balance:,.2f}")
    
    def execute_order(self, symbol: str, side: str, quantity: float,
                      price: float) -> bool:
        """
        Execute a paper trade
        
        Args:
            symbol: Symbol to trade
            side: 'BUY' or 'SELL'
            quantity: Quantity to trade
            price: Execution price
        
        Returns:
            bool: True if executed successfully
        """
        if quantity <= 0:
            logger.warning(f"Invalid quantity: {quantity}")
            return False
        
        # Calculate cost
        cost = quantity * price
        
        if side.upper() == 'BUY':
            # Check if enough balance
            if cost > self.balance:
                logger.warning(f"Insufficient balance: ${cost:.2f} > ${self.balance:.2f}")
                return False
            
            # Update balance
            self.balance -= cost
            
            # Create position
            self.positions[symbol] = PaperPosition(
                symbol=symbol,
                side='BUY',
                entry_price=price,
                quantity=quantity,
                entry_time=datetime.now(),
                current_price=price,
                unrealized_pnl=0.0,
                realized_pnl=0.0
            )
            
            logger.info(f"BUY {quantity} {symbol} @ ${price:.2f}")
            
        elif side.upper() == 'SELL':
            # Check if position exists
            if symbol not in self.positions:
                logger.warning(f"No position to sell: {symbol}")
                return False
            
            position = self.positions[symbol]
            
            if position.side == 'BUY':
                # Calculate PnL
                pnl = (price - position.entry_price) * quantity
                pnl_percent = ((price - position.entry_price) / position.entry_price) * 100
                
                # Update balance
                self.balance += quantity * price
                
                # Track trade
                self.total_pnl += pnl
                self.total_trades += 1
                
                if pnl > 0:
                    self.winning_trades += 1
                else:
                    self.losing_trades += 1
                
                # Record trade
                trade_record = {
                    'symbol': symbol,
                    'side': side,
                    'entry_price': position.entry_price,
                    'exit_price': price,
                    'quantity': quantity,
                    'pnl': pnl,
                    'pnl_percent': pnl_percent,
                    'entry_time': position.entry_time.isoformat(),
                    'exit_time': datetime.now().isoformat()
                }
                self.trade_history.append(trade_record)
                
                # Remove position
                del self.positions[symbol]
                
                logger.info(f"SELL {quantity} {symbol} @ ${price:.2f} - PnL: ${pnl:.2f} ({pnl_percent:.2f}%)")
                
            else:
                logger.warning("Cannot sell, position is not BUY")
                return False
        
        # Update portfolio value
        self._update_portfolio_value()
        
        # Save data
        self._save_data()
        
        return True
    
    def _update_portfolio_value(self):
        """Update total portfolio value"""
        positions_value = 0.0
        
        for symbol, position in self.positions.items():
            current_price = self.get_price(symbol)
            if current_price:
                position.current_price = current_price
                positions_value += current_price * position.quantity
                position.unrealized_pnl = (current_price - position.entry_price) * position.quantity
        
        self.portfolio_value = self.balance + positions_value
    
    def get_portfolio_value(self) -> float:
        """Get current portfolio value"""
        self._update_portfolio_value()
        return self.portfolio_value
    
    def get_price(self, symbol: str) -> Optional[float]:
        """
        Get current price for a symbol
        
        Args:
            symbol: Symbol to get price for
        
        Returns:
            float: Current price or None
        """
        # Check cache first (avoid too many updates)
        if symbol in self.price_cache:
            cached_time, cached_price = self.price_cache[symbol]
            if datetime.now() - cached_time < timedelta(seconds=5):
                return cached_price
        
        # Try to get real price from yfinance
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            current_price = ticker.history(period='1d')['Close'].iloc[-1]
            
            # Add random fluctuation for realism
            if random.random() < 0.3:  # 30% chance of small movement
                fluctuation = random.uniform(-0.005, 0.005)
                current_price = current_price * (1 + fluctuation)
            
            # Cache the price
            self.price_cache[symbol] = (datetime.now(), current_price)
            
            return current_price
            
        except Exception as e:
            logger.error(f"Error getting price for {symbol}: {e}")
            
            # Fallback: generate random price
            base_price = 100.0
            if 'BTC' in symbol:
                base_price = 30000.0
            elif 'ETH' in symbol:
                base_price = 2000.0
            
            # Add random walk
            random_change = random.uniform(-0.02, 0.02)
            current_price = base_price * (1 + random_change)
            
            return current_price
    
    def get_positions(self) -> List[Dict]:
        """Get all current positions"""
        positions = []
        
        for symbol, position in self.positions.items():
            positions.append({
                'symbol': position.symbol,
                'side': position.side,
                'entry_price': position.entry_price,
                'current_price': position.current_price,
                'quantity': position.quantity,
                'unrealized_pnl': position.unrealized_pnl,
                'pnl_percent': (position.unrealized_pnl / (position.entry_price * position.quantity)) * 100
            })
        
        return positions
    
    def get_performance(self) -> Dict:
        """Get performance metrics"""
        win_rate = self.winning_trades / self.total_trades if self.total_trades > 0 else 0
        
        return {
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'win_rate': win_rate,
            'total_pnl': self.total_pnl,
            'balance': self.balance,
            'portfolio_value': self.portfolio_value,
            'total_return': ((self.portfolio_value - self.initial_balance) / self.initial_balance) * 100
        }
    
    def close_all_positions(self):
        """Close all positions at current market price"""
        for symbol in list(self.positions.keys()):
            current_price = self.get_price(symbol)
            if current_price:
                position = self.positions[symbol]
                self.execute_order(
                    symbol=symbol,
                    side='SELL',
                    quantity=position.quantity,
                    price=current_price
                )
    
    def _save_data(self):
        """Save trading data to file"""
        try:
            os.makedirs('data', exist_ok=True)
            
            data = {
                'balance': self.balance,
                'total_pnl': self.total_pnl,
                'total_trades': self.total_trades,
                'winning_trades': self.winning_trades,
                'losing_trades': self.losing_trades,
                'trade_history': self.trade_history,
                'positions': [
                    {
                        'symbol': p.symbol,
                        'side': p.side,
                        'entry_price': p.entry_price,
                        'quantity': p.quantity,
                        'entry_time': p.entry_time.isoformat(),
                        'current_price': p.current_price
                    }
                    for p in self.positions.values()
                ]
            }
            
            with open('data/paper_trading.json', 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            logger.error(f"Error saving data: {e}")
    
    def _load_data(self):
        """Load trading data from file"""
        try:
            if os.path.exists('data/paper_trading.json'):
                with open('data/paper_trading.json', 'r') as f:
                    data = json.load(f)
                
                self.balance = data.get('balance', self.initial_balance)
                self.total_pnl = data.get('total_pnl', 0.0)
                self.total_trades = data.get('total_trades', 0)
                self.winning_trades = data.get('winning_trades', 0)
                self.losing_trades = data.get('losing_trades', 0)
                self.trade_history = data.get('trade_history', [])
                
                # Restore positions
                for pos_data in data.get('positions', []):
                    position = PaperPosition(
                        symbol=pos_data['symbol'],
                        side=pos_data['side'],
                        entry_price=pos_data['entry_price'],
                        quantity=pos_data['quantity'],
                        entry_time=datetime.fromisoformat(pos_data['entry_time']),
                        current_price=pos_data.get('current_price', pos_data['entry_price']),
                        unrealized_pnl=0.0,
                        realized_pnl=0.0
                    )
                    self.positions[position.symbol] = position
                
                logger.info(f"Loaded paper trading data - Balance: ${self.balance:.2f}")
                
        except Exception as e:
            logger.info(f"No existing data found: {e}")

# Example usage
if __name__ == "__main__":
    paper = PaperTrading(initial_balance=10000.0)
    
    print("Paper Trading Test")
    print("=" * 40)
    
    # Buy some BTC
    btc_price = paper.get_price('BTC-USD')
    if btc_price:
        paper.execute_order('BTC-USD', 'BUY', 0.1, btc_price)
    
    # Get performance
    perf = paper.get_performance()
    print(f"Balance: ${perf['balance']:.2f}")
    print(f"Portfolio Value: ${perf['portfolio_value']:.2f}")
    print(f"Total Return: {perf['total_return']:.2f}%")
    print(f"Total Trades: {perf['total_trades']}")
    print(f"Win Rate: {perf['win_rate']:.2%}")
    
    # Get positions
    positions = paper.get_positions()
    for pos in positions:
        print(f"Position: {pos['symbol']} - {pos['side']} - {pos['quantity']} @ ${pos['entry_price']:.2f} - PnL: ${pos['unrealized_pnl']:.2f}")
