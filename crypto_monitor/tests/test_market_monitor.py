"""
Test market monitor functionality.
"""

import sys
from pathlib import Path
import asyncio
import logging
from datetime import datetime

# Add parent directory to Python path
sys.path.append(str(Path(__file__).parent.parent))

from crypto_monitor.core.market.market_monitor import MarketMonitor
from config import LOGGING_CONFIG, TRADING_CONFIG

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format=LOGGING_CONFIG['log_format'],
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger('MarketMonitorTest')

# Test callbacks
async def test_trade_callback(msg):
    """Process trade events."""
    timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
    symbol = msg['s']
    price = float(msg['p'])
    quantity = float(msg['q'])
    logger.info(f"[{timestamp}] Trade: {symbol} - Price: ${price:.2f}, Quantity: {quantity:.8f}")

async def test_ticker_callback(msg):
    """Process ticker events."""
    timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
    symbol = msg['s']
    price = float(msg['c'])
    volume = float(msg['v'])
    price_change = float(msg['P'])
    logger.info(f"[{timestamp}] Ticker: {symbol} - Price: ${price:.2f}, "
                f"24h Change: {price_change:.2f}%, Volume: {volume:.2f}")

async def main():
    """Run market monitor test."""
    # Initialize monitor with default trading pairs from config
    monitor = MarketMonitor()
    
    # Add callbacks
    monitor.add_callback('trade', test_trade_callback)
    monitor.add_callback('ticker', test_ticker_callback)
    
    try:
        # Start monitor
        logger.info(f"Starting market monitor test for pairs: {monitor.trading_pairs}...")
        await monitor.start()
        
        # Run for 30 seconds
        logger.info("Monitoring market data for 30 seconds...")
        await asyncio.sleep(30)
        
    except Exception as e:
        logger.error(f"Error during test: {e}")
        
    finally:
        # Stop monitor
        logger.info("Stopping market monitor...")
        await monitor.stop()
        logger.info("Test complete!")

if __name__ == "__main__":
    asyncio.run(main())
