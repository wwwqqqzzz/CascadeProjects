"""
测试交易管理器功能
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta
from ..services.trading.trading_manager import TradingManager

@pytest.fixture
async def mock_binance_trader():
    """创建mock交易执行器"""
    mock = AsyncMock()
    mock.get_symbol_price.return_value = 50000.0
    mock.market_buy.return_value = {
        'symbol': 'BTCUSDT',
        'orderId': '12345',
        'status': 'FILLED',
        'executedQty': '1.0',
        'price': '50000.0'
    }
    return mock

@pytest.fixture
async def trading_manager(mock_binance_trader):
    """创建交易管理器实例"""
    with patch('crypto_monitor.services.trading.trading_manager.BinanceTrader', return_value=mock_binance_trader):
        manager = TradingManager(
            api_key='test_key',
            api_secret='test_secret',
            keywords=['buy', 'sell'],
            test_mode=True
        )
        await manager.start()
        yield manager
        await manager.stop()

@pytest.mark.asyncio
async def test_trading_manager_initialization(trading_manager):
    """测试交易管理器初始化"""
    assert trading_manager.trade_count == 0
    assert trading_manager.last_trade_time is None
    assert trading_manager.signal_detector is not None
    assert trading_manager.trader is not None
    assert trading_manager.is_running is True

@pytest.mark.asyncio
async def test_process_tweet_no_signal(trading_manager):
    """测试处理无信号的推文"""
    tweet = {
        'text': 'Just a normal tweet',
        'created_at': datetime.now().isoformat()
    }
    result = await trading_manager.process_tweet(tweet)
    assert result is None

@pytest.mark.asyncio
async def test_process_tweet_with_signal(trading_manager, mock_binance_trader):
    """测试处理包含交易信号的推文"""
    tweet = {
        'text': 'BTC is going to moon! Time to buy!',
        'created_at': datetime.now().isoformat()
    }
    
    # 设置初始状态
    trading_manager.trade_count = 0
    trading_manager.last_trade_time = datetime.now() - timedelta(hours=1)
    
    # 设置信号检测结果
    trading_manager.signal_detector.detect_signal = Mock(return_value={
        'symbol': 'BTCUSDT',
        'side': 'BUY',
        'score': 0.9
    })
    
    result = await trading_manager.process_tweet(tweet)
    assert result is not None
    assert result['symbol'] == 'BTCUSDT'
    assert result['status'] == 'FILLED'
    assert result['executedQty'] == '1.0'
    assert trading_manager.trade_count == 1
    assert trading_manager.last_trade_time is not None

@pytest.mark.asyncio
async def test_execute_trade_price_error(trading_manager, mock_binance_trader):
    """测试获取价格失败时的交易执行"""
    mock_binance_trader.get_symbol_price.side_effect = Exception("Price fetch failed")
    signal = {
        'symbol': 'BTCUSDT',
        'side': 'BUY',
        'score': 0.9
    }
    result = await trading_manager._execute_trade(signal)
    assert result is None

@pytest.mark.asyncio
async def test_validate_trading_conditions(trading_manager):
    """测试交易条件验证"""
    # 测试信号分数过低
    signal = {'score': 0.1}
    trading_manager.config['min_signal_score'] = 0.5
    result = await trading_manager._validate_trading_conditions(signal)
    assert result is False
    
    # 测试超过每日交易次数限制
    signal = {'score': 0.9}
    trading_manager.trade_count = 10
    trading_manager.config['max_trades_per_day'] = 10
    result = await trading_manager._validate_trading_conditions(signal)
    assert result is False
    
    # 测试交易间隔过短
    trading_manager.trade_count = 0
    trading_manager.last_trade_time = datetime.now()
    trading_manager.config['min_trade_interval'] = 300
    result = await trading_manager._validate_trading_conditions(signal)
    assert result is False
    
    # 测试正常情况
    trading_manager.last_trade_time = datetime.now() - timedelta(minutes=10)
    result = await trading_manager._validate_trading_conditions(signal)
    assert result is True

@pytest.mark.asyncio
async def test_manager_lifecycle(trading_manager, mock_binance_trader):
    """测试交易管理器生命周期"""
    # 停止管理器
    await trading_manager.stop()
    assert trading_manager.is_running is False
    mock_binance_trader.cleanup.assert_called_once()
    
    # 重新启动管理器
    await trading_manager.start()
    assert trading_manager.is_running is True
    mock_binance_trader.initialize.assert_called()

@pytest.mark.asyncio
async def test_error_handling(trading_manager, mock_binance_trader):
    """测试错误处理"""
    # 模拟初始化错误
    mock_binance_trader.initialize.side_effect = Exception("Initialization failed")
    await trading_manager.stop()
    
    # 重新启动应该捕获错误
    await trading_manager.start()
    assert trading_manager.is_running is True  # 即使初始化失败也应该继续运行 