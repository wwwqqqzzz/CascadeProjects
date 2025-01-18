"""
Binance trader unit tests
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime
from binance.exceptions import BinanceAPIException
from crypto_monitor.services.trading.binance_trader import BinanceTrader

@pytest.fixture
async def mock_client():
    """创建mock异步client"""
    mock = AsyncMock()
    # 设置成功响应
    mock.create.return_value.get_account.return_value = {
        'balances': [{'asset': 'USDT', 'free': '1000.0'}]
    }
    mock.create.return_value.get_symbol_ticker.return_value = {'price': '50000.0'}
    mock.create.return_value.create_order.return_value = {
        'orderId': '12345',
        'symbol': 'BTCUSDT',
        'status': 'FILLED',
        'executedQty': '1.0',
        'cummulativeQuoteQty': '50000.0',
        'transactTime': 1609459200000
    }
    return mock

@pytest.fixture
async def trader(mock_client):
    """创建trader实例"""
    with patch('crypto_monitor.services.trading.binance_trader.AsyncClient', mock_client):
        trader = BinanceTrader('test_key', 'test_secret', test_mode=True)
        await trader.initialize()
        yield trader
        await trader.cleanup()

@pytest.mark.asyncio
async def test_market_buy_success(trader, mock_client):
    """测试市价买入成功"""
    result = await trader.market_buy('BTCUSDT', 1.0)
    assert result is not None
    assert result['symbol'] == 'BTCUSDT'
    assert result['status'] == 'FILLED'
    assert result['executedQty'] == '1.0'

@pytest.mark.asyncio
async def test_market_buy_api_error(trader, mock_client):
    """测试市价买入API错误"""
    error = BinanceAPIException(
        response=Mock(status_code=400, text="Internal server error"),
        status_code=400,
        text="Internal server error"
    )
    mock_client.create.return_value.create_order.side_effect = error
    result = await trader.market_buy('BTCUSDT', 1.0)
    assert result is None

@pytest.mark.asyncio
async def test_market_sell_success(trader, mock_client):
    """测试市价卖出成功"""
    result = await trader.market_sell('BTCUSDT', 1.0)
    assert result is not None
    assert result['symbol'] == 'BTCUSDT'
    assert result['status'] == 'FILLED'
    assert result['executedQty'] == '1.0'

@pytest.mark.asyncio
async def test_market_sell_api_error(trader, mock_client):
    """测试市价卖出API错误"""
    error = BinanceAPIException(
        response=Mock(status_code=400, text="Internal server error"),
        status_code=400,
        text="Internal server error"
    )
    mock_client.create.return_value.create_order.side_effect = error
    result = await trader.market_sell('BTCUSDT', 1.0)
    assert result is None

@pytest.mark.asyncio
async def test_get_symbol_price(trader, mock_client):
    """测试获取交易对价格"""
    # 第一次调用，从API获取价格
    price = await trader.get_symbol_price('BTCUSDT')
    assert price == 50000.0
    assert mock_client.create.return_value.get_symbol_ticker.call_count == 1
    
    # 第二次调用，应该从缓存获取价格
    price = await trader.get_symbol_price('BTCUSDT')
    assert price == 50000.0
    assert mock_client.create.return_value.get_symbol_ticker.call_count == 1  # 调用次数不变

@pytest.mark.asyncio
async def test_cleanup(trader, mock_client):
    """测试资源清理"""
    await trader.cleanup()
    assert trader.client is None
    mock_client.create.return_value.close_connection.assert_called_once()

@pytest.mark.asyncio
async def test_initialize_error(mock_client):
    """测试初始化错误"""
    mock_client.create.side_effect = Exception("Connection error")
    trader = BinanceTrader('test_key', 'test_secret', test_mode=True)
    with pytest.raises(Exception):
        await trader.initialize() 

@pytest.mark.asyncio
async def test_concurrent_price_queries(trader, mock_client):
    """测试并发价格查询"""
    # 创建多个并发任务
    tasks = [trader.get_symbol_price('BTCUSDT') for _ in range(10)]
    results = await asyncio.gather(*tasks)
    
    # 验证所有请求都成功
    assert all(price == 50000.0 for price in results)
    
    # 验证由于缓存机制，实际API调用次数应该小于请求次数
    assert mock_client.create.return_value.get_symbol_ticker.call_count < 10
    
    # 验证缓存命中率
    stats = trader.get_performance_stats()
    assert stats['cache_hit_rate'] > 0

@pytest.mark.asyncio
async def test_concurrent_orders(trader, mock_client):
    """测试并发订单执行"""
    # 创建多个并发订单
    tasks = [trader.market_buy('BTCUSDT', 1.0) for _ in range(5)]
    results = await asyncio.gather(*tasks)
    
    # 验证所有订单都成功执行
    assert all(order is not None for order in results)
    assert all(order['status'] == 'FILLED' for order in results)
    
    # 验证性能指标
    stats = trader.get_performance_stats()
    assert len(stats['order_execution_time']) == 5
    assert stats['avg_order_execution_time'] > 0

@pytest.mark.asyncio
async def test_performance_monitoring(trader, mock_client):
    """测试性能监控功能"""
    # 执行一些操作
    await trader.get_symbol_price('BTCUSDT')
    await trader.market_buy('BTCUSDT', 1.0)
    
    # 获取性能统计
    stats = trader.get_performance_stats()
    
    # 验证统计信息
    assert stats['price_query_count'] > 0
    assert stats['avg_api_latency'] >= 0
    assert stats['max_api_latency'] >= 0
    assert stats['error_rate'] >= 0
    assert 0 <= stats['cache_hit_rate'] <= 1

@pytest.mark.asyncio
async def test_error_handling_and_metrics(trader, mock_client):
    """测试错误处理和指标记录"""
    # 模拟API错误
    error = BinanceAPIException(
        response=Mock(status_code=500, text="Server error"),
        status_code=500,
        text="Server error"
    )
    mock_client.create.return_value.get_symbol_ticker.side_effect = error
    
    # 执行会失败的操作
    result = await trader.get_symbol_price('BTCUSDT')
    assert result is None
    
    # 验证错误计数
    stats = trader.get_performance_stats()
    assert stats['error_rate'] > 0
    assert trader.metrics['error_count'] > 0

@pytest.mark.asyncio
async def test_api_latency_warning(trader, mock_client, caplog):
    """测试API延迟警告"""
    # 模拟延迟响应
    async def delayed_response():
        await asyncio.sleep(1.1)  # 超过1秒的延迟
        return {'price': '50000.0'}
    
    mock_client.create.return_value.get_symbol_ticker.side_effect = delayed_response
    
    # 执行操作
    await trader.get_symbol_price('BTCUSDT')
    
    # 验证是否记录了警告日志
    assert any(record.levelname == 'WARNING' and 'API调用延迟过高' in record.message 
              for record in caplog.records)

@pytest.mark.asyncio
async def test_metrics_limit(trader, mock_client):
    """测试指标记录数量限制"""
    # 执行大量操作
    for _ in range(1100):  # 超过最大记录数
        await trader.get_symbol_price('BTCUSDT')
    
    # 验证指标列表长度不超过限制
    assert len(trader.metrics['api_latency']) <= trader.max_metrics_length 