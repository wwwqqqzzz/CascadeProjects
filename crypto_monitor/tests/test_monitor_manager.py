"""
测试 MonitorManager 的功能
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from ..utils.config import TRADING_CONFIG, LOGGING_CONFIG, BINANCE_CONFIG
from ..services.monitor.monitor_manager import MonitorManager
import asyncio

# 测试配置
TEST_CONFIG = {
    'target_user': '@0xENAS',  # 添加目标用户配置
    'keywords': ['buy', 'sell'],
    'max_trades_per_day': 10,
    'min_trade_interval': 300,
    'trade_amount': 1000
}

@pytest.fixture
async def monitor_manager():
    """创建 MonitorManager 实例"""
    # 创建 mock 对象
    mock_twitter_scraper = MagicMock()
    mock_twitter_scraper.get_user_tweets = AsyncMock()
    mock_twitter_scraper.cleanup = AsyncMock()
    
    mock_trading_manager = MagicMock()
    mock_trading_manager.process_tweet = AsyncMock()
    mock_trading_manager.start = AsyncMock()
    mock_trading_manager.stop = AsyncMock()
    
    # 使用 patch 替换依赖和配置
    with patch('crypto_monitor.services.monitor.monitor_manager.TradingManager', return_value=mock_trading_manager), \
         patch('crypto_monitor.services.monitor.monitor_manager.TwitterScraper', return_value=mock_twitter_scraper), \
         patch('crypto_monitor.services.monitor.monitor_manager.TRADING_CONFIG', TEST_CONFIG):
        
        manager = MonitorManager()
        manager.twitter_scraper = mock_twitter_scraper
        manager.trading_manager = mock_trading_manager
        
        try:
            yield manager
        finally:
            await manager.stop()

@pytest.mark.asyncio
async def test_monitor_manager_initialization(monitor_manager):
    """测试 MonitorManager 初始化"""
    async for manager in monitor_manager:
        assert not manager._running
        assert isinstance(manager.twitter_scraper, MagicMock)
        assert isinstance(manager.trading_manager, MagicMock)

@pytest.mark.asyncio
async def test_fetch_data_success(monitor_manager):
    """测试成功获取数据"""
    async for manager in monitor_manager:
        # 模拟推文数据
        mock_tweets = [
            {
                'url': 'https://twitter.com/user/123',
                'text': 'Test tweet 1',
                'timestamp': datetime.now().isoformat()
            },
            {
                'url': 'https://twitter.com/user/124',
                'text': 'Test tweet 2',
                'timestamp': datetime.now().isoformat()
            }
        ]
        
        manager.twitter_scraper.get_user_tweets.return_value = mock_tweets
        data = await manager._fetch_data()
        assert data is not None
        assert 'tweets' in data
        assert len(data['tweets']) == 2

@pytest.mark.asyncio
async def test_fetch_data_no_new_tweets(monitor_manager):
    """测试没有新推文的情况"""
    async for manager in monitor_manager:
        manager.last_tweet_id = '124'
        manager.twitter_scraper.get_user_tweets.return_value = []
        data = await manager._fetch_data()
        assert data is None

@pytest.mark.asyncio
async def test_process_data(monitor_manager):
    """测试数据处理"""
    async for manager in monitor_manager:
        # 模拟推文数据
        mock_data = {
            'tweets': [
                {
                    'url': 'https://twitter.com/user/125',
                    'text': 'Test tweet 3',
                    'timestamp': datetime.now().isoformat()
                }
            ]
        }
        
        await manager._process_data(mock_data)
        manager.trading_manager.process_tweet.assert_called_once_with(mock_data['tweets'][0])

@pytest.mark.asyncio
async def test_get_performance_stats(monitor_manager):
    """测试性能统计"""
    async for manager in monitor_manager:
        manager.performance_metrics['response_times'] = [0.1, 0.2, 0.3]
        manager.performance_metrics['processing_times'] = [0.05, 0.15, 0.25]
        manager.performance_metrics['success_count'] = 10
        manager.performance_metrics['error_count'] = 2
        
        stats = manager.get_performance_stats()
        assert abs(stats['avg_response_time'] - 0.2) < 0.0001  # 使用近似比较
        assert abs(stats['avg_processing_time'] - 0.15) < 0.0001
        assert abs(stats['success_rate'] - 0.833) < 0.001

@pytest.mark.asyncio
async def test_monitor_lifecycle(monitor_manager):
    """测试监控器的生命周期"""
    async for manager in monitor_manager:
        # Mock 相关方法
        manager._fetch_data = AsyncMock(return_value=None)
        manager._process_data = AsyncMock()
        
        # 测试启动
        await manager.start()
        assert manager._running == True
        assert manager.trading_manager.start.called
        assert manager._monitor_task is not None
        assert not manager._monitor_task.done()
        
        # 等待一小段时间让循环运行
        await asyncio.sleep(0.1)
        
        # 测试停止
        await manager.stop()
        assert manager._running == False
        assert manager.trading_manager.stop.called
        assert manager.twitter_scraper.cleanup.called
        assert manager._monitor_task is None 