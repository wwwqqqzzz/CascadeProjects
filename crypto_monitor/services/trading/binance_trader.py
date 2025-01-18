"""
Binance交易执行器，封装交易所API操作
"""

import logging
import asyncio
from typing import Dict, Optional, List
from datetime import datetime
from binance.client import AsyncClient
from binance.exceptions import BinanceAPIException
from ...utils.config import TRADING_CONFIG
from ..monitor.performance_monitor import PerformanceMonitor
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

class BinanceTrader:
    def __init__(self, api_key: str, api_secret: str, test_mode: bool = False):
        """
        初始化Binance交易执行器
        
        Args:
            api_key: Binance API key
            api_secret: Binance API secret
            test_mode: 是否使用测试网络
        """
        self.logger = logging.getLogger(__name__)
        self.open_orders = {}  # 跟踪未完成的订单
        self.api_key = api_key
        self.api_secret = api_secret
        self.test_mode = test_mode
        self.client = None
        
        # 性能监控
        self.performance_monitor = PerformanceMonitor()
        
        # 缓存配置
        self._price_cache = {}  # 价格缓存
        
        # 并发控制
        self._price_semaphore = asyncio.Semaphore(5)  # 限制价格查询并发
        self._order_semaphore = asyncio.Semaphore(3)  # 限制订单操作并发

    async def initialize(self):
        """初始化异步客户端"""
        if self.client is None:
            try:
                start_time = datetime.now()
                self.client = await AsyncClient.create(
                    api_key=self.api_key,
                    api_secret=self.api_secret,
                    testnet=self.test_mode
                )
                await self.performance_monitor.start()
                self.logger.info("Successfully initialized Binance client")
                
                # 记录初始化时间
                latency = (datetime.now() - start_time).total_seconds()
                self.performance_monitor.record_api_latency('initialize', latency)
            except Exception as e:
                self.logger.error(f"Failed to initialize Binance client: {str(e)}")
                self.performance_monitor.record_error('InitializationError', str(e))
                raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def market_buy(self, symbol: str, quantity: float) -> Optional[Dict]:
        """执行市价买入"""
        try:
            async with self._order_semaphore:
                if not self.client:
                    await self.initialize()
                
                start_time = datetime.now()
                
                order = await self.client.create_order(
                    symbol=symbol,
                    side='BUY',
                    type='MARKET',
                    quantity=quantity
                )
                
                # 记录执行时间
                execution_time = (datetime.now() - start_time).total_seconds()
                self.performance_monitor.record_execution_time('market_buy', execution_time)
                
                logger.info(f"市价买入订单执行成功: {order}, 耗时: {execution_time:.3f}秒")
                return order
                
        except BinanceAPIException as e:
            self.performance_monitor.record_error('MarketBuyError', str(e))
            logger.error(f"Failed to execute market buy order: {str(e)}")
            return None
        except Exception as e:
            self.performance_monitor.record_error('MarketBuyError', str(e))
            logger.error(f"Failed to execute market buy order: {str(e)}")
            return None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def market_sell(self, symbol: str, quantity: float) -> Optional[Dict]:
        """执行市价卖出"""
        try:
            async with self._order_semaphore:
                if not self.client:
                    await self.initialize()
                
                start_time = datetime.now()
                
                order = await self.client.create_order(
                    symbol=symbol,
                    side='SELL',
                    type='MARKET',
                    quantity=quantity
                )
                
                # 记录执行时间
                execution_time = (datetime.now() - start_time).total_seconds()
                self.performance_monitor.record_execution_time('market_sell', execution_time)
                
                logger.info(f"市价卖出订单执行成功: {order}")
                return order
        except BinanceAPIException as e:
            self.performance_monitor.record_error('MarketSellError', str(e))
            logger.error(f"Failed to execute market sell order: {str(e)}")
            return None
        except Exception as e:
            self.performance_monitor.record_error('MarketSellError', str(e))
            logger.error(f"Failed to execute market sell order: {str(e)}")
            return None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def get_symbol_price(self, symbol: str) -> Optional[float]:
        """获取交易对当前价格"""
        try:
            # 检查缓存
            cache_key = f"{symbol}_price"
            cached_price = self._price_cache.get(cache_key)
            cache_ttl = self.performance_monitor.calculate_cache_ttl(symbol)
            
            if cached_price and (datetime.now() - cached_price['timestamp']).total_seconds() < cache_ttl:
                return cached_price['price']
            
            # 使用信号量限制并发
            async with self._price_semaphore:
                if not self.client:
                    await self.initialize()
                
                start_time = datetime.now()
                
                # 获取最新价格
                ticker = await self.client.get_symbol_ticker(symbol=symbol)
                price = float(ticker['price'])
                
                # 记录API延迟和价格波动
                latency = (datetime.now() - start_time).total_seconds()
                self.performance_monitor.record_api_latency('get_symbol_price', latency)
                self.performance_monitor.record_price_volatility(symbol, price)
                
                # 更新缓存
                self._price_cache[cache_key] = {
                    'price': price,
                    'timestamp': datetime.now()
                }
                
                return price
                
        except BinanceAPIException as e:
            self.performance_monitor.record_error('GetPriceError', str(e))
            logger.error(f"Failed to get symbol price: {str(e)}")
            raise
        except Exception as e:
            self.performance_monitor.record_error('GetPriceError', str(e))
            logger.error(f"Failed to get symbol price: {str(e)}")
            return None

    async def cleanup(self):
        """清理资源"""
        if self.client:
            await self.client.close_connection()
            self.client = None
            await self.performance_monitor.stop()
            self.logger.info("Closed Binance client connection")

    def get_performance_stats(self) -> Dict:
        """获取性能统计信息"""
        return self.performance_monitor.get_performance_stats()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def check_balance(self, asset: str) -> Optional[float]:
        """检查资产余额"""
        try:
            if not self.client:
                await self.initialize()
                
            account = await self.client.get_account()
            for balance in account['balances']:
                if balance['asset'] == asset:
                    return float(balance['free'])
            return 0.0
        except BinanceAPIException as e:
            logger.error(f"Failed to check balance: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Failed to check balance: {str(e)}")
            return None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def check_position(self, asset: str) -> Optional[float]:
        """检查资产持仓"""
        try:
            account = await self.client.get_account()
            for balance in account['balances']:
                if balance['asset'] == asset:
                    return float(balance['free'])
            return 0.0
        except BinanceAPIException as e:
            logger.error(f"Failed to check position: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Failed to check position: {str(e)}")
            return None

    def _format_order_response(self, order: Dict) -> Dict:
        """
        格式化订单响应
        
        Args:
            order: Binance API返回的订单信息
            
        Returns:
            格式化后的订单信息
        """
        return {
            'order_id': order['orderId'],
            'symbol': order['symbol'],
            'side': order['side'],
            'type': order['type'],
            'quantity': float(order['executedQty']),
            'price': float(order['cummulativeQuoteQty']) / float(order['executedQty']),
            'status': order['status'],
            'timestamp': datetime.fromtimestamp(order['transactTime'] / 1000).isoformat(),
            'test_mode': self.test_mode
        } 
        
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def get_price_change_percentage(self, symbol: str) -> Optional[float]:
        """获取24小时价格变化百分比"""
        try:
            async with self._price_semaphore:
                if not self.client:
                    await self.initialize()
                    
                ticker = await self.client.get_ticker(symbol=symbol)
                return float(ticker['priceChangePercent'])
                
        except BinanceAPIException as e:
            self.performance_monitor.record_error('GetPriceChangeError', str(e))
            logger.error(f"获取价格变化失败: {str(e)}")
            return None
        except Exception as e:
            self.performance_monitor.record_error('GetPriceChangeError', str(e))
            logger.error(f"获取价格变化失败: {str(e)}")
            return None
            
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def get_price_volatility(self, symbol: str) -> Optional[float]:
        """计算价格波动率（基于最近100个K线的标准差）"""
        try:
            async with self._price_semaphore:
                if not self.client:
                    await self.initialize()
                    
                # 获取最近100个1分钟K线
                klines = await self.client.get_klines(
                    symbol=symbol,
                    interval='1m',
                    limit=100
                )
                
                if not klines:
                    return None
                    
                # 计算收盘价的标准差
                closes = [float(k[4]) for k in klines]  # 收盘价在索引4
                mean = sum(closes) / len(closes)
                variance = sum((x - mean) ** 2 for x in closes) / len(closes)
                volatility = (variance ** 0.5) / mean  # 相对标准差
                
                return volatility
                
        except BinanceAPIException as e:
            self.performance_monitor.record_error('GetVolatilityError', str(e))
            logger.error(f"计算波动率失败: {str(e)}")
            return None
        except Exception as e:
            self.performance_monitor.record_error('GetVolatilityError', str(e))
            logger.error(f"计算波动率失败: {str(e)}")
            return None
            
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def set_stop_orders(self, symbol: str, quantity: float, entry_price: float,
                            stop_loss_pct: float, take_profit_pct: float) -> Optional[Dict]:
        """
        设置止损和止盈订单
        
        Args:
            symbol: 交易对
            quantity: 交易数量
            entry_price: 入场价格
            stop_loss_pct: 止损百分比
            take_profit_pct: 止盈百分比
            
        Returns:
            包含止损止盈订单ID的字典
        """
        try:
            async with self._order_semaphore:
                if not self.client:
                    await self.initialize()
                    
                # 计算止损和止盈价格
                stop_loss_price = entry_price * (1 - stop_loss_pct)
                take_profit_price = entry_price * (1 + take_profit_pct)
                
                # 创建止损订单
                stop_loss_order = await self.client.create_order(
                    symbol=symbol,
                    side='SELL',
                    type='STOP_LOSS_LIMIT',
                    timeInForce='GTC',
                    quantity=quantity,
                    stopPrice=stop_loss_price,
                    price=stop_loss_price * 0.99  # 稍低于触发价格以确保执行
                )
                
                # 创建止盈订单
                take_profit_order = await self.client.create_order(
                    symbol=symbol,
                    side='SELL',
                    type='TAKE_PROFIT_LIMIT',
                    timeInForce='GTC',
                    quantity=quantity,
                    stopPrice=take_profit_price,
                    price=take_profit_price * 0.99  # 稍低于触发价格以确保执行
                )
                
                # 记录订单信息
                orders = {
                    'stop_loss': {
                        'orderId': stop_loss_order['orderId'],
                        'price': stop_loss_price,
                        'type': 'STOP_LOSS'
                    },
                    'take_profit': {
                        'orderId': take_profit_order['orderId'],
                        'price': take_profit_price,
                        'type': 'TAKE_PROFIT'
                    }
                }
                
                # 更新开放订单跟踪
                self.open_orders[symbol] = {
                    'entry_price': entry_price,
                    'quantity': quantity,
                    'orders': orders,
                    'timestamp': datetime.now().isoformat()
                }
                
                logger.info(f"设置止损止盈订单成功: {symbol}")
                return orders
                
        except BinanceAPIException as e:
            self.performance_monitor.record_error('SetStopOrdersError', str(e))
            logger.error(f"设置止损止盈订单失败: {str(e)}")
            return None
        except Exception as e:
            self.performance_monitor.record_error('SetStopOrdersError', str(e))
            logger.error(f"设置止损止盈订单失败: {str(e)}")
            return None
            
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def check_open_orders(self) -> List[Dict]:
        """检查开放订单状态"""
        try:
            if not self.client:
                await self.initialize()
                
            triggered_orders = []
            
            # 获取所有开放订单
            for symbol, order_info in list(self.open_orders.items()):
                orders = await self.client.get_open_orders(symbol=symbol)
                current_orders = {str(order['orderId']): order for order in orders}
                
                # 检查是否有订单被触发
                for order_type, order_data in order_info['orders'].items():
                    order_id = str(order_data['orderId'])
                    if order_id not in current_orders:
                        # 订单已经被触发或取消
                        triggered_orders.append({
                            'symbol': symbol,
                            'type': order_data['type'],
                            'price': order_data['price'],
                            'quantity': order_info['quantity'],
                            'timestamp': datetime.now().isoformat()
                        })
                        
                # 如果所有订单都已触发，从跟踪列表中移除
                if not any(str(order_data['orderId']) in current_orders 
                          for order_data in order_info['orders'].values()):
                    del self.open_orders[symbol]
                    
            return triggered_orders
            
        except BinanceAPIException as e:
            self.performance_monitor.record_error('CheckOrdersError', str(e))
            logger.error(f"检查开放订单失败: {str(e)}")
            return []
        except Exception as e:
            self.performance_monitor.record_error('CheckOrdersError', str(e))
            logger.error(f"检查开放订单失败: {str(e)}")
            return []
            
    def get_open_orders(self) -> Dict:
        """获取当前开放订单信息"""
        return self.open_orders 