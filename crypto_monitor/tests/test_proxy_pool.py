"""Unit tests for proxy pool."""
import os
import sys
import unittest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from proxy_pool import ProxyPool, ProxyStats
from proxy_source_manager import ProxyValidationResult

def async_test(coro):
    """Decorator for running async tests."""
    def wrapper(*args, **kwargs):
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(coro(*args, **kwargs))
    return wrapper

class TestProxyPool(unittest.TestCase):
    """Test cases for ProxyPool class."""
    
    def setUp(self):
        """Set up test environment."""
        self.pool = ProxyPool()
        
    def test_proxy_stats_health_score(self):
        """Test health score calculation."""
        stats = ProxyStats()
        
        # Test perfect health
        stats.success_window.extend([1] * 10)
        stats.response_times.extend([0.5] * 10)
        stats.total_requests = 10
        stats.successful_requests = 10
        self.assertGreater(stats.calculate_health_score(), 0.7)
        
        # Test poor health
        stats = ProxyStats()
        stats.success_window.extend([0] * 10)
        stats.response_times.extend([5.0] * 10)
        stats.total_requests = 10
        stats.failure_types['timeout'] = 5
        stats.failure_types['connection_error'] = 3
        stats.consecutive_failures = 3
        self.assertLess(stats.calculate_health_score(), 0.2)
        
    @async_test
    async def test_refresh_proxy_pool(self):
        """Test proxy pool refresh."""
        # Mock validated proxies
        mock_proxies = [
            {'server': '1.2.3.4:8080', 'protocol': 'http'},
            {'server': '5.6.7.8:8080', 'protocol': 'http'}
        ]
        
        with patch('proxy_source_manager.ProxySourceManager.get_validated_proxies',
                  return_value=mock_proxies):
            await self.pool.refresh_proxy_pool()
            self.assertEqual(len(self.pool.proxies), 2)
        
    @async_test
    async def test_proxy_banning(self):
        """Test proxy banning mechanism."""
        proxy_id = 'test_proxy'
        proxy_info = {'server': '1.2.3.4:8080', 'protocol': 'http'}
        
        await self.pool.add_proxy(proxy_id, proxy_info)
        
        # Simulate consecutive failures
        for _ in range(5):
            await self.pool.update_proxy_status(
                proxy_id,
                success=False,
                response_time=10.0,
                failure_type='timeout'
            )
            
        self.assertIn(proxy_id, self.pool.banned_proxies)
        
    @async_test
    async def test_get_proxy(self):
        """Test proxy selection."""
        # Add test proxies
        proxies = [
            ('proxy1', {'server': '1.2.3.4:8080', 'protocol': 'http'}),
            ('proxy2', {'server': '5.6.7.8:8080', 'protocol': 'http'})
        ]
        
        for proxy_id, info in proxies:
            await self.pool.add_proxy(proxy_id, info)
            
        # Update stats for different health scores
        await self.pool.update_proxy_status('proxy1', True, 0.5)
        await self.pool.update_proxy_status('proxy2', True, 1.0)
        
        # Get proxy and verify it's the better performing one
        proxy = await self.pool.get_proxy()
        self.assertIsNotNone(proxy)
        self.assertEqual(proxy['proxy_address'], '1.2.3.4')
        
    @async_test
    async def test_remove_poor_performing_proxies(self):
        """Test removal of poor performing proxies."""
        proxy_id = 'poor_proxy'
        proxy_info = {'server': '1.2.3.4:8080', 'protocol': 'http'}
        
        await self.pool.add_proxy(proxy_id, proxy_info)
        
        # Simulate poor performance
        stats = self.pool.proxy_stats[proxy_id]
        stats.total_requests = 20
        stats.success_window.extend([0] * 10)
        stats.response_times.extend([10.0] * 10)
        stats.failure_types['timeout'] = 8
        stats.failure_types['connection_error'] = 2
        
        await self.pool._remove_poor_performing_proxies()
        self.assertNotIn(proxy_id, self.pool.proxies)
        
    @async_test
    async def test_pool_stats(self):
        """Test pool statistics calculation."""
        # Add test proxies with different performance profiles
        proxies = [
            ('proxy1', {'server': '1.2.3.4:8080', 'protocol': 'http'}),
            ('proxy2', {'server': '5.6.7.8:8080', 'protocol': 'http'})
        ]
        
        for proxy_id, info in proxies:
            await self.pool.add_proxy(proxy_id, info)
            
        # Update stats
        await self.pool.update_proxy_status('proxy1', True, 0.5)
        await self.pool.update_proxy_status('proxy2', False, 5.0)
        
        stats = await self.pool.get_pool_stats()
        self.assertEqual(stats['total_proxies'], 2)
        self.assertEqual(stats['available_proxies'], 2)
        self.assertGreater(stats['average_health_score'], 0)
        
    def test_health_distribution(self):
        """Test health score distribution calculation."""
        # 添加不同状态的代理
        test_cases = [
            ('excellent', 0.9),  # 优
            ('good', 0.7),      # 良
            ('fair', 0.5),      # 一般
            ('poor', 0.3),      # 差
            ('critical', 0.1)   # 危险
        ]
        
        for category, score in test_cases:
            proxy_id = f'proxy_{category}'
            self.pool.proxies[proxy_id] = {}  # 添加代理到代理池
            self.pool.proxy_stats[proxy_id] = ProxyStats()
            stats = self.pool.proxy_stats[proxy_id]
            
            # 模拟不同的健康状况
            success_rate = 1.0 if score > 0.8 else score
            stats.success_window.extend([1] * int(10 * success_rate) + [0] * int(10 * (1 - success_rate)))
            stats.response_times.extend([0.5 if score > 0.8 else 5.0 - score * 4] * 10)
            stats.total_requests = 10
            
        distribution = self.pool._get_health_distribution()
        
        # 打印调试信息
        for proxy_id in self.pool.proxies:
            stats = self.pool.proxy_stats[proxy_id]
            print(f"Proxy {proxy_id}:")
            print(f"  Success rate: {stats.success_rate}")
            print(f"  Avg response time: {stats.average_response_time}")
            print(f"  Health score: {stats.calculate_health_score()}")
            
        print(f"Distribution: {distribution}")
        
        # 验证每个类别都有一个代理
        self.assertEqual(distribution['excellent'], 1)
        self.assertEqual(distribution['good'], 1)
        self.assertEqual(distribution['fair'], 1)
        self.assertEqual(distribution['poor'], 1)
        self.assertEqual(distribution['critical'], 1)
        
    def test_response_time_percentiles(self):
        """Test response time percentiles calculation."""
        # 创建一个代理并添加各种响应时间
        proxy_id = 'test_proxy'
        self.pool.proxy_stats[proxy_id] = ProxyStats()
        stats = self.pool.proxy_stats[proxy_id]
        
        # 添加一系列响应时间：0.1s到1.0s
        response_times = [i/10 for i in range(1, 11)]
        stats.response_times.extend(response_times)
        
        percentiles = self.pool._get_response_time_percentiles()
        
        # 验证百分位数
        self.assertAlmostEqual(percentiles['p50'], 0.5, places=1)
        self.assertAlmostEqual(percentiles['p75'], 0.8, places=1)
        self.assertAlmostEqual(percentiles['p90'], 0.9, places=1)
        self.assertAlmostEqual(percentiles['p95'], 1.0, places=1)
        self.assertAlmostEqual(percentiles['p99'], 1.0, places=1)
        
    def test_failure_distribution(self):
        """Test failure type distribution calculation."""
        proxy_id = 'test_proxy'
        self.pool.proxy_stats[proxy_id] = ProxyStats()
        stats = self.pool.proxy_stats[proxy_id]
        
        # 模拟各种类型的失败
        failure_counts = {
            'timeout': 5,
            'connection_error': 3,
            'http_error': 2,
            'other': 1
        }
        
        for failure_type, count in failure_counts.items():
            stats.failure_types[failure_type] = count
            
        distribution = self.pool._get_failure_distribution()
        
        # 验证总数
        self.assertEqual(distribution['total']['timeout'], 5)
        self.assertEqual(distribution['total']['connection_error'], 3)
        self.assertEqual(distribution['total']['http_error'], 2)
        self.assertEqual(distribution['total']['other'], 1)
        
        # 验证平均值（只有一个代理，所以平均值等于总数）
        self.assertEqual(distribution['per_proxy_avg']['timeout'], 5)
        self.assertEqual(distribution['per_proxy_avg']['connection_error'], 3)
        
    @async_test
    async def test_detailed_metrics(self):
        """Test detailed metrics collection."""
        # 添加测试代理
        proxy_id = 'test_proxy'
        proxy_info = {'server': '1.2.3.4:8080', 'protocol': 'http'}
        await self.pool.add_proxy(proxy_id, proxy_info)
        
        # 更新代理状态
        stats = self.pool.proxy_stats[proxy_id]
        stats.success_window.extend([1, 1, 1, 0, 1])  # 80% 成功率
        stats.response_times.extend([0.5, 0.6, 0.4, 0.5, 0.5])
        stats.total_requests = 5
        stats.successful_requests = 4
        stats.last_success = datetime.now()
        
        metrics = await self.pool.get_detailed_metrics()
        
        # 验证指标结构
        self.assertIn('base_stats', metrics)
        self.assertIn('health_distribution', metrics)
        self.assertIn('response_time_percentiles', metrics)
        self.assertIn('failure_distribution', metrics)
        self.assertIn('proxy_details', metrics)
        
        # 验证代理详情
        proxy_detail = metrics['proxy_details'][0]
        self.assertEqual(proxy_detail['proxy_id'], proxy_id)
        self.assertGreater(proxy_detail['health_score'], 0.7)
        self.assertEqual(proxy_detail['total_requests'], 5)
        
    @async_test
    async def test_anomaly_detection(self):
        """Test anomaly detection."""
        proxy_id = 'test_proxy'
        self.pool.proxy_stats[proxy_id] = ProxyStats()
        stats = self.pool.proxy_stats[proxy_id]
        
        # 模拟异常情况
        stats.consecutive_failures = 5
        stats.response_times.extend([6.0] * 10)
        stats.success_window.extend([0] * 10)
        stats.total_requests = 10
        
        anomalies = self.pool._detect_anomalies()
        
        # 验证检测到的异常
        self.assertTrue(any(a['type'] == 'consecutive_failures' and a['severity'] == 'high' 
                          for a in anomalies))
        self.assertTrue(any(a['type'] == 'high_latency' for a in anomalies))
        self.assertTrue(any(a['type'] == 'low_success_rate' for a in anomalies))
        
    @async_test
    async def test_health_report(self):
        """Test health report generation."""
        # 添加一些测试代理
        proxies = [
            ('good_proxy', {'server': '1.2.3.4:8080', 'protocol': 'http'}),
            ('bad_proxy', {'server': '5.6.7.8:8080', 'protocol': 'http'})
        ]
        
        for proxy_id, info in proxies:
            await self.pool.add_proxy(proxy_id, info)
            
        # 设置一个好代理的状态
        good_stats = self.pool.proxy_stats['good_proxy']
        good_stats.success_window.extend([1] * 10)
        good_stats.response_times.extend([0.5] * 10)
        good_stats.total_requests = 10
        good_stats.successful_requests = 10
        good_stats.last_success = datetime.now()
        
        # 设置一个差代理的状态
        bad_stats = self.pool.proxy_stats['bad_proxy']
        bad_stats.success_window.extend([0] * 10)
        bad_stats.response_times.extend([6.0] * 10)
        bad_stats.total_requests = 10
        bad_stats.consecutive_failures = 5
        bad_stats.last_failure = datetime.now()
        
        report = await self.pool.generate_health_report()
        
        # 验证报告结构
        self.assertIn('timestamp', report)
        self.assertIn('metrics', report)
        self.assertIn('anomalies', report)
        self.assertIn('performance_trends', report)
        self.assertIn('recommendations', report)
        self.assertIn('summary', report)
        
        # 验证是否有相关建议
        self.assertTrue(any(r['type'] == 'critical_proxies' for r in report['recommendations']))
        self.assertTrue(any(r['type'] == 'high_latency' for r in report['recommendations']))
        
        # 验证性能趋势
        trends = report['performance_trends']
        self.assertIn('health_scores', trends)
        self.assertIn('success_rates', trends)
        self.assertIn('response_times', trends)
        self.assertIn('active_proxies', trends)

if __name__ == '__main__':
    unittest.main()
