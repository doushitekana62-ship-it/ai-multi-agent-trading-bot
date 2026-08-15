"""
test_multi_cycle.py - Multi-Cycle Test 50 Cycles (WITH FORCE SIGNAL)

Untuk testing, kita paksa sinyal BUY/SELL pada cycle tertentu
untuk memastikan pipeline eksekusi berjalan.
"""

import asyncio
import json
import logging
import random
import math
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional
from pathlib import Path

from integration.trading_engine import TradingIntegrationEngine

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger(__name__)


class MultiCycleTester:
    """
    Multi-Cycle Tester - Menjalankan 50 trading cycle.
    """
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.cycles = self.config.get("cycles", 50)
        self.symbol = self.config.get("symbol", "BTC-USD")
        self.base_price = self.config.get("base_price", 62760.21)
        self.price_volatility = self.config.get("price_volatility", 0.002)
        self.force_signal = self.config.get("force_signal", True)  # ← DEFAULT TRUE
        self.output_dir = Path(self.config.get("output_dir", "test_results"))
        self.output_dir.mkdir(exist_ok=True)
        
        # Results storage
        self.results: List[Dict] = []
        self.trade_history: List[Dict] = []
        self.cycle_stats = {
            "total": 0,
            "hold": 0,
            "buy": 0,
            "sell": 0,
            "executed": 0,
            "blocked": 0,
            "errors": 0
        }
        
        # Historical price data
        self.historical_prices: List[float] = []
        self._initialize_historical_data()
        
        # Engine
        self.engine = None
        
        logger.info(f"MultiCycleTester initialized: {self.cycles} cycles for {self.symbol}")
        logger.info(f"Force Signal: {self.force_signal}")
    
    def _initialize_historical_data(self):
        """Initialize historical price data (100 days)."""
        price = self.base_price * 0.95
        for i in range(100):
            drift = random.gauss(0, 0.001) + 0.0002 * math.sin(i / 20)
            price = price * (1 + drift)
            self.historical_prices.append(price)
        
        self.base_price = self.historical_prices[-1]
        logger.info(f"Historical data initialized: {len(self.historical_prices)} prices")
    
    def _generate_price_path(self) -> List[float]:
        """Generate price path."""
        prices = []
        price = self.base_price
        
        for i in range(self.cycles):
            if i < 15:
                drift = 0.003 + random.gauss(0, 0.001)
            elif i < 30:
                drift = -0.003 + random.gauss(0, 0.001)
            else:
                drift = random.gauss(0, 0.005)
            
            price = price * (1 + drift)
            price = max(price, self.base_price * 0.70)
            price = min(price, self.base_price * 1.30)
            prices.append(price)
        
        return prices
    
    def _generate_full_ohlcv(self, current_price: float, cycle: int) -> List[Dict]:
        """Generate FULL OHLCV data dengan 100 candles."""
        ohlcv = []
        now = datetime.now(timezone.utc)
        
        base_prices = self.historical_prices[-90:] if len(self.historical_prices) >= 90 else self.historical_prices
        all_prices = base_prices + [current_price]
        
        for i in range(100):
            idx = min(i, len(all_prices) - 1)
            price = all_prices[idx] if idx < len(all_prices) else current_price
            
            open_price = price * (1 + random.gauss(0, 0.0005))
            high_price = price * (1 + abs(random.gauss(0, 0.001)))
            low_price = price * (1 - abs(random.gauss(0, 0.001)))
            close_price = price
            volume = 1000 + 500 * (1 + math.sin(i / 10)) + 200 * math.sin(i / 3)
            
            candle_time = now - timedelta(hours=(100 - i) * 1)
            
            ohlcv.append({
                "timestamp": candle_time.isoformat(),
                "open": round(open_price, 2),
                "high": round(high_price, 2),
                "low": round(low_price, 2),
                "close": round(close_price, 2),
                "volume": round(volume, 2)
            })
        
        return ohlcv
    
    async def run_single_cycle(self, cycle: int, price: float) -> Dict:
        """Jalankan satu trading cycle."""
        logger.info(f"\n{'='*60}")
        logger.info(f"CYCLE #{cycle + 1}/{self.cycles} | {self.symbol} | Price: ${price:.2f}")
        logger.info(f"{'='*60}")
        
        # Generate FULL OHLCV (100 candles)
        ohlcv = self._generate_full_ohlcv(price, cycle)
        
        # Update historical prices
        self.historical_prices.append(price)
        if len(self.historical_prices) > 200:
            self.historical_prices = self.historical_prices[-100:]
        
        market_data = {
            "symbol": self.symbol,
            "current_price": price,
            "timeframe": "1h",
            "volume_24h": 15000000 * (1 + 0.1 * math.sin(cycle / 5)),
            "high_24h": price * (1 + 0.01 * random.random()),
            "low_24h": price * (1 - 0.01 * random.random()),
            "fear_greed_index": 40 + 20 * math.sin(cycle / 10),
            "ohlcv": ohlcv,
            "volatility": self.price_volatility * (1 + 0.5 * math.sin(cycle / 7)),
            "market_phase": ["BULLISH", "BEARISH", "NEUTRAL", "VOLATILE"][cycle % 4],
        }
        
        # ============================================================
        # FORCE SIGNAL - Untuk testing pipeline eksekusi
        # ============================================================
        if self.force_signal:
            # Pattern: BUY pada cycle kelipatan 5, SELL pada cycle kelipatan 7
            if cycle % 5 == 0 and cycle % 7 != 0:
                # BUY signal
                market_data["sentiment_score"] = 0.8
                market_data["technical_score"] = 0.7
                market_data["_force_action"] = "BUY"
                logger.info(f"🔴 FORCE SIGNAL: BUY on cycle {cycle + 1}")
            elif cycle % 7 == 0:
                # SELL signal
                market_data["sentiment_score"] = -0.7
                market_data["technical_score"] = -0.8
                market_data["_force_action"] = "SELL"
                logger.info(f"🔴 FORCE SIGNAL: SELL on cycle {cycle + 1}")
        
        try:
            result = await self.engine.analyze_and_execute(self.symbol, market_data)
            result["cycle"] = cycle + 1
            result["price"] = price
            result["timestamp"] = datetime.now(timezone.utc).isoformat()
            return result
            
        except Exception as e:
            logger.error(f"Error in cycle {cycle + 1}: {e}")
            return {
                "cycle": cycle + 1,
                "price": price,
                "status": "ERROR",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    async def run(self):
        """Jalankan semua cycle."""
        logger.info("\n" + "="*70)
        logger.info(f"MULTI-CYCLE TEST: {self.cycles} CYCLES")
        logger.info(f"Symbol: {self.symbol}")
        logger.info(f"Base Price: ${self.base_price:.2f}")
        logger.info(f"Volatility: {self.price_volatility:.2%}")
        logger.info(f"Force Signal: {self.force_signal}")
        logger.info("="*70 + "\n")
        
        # Config
        config = {
            "mode": "paper",
            "use_unified_data": True,
            "execution_allowed": True,
            "orchestrator": {
                "enable_dynamic_weights": True,
                "max_position_size": 0.20,
                "min_confidence": 0.20,
                "debug_enabled": False
            },
            "risk_engine": {
                "minimum_confidence": 0.20,
                "max_position_size": 0.20,
                "minimum_risk_reward": 1.0,
                "max_daily_loss": 0.10
            },
            "decision_engine": {
                "min_confidence": 0.20,
                "min_consensus": 0.10,
                "min_directional_edge": 0.05,
                "min_risk_reward": 1.0,
                "live_trading_enabled": False
            },
            "execution_gate": {
                "min_confidence": 0.20,
                "min_risk_reward": 1.0,
                "max_position_size": 0.20
            },
            "paper_trading": {
                "initial_balance": 10000.0,
                "max_position_size": 0.20
            }
        }
        
        self.engine = TradingIntegrationEngine(config)
        self.engine.start()
        
        # Generate price path
        price_path = self._generate_price_path()
        
        # Run cycles
        start_time = datetime.now()
        
        for i, price in enumerate(price_path):
            result = await self.run_single_cycle(i, price)
            self.results.append(result)
            
            # Update stats
            self.cycle_stats["total"] += 1
            
            action = result.get("action", "UNKNOWN")
            status = result.get("status", "UNKNOWN")
            
            if action == "HOLD":
                self.cycle_stats["hold"] += 1
            elif action in ["BUY", "STRONG_BUY"]:
                self.cycle_stats["buy"] += 1
            elif action in ["SELL", "STRONG_SELL"]:
                self.cycle_stats["sell"] += 1
            
            if status == "PAPER_EXECUTED":
                self.cycle_stats["executed"] += 1
                self.trade_history.append({
                    "cycle": i + 1,
                    "price": price,
                    "action": action,
                    "confidence": result.get("confidence", 0),
                    "position_size": result.get("position_size", 0),
                    "timestamp": result.get("timestamp")
                })
            elif status in ["RISK_REJECTED", "DECISION_REJECTED", "EXECUTION_BLOCKED"]:
                self.cycle_stats["blocked"] += 1
            elif status == "ERROR":
                self.cycle_stats["errors"] += 1
            
            if (i + 1) % 10 == 0:
                logger.info(f"\n📊 PROGRESS: {i+1}/{self.cycles} cycles completed")
                logger.info(f"   Executed: {self.cycle_stats['executed']}")
                logger.info(f"   Blocked: {self.cycle_stats['blocked']}")
                logger.info(f"   HOLD: {self.cycle_stats['hold']}")
                logger.info(f"   BUY: {self.cycle_stats['buy']}")
                logger.info(f"   SELL: {self.cycle_stats['sell']}")
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        self.engine.stop()
        self._save_results()
        self._print_summary(duration)
    
    def _save_results(self):
        """Simpan hasil ke file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        results_file = self.output_dir / f"multi_cycle_results_{timestamp}.json"
        with open(results_file, "w") as f:
            json.dump({
                "metadata": {
                    "symbol": self.symbol,
                    "cycles": self.cycles,
                    "base_price": self.base_price,
                    "volatility": self.price_volatility,
                    "force_signal": self.force_signal,
                    "timestamp": datetime.now().isoformat()
                },
                "summary": self.cycle_stats,
                "trade_history": self.trade_history,
                "all_results": self.results
            }, f, indent=2, default=str)
        
        logger.info(f"\n📁 Results saved to: {results_file}")
        
        summary_file = self.output_dir / f"multi_cycle_summary_{timestamp}.txt"
        with open(summary_file, "w") as f:
            f.write("="*70 + "\n")
            f.write(f"MULTI-CYCLE TEST SUMMARY\n")
            f.write("="*70 + "\n\n")
            f.write(f"Symbol: {self.symbol}\n")
            f.write(f"Cycles: {self.cycles}\n")
            f.write(f"Force Signal: {self.force_signal}\n")
            f.write(f"Base Price: ${self.base_price:.2f}\n\n")
            f.write("STATISTICS:\n")
            f.write(f"  Total Cycles: {self.cycle_stats['total']}\n")
            f.write(f"  HOLD Decisions: {self.cycle_stats['hold']} ({self.cycle_stats['hold']/self.cycles*100:.1f}%)\n")
            f.write(f"  BUY Decisions: {self.cycle_stats['buy']} ({self.cycle_stats['buy']/self.cycles*100:.1f}%)\n")
            f.write(f"  SELL Decisions: {self.cycle_stats['sell']} ({self.cycle_stats['sell']/self.cycles*100:.1f}%)\n")
            f.write(f"  Trades Executed: {self.cycle_stats['executed']} ({self.cycle_stats['executed']/self.cycles*100:.1f}%)\n")
            f.write(f"  Trades Blocked: {self.cycle_stats['blocked']} ({self.cycle_stats['blocked']/self.cycles*100:.1f}%)\n")
            f.write(f"  Errors: {self.cycle_stats['errors']}\n\n")
            
            if self.trade_history:
                f.write("TRADE HISTORY:\n")
                for trade in self.trade_history:
                    f.write(f"  Cycle #{trade['cycle']:2d}: {trade['action']} @ ${trade['price']:.2f} (conf: {trade['confidence']:.2%}, size: {trade['position_size']:.2%})\n")
        
        logger.info(f"📁 Summary saved to: {summary_file}")
    
    def _print_summary(self, duration: float):
        """Print summary ke console."""
        print("\n" + "="*70)
        print("MULTI-CYCLE TEST COMPLETED")
        print("="*70)
        print(f"\n📊 SUMMARY STATISTICS:")
        print(f"   Total Cycles: {self.cycle_stats['total']}")
        print(f"   Duration: {duration:.2f} seconds")
        print(f"   Avg Time per Cycle: {duration/self.cycles:.2f} seconds")
        print()
        print(f"   HOLD Decisions: {self.cycle_stats['hold']} ({self.cycle_stats['hold']/self.cycles*100:.1f}%)")
        print(f"   BUY Decisions: {self.cycle_stats['buy']} ({self.cycle_stats['buy']/self.cycles*100:.1f}%)")
        print(f"   SELL Decisions: {self.cycle_stats['sell']} ({self.cycle_stats['sell']/self.cycles*100:.1f}%)")
        print()
        print(f"   ✅ Trades Executed: {self.cycle_stats['executed']} ({self.cycle_stats['executed']/self.cycles*100:.1f}%)")
        print(f"   ⛔ Trades Blocked: {self.cycle_stats['blocked']} ({self.cycle_stats['blocked']/self.cycles*100:.1f}%)")
        print(f"   ❌ Errors: {self.cycle_stats['errors']}")
        
        if self.trade_history:
            print(f"\n📈 TRADE HISTORY (Total: {len(self.trade_history)} trades):")
            for trade in self.trade_history[-10:]:
                print(f"   Cycle #{trade['cycle']:2d}: {trade['action']} @ ${trade['price']:.2f} (conf: {trade['confidence']:.2%})")
        
        print("\n" + "="*70)
        print("✅ TEST COMPLETE - Results saved to test_results/")
        print("="*70)


async def main():
    """Main entry point."""
    tester = MultiCycleTester({
        "cycles": 50,
        "symbol": "BTC-USD",
        "base_price": 62760.21,
        "price_volatility": 0.002,
        "force_signal": True,  # ← AKTIFKAN FORCE SIGNAL
        "output_dir": "test_results"
    })
    
    await tester.run()


if __name__ == "__main__":
    asyncio.run(main())
