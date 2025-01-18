import pytest
import asyncio
from datetime import datetime, timedelta
from crypto_monitor.infrastructure.proxy.proxy_manager import ProxyManager, ProxyScore

@pytest.fixture
def proxy_manager():
    """创建代理管理器实例"""
    return ProxyManager()

@pytest.fixture
def proxy_score():
    """创建代理评分实例"""
    return ProxyScore()

def test_proxy_score_initialization(proxy_score):
    """测试代理评分初始化"""
    assert proxy_score.success_count == 0
    assert proxy_score.fail_count == 0
    assert proxy_score.avg_response_time == 0.0
    assert proxy_score.last_success is None
    assert proxy_score.last_used is None
    assert proxy_score.consecutive_failures == 0
    assert proxy_score.total_uptime == 0.0
    assert proxy_score.location_score == 1.0
    assert proxy_score.stability_score == 1.0

def test_proxy_score_update(proxy_score):
    """测试代理评分更新"""
    # 测试成功更新
    proxy_score.update_success(0.5)
    assert proxy_score.success_count == 1
    assert proxy_score.avg_response_time == 0.5
    assert proxy_score.last_success is not None
    assert proxy_score.last_used is not None
    assert proxy_score.consecutive_failures == 0

    # 测试失败更新
    proxy_score.update_failure()
    assert proxy_score.fail_count == 1
    assert proxy_score.consecutive_failures == 1

    # 测试连续失败
    proxy_score.update_failure()
    assert proxy_score.consecutive_failures == 2
    
    # 测试成功重置连续失败
    proxy_score.update_success(0.3)
    assert proxy_score.consecutive_failures == 0

def test_proxy_score_location(proxy_score):
    """测试地理位置评分"""
    # 测试高优先级地区
    proxy_score.set_location_score('US')
    assert proxy_score.location_score == 1.0
    
    proxy_score.set_location_score('GB')
    assert proxy_score.location_score == 0.9
    
    # 测试中等优先级地区
    proxy_score.set_location_score('SG')
    assert proxy_score.location_score == 0.8
    
    # 测试未知地区
    proxy_score.set_location_score('XX')
    assert proxy_score.location_score == 0.6

def test_proxy_score_stability(proxy_score):
    """测试稳定性评分"""
    # 初始状态（没有任何请求记录）
    proxy_score.update_stability_score()
    initial_stability = proxy_score.stability_score
    assert initial_stability == 0.0  # 初始状态应该是0分
    
    # 添加一些成功记录
    for _ in range(5):
        proxy_score.update_success(0.5)
    
    # 验证稳定性提高
    proxy_score.update_stability_score()
    mid_stability = proxy_score.stability_score
    assert mid_stability > initial_stability
    assert 0 <= mid_stability <= 1.0  # 确保分数在有效范围内
    
    # 添加一些失败记录
    for _ in range(3):
        proxy_score.update_failure()
    
    # 验证稳定性降低
    proxy_score.update_stability_score()
    final_stability = proxy_score.stability_score
    assert final_stability < mid_stability
    assert 0 <= final_stability <= 1.0  # 确保分数在有效范围内

def test_proxy_score_calculation(proxy_score):
    """测试综合评分计算"""
    # 设置一些基础数据
    proxy_score.set_location_score('US')  # 最高地理位置分
    proxy_score.update_success(0.5)  # 添加一次成功
    
    # 获取初始评分
    initial_score = proxy_score.score
    
    # 添加更多成功记录
    for _ in range(4):
        proxy_score.update_success(0.3)
    
    # 验证评分提高
    assert proxy_score.score > initial_score
    
    # 添加一些失败记录
    for _ in range(2):
        proxy_score.update_failure()
    
    # 验证评分降低
    assert proxy_score.score < initial_score

@pytest.mark.asyncio
async def test_proxy_manager_initialization(proxy_manager):
    """测试代理管理器初始化"""
    stats = proxy_manager.get_proxy_stats()
    assert isinstance(stats, dict)
    assert 'total_proxies' in stats
    assert 'active_proxies' in stats
    assert 'working_proxies' in stats
    assert 'average_score' in stats
    assert 'top_proxies' in stats
    assert 'failed_proxies' in stats

@pytest.mark.asyncio
async def test_proxy_manager_get_proxy(proxy_manager):
    """测试获取代理"""
    proxy = await proxy_manager.get_proxy()
    if proxy is not None:  # 如果成功获取代理
        assert isinstance(proxy, dict)
        assert 'host' in proxy
        assert 'port' in proxy

