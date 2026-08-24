"""
Main entry point for AI Multi-Agent Trading Bot
"""

import os
import sys
import logging
import asyncio
from dotenv import load_dotenv
from datetime import datetime

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/trading.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Import orchestrator
from core.orchestrator import Orchestrator
from core.executor import Executor
from exchange_integration.paper_trading import PaperTrading


async def main():
    """Main async function to run the bot"""
    logger.info("=" * 60)
    logger.info("AI Multi-Agent Trading Bot Started")
    logger.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)
    
    try:
        # Initialize components
        orchestrator = Orchestrator()
        executor = Executor()
        paper_trading = PaperTrading()
        
        logger.info("All components initialized successfully")
        
        # Example: Analyze a symbol
        symbol = "BTC-USD"
        logger.info(f"Analyzing {symbol}...")
        
        result = await orchestrator.analyze(symbol)
        
        # Print result
        print("\n" + "=" * 60)
        print("ORCHESTRATOR RESULT")
        print("=" * 60)
        print(f"Symbol: {result.symbol}")
        print(f"Price: ${result.current_price:.2f}")
        print(f"Action: {result.final_action}")
        print(f"Confidence: {result.final_confidence:.1%}")
        print(f"Position Size: {result.position_size:.1%}")
        
        if result.stop_loss:
            print(f"Stop Loss: ${result.stop_loss:.2f}")
        if result.take_profit:
            print(f"Take Profit: ${result.take_profit:.2f}")
        
        print(f"\nAgent Votes:")
        for agent, vote in result.agent_votes.items():
            print(f"  {agent}: {vote}")
        
        print(f"\n{result.summary}")
        print("=" * 60)
        
        # Execute if not HOLD
        if result.final_action not in ['HOLD']:
            logger.info(f"Executing {result.final_action} for {result.symbol}")
            order = executor.execute(
                symbol=result.symbol,
                action=result.final_action,
                confidence=result.final_confidence,
                position_size=result.position_size,
                stop_loss=result.stop_loss,
                take_profit=result.take_profit
            )
            
            if order:
                logger.info(f"Order executed: {order.order_id}")
            else:
                logger.warning("Order execution failed")
        
        # Show performance summary
        perf = paper_trading.get_performance()
        print("\n" + "=" * 60)
        print("PERFORMANCE SUMMARY")
        print("=" * 60)
        print(f"Portfolio Value: ${perf['portfolio_value']:.2f}")
        print(f"Total Return: {perf['total_return']:.2f}%")
        print(f"Total Trades: {perf['total_trades']}")
        print(f"Win Rate: {perf['win_rate']:.2%}")
        print("=" * 60)
        
    except Exception as e:
        logger.error(f"Error in main: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        sys.exit(1)
