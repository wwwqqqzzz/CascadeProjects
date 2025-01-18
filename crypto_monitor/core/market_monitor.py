"""
Real-time market monitor using Binance WebSocket.
Provides millisecond-level market data and trading signals.
"""

import json
import logging
import asyncio
from datetime import datetime
from typing import Dict, List, Callable, Optional
import websockets
from binance import AsyncClient, BinanceSocketManager
from binance.exceptions import BinanceAPIException

from config import (
    BINANCE_API_KEY,
    BINANCE_API_SECRET,
    LOGGING_CONFIG,
    TRADING_CONFIG
)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format=LOGGING_CONFIG['log_format'],
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger('MarketMonitor')

class MarketMonitor:
    def __init__(self, trading_pairs: Optional[List[str]] = None):
        """Initialize market monitor.
        
        Args:
            trading_pairs: List of trading pairs to monitor (e.g., ['BTCUSDT', 'ETHUSDT'])
                         If None, uses pairs from TRADING_CONFIG
        """
        self.trading_pairs = trading_pairs or TRADING_CONFIG['trading_pairs']
        self.callbacks: Dict[str, List[Callable]] = {
            'trade': [],
            'kline': [],
            'depth': [],
            'ticker': []
        }
        self.client: Optional[AsyncClient] = None
        self.bm: Optional[BinanceSocketManager] = None
        self._running = False
        self._tasks = []
        
    async def initialize(self):
        """Initialize Binance client and socket manager."""
        try:
            logger.info("Initializing Binance client...")
            self.client = await AsyncClient.create(
                api_key=BINANCE_API_KEY,
                api_secret=BINANCE_API_SECRET
            )
            self.bm = BinanceSocketManager(self.client)
            logger.info("Successfully initialized Binance client")
            return True
        except BinanceAPIException as e:
            logger.error(f"Failed to initialize Binance client: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error initializing Binance client: {e}")
            return False
            
    def add_callback(self, event_type: str, callback: Callable):
        """Add callback for specific event type.
        
        Args:
            event_type: Type of event ('trade', 'kline', 'depth', 'ticker')
            callback: Callback function to be called when event occurs
        """
        if event_type in self.callbacks:
            self.callbacks[event_type].append(callback)
            logger.info(f"Added callback for {event_type} events")
        else:
            logger.error(f"Unknown event type: {event_type}")
            
    async def _handle_socket_message(self, message: Dict):
        """Handle incoming WebSocket message.
        
        Args:
            message: Message from WebSocket
        """
        try:
            event_type = message.get('e', '')
            if event_type in self.callbacks:
                for callback in self.callbacks[event_type]:
                    try:
                        await callback(message)
                    except Exception as e:
                        logger.error(f"Error in callback for {event_type}: {e}")
        except Exception as e:
            logger.error(f"Error handling socket message: {e}")
            
    async def _start_symbol_ticker(self, symbol: str):
        """Start symbol ticker socket.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT')
        """
        logger.info(f"Starting ticker socket for {symbol}...")
        try:
            ts = self.bm.symbol_ticker_socket(symbol)
            async with ts as tscm:
                while self._running:
                    try:
                        msg = await tscm.recv()
                        await self._handle_socket_message(msg)
                    except Exception as e:
                        logger.error(f"Error in ticker socket for {symbol}: {e}")
                        if not self._running:
                            break
                        await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Failed to start ticker socket for {symbol}: {e}")
                    
    async def _start_trade_socket(self, symbol: str):
        """Start trade socket.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT')
        """
        logger.info(f"Starting trade socket for {symbol}...")
        try:
            ts = self.bm.trade_socket(symbol)
            async with ts as tscm:
                while self._running:
                    try:
                        msg = await tscm.recv()
                        await self._handle_socket_message(msg)
                    except Exception as e:
                        logger.error(f"Error in trade socket for {symbol}: {e}")
                        if not self._running:
                            break
                        await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Failed to start trade socket for {symbol}: {e}")
                    
    async def _start_depth_socket(self, symbol: str):
        """Start depth socket.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT')
        """
        logger.info(f"Starting depth socket for {symbol}...")
        try:
            ds = self.bm.depth_socket(symbol)
            async with ds as dscm:
                while self._running:
                    try:
                        msg = await dscm.recv()
                        await self._handle_socket_message(msg)
                    except Exception as e:
                        logger.error(f"Error in depth socket for {symbol}: {e}")
                        if not self._running:
                            break
                        await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Failed to start depth socket for {symbol}: {e}")
                    
    async def start(self):
        """Start market monitor."""
        if self._running:
            logger.warning("Market monitor is already running")
            return False
            
        if not self.client or not self.bm:
            if not await self.initialize():
                logger.error("Failed to initialize market monitor")
                return False
            
        self._running = True
        
        # Start sockets for each trading pair
        for symbol in self.trading_pairs:
            self._tasks.extend([
                asyncio.create_task(self._start_symbol_ticker(symbol)),
                asyncio.create_task(self._start_trade_socket(symbol)),
                asyncio.create_task(self._start_depth_socket(symbol))
            ])
            
        logger.info(f"Started market monitor for {len(self.trading_pairs)} trading pairs")
        return True
        
    async def stop(self):
        """Stop market monitor."""
        self._running = False
        
        # Cancel all tasks
        for task in self._tasks:
            try:
                task.cancel()
                await task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"Error cancelling task: {e}")
            
        self._tasks.clear()
            
        # Close Binance client
        if self.client:
            try:
                await self.client.close_connection()
                self.client = None
            except Exception as e:
                logger.error(f"Error closing client connection: {e}")
            
        logger.info("Stopped market monitor")

# Example usage
async def example_trade_callback(msg: Dict):
    """Example callback for trade events."""
    print(f"Trade: {msg['s']} - Price: {msg['p']}, Quantity: {msg['q']}")
    
async def example_ticker_callback(msg: Dict):
    """Example callback for ticker events."""
    print(f"Ticker: {msg['s']} - Price: {msg['c']}, Volume: {msg['v']}")
    
async def main():
    # Initialize monitor
    monitor = MarketMonitor()
    
    # Add callbacks
    monitor.add_callback('trade', example_trade_callback)
    monitor.add_callback('ticker', example_ticker_callback)
    
    # Start monitor
    if await monitor.start():
        # Run for 60 seconds
        await asyncio.sleep(60)
        
        # Stop monitor
        await monitor.stop()
    else:
        logger.error("Failed to start market monitor")

if __name__ == "__main__":
    asyncio.run(main())
