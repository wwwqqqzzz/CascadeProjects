"""
交易策略测试模块
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock
from crypto_monitor.services.trading.trading_manager import TradingManager
from crypto_monitor.services.trading.binance_trader import BinanceTrader

@pytest.fixture
async def trading_manager():
    """创建交易管理器实例"""
    # 测试用的关键词列表
    test_keywords = [
        '$BTC', '#BTC', 'BTCUSDT',
        '$ETH', '#ETH', 'ETHUSDT',
        '$BNB', '#BNB', 'BNBUSDT'
    ]
    
    manager = TradingManager(
        api_key='test_key',
        api_secret='test_secret',
        test_mode=True,
        keywords=test_keywords
    )
    
    # 初始化必要的属性
    manager.position_sizes = {}
    manager.max_position_size = 100000
    manager.max_daily_volume = 500000
    manager.daily_volume = 0
    manager.max_slippage = 0.01
    manager.last_trade_time = datetime.now()
    manager.trade_count = 0
    
    # 启动管理器
    await manager.start()
    try:
        yield manager
    finally:
        await manager.stop()

@pytest.mark.asyncio
async def test_process_tweet_with_valid_signal(trading_manager):
    """测试处理有效的交易信号"""
    manager = await anext(trading_manager)
    
    # 模拟推文
    tweet = {
        'text': 'Time to buy $BTC! Price looks good for #BTCUSDT',
        'author': 'crypto_trader',
        'timestamp': datetime.now().isoformat()
    }
    
    # Mock Binance API响应
    mock_price = 50000.0
    mock_balance = 50000.0
    mock_order = {
        'symbol': 'BTCUSDT',
        'orderId': '12345',
        'price': mock_price,
        'executedQty': '0.1',
        'status': 'FILLED'
    }
    
    # Mock信号检测
    mock_signal = {
        'text': tweet['text'],
        'score': 0.9,
        'keywords': ['$BTC', '#BTCUSDT'],
        'author': tweet['author'],
        'timestamp': tweet['timestamp'],
        'source': 'twitter'
    }
    manager.signal_detector.detect_signal = Mock(return_value=mock_signal)
    
    # Mock交易相关的异步方法
    manager.trader.get_symbol_price = AsyncMock(return_value=mock_price)
    manager.trader.check_balance = AsyncMock(return_value=mock_balance)
    manager.trader.market_buy = AsyncMock(return_value=mock_order)
    manager.trader.get_price_change_percentage = AsyncMock(return_value=5.0)
    manager.trader.get_price_volatility = AsyncMock(return_value=0.02)
    
    # 重置交易状态
    manager.trade_count = 0
    manager.last_trade_time = datetime.now() - timedelta(minutes=10)
    manager.daily_volume = 0
    manager.position_sizes = {}
    
    # 执行测试
    result = await manager.process_tweet(tweet)
    
    # 验证结果
    assert result is not None
    assert result['symbol'] == 'BTCUSDT'
    assert result['status'] == 'FILLED'
    assert float(result['price']) == mock_price
    assert float(result['executedQty']) == 0.1
    
    # 验证mock调用
    manager.signal_detector.detect_signal.assert_called_once_with(tweet)
    manager.trader.get_symbol_price.assert_called()
    manager.trader.check_balance.assert_called_once()
    manager.trader.market_buy.assert_called_once()
    manager.trader.get_price_change_percentage.assert_called()
    manager.trader.get_price_volatility.assert_called()
    
    # 验证交易状态更新
    assert manager.trade_count == 1
    assert manager.daily_volume > 0
    assert manager.last_trade_time is not None
    assert manager.position_sizes['BTCUSDT'] == 0.1

@pytest.mark.asyncio
async def test_trading_conditions_validation(trading_manager):
    """测试交易条件验证"""
    manager = await anext(trading_manager)
    
    signal = {
        'text': 'Buy $BTC now!',
        'score': 0.9,
        'symbol': 'BTCUSDT'
    }
    
    # Mock交易相关的异步方法
    manager.trader.get_symbol_price = AsyncMock(return_value=50000.0)
    manager.trader.get_price_change_percentage = AsyncMock(return_value=5.0)
    
    # 重置交易状态
    manager.trade_count = 0
    manager.last_trade_time = datetime.now() - timedelta(minutes=10)
    manager.daily_volume = 0
    manager.position_sizes = {}
    
    # 测试基本条件
    is_valid = await manager._validate_trading_conditions(signal)
    assert is_valid is True
    
    # 测试信号分数过低
    signal['score'] = 0.1
    is_valid = await manager._validate_trading_conditions(signal)
    assert is_valid is False
    
    # 测试价格变化过大
    signal['score'] = 0.9
    manager.trader.get_price_change_percentage = AsyncMock(return_value=15.0)
    is_valid = await manager._validate_trading_conditions(signal)
    assert is_valid is False

@pytest.mark.asyncio
async def test_trade_quantity_calculation(trading_manager):
    """测试交易数量计算"""
    manager = await anext(trading_manager)
    
    symbol = 'BTCUSDT'
    mock_price = 50000.0
    mock_balance = 10000.0
    
    # 设置mock对象
    manager.trader.get_symbol_price = AsyncMock(return_value=mock_price)
    manager.trader.check_balance = AsyncMock(return_value=mock_balance)
    
    # 测试正常计算
    quantity = await manager._calculate_trade_quantity(symbol)
    assert quantity is not None
    assert quantity > 0
    
    # 测试持仓限制
    manager.position_sizes[symbol] = manager.max_position_size / mock_price
    quantity = await manager._calculate_trade_quantity(symbol)
    assert quantity is None
    
    # 测试每日交易量限制
    manager.position_sizes[symbol] = 0
    manager.daily_volume = manager.max_daily_volume
    quantity = await manager._calculate_trade_quantity(symbol)
    assert quantity is None

@pytest.mark.asyncio
async def test_stop_orders_setup(trading_manager):
    """测试止损止盈订单设置"""
    manager = await anext(trading_manager)
    
    symbol = 'BTCUSDT'
    quantity = 0.1
    entry_price = 50000.0
    
    mock_volatility = 0.02
    mock_orders = {
        'stop_loss': {'orderId': '123', 'price': 49000.0},
        'take_profit': {'orderId': '456', 'price': 51000.0}
    }
    
    # 设置mock对象
    manager.trader.get_price_volatility = AsyncMock(return_value=mock_volatility)
    manager.trader.set_stop_orders = AsyncMock(return_value=mock_orders)
    
    # 执行测试
    await manager._set_stop_orders(symbol, quantity, entry_price)
    
    # 验证止损止盈订单的设置
    manager.trader.set_stop_orders.assert_called_once()
    call_args = manager.trader.set_stop_orders.call_args[1]
    assert call_args['symbol'] == symbol
    assert call_args['quantity'] == quantity
    assert call_args['entry_price'] == entry_price
    assert 0.01 <= call_args['stop_loss_pct'] <= 0.05
    assert call_args['take_profit_pct'] == call_args['stop_loss_pct'] * 2

@pytest.mark.asyncio
async def test_order_monitoring(trading_manager):
    """测试订单监控"""
    manager = await anext(trading_manager)
    
    symbol = 'BTCUSDT'
    mock_triggered_orders = [{
        'symbol': symbol,
        'type': 'STOP_LOSS',
        'side': 'SELL',
        'price': 49000.0,
        'quantity': 0.1,
        'timestamp': datetime.now().isoformat()
    }]
    
    # 设置初始持仓
    manager.position_sizes[symbol] = 0.1
    
    # 设置mock对象
    manager.trader.check_open_orders = AsyncMock(return_value=mock_triggered_orders)
    
    # 执行测试
    await manager._check_orders(test_mode=True)
    
    # 验证持仓更新
    assert manager.position_sizes[symbol] == 0

@pytest.mark.asyncio
async def test_risk_management(trading_manager):
    """测试风险管理"""
    manager = await anext(trading_manager)
    
    symbol = 'BTCUSDT'
    mock_price = 50000.0
    
    # 测试持仓限制
    manager.position_sizes[symbol] = manager.max_position_size / mock_price
    manager.trader.get_symbol_price = AsyncMock(return_value=mock_price)
    
    signal = {
        'text': 'Buy $BTC now!',
        'score': 0.9,
        'symbol': symbol
    }
    is_valid = await manager._validate_trading_conditions(signal)
    assert is_valid is False
    
    # 测试每日交易量限制
    manager.daily_volume = manager.max_daily_volume
    is_valid = await manager._validate_trading_conditions(signal)
    assert is_valid is False
    
    # 测试交易间隔
    manager.last_trade_time = datetime.now()
    is_valid = await manager._validate_trading_conditions(signal)
    assert is_valid is False

@pytest.mark.asyncio
async def test_slippage_monitoring(trading_manager):
    """测试滑点监控"""
    manager = await anext(trading_manager)
    
    symbol = 'BTCUSDT'
    quantity = 0.1
    pre_price = 50000.0
    execution_price = pre_price * (1 + manager.max_slippage * 2)  # 超出最大滑点
    
    mock_order = {
        'symbol': symbol,
        'orderId': '12345',
        'price': execution_price,
        'executedQty': str(quantity),
        'status': 'FILLED'
    }
    
    # 设置mock对象
    manager.trader.get_symbol_price = AsyncMock(return_value=pre_price)
    manager.trader.market_buy = AsyncMock(return_value=mock_order)
    
    signal = {
        'symbol': symbol,
        'quantity': quantity
    }
    
    # 执行测试
    result = await manager._execute_trade(signal)
    assert result is not None
    assert result['slippage'] > manager.max_slippage

@pytest.mark.asyncio
async def test_trading_symbol_recognition(trading_manager):
    """测试交易对识别"""
    manager = await anext(trading_manager)
    
    # 测试各种格式的币种标识
    test_cases = [
        {
            'text': 'Looking to buy some $BTC right now!',
            'expected': 'BTCUSDT'
        },
        {
            'text': 'Great opportunity for #ETH/USDT trading',
            'expected': 'ETHUSDT'
        },
        {
            'text': 'BNB-USDT is showing strong signals',
            'expected': 'BNBUSDT'
        },
        {
            'text': 'No valid trading pair mentioned',
            'expected': None
        }
    ]
    
    for case in test_cases:
        signal = {'text': case['text']}
        symbol = manager._get_trading_symbol(signal)
        assert symbol == case['expected']

@pytest.mark.asyncio
async def test_daily_stats_reset(trading_manager):
    """测试每日统计重置"""
    manager = await anext(trading_manager)
    
    # 设置昨天的最后交易时间
    manager.last_trade_time = datetime.now() - timedelta(days=1)
    manager.daily_volume = 1000
    manager.trade_count = 5
    
    # 触发重置
    manager._reset_daily_stats()
    
    # 验证重置结果
    assert manager.daily_volume == 0
    assert manager.trade_count == 0 