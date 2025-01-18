"""
交易管理器，负责交易信号处理和交易执行
"""

import logging
import asyncio
from typing import Dict, Optional, List
from datetime import datetime, timedelta
import re
from ...utils.config import TRADING_CONFIG
from ..trading.binance_trader import BinanceTrader
from ..trading.signal_detector import SignalDetector
from ..trading.trade_logger import TradeLogger

logger = logging.getLogger(__name__)

class TradingManager:
    def __init__(self, api_key: str, api_secret: str, test_mode: bool = True, keywords: List[str] = None):
        """初始化交易管理器
        
        Args:
            api_key: Binance API key
            api_secret: Binance API secret
            test_mode: 是否使用测试模式
            keywords: 用于信号检测的关键词列表
        """
        self.config = TRADING_CONFIG
        self.test_mode = test_mode
        self.is_running = False
        
        # 初始化组件
        self.trader = BinanceTrader(api_key, api_secret, test_mode)
        self.signal_detector = SignalDetector(keywords or self.config.get('keywords', []))
        self.trade_logger = TradeLogger()
        
        # 交易状态
        self.trade_count = 0
        self.last_trade_time = None
        self.daily_volume = 0.0  # 每日交易量
        self.position_sizes = {}  # 各交易对持仓大小
        
        # 风险控制参数
        self.max_position_size = self.config.get('max_position_size', 1000)  # 最大持仓（USDT）
        self.max_daily_volume = self.config.get('max_daily_volume', 5000)   # 最大日交易量
        self.position_size_pct = self.config.get('position_size_pct', 0.1)  # 单次交易占账户比例
        self.max_slippage = self.config.get('max_slippage', 0.002)         # 最大滑点
        
        # 默认配置值
        if 'min_signal_score' not in self.config:
            self.config['min_signal_score'] = 0.7
        if 'max_trades_per_day' not in self.config:
            self.config['max_trades_per_day'] = 10
        if 'min_trade_interval' not in self.config:
            self.config['min_trade_interval'] = 300  # 5分钟
        if 'max_price_change_pct' not in self.config:
            self.config['max_price_change_pct'] = 10.0
        if 'min_stop_loss_pct' not in self.config:
            self.config['min_stop_loss_pct'] = 0.01  # 1%
        if 'max_stop_loss_pct' not in self.config:
            self.config['max_stop_loss_pct'] = 0.05  # 5%
        if 'trading_pairs' not in self.config:
            self.config['trading_pairs'] = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT']
        
    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.start()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        await self.stop()
        
    async def start(self):
        """启动交易管理器"""
        if self.is_running:
            return
            
        self.is_running = True
        logger.info("交易管理器已启动")
        
        # 初始化交易状态
        await self._initialize_trading_state()
        
        # 启动订单检查任务
        asyncio.create_task(self._check_orders())
        
    async def stop(self):
        """停止交易管理器"""
        if not self.is_running:
            return
            
        self.is_running = False
        await self.trader.cleanup()
        logger.info("交易管理器已停止")
        
    async def _initialize_trading_state(self):
        """初始化交易状态"""
        try:
            # 获取账户余额
            balance = await self.trader.check_balance('USDT')
            if balance is None:
                logger.error("无法获取账户余额")
                return
                
            logger.info(f"当前USDT余额: {balance}")
            
            # 获取当前持仓
            for symbol in self.config['trading_pairs']:
                base_asset = symbol.replace('USDT', '')
                position = await self.trader.check_position(base_asset)
                if position is not None:
                    self.position_sizes[symbol] = position
                    logger.info(f"当前{symbol}持仓: {position}")
                    
            # 重置每日统计
            if self._is_new_trading_day():
                self._reset_daily_stats()
                
        except Exception as e:
            logger.error(f"初始化交易状态时出错: {e}")
            
    def _is_new_trading_day(self) -> bool:
        """检查是否是新的交易日"""
        if not self.last_trade_time:
            return True
        current_date = datetime.now().date()
        last_trade_date = self.last_trade_time.date()
        return current_date != last_trade_date
        
    def _reset_daily_stats(self):
        """重置每日统计数据"""
        self.trade_count = 0
        self.daily_volume = 0.0
        logger.info("已重置每日交易统计")
        
    async def process_tweet(self, tweet: Dict) -> Optional[Dict]:
        """处理推文"""
        try:
            # 1. 检测交易信号
            signal = self.signal_detector.detect_signal(tweet)
            if not signal:
                logger.info("未检测到交易信号")
                return None
                
            # 2. 识别交易对
            symbol = self._get_trading_symbol(signal)
            if not symbol:
                logger.warning("无法识别有效的交易对")
                return None
                
            # 3. 构建完整的交易信号
            trade_signal = {
                'text': signal['text'],
                'score': signal.get('score', 0.9),  # 使用信号中的分数或默认值
                'symbol': symbol,
                'source': signal.get('source', 'twitter'),
                'timestamp': signal.get('timestamp', datetime.now().isoformat())
            }
            
            # 4. 验证交易条件
            if not await self._validate_trading_conditions(trade_signal):
                logger.warning("交易条件验证失败")
                return None
                
            # 5. 计算交易数量
            quantity = await self._calculate_trade_quantity(symbol)
            if not quantity:
                logger.warning("无法计算有效的交易数量")
                return None
                
            trade_signal['quantity'] = quantity
            
            # 6. 执行交易
            result = await self._execute_trade(trade_signal)
            if not result:
                logger.error("交易执行失败")
                return None
                
            # 7. 设置止损止盈
            await self._set_stop_orders(symbol, quantity, float(result['price']))
            
            return result
            
        except Exception as e:
            logger.error(f"处理推文时出错: {str(e)}")
            return None
            
    def _get_trading_symbol(self, signal: Dict) -> Optional[str]:
        """从信号中识别交易对"""
        try:
            # 1. 从推文中提取币种名称
            text = signal['text'].upper()
            
            # 常见的币种模式
            patterns = [
                r'\$([A-Z]{2,10})',  # $BTC
                r'#([A-Z]{2,10})',   # #BTC
                r'([A-Z]{2,10})/USDT',  # BTC/USDT
                r'([A-Z]{2,10})-USDT'   # BTC-USDT
            ]
            
            found_symbols = []
            for pattern in patterns:
                matches = re.findall(pattern, text)
                found_symbols.extend(matches)
                
            # 2. 验证找到的币种是否在支持的交易对列表中
            valid_symbols = []
            for symbol in found_symbols:
                symbol_usdt = f"{symbol}USDT"
                if symbol_usdt in self.config['trading_pairs']:
                    valid_symbols.append(symbol_usdt)
                    
            if not valid_symbols:
                return None
                
            # 3. 如果找到多个交易对，选择信号强度最高的
            if len(valid_symbols) > 1:
                # TODO: 实现更智能的交易对选择逻辑
                return valid_symbols[0]
                
            return valid_symbols[0]
            
        except Exception as e:
            logger.error(f"识别交易对时出错: {e}")
            return None
            
    async def _calculate_trade_quantity(self, symbol: str) -> Optional[float]:
        """计算交易数量"""
        try:
            # 1. 获取账户余额
            balance = await self.trader.check_balance('USDT')
            if not balance:
                return None
                
            # 2. 获取当前市场价格
            price = await self.trader.get_symbol_price(symbol)
            if not price:
                return None
                
            # 3. 计算基础交易量（按账户比例）
            base_quantity = (balance * self.position_size_pct) / price
            
            # 4. 应用风险限制
            # 检查是否超过最大持仓
            current_position = self.position_sizes.get(symbol, 0)
            max_additional = (self.max_position_size / price) - current_position
            if max_additional <= 0:
                logger.warning(f"{symbol}已达到最大持仓限制")
                return None
                
            # 检查是否超过每日交易量
            remaining_volume = self.max_daily_volume - self.daily_volume
            if remaining_volume <= 0:
                logger.warning("已达到每日最大交易量")
                return None
                
            # 取最小值作为最终交易量
            quantity = min(
                base_quantity,
                max_additional,
                remaining_volume / price
            )
            
            # 5. 调整数量精度
            quantity = self._adjust_quantity_precision(symbol, quantity)
            
            return quantity
            
        except Exception as e:
            logger.error(f"计算交易数量时出错: {e}")
            return None
            
    def _adjust_quantity_precision(self, symbol: str, quantity: float) -> float:
        """调整交易数量精度"""
        # TODO: 从交易所获取实际精度要求
        # 临时使用6位小数
        return round(quantity, 6)
        
    async def _validate_trading_conditions(self, signal: Dict) -> bool:
        """验证交易条件"""
        try:
            # 1. 基本条件检查
            if signal['score'] < self.config['min_signal_score']:
                logger.info(f"信号分数{signal['score']}低于阈值{self.config['min_signal_score']}")
                return False
                
            if self.trade_count >= self.config['max_trades_per_day']:
                logger.info(f"已达到每日最大交易次数{self.config['max_trades_per_day']}")
                return False
                
            if self.last_trade_time:
                time_since_last_trade = datetime.now() - self.last_trade_time
                min_interval = timedelta(seconds=self.config['min_trade_interval'])
                if time_since_last_trade < min_interval:
                    logger.info(f"距离上次交易时间{time_since_last_trade}小于最小间隔{min_interval}")
                    return False
                    
            # 2. 市场条件检查
            symbol = signal['symbol']
            
            # 检查价格波动
            price = await self.trader.get_symbol_price(symbol)
            if not price:
                return False
                
            # 检查24小时价格变化
            price_change = await self.trader.get_price_change_percentage(symbol)
            if abs(price_change) > self.config.get('max_price_change_pct', 10):
                logger.warning(f"{symbol} 24小时价格变化{price_change}%超过限制")
                return False
                
            # 3. 风险控制检查
            # 检查持仓限制
            current_position = self.position_sizes.get(symbol, 0)
            if current_position * price >= self.max_position_size:
                logger.warning(f"{symbol}持仓已达到上限")
                return False
                
            # 检查每日交易量
            if self.daily_volume >= self.max_daily_volume:
                logger.warning("已达到每日交易量上限")
                return False
                
            return True
            
        except Exception as e:
            logger.error(f"验证交易条件时出错: {e}")
            return False
            
    async def _execute_trade(self, signal: Dict) -> Optional[Dict]:
        """执行交易"""
        try:
            symbol = signal['symbol']
            quantity = signal['quantity']
            
            # 1. 获取执行前的市场价格
            pre_price = await self.trader.get_symbol_price(symbol)
            if not pre_price:
                return None
                
            # 2. 执行市价单
            result = await self.trader.market_buy(symbol, quantity)
            if not result:
                return None
                
            # 3. 检查成交价格滑点
            execution_price = float(result['price'])
            slippage = abs(execution_price - pre_price) / pre_price
            
            if slippage > self.max_slippage:
                logger.warning(f"交易滑点{slippage:.4%}超过限制{self.max_slippage:.4%}")
                # TODO: 考虑是否需要回滚交易
                
            # 4. 更新交易状态
            self.trade_count += 1
            self.last_trade_time = datetime.now()
            self.daily_volume += quantity * execution_price
            self.position_sizes[symbol] = self.position_sizes.get(symbol, 0) + quantity
            
            # 5. 记录交易
            trade_record = {
                'timestamp': datetime.now().isoformat(),
                'symbol': symbol,
                'side': 'BUY',
                'quantity': quantity,
                'executedQty': result['executedQty'],
                'price': execution_price,
                'amount': quantity * execution_price,
                'slippage': slippage,
                'signal': signal,
                'status': result['status'],
                'test_mode': self.test_mode
            }
            
            self.trade_logger.log_trade(trade_record)
            logger.info(f"交易执行成功: {trade_record}")
            
            return trade_record
            
        except Exception as e:
            logger.error(f"执行交易时出错: {e}")
            return None
            
    async def _set_stop_orders(self, symbol: str, quantity: float, entry_price: float):
        """设置止损和止盈订单"""
        try:
            # 动态计算止损止盈价格
            volatility = await self.trader.get_price_volatility(symbol)
            
            # 根据波动率调整止损比例
            stop_loss_pct = min(
                self.config['max_stop_loss_pct'],
                max(self.config['min_stop_loss_pct'], volatility * 2)
            )
            
            # 止盈设置为止损的2倍
            take_profit_pct = stop_loss_pct * 2
            
            # 设置订单
            orders = await self.trader.set_stop_orders(
                symbol=symbol,
                quantity=quantity,
                entry_price=entry_price,
                stop_loss_pct=stop_loss_pct,
                take_profit_pct=take_profit_pct
            )
            
            if orders:
                logger.info(f"已设置止损止盈订单: 止损{stop_loss_pct:.2%}, 止盈{take_profit_pct:.2%}")
            
        except Exception as e:
            logger.error(f"设置止损止盈订单时出错: {e}")
            
    async def _check_orders(self, test_mode: bool = False):
        """检查开放订单状态的循环任务
        
        Args:
            test_mode: 如果为True，则只运行一次（用于测试）
        """
        while self.is_running:
            try:
                # 检查订单状态
                triggered_orders = await self.trader.check_open_orders()
                
                # 处理已触发的订单
                for order in triggered_orders:
                    # 更新持仓信息
                    symbol = order['symbol']
                    quantity = float(order['quantity'])
                    if order['side'] == 'SELL':
                        self.position_sizes[symbol] = max(0, self.position_sizes.get(symbol, 0) - quantity)
                    
                    # 记录订单触发
                    self.trade_logger.log_trade({
                        'type': 'order_triggered',
                        'symbol': symbol,
                        'order_type': order['type'],
                        'price': order['price'],
                        'quantity': quantity,
                        'timestamp': order['timestamp']
                    })
                    
                    logger.info(f"订单已触发: {symbol}, 类型: {order['type']}, 价格: {order['price']}")
                
                if test_mode:
                    break
                    
                # 等待下一次检查
                await asyncio.sleep(self.config.get('order_check_interval', 10))
                
            except Exception as e:
                logger.error(f"检查订单状态时出错: {e}")
                if test_mode:
                    break
                await asyncio.sleep(5)  # 出错后等待一段时间再重试
                
    def get_status(self) -> Dict:
        """获取当前状态"""
        return {
            'is_running': self.is_running,
            'test_mode': self.test_mode,
            'trade_count': self.trade_count,
            'daily_volume': self.daily_volume,
            'last_trade_time': self.last_trade_time.isoformat() if self.last_trade_time else None,
            'position_sizes': self.position_sizes,
            'open_orders': self.trader.get_open_orders(),
            'daily_stats': self.trade_logger.get_daily_stats()
        } 