"""
Trade execution module for cryptocurrency trading.
"""

import logging
from typing import Dict, Optional
from datetime import datetime
from binance.client import Client
from binance.exceptions import BinanceAPIException

logger = logging.getLogger(__name__)

class TradeExecutor:
    def __init__(self, api_key: str, api_secret: str, test_mode: bool = True):
        """
        初始化交易执行器
        
        Args:
            api_key: Binance API key
            api_secret: Binance API secret
            test_mode: 是否使用测试模式
        """
        self.client = Client(api_key, api_secret)
        self.test_mode = test_mode
        self.min_trade_amount = 10.0  # 最小交易金额(USDT)
        
    async def execute_trade(self, signal: Dict) -> Optional[Dict]:
        """
        执行交易操作
        
        Args:
            signal: 交易信号详情
            
        Returns:
            交易结果详情,如果失败则返回 None
        """
        try:
            # 交易对和金额计算
            symbol = self._determine_trading_pair(signal)
            amount = self._calculate_trade_amount(signal)
            
            if not symbol or not amount:
                logger.warning("无法确定交易对或金额")
                return None
                
            # 获取当前市场价格
            ticker = self.client.get_symbol_ticker(symbol=symbol)
            current_price = float(ticker['price'])
            
            # 计算购买数量
            quantity = amount / current_price
            
            # 执行购买
            if self.test_mode:
                # 测试模式
                order = self.client.create_test_order(
                    symbol=symbol,
                    side='BUY',
                    type='MARKET',
                    quantity=quantity
                )
                logger.info(f"测试模式下的交易执行成功: {order}")
            else:
                # 实际交易
                order = self.client.create_order(
                    symbol=symbol,
                    side='BUY',
                    type='MARKET',
                    quantity=quantity
                )
                logger.info(f"交易执行成功: {order}")
                
            # 返回交易结果
            return {
                'timestamp': datetime.now().isoformat(),
                'signal': signal,
                'symbol': symbol,
                'side': 'BUY',
                'amount': amount,
                'price': current_price,
                'quantity': quantity,
                'status': 'success',
                'test_mode': self.test_mode,
                'order_id': order.get('orderId')
            }
            
        except BinanceAPIException as e:
            logger.error(f"Binance API 错误: {e}")
            return {
                'timestamp': datetime.now().isoformat(),
                'signal': signal,
                'status': 'failed',
                'error': str(e),
                'test_mode': self.test_mode
            }
        except Exception as e:
            logger.error(f"交易执行错误: {e}")
            return None
            
    def _determine_trading_pair(self, signal: Dict) -> Optional[str]:
        """
        根据信号确定交易对
        
        目前使用简单的逻辑,后续可以:
        1. 分析推文内容提取币种
        2. 使用配置文件定义交易对
        3. 根据市场流动性选择
        """
        # 示例: 默认使用 BTC/USDT
        return 'BTCUSDT'
        
    def _calculate_trade_amount(self, signal: Dict) -> float:
        """
        计算交易金额
        
        目前使用固定金额,后续可以:
        1. 根据信号强度调整
        2. 考虑账户余额
        3. 使用风险管理策略
        """
        # 示例: 使用最小交易金额
        return self.min_trade_amount 