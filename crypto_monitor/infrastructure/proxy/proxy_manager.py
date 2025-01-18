"""
Proxy pool manager for handling multiple proxies.
Supports Webshare.io proxy integration and proxy scoring.
"""

import random
import logging
import asyncio
from typing import List, Dict, Optional, Tuple, Any
import aiohttp
from datetime import datetime, timedelta
import json
from pathlib import Path
import os
from dotenv import load_dotenv
import time
import ssl
from aiohttp_socks import ProxyConnector, ProxyType

from crypto_monitor.utils.config import LOGGING_CONFIG

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format=LOGGING_CONFIG['formatters']['detailed']['format']
)
logger = logging.getLogger('ProxyManager')

class ProxyScore:
    def __init__(self):
        self.success_count = 0
        self.fail_count = 0
        self.avg_response_time = 0.0
        self.last_success = None
        self.last_used = None
        self.consecutive_failures = 0  # 连续失败次数
        self.total_uptime = 0.0  # 总在线时间（小时）
        self.location_score = 1.0  # 地理位置评分（默认1.0）
        self.stability_score = 1.0  # 稳定性评分
        
    def update_success(self, response_time: float):
        """更新代理成功使用的统计信息"""
        self.success_count += 1
        self.consecutive_failures = 0  # 重置连续失败计数
        
        # 更新时间相关统计
        current_time = datetime.now()
        if self.last_success:
            # 计算在线时间
            time_diff = (current_time - self.last_success).total_seconds() / 3600
            self.total_uptime += time_diff
            
        self.last_success = current_time
        self.last_used = current_time
        
        # 更新响应时间（使用指数移动平均）
        alpha = 0.2  # 平滑因子
        if self.avg_response_time == 0:
            self.avg_response_time = response_time
        else:
            self.avg_response_time = (1 - alpha) * self.avg_response_time + alpha * response_time
            
        # 更新稳定性评分
        self.update_stability_score()
            
    def update_failure(self):
        """更新代理失败使用的统计信息"""
        self.fail_count += 1
        self.consecutive_failures += 1
        self.last_used = datetime.now()
        
        # 更新稳定性评分
        self.update_stability_score()
        
    def update_stability_score(self):
        """更新稳定性评分"""
        # 基于连续失败次数的惩罚（每次失败降低20%）
        failure_penalty = max(0, 1 - (self.consecutive_failures * 0.2))
        
        # 基于总体成功率的评分
        total_requests = self.success_count + self.fail_count
        success_rate = self.success_count / total_requests if total_requests > 0 else 0
        
        # 基于使用时长的加权（最多1天的奖励）
        uptime_bonus = min(1.0, self.total_uptime / 24)
        
        # 计算基础稳定性分数
        base_stability = (failure_penalty * 0.4 + 
                        success_rate * 0.4 + 
                        uptime_bonus * 0.2)
        
        # 如果有连续失败，显著降低稳定性分数
        if self.consecutive_failures > 0:
            base_stability *= max(0.1, 1 - (self.consecutive_failures * 0.25))
            
        # 如果总请求次数较少，降低稳定性分数
        if total_requests < 10:
            base_stability *= (total_requests / 10)
            
        self.stability_score = base_stability
        
    def set_location_score(self, country_code: str):
        """设置地理位置评分
        
        Args:
            country_code: 国家代码（如：US, GB, JP等）
        """
        # 根据不同地区设置评分
        location_scores = {
            'US': 1.0,  # 美国
            'GB': 0.9,  # 英国
            'JP': 0.9,  # 日本
            'DE': 0.9,  # 德国
            'FR': 0.9,  # 法国
            'CA': 0.9,  # 加拿大
            'AU': 0.8,  # 澳大利亚
            'SG': 0.8,  # 新加坡
            'KR': 0.8,  # 韩国
            'HK': 0.8,  # 香港
        }
        self.location_score = location_scores.get(country_code, 0.6)
        
    @property
    def success_rate(self) -> float:
        """计算成功率"""
        total = self.success_count + self.fail_count
        return self.success_count / total if total > 0 else 0
        
    @property
    def score(self) -> float:
        """计算综合评分
        
        评分维度：
        1. 成功率 (25%)
        2. 响应时间 (20%)
        3. 最近使用时间 (15%)
        4. 稳定性 (25%)
        5. 地理位置 (15%)
        """
        # 成功率评分 (0-1)
        success_score = self.success_rate
        
        # 响应时间评分 (0-1, 越快越好)
        response_score = 1.0
        if self.avg_response_time > 0:
            # 假设超过5秒就是很差的响应时间
            response_score = max(0, 1 - (self.avg_response_time / 5.0))
            
        # 最近使用时间评分 (0-1, 越近越好)
        recency_score = 0.0
        if self.last_success:
            hours_ago = (datetime.now() - self.last_success).total_seconds() / 3600
            # 24小时内使用过的代理获得较高分数
            recency_score = max(0, 1 - (hours_ago / 24))
            
        # 计算加权平均分
        weights = {
            'success': 0.25,
            'response': 0.20,
            'recency': 0.15,
            'stability': 0.25,
            'location': 0.15
        }
        
        final_score = (
            success_score * weights['success'] +
            response_score * weights['response'] +
            recency_score * weights['recency'] +
            self.stability_score * weights['stability'] +
            self.location_score * weights['location']
        )
        
        # 对连续失败进行惩罚
        if self.consecutive_failures > 0:
            penalty = max(0.1, 1 - (self.consecutive_failures * 0.3))
            final_score *= penalty
            
        return max(0, min(1, final_score))  # 确保分数在0-1之间

