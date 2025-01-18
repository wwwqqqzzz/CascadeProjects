"""
Trading module unit tests.
"""

import pytest
import asyncio
from datetime import datetime
import time
from unittest.mock import Mock, patch
from crypto_monitor.services.trading.signal_detector import SignalDetector
from crypto_monitor.services.trading.trade_executor import TradeExecutor
from crypto_monitor.services.trading.trade_logger import TradeLogger

@pytest.fixture
def signal_detector():
    """创建信号检测器实例"""
    keywords = ['buy', 'moon', 'pump']
    return SignalDetector(keywords=keywords)

@pytest.fixture
def trade_executor():
    """创建交易执行器实例(测试模式)"""
    return TradeExecutor(
        api_key='test_key',
        api_secret='test_secret',
        test_mode=True
    )

@pytest.fixture
def trade_logger(tmp_path):
    """创建交易日志记录器实例(使用临时目录)"""
    return TradeLogger(log_dir=str(tmp_path / 'trades'))

def test_signal_detection(signal_detector):
    """测试信号检测功能"""
    # 测试包含关键词的推文
    tweet_data = {
        'text': 'Time to buy BTC! To the moon!',
        'author': 'crypto_trader',
        'timestamp': datetime.now().isoformat()
    }
    signal = signal_detector.detect_signal(tweet_data)
    assert signal is not None
    assert signal['author'] == 'crypto_trader'
    assert len(signal['keywords']) == 2  # 'buy' and 'moon'
    assert signal['score'] > 0.5
    
    # 测试不包含关键词的推文
    tweet_data = {
        'text': 'Just another normal day',
        'author': 'random_user'
    }
    signal = signal_detector.detect_signal(tweet_data)
    assert signal is None
    
    # 测试重复信号的评分降低
    tweet_data = {
        'text': 'Buy BTC now! Moon soon!',
        'author': 'crypto_trader'
    }
    signal1 = signal_detector.detect_signal(tweet_data)
    signal2 = signal_detector.detect_signal(tweet_data)  # 立即重复
    assert signal2 is None or signal2['score'] < signal1['score']

@pytest.mark.asyncio
async def test_trade_execution(trade_executor):
    """测试交易执行功能"""
    # Mock Binance API 响应
    mock_ticker = {'price': '50000.0'}
    mock_order = {'orderId': '12345'}
    
    with patch.object(trade_executor.client, 'get_symbol_ticker', return_value=mock_ticker), \
         patch.object(trade_executor.client, 'create_test_order', return_value=mock_order):
        
        # 创建测试信号
        signal = {
            'timestamp': datetime.now().isoformat(),
            'author': 'test_user',
            'keywords': ['buy', 'moon'],
            'score': 0.9,
            'text': 'Test signal',
            'source': 'twitter'
        }
        
        # 执行交易
        result = await trade_executor.execute_trade(signal)
        
        # 验证交易结果
        assert result is not None
        assert result['status'] == 'success'
        assert result['symbol'] == 'BTCUSDT'
        assert result['test_mode'] is True
        assert result['order_id'] == '12345'
        assert float(result['price']) == 50000.0
        
        # 测试错误处理
        with patch.object(trade_executor.client, 'get_symbol_ticker', 
                         side_effect=Exception('API Error')):
            result = await trade_executor.execute_trade(signal)
            assert result is None

def test_trade_logging(trade_logger):
    """测试交易日志记录功能"""
    # 记录交易信号
    signal = {
        'timestamp': datetime.now().isoformat(),
        'source': 'twitter',
        'author': 'test_user',
        'keywords': ['buy', 'moon'],
        'score': 0.9,
        'text': 'Test signal'
    }
    trade_logger.log_signal(signal)
    
    # 记录成功的交易
    trade_result = {
        'timestamp': datetime.now().isoformat(),
        'signal': signal,
        'symbol': 'BTCUSDT',
        'side': 'BUY',
        'amount': 100.0,
        'price': 50000.0,
        'quantity': 0.002,
        'status': 'success',
        'test_mode': True,
        'order_id': '12345'
    }
    trade_logger.log_trade(trade_result)
    
    # 等待一秒确保时间戳不同
    time.sleep(0.1)
    
    # 记录失败的交易
    failed_trade = {
        'timestamp': datetime.now().isoformat(),
        'signal': signal,
        'status': 'failed',
        'error': 'Insufficient funds',
        'test_mode': True
    }
    trade_logger.log_trade(failed_trade)
    
    # 验证统计信息
    stats = trade_logger.get_daily_stats()
    assert stats['total_trades'] == 2
    assert stats['successful_trades'] == 1
    assert stats['failed_trades'] == 1
    assert stats['signals_received'] == 1
    assert stats['total_amount'] == 100.0
    
    # 验证历史记录
    history = trade_logger.get_trade_history(days=1)
    assert len(history) == 2
    assert history[0]['status'] == 'failed'  # 最新的记录
    assert history[1]['status'] == 'success'

@pytest.mark.asyncio
async def test_end_to_end_flow(signal_detector, trade_executor, trade_logger):
    """测试完整的交易流程"""
    # Mock Binance API
    mock_ticker = {'price': '50000.0'}
    mock_order = {'orderId': '12345'}
    
    with patch.object(trade_executor.client, 'get_symbol_ticker', return_value=mock_ticker), \
         patch.object(trade_executor.client, 'create_test_order', return_value=mock_order):
        
        # 1. 检测信号
        tweet_data = {
            'text': 'Time to buy BTC! To the moon!',
            'author': 'crypto_trader',
            'timestamp': datetime.now().isoformat()
        }
        signal = signal_detector.detect_signal(tweet_data)
        assert signal is not None
        
        # 记录信号
        trade_logger.log_signal(signal)
        
        # 2. 执行交易
        trade_result = await trade_executor.execute_trade(signal)
        assert trade_result is not None
        assert trade_result['status'] == 'success'
        
        # 3. 记录交易
        trade_logger.log_trade(trade_result)
        
        # 验证完整流程
        stats = trade_logger.get_daily_stats()
        assert stats['signals_received'] == 1
        assert stats['successful_trades'] == 1
        assert stats['total_trades'] == 1 