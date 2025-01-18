"""
性能监控模块的单元测试
"""

import pytest
import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from crypto_monitor.services.monitor.performance_monitor import PerformanceMonitor

@pytest.fixture
def monitor():
    """创建性能监控器实例"""
    monitor = PerformanceMonitor(data_dir="test_data/performance")
    return monitor

@pytest.mark.asyncio
async def test_monitor_lifecycle(monitor):
    """测试监控器的生命周期管理"""
    # 启动监控
    await monitor.start()
    assert monitor._save_task is not None
    
    # 停止监控
    await monitor.stop()
    assert monitor._save_task is None

def test_cache_ttl_calculation(monitor):
    """测试缓存时间动态计算"""
    # 记录一些价格数据
    symbol = 'BTCUSDT'
    prices = [50000.0, 50100.0, 50200.0, 50150.0, 50050.0]
    for price in prices:
        monitor.record_price_volatility(symbol, price)
    
    # 计算缓存时间
    ttl = monitor.calculate_cache_ttl(symbol)
    assert monitor.cache_config['min_ttl'] <= ttl <= monitor.cache_config['max_ttl']
    
    # 没有价格数据时应返回基础缓存时间
    ttl = monitor.calculate_cache_ttl('ETHUSDT')
    assert ttl == monitor.cache_config['base_ttl']

def test_performance_metrics_recording(monitor):
    """测试性能指标记录"""
    # 记录API延迟
    monitor.record_api_latency('test_operation', 0.5)
    assert len(monitor.metrics['api_latency']) == 1
    assert monitor.metrics['api_latency'][0]['operation'] == 'test_operation'
    
    # 记录高延迟警告
    monitor.record_api_latency('slow_operation', 1.5)
    assert monitor.metrics['warning_count'] == 1
    
    # 记录错误
    monitor.record_error('TestError', 'Test error message')
    assert monitor.metrics['error_count'] == 1
    
    # 记录执行时间
    monitor.record_execution_time('test_operation', 0.3)
    assert len(monitor.metrics['execution_time']) == 1

@pytest.mark.asyncio
async def test_metrics_persistence(monitor, tmp_path):
    """测试指标持久化"""
    # 设置临时数据目录
    monitor.data_dir = tmp_path / "performance"
    monitor.data_dir.mkdir(parents=True)
    
    # 记录一些数据
    monitor.record_api_latency('test', 0.5)
    monitor.record_error('TestError', 'Test error')
    
    # 保存指标
    await monitor.save_metrics()
    
    # 验证文件是否创建
    files = list(monitor.data_dir.glob("metrics_*.json"))
    assert len(files) == 1
    
    # 验证文件内容
    with open(files[0], 'r', encoding='utf-8') as f:
        data = json.load(f)
        assert len(data['api_latency']) == 1
        assert data['error_count'] == 1

@pytest.mark.asyncio
async def test_old_files_cleanup(monitor, tmp_path):
    """测试旧文件清理"""
    # 设置临时数据目录
    monitor.data_dir = tmp_path / "performance"
    monitor.data_dir.mkdir(parents=True)
    
    # 创建一些测试文件
    old_date = datetime.now() - timedelta(days=10)
    recent_date = datetime.now()
    
    # 创建旧文件
    old_file = monitor.data_dir / f"metrics_{old_date.strftime('%Y%m%d_%H%M%S')}.json"
    old_file.write_text("{}")
    
    # 创建新文件
    recent_file = monitor.data_dir / f"metrics_{recent_date.strftime('%Y%m%d_%H%M%S')}.json"
    recent_file.write_text("{}")
    
    # 执行清理
    await monitor._cleanup_old_files(max_age_days=7)
    
    # 验证结果
    files = list(monitor.data_dir.glob("metrics_*.json"))
    assert len(files) == 1
    assert old_file.name not in [f.name for f in files]
    assert recent_file.name in [f.name for f in files]

def test_performance_stats_calculation(monitor):
    """测试性能统计计算"""
    # 记录一些测试数据
    monitor.record_api_latency('op1', 0.5)
    monitor.record_api_latency('op2', 1.5)
    monitor.record_error('TestError', 'Test error')
    
    # 获取统计信息
    stats = monitor.get_performance_stats()
    
    # 验证统计结果
    assert stats['avg_latency'] == 1.0  # (0.5 + 1.5) / 2
    assert stats['max_latency'] == 1.5
    assert stats['error_rate'] == 0.5  # 1 error / 2 calls
    assert stats['warning_rate'] == 0.5  # 1 warning (from high latency) / 2 calls
    assert stats['total_calls'] == 2

@pytest.mark.asyncio
async def test_auto_save(monitor, tmp_path):
    """测试自动保存功能"""
    # 设置较短的保存间隔用于测试
    monitor._save_interval = 0.1  # 100ms
    monitor.data_dir = tmp_path / "performance"
    monitor.data_dir.mkdir(parents=True)
    
    # 启动监控
    await monitor.start()
    
    # 记录一些数据
    monitor.record_api_latency('test', 0.5)
    
    # 等待自动保存
    await asyncio.sleep(0.2)
    
    # 停止监控
    await monitor.stop()
    
    # 验证文件是否创建
    files = list(monitor.data_dir.glob("metrics_*.json"))
    assert len(files) > 0 