@pytest.mark.asyncio
async def test_proxy_testing(proxy_manager):
    """测试代理测试功能"""
    # 创建测试代理
    test_proxy = {
        'host': 'example.com',
        'port': '8080',
        'username': 'test',
        'password': 'test'
    }
    
    # 测试代理
    success, response_time = await proxy_manager.test_proxy(
        test_proxy,
        test_url="http://httpbin.org/ip"
    )
    
    # 验证返回值类型
    assert isinstance(success, bool)
    assert isinstance(response_time, float)

@pytest.mark.asyncio
async def test_proxy_score_management(proxy_manager):
    """测试代理评分管理"""
    test_proxy = {
        'host': 'example.com',
        'port': '8080'
    }
    
    # 测试更新代理分数
    await proxy_manager.update_proxy_score(test_proxy, True, 0.5)
    await proxy_manager.update_proxy_score(test_proxy, False, 0)
    
    # 测试标记代理失败
    await proxy_manager.mark_proxy_failed(test_proxy)

@pytest.mark.asyncio
async def test_proxy_cache(proxy_manager):
    """测试代理缓存机制"""
    # 获取初始统计信息
    initial_stats = proxy_manager.get_proxy_stats()
    
    # 触发更新
    await proxy_manager._update_if_needed()
    
    # 获取更新后的统计信息
    updated_stats = proxy_manager.get_proxy_stats()
    
    # 验证统计信息是否更新
    assert isinstance(updated_stats, dict) 

@pytest.mark.asyncio
async def test_proxy_rotation(proxy_manager):
    """测试代理轮转功能"""
    # 添加测试代理
    test_proxies = [
        {
            'host': 'proxy1.example.com',
            'port': '8080',
            'country_code': 'US'
        },
        {
            'host': 'proxy2.example.com',
            'port': '8080',
            'country_code': 'GB'
        },
        {
            'host': 'proxy3.example.com',
            'port': '8080',
            'country_code': 'JP'
        }
    ]
    
    for proxy in test_proxies:
        proxy_url = f"{proxy['host']}:{proxy['port']}"
        proxy_manager.proxies[proxy_url] = proxy
        proxy_manager.scores[proxy_url] = ProxyScore()
        # 设置不同的评分
        proxy_manager.scores[proxy_url].update_success(0.5)
        
    # 测试基本代理获取
    proxy = await proxy_manager.get_proxy(test_mode=True)
    assert proxy is not None
    assert isinstance(proxy, dict)
    assert 'host' in proxy
    assert 'port' in proxy
    
    # 测试按国家获取代理
    uk_proxy = await proxy_manager.get_proxy(country_code='GB', test_mode=True)
    assert uk_proxy is not None
    assert uk_proxy['country_code'] == 'GB'
    
    # 测试最低评分要求
    high_score_proxy = await proxy_manager.get_proxy(min_score=0.9, test_mode=True)
    assert high_score_proxy is None  # 应该没有代理满足这个高评分要求
    
    # 测试并发限制
    proxies = []
    for _ in range(6):  # 尝试获取6个代理（超过最大并发数5）
        proxy = await proxy_manager.get_proxy(test_mode=True)
        if proxy is not None:
            proxies.append(proxy)
    assert len(proxies) <= 5  # 不应该超过最大并发数
    
    # 测试代理释放
    for proxy in proxies:
        await proxy_manager.release_proxy(proxy)
        
    # 验证统计信息
    rotation_stats = proxy_manager.get_rotation_stats()
    assert isinstance(rotation_stats, dict)
    assert 'total_rotations' in rotation_stats
    assert 'active_proxies' in rotation_stats
    assert rotation_stats['active_proxies'] == 0  # 所有代理都已释放
    
    # 验证每个代理的并发使用数
    for proxy_url in proxy_manager.proxies:
        assert proxy_url not in proxy_manager.concurrent_uses or proxy_manager.concurrent_uses[proxy_url] == 0
        if proxy_url in proxy_manager.rotation_stats:
            assert proxy_manager.rotation_stats[proxy_url]['current_uses'] == 0
                
    # 验证所有代理的轮转统计
    for proxy_stats in rotation_stats['proxy_stats']:
        assert proxy_stats['current_uses'] == 0
            
    # 验证并发使用数字典是否为空
    assert len(proxy_manager.concurrent_uses) == 0