class ProxyManager:
    def __init__(self):
        """Initialize proxy manager."""
        self.proxies: Dict[str, Dict] = {}  # proxy_url -> proxy_config
        self.scores: Dict[str, ProxyScore] = {}  # proxy_url -> score
        self.last_update = None
        self.update_interval = timedelta(hours=1)
        
        # 轮转相关属性
        self.rotation_stats: Dict[str, Dict] = {}  # 代理轮转统计
        self.last_rotation: Dict[str, datetime] = {}  # 上次轮转时间
        self.concurrent_uses: Dict[str, int] = {}  # 当前并发使用数
        self.max_concurrent_per_proxy = 5  # 每个代理的最大并发数
        self.min_rotation_interval = 60  # 最小轮转间隔（秒）
        
        # Load cached proxies if available
        self._load_cache()
        
    def _get_cache_path(self) -> Path:
        """Get path to proxy cache file."""
        return Path(__file__).parent / 'data' / 'proxy_cache.json'
        
    def _load_cache(self):
        """Load cached proxies and scores."""
        cache_path = self._get_cache_path()
        if cache_path.exists():
            try:
                with open(cache_path, 'r') as f:
                    data = json.load(f)
                    
                self.proxies = data.get('proxies', {})
                
                # Reconstruct score objects
                scores_data = data.get('scores', {})
                for proxy_url, score_data in scores_data.items():
                    score = ProxyScore()
                    score.success_count = score_data.get('success_count', 0)
                    score.fail_count = score_data.get('fail_count', 0)
                    score.avg_response_time = score_data.get('avg_response_time', 0.0)
                    
                    last_success = score_data.get('last_success')
                    if last_success:
                        score.last_success = datetime.fromisoformat(last_success)
                        
                    last_used = score_data.get('last_used')
                    if last_used:
                        score.last_used = datetime.fromisoformat(last_used)
                        
                    self.scores[proxy_url] = score
                    
                logger.info(f"Loaded {len(self.proxies)} proxies from cache")
                
            except Exception as e:
                logger.error(f"Error loading proxy cache: {e}")
                
    def _save_cache(self):
        """Save proxies and scores to cache."""
        cache_path = self._get_cache_path()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            # Convert scores to serializable format
            scores_data = {}
            for proxy_url, score in self.scores.items():
                scores_data[proxy_url] = {
                    'success_count': score.success_count,
                    'fail_count': score.fail_count,
                    'avg_response_time': score.avg_response_time,
                    'last_success': score.last_success.isoformat() if score.last_success else None,
                    'last_used': score.last_used.isoformat() if score.last_used else None
                }
                
            data = {
                'proxies': self.proxies,
                'scores': scores_data
            }
            
            with open(cache_path, 'w') as f:
                json.dump(data, f, indent=2)
                
            logger.debug("Saved proxy cache")
            
        except Exception as e:
            logger.error(f"Error saving proxy cache: {e}")
            
    async def get_proxy(self, 
                       target_url: Optional[str] = None,
                       country_code: Optional[str] = None,
                       min_score: float = 0.5,
                       max_concurrent: int = 5,
                       test_mode: bool = False) -> Optional[Dict[str, str]]:
        """智能获取代理
        
        Args:
            target_url: 目标URL，用于地理位置优化
            country_code: 期望的代理所在国家
            min_score: 最低评分要求
            max_concurrent: 最大并发使用数
            test_mode: 是否处于测试模式（跳过代理连接测试）
            
        Returns:
            Dict[str, str]: 代理配置，如果没有合适的代理则返回None
        """
        if not self.proxies:
            logger.warning("No proxies available")
            return None
            
        # 更新代理池（如果需要且不在测试模式）
        if not test_mode:
            await self._update_if_needed()
        
        # 检查总并发数是否超过限制
        total_concurrent = sum(self.concurrent_uses.values())
        if total_concurrent >= max_concurrent:
            logger.warning(f"Maximum concurrent uses ({max_concurrent}) reached")
            return None
            
        # 获取所有可用代理及其评分
        available_proxies = []
        for proxy_url, proxy_data in self.proxies.items():
            score = self.scores.get(proxy_url, ProxyScore())
            current_uses = self.concurrent_uses.get(proxy_url, 0)
            
            # 检查代理是否满足条件
            if (score.score >= min_score and 
                current_uses < self.max_concurrent_per_proxy):
                
                # 如果指定了国家，检查地理位置匹配
                if country_code and proxy_data.get('country_code') != country_code:
                    continue
                    
                # 计算综合权重
                weight = self._calculate_rotation_weight(proxy_url, score)
                
                available_proxies.append((proxy_url, proxy_data, weight))
                
        if not available_proxies:
            logger.warning("No suitable proxies found")
            return None
            
        # 按权重排序
        available_proxies.sort(key=lambda x: x[2], reverse=True)
        
        # 选择最佳代理
        selected_url, selected_proxy, _ = available_proxies[0]
        
        # 更新并发使用数
        if selected_url not in self.concurrent_uses:
            self.concurrent_uses[selected_url] = 0
        self.concurrent_uses[selected_url] += 1
        
        # 更新使用统计
        self._update_rotation_stats(selected_url)
        
        # 返回代理配置（确保包含host和port）
        if 'host' not in selected_proxy or 'port' not in selected_proxy:
            host, port = selected_url.split(':')
            selected_proxy = selected_proxy.copy()  # 创建副本以避免修改原始数据
            selected_proxy['host'] = host
            selected_proxy['port'] = port
            
        # 确保返回的代理配置包含server字段
        selected_proxy['server'] = selected_url
            
        return selected_proxy
        
    def _calculate_rotation_weight(self, proxy_url: str, score: ProxyScore) -> float:
        """计算代理的轮转权重
        
        权重计算考虑以下因素：
        1. 代理评分 (40%)
        2. 当前并发使用数 (30%)
        3. 最近使用时间 (30%)
        """
        # 基础权重（代理评分）
        weight = score.score * 0.4
        
        # 并发使用数权重（使用数越多权重越低）
        current_uses = self.concurrent_uses.get(proxy_url, 0)
        concurrent_weight = max(0, 1 - (current_uses / self.max_concurrent_per_proxy))
        weight += concurrent_weight * 0.3
        
        # 最近使用时间权重（越久没用权重越高）
        if proxy_url in self.last_rotation:
            time_since_last_use = (datetime.now() - self.last_rotation[proxy_url]).total_seconds()
            time_weight = min(1, time_since_last_use / (self.min_rotation_interval * 5))
        else:
            time_weight = 1.0  # 从未使用过的代理获得最高时间权重
            
        weight += time_weight * 0.3
        
        return weight
        
    def _update_rotation_stats(self, proxy_url: str):
        """更新代理轮转统计信息"""
        now = datetime.now()
        
        # 初始化统计信息
        if proxy_url not in self.rotation_stats:
            self.rotation_stats[proxy_url] = {
                'total_uses': 0,
                'last_hour_uses': 0,
                'current_uses': 0
            }
            
        # 更新使用次数
        self.rotation_stats[proxy_url]['total_uses'] += 1
        
        # 更新并发使用数
        self.rotation_stats[proxy_url]['current_uses'] = self.concurrent_uses.get(proxy_url, 0)
        
        # 更新最后使用时间
        self.last_rotation[proxy_url] = now
        
        # 更新最近一小时使用次数
        one_hour_ago = now - timedelta(hours=1)
        if proxy_url in self.last_rotation and self.last_rotation[proxy_url] > one_hour_ago:
            self.rotation_stats[proxy_url]['last_hour_uses'] += 1
        else:
            self.rotation_stats[proxy_url]['last_hour_uses'] = 1
            
        # 清理轮转统计中的无效代理
        for url in list(self.rotation_stats.keys()):
            if url not in self.concurrent_uses:
                self.rotation_stats[url]['current_uses'] = 0
        
    async def release_proxy(self, proxy: Dict[str, str]):
        """释放代理，更新并发使用数
        
        参数:
            proxy (Dict[str, str]): 包含代理信息的字典，必须包含 'server' 或 ('host', 'port')
            
        行为:
            1. 从并发使用计数中移除代理
            2. 更新轮转统计的使用计数
            3. 清理无效的统计信息
        """
        if not proxy:
            logger.warning("尝试释放空代理")
            return
            
        # 获取代理URL（支持多种格式）
        proxy_url = None
        if 'server' in proxy:
            proxy_url = proxy['server']
        elif 'host' in proxy and 'port' in proxy:
            proxy_url = f"{proxy['host']}:{proxy['port']}"
            
        if not proxy_url:
            logger.warning("无法从代理配置中获取URL")
            return
            
        logger.info(f"释放代理 {proxy_url}")
            
        # 更新并发使用数
        if proxy_url in self.concurrent_uses:
            # 直接删除并发使用记录
            del self.concurrent_uses[proxy_url]
            logger.debug(f"删除代理的并发使用记录: {proxy_url}")
                
        # 更新轮转统计
        if proxy_url in self.rotation_stats:
            self.rotation_stats[proxy_url]['current_uses'] = 0
            logger.debug(f"重置代理的轮转统计: {proxy_url}")
            
        # 清理无效统计
        await self.cleanup_unused_stats()

    async def cleanup_unused_stats(self):
        """清理无效的统计信息
        
        清理内容包括:
        1. 无效的轮转统计记录
        2. 无效的并发使用记录
        3. 更新所有代理的使用状态
        """
        logger.debug("开始清理无效的统计信息...")
        
        # 清理无效的轮转统计
        for url in list(self.rotation_stats.keys()):
            if url not in self.proxies:
                del self.rotation_stats[url]
                logger.debug(f"删除无效代理的轮转统计: {url}")
            elif url not in self.concurrent_uses:
                self.rotation_stats[url]['current_uses'] = 0
                logger.debug(f"重置未使用代理的并发数: {url}")
                
        # 清理无效的并发使用数
        for url in list(self.concurrent_uses.keys()):
            if url not in self.proxies:
                del self.concurrent_uses[url]
                logger.debug(f"删除无效代理的并发使用记录: {url}")
                
        logger.debug(f"清理完成。当前状态: concurrent_uses={len(self.concurrent_uses)}, rotation_stats={len(self.rotation_stats)}")

    def get_rotation_stats(self) -> Dict[str, Any]:
        """获取代理轮转统计信息"""
        # 清理无效统计
        asyncio.create_task(self.cleanup_unused_stats())
                
        # 计算活跃代理数（只计算当前并发使用数大于0的代理）
        active_proxies = len([url for url in self.concurrent_uses if self.concurrent_uses[url] > 0])
        logger.debug(f"当前活跃代理数: {active_proxies}")
                
        stats = {
            'total_rotations': sum(s['total_uses'] for s in self.rotation_stats.values()),
            'active_proxies': active_proxies,
            'proxy_stats': []
        }
        
        # 收集每个代理的统计信息
        for proxy_url, rotation_data in self.rotation_stats.items():
            proxy_stats = {
                'server': proxy_url,
                'total_uses': rotation_data['total_uses'],
                'last_hour_uses': rotation_data['last_hour_uses'],
                'current_uses': self.concurrent_uses.get(proxy_url, 0),
                'last_used': self.last_rotation.get(proxy_url).isoformat() 
                            if proxy_url in self.last_rotation else None
            }
            
            # 添加评分信息
            if proxy_url in self.scores:
                score = self.scores[proxy_url]
                proxy_stats.update({
                    'score': score.score,
                    'success_rate': score.success_rate,
                    'avg_response_time': score.avg_response_time
                })
                
            stats['proxy_stats'].append(proxy_stats)
            
        # 按使用次数排序
        stats['proxy_stats'].sort(key=lambda x: x['total_uses'], reverse=True)
        
        return stats
        
    async def _update_if_needed(self):
        """Update proxy list if it's time to update."""
        now = datetime.now()
        if (not self.last_update or 
            now - self.last_update > self.update_interval):
            await self._update_proxy_list()
            
    async def _update_proxy_list(self):
        """Update the proxy list from various sources."""
        logger.info("Updating proxy list...")
        
        # Get proxies from Webshare
        webshare_proxies = await self._get_webshare_proxies()
        if webshare_proxies:
            self.proxies.update(webshare_proxies)
            logger.info(f"Added {len(webshare_proxies)} Webshare proxies")
            return
            
        logger.warning("No Webshare proxies available, falling back to free proxies")
        
        # Get proxies from free sources
        free_proxies = {}
        
        # Limit the number of proxies to test
        max_proxies = 50  # Adjust this number based on your needs
        
        try:
            # GeoNode Free Proxies
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    'https://proxylist.geonode.com/api/proxy-list'
                    '?limit=100&page=1&sort_by=lastChecked&sort_type=desc'
                    '&protocols=http%2Chttps',
                    ssl=False
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        proxies = data.get('data', [])[:max_proxies]  # Limit the number of proxies
                        for proxy in proxies:
                            proxy_url = f"{proxy['ip']}:{proxy['port']}"
                            free_proxies[proxy_url] = {'server': proxy_url}
        except Exception as e:
            logger.error(f"Error fetching proxies from GeoNode: {e}")
            
        # Update proxy list
        self.proxies.update(free_proxies)
        logger.info(f"Testing {len(self.proxies)} proxies...")
        
        # Test proxies before adding them
        working_proxies = {}
        test_urls = [
            'https://twitter.com',
            'https://api.twitter.com',
            'https://abs.twimg.com'
        ]
        
        logger.info(f"Testing {len(self.proxies)} proxies...")
        for proxy_url, proxy in self.proxies.items():
            proxy_working = True
            total_response_time = 0
            successful_tests = 0
            
            # Test each URL
            for test_url in test_urls:
                success, response_time = await self.test_proxy(
                    proxy,
                    test_url,
                    timeout=20
                )
                if success:
                    total_response_time += response_time
                    successful_tests += 1
                else:
                    proxy_working = False
                    break
                    
            # Only add proxy if it works with all test URLs
            if proxy_working and successful_tests == len(test_urls):
                avg_response_time = total_response_time / successful_tests
                working_proxies[proxy_url] = proxy
                logger.info(f"Found working proxy: {proxy_url} (avg response: {avg_response_time:.2f}s)")
                
                # Initialize or update score
                if proxy_url not in self.scores:
                    self.scores[proxy_url] = ProxyScore()
                await self.update_proxy_score(proxy, True, avg_response_time)
            else:
                logger.debug(f"Proxy failed tests: {proxy_url}")
        
        # Update proxy list with working proxies
        self.proxies = working_proxies
        
        # Save to cache
        self._save_cache()
        
        self.last_update = datetime.now()
        
        logger.info(f"Found {len(self.proxies)} working proxies")
        
    async def _get_webshare_proxies(self) -> Dict[str, Dict[str, str]]:
        """Get proxies from Webshare.io API."""
        proxies = {}
        
        # Get API key from environment variable
        api_key = os.getenv('WEBSHARE_API_KEY')
        if not api_key:
            logger.error("No Webshare API key found in environment variables")
            logger.error("Please set WEBSHARE_API_KEY in your .env file")
            return {}
            
        logger.info("Found Webshare API key, fetching proxies...")
        
        # Webshare API endpoint and parameters
        api_url = "https://proxy.webshare.io/api/v2/proxy/list/"
        params = {
            'mode': 'direct',  # or 'rotating' based on your subscription
            'page': 1,
            'page_size': 25,
            'protocol': ['http', 'https']
        }
        
        try:
            headers = {
                'Authorization': f'Token {api_key}',
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            }
            
            timeout = aiohttp.ClientTimeout(total=20)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(api_url, headers=headers, params=params, ssl=False) as response:
                    if response.status == 200:
                        data = await response.json()
                        proxy_list = data.get('results', [])
                        logger.info(f"Retrieved {len(proxy_list)} proxies from Webshare")
                        
                        for proxy in proxy_list:
                            try:
                                # Handle both old and new API response formats
                                if 'ports' in proxy:
                                    port = proxy['ports'].get('http') or proxy['ports'].get('https')
                                else:
                                    port = proxy.get('port')
                                    
                                if not port:
                                    logger.warning(f"No valid port found for proxy: {proxy}")
                                    continue
                                    
                                proxy_url = f"{proxy['proxy_address']}:{port}"
                                proxies[proxy_url] = {
                                    'server': proxy_url,
                                    'username': proxy['username'],
                                    'password': proxy['password']
                                }
                                logger.debug(f"Added proxy: {proxy_url}")
                            except KeyError as e:
                                logger.warning(f"Invalid proxy data: {e}")
                                continue
                    else:
                        logger.error(f"Failed to get Webshare proxies: {response.status}")
                        if response.status == 401:
                            logger.error("Invalid API key. Please check your WEBSHARE_API_KEY")
                        elif response.status == 429:
                            logger.error("Rate limited by Webshare API")
                        elif response.status == 400:
                            response_json = await response.json()
                            logger.error(f"Bad request to Webshare API: {response_json}")
                            logger.error(f"Request URL: {str(response.url)}")
                            logger.error(f"Request params: {params}")
                        response_text = await response.text()
                        logger.error(f"Response: {response_text}")
                        
        except aiohttp.ClientError as e:
            logger.error(f"Network error fetching Webshare proxies: {e}")
        except Exception as e:
            logger.error(f"Error fetching Webshare proxies: {e}")
            
        return proxies
        
    async def _get_free_proxies(self) -> Dict[str, Dict[str, str]]:
        """Get proxies from free proxy sources."""
        proxies = {}
        
        # List of free proxy APIs
        proxy_apis = [
            'https://proxylist.geonode.com/api/proxy-list?limit=100&page=1&sort_by=lastChecked&sort_type=desc&protocols=http%2Chttps',
            'https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt',
            'https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt'
        ]
        
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for api_url in proxy_apis:
                try:
                    async with session.get(api_url) as response:
                        if response.status == 200:
                            if 'geonode' in api_url:
                                # Parse GeoNode JSON response
                                data = await response.json()
                                for proxy in data.get('data', []):
                                    proxy_url = f"{proxy['ip']}:{proxy['port']}"
                                    proxies[proxy_url] = {
                                        'server': f"http://{proxy_url}",
                                        'username': '',
                                        'password': ''
                                    }
                            else:
                                # Parse plain text proxy lists
                                text = await response.text()
                                for line in text.splitlines():
                                    if ':' in line:
                                        proxy_url = line.strip()
                                        proxies[proxy_url] = {
                                            'server': f"http://{proxy_url}",
                                            'username': '',
                                            'password': ''
                                        }
                                        
                except Exception as e:
                    logger.error(f"Error fetching proxies from {api_url}: {e}")
                    continue
                    
        return proxies
        
    async def test_proxy(self, proxy: Dict[str, str], test_url: str = "http://httpbin.org/ip", timeout: int = 30) -> Tuple[bool, float]:
        """Test if a proxy is working."""
        if not proxy or not all(k in proxy for k in ['host', 'port']):
            logger.error("Invalid proxy configuration")
            return False, 0.0  # 返回浮点数
            
        host = proxy['host']
        port = int(proxy['port'])
        username = proxy.get('username')
        password = proxy.get('password')
        proxy_type = proxy.get('type', 'socks5').lower()
        
        logger.info(f"Testing {proxy_type.upper()} proxy: {host}:{port}")
        
        # Configure timeout
        timeout = aiohttp.ClientTimeout(
            total=timeout,
            connect=10,
            sock_connect=10,
            sock_read=10
        )
        
        start_time = time.time()  # 记录开始时间
        
        try:
            # Create connector based on proxy type
            if proxy_type == 'socks5':
                connector = ProxyConnector(
                    proxy_type=ProxyType.SOCKS5,
                    host=host,
                    port=port,
                    username=username,
                    password=password,
                    ssl=False,
                    rdns=True
                )
            else:  # http/https proxy
                proxy_url = f"http://{username}:{password}@{host}:{port}" if username and password else f"http://{host}:{port}"
                connector = aiohttp.TCPConnector(ssl=False)
                
            logger.debug(f"Created {proxy_type.upper()} connector")
            
            async with aiohttp.ClientSession(
                connector=connector,
                timeout=timeout
            ) as session:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
                
                # Try both HTTPS and HTTP
                for scheme in ['https', 'http']:
                    test_url_with_scheme = test_url.replace('http://', f'{scheme}://')
                    logger.debug(f"Trying {scheme.upper()}: {test_url_with_scheme}")
                    
                    try:
                        # Add proxy settings for HTTP/HTTPS proxies
                        if proxy_type != 'socks5':
                            proxy_settings = {
                                'proxy': proxy_url,
                                'proxy_auth': None if not (username and password) else aiohttp.BasicAuth(username, password)
                            }
                        else:
                            proxy_settings = {}
                            
                        async with session.get(test_url_with_scheme, headers=headers, **proxy_settings) as response:
                            logger.debug(f"Response status: {response.status}")
                            
                            if response.status == 200:
                                # Try to read response data
                                try:
                                    content_type = response.headers.get('Content-Type', '')
                                    if 'application/json' in content_type:
                                        data = await response.json()
                                        logger.info(f"Successfully connected via {scheme.upper()}. Response: {data}")
                                    else:
                                        text = await response.text()
                                        logger.info(f"Successfully connected via {scheme.upper()}. Response length: {len(text)} bytes")
                                    return True, time.time() - start_time  # 返回实际响应时间
                                except Exception as e:
                                    logger.error(f"Error reading response data: {e}")
                            else:
                                logger.warning(f"Got status {response.status}")
                                
                    except asyncio.TimeoutError:
                        logger.error(f"Timeout with {scheme}")
                    except Exception as e:
                        logger.error(f"Error with {scheme}: {e}")
                        
        except Exception as e:
            logger.error(f"Error creating/using connector: {e}")
            
        return False, 0.0  # 返回浮点数
        
    async def update_proxy_score(self, proxy: Dict[str, str], success: bool, response_time: float = 0):
        """Update the score of a proxy based on its performance."""
        if not proxy or 'server' not in proxy:
            return
            
        proxy_url = proxy['server']
        current_score = self.scores.get(proxy_url, ProxyScore()).score
        
        if success:
            # Increase score for successful connection
            new_score = min(current_score + 0.1, 1.0)
            logger.debug(f"Proxy {proxy_url} succeeded, score increased: {current_score} -> {new_score}")
        else:
            # Decrease score for failed connection
            new_score = max(current_score - 0.1, 0.0)
            logger.debug(f"Proxy {proxy_url} failed, score decreased: {current_score} -> {new_score}")
            
        # Get or create score object
        score = self.scores.get(proxy_url)
        if not score:
            score = ProxyScore()
            self.scores[proxy_url] = score
            
        # Update score
        if success:
            score.update_success(response_time)
        else:
            score.update_failure()
            
        # Save updated scores
        self._save_cache()
        
    async def mark_proxy_failed(self, proxy: Dict[str, str]):
        """
        Mark a proxy as failed and update its score.
        
        Args:
            proxy: Failed proxy configuration
        """
        await self.update_proxy_score(proxy, success=False)
        
        # If proxy list is getting too small, update it
        if len(self.proxies) < 2:
            await self._update_proxy_list()
            
    def get_proxy_stats(self) -> Dict[str, Any]:
        """Get statistics about the proxy pool."""
        stats = {
            'total_proxies': len(self.proxies),
            'active_proxies': 0,
            'working_proxies': 0,
            'average_score': 0.0,
            'top_proxies': [],
            'failed_proxies': []
        }
        
        if not self.proxies:
            return stats
            
        # Calculate statistics
        total_score = 0
        for proxy_url, proxy_data in self.proxies.items():
            score = self.scores.get(proxy_url, ProxyScore())
            if score.score > 0:
                stats['working_proxies'] += 1
                stats['active_proxies'] += 1
                total_score += score.score
                
                # Add to top proxies if score is good
                if score.score >= 0.7:
                    stats['top_proxies'].append({
                        'server': proxy_url,
                        'score': score.score,
                        'success_count': score.success_count,
                        'failure_count': score.fail_count,
                        'avg_response_time': score.avg_response_time
                    })
            else:
                # Add to failed proxies if score is 0
                stats['failed_proxies'].append({
                    'server': proxy_url,
                    'last_failure': score.last_used.isoformat() if score.last_used else None,
                    'failure_count': score.fail_count
                })
                
        # Calculate average score
        if stats['working_proxies'] > 0:
            stats['average_score'] = total_score / stats['working_proxies']
            
        # Sort top proxies by score
        stats['top_proxies'].sort(key=lambda x: x['score'], reverse=True)
        
        # Sort failed proxies by failure count
        stats['failed_proxies'].sort(key=lambda x: x['failure_count'], reverse=True)
        
        return stats