@pytest.mark.asyncio
async def test_proxy_weight_calculation(proxy_manager):
    """测试代理权重计算"""
    # 创建测试代理
    proxy_url = "test.proxy.com:8080"
    score = ProxyScore()
    score.update_success(0.5)  # 设置一个中等评分
    
    # 计算初始权重
    initial_weight = proxy_manager._calculate_rotation_weight(proxy_url, score)
    assert 0 <= initial_weight <= 1.0
    
    # 模拟使用代理
    proxy_manager._update_rotation_stats(proxy_url)
    
    # 计算使用后的权重（应该降低）
    used_weight = proxy_manager._calculate_rotation_weight(proxy_url, score)
    assert used_weight < initial_weight
    
    # 等待一段时间
    await asyncio.sleep(0.1)
    
    # 计算等待后的权重（应该略有提升）
    waited_weight = proxy_manager._calculate_rotation_weight(proxy_url, score)
    assert waited_weight > used_weight
    
@pytest.mark.asyncio
async def test_rotation_stats_update(proxy_manager):
    """测试轮转统计更新"""
    proxy_url = "test.proxy.com:8080"
    proxy = {
        'host': 'test.proxy.com',
        'port': '8080'
    }
    
    # 添加代理到代理池
    proxy_manager.proxies[proxy_url] = proxy
    proxy_manager.scores[proxy_url] = ProxyScore()
    
    # 获取代理（这会更新并发使用数）
    await proxy_manager.get_proxy(test_mode=True)
    
    # 验证统计信息
    stats = proxy_manager.get_rotation_stats()
    proxy_stats = next((p for p in stats['proxy_stats'] if p['server'] == proxy_url), None)
    
    assert proxy_stats is not None
    assert proxy_stats['total_uses'] == 1
    assert proxy_stats['last_hour_uses'] == 1
    assert proxy_stats['current_uses'] == 1
    
    # 释放代理
    await proxy_manager.release_proxy(proxy)
    
    # 再次验证统计信息
    stats = proxy_manager.get_rotation_stats()
    proxy_stats = next((p for p in stats['proxy_stats'] if p['server'] == proxy_url), None)
    
    assert proxy_stats is not None
    assert proxy_stats['total_uses'] == 1
    assert proxy_stats['last_hour_uses'] == 1
    assert proxy_stats['current_uses'] == 0 

@pytest.mark.asyncio
async def test_proxy_cleanup(proxy_manager):
    """测试代理清理功能"""
    # 添加测试代理
    test_proxies = [
        {
            'host': 'proxy1.example.com',
            'port': '8080',
            'country_code': 'US'
        },
        {
            'host': 'proxy2.example.com',
            'port': '8080',
            'country_code': 'GB'
        }
    ]
    
    for proxy in test_proxies:
        proxy_url = f"{proxy['host']}:{proxy['port']}"
        proxy_manager.proxies[proxy_url] = proxy
        proxy_manager.scores[proxy_url] = ProxyScore()
        
    # 测试释放空代理
    await proxy_manager.release_proxy(None)
    await proxy_manager.release_proxy({})
    
    # 测试释放无效代理
    await proxy_manager.release_proxy({'host': 'invalid.proxy.com', 'port': '1234'})
    
    # 测试连续释放同一个代理
    proxy = test_proxies[0]
    for _ in range(3):
        await proxy_manager.release_proxy(proxy)
        
    # 验证状态
    stats = proxy_manager.get_rotation_stats()
    assert stats['active_proxies'] == 0
    
    # 验证清理后的状态
    assert len(proxy_manager.concurrent_uses) == 0
    for proxy_stats in stats['proxy_stats']:
        assert proxy_stats['current_uses'] == 0

@pytest.mark.asyncio
async def test_proxy_stats_consistency(proxy_manager):
    """测试代理统计信息的一致性"""
    # 添加测试代理
    proxy = {
        'host': 'test.proxy.com',
        'port': '8080'
    }
    proxy_url = f"{proxy['host']}:{proxy['port']}"
    
    # 添加代理到代理池
    proxy_manager.proxies[proxy_url] = proxy
    proxy_manager.scores[proxy_url] = ProxyScore()
    
    # 获取代理多次
    for _ in range(3):
        await proxy_manager.get_proxy(test_mode=True)
        
    # 验证统计信息
    stats = proxy_manager.get_rotation_stats()
    proxy_stats = next((p for p in stats['proxy_stats'] if p['server'] == proxy_url), None)
    
    assert proxy_stats is not None
    assert proxy_stats['total_uses'] == 3
    assert proxy_stats['current_uses'] == 3
    
    # 释放代理
    for _ in range(3):
        await proxy_manager.release_proxy(proxy)
        
    # 再次验证统计信息
    stats = proxy_manager.get_rotation_stats()
    proxy_stats = next((p for p in stats['proxy_stats'] if p['server'] == proxy_url), None)
    
    assert proxy_stats is not None
    assert proxy_stats['total_uses'] == 3  # 总使用次数不变
    assert proxy_stats['current_uses'] == 0  # 当前使用数为0 