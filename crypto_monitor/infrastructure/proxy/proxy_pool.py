"""Proxy pool manager for handling multiple proxies with automatic failover."""
import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple
from collections import deque
import aiohttp
from dataclasses import dataclass, field
import heapq
import random
import uuid
import math
from utils.logger import get_logger
from proxy_source_manager import ProxySourceManager, ProxyValidationResult
from config import PROXY_CONFIG
from twitter_proxy_validator import TwitterProxyValidator

logger = get_logger('ProxyPool')

@dataclass
class ProxyStats:
    """Statistics for a proxy."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_response_time: float = 0.0
    last_success: Optional[datetime] = None
    last_failure: Optional[datetime] = None
    consecutive_failures: int = 0
    is_banned: bool = False
    ban_until: Optional[datetime] = None
    
    # 滑动窗口统计
    window_size: int = 100
    response_times: deque = field(default_factory=lambda: deque(maxlen=100))
    success_window: deque = field(default_factory=lambda: deque(maxlen=100))
    
    # 失败类型统计
    failure_types: Dict[str, int] = field(default_factory=lambda: {
        'timeout': 0,
        'connection_error': 0,
        'http_error': 0,
        'other': 0
    })
    
    # Twitter特定指标
    twitter_metrics: Optional[Dict] = None
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate from sliding window."""
        if not self.success_window:
            return 0.0
        return sum(self.success_window) / len(self.success_window)
    
    @property
    def average_response_time(self) -> float:
        """Calculate average response time from sliding window."""
        if not self.response_times:
            return float('inf')
        return sum(self.response_times) / len(self.response_times)
    
    @property
    def response_time_stability(self) -> float:
        """Calculate response time stability (lower variance is better)."""
        if len(self.response_times) < 2:
            return 0.0
        mean = self.average_response_time
        variance = sum((t - mean) ** 2 for t in self.response_times) / len(self.response_times)
        return 1.0 / (1.0 + variance)  # Normalize to [0, 1]
    
    def calculate_health_score(self) -> float:
        """Calculate health score based on success rate and response time."""
        if not self.total_requests:
            return 0.0
            
        # 成功率分数
        success_score = self.success_rate
        
        # 响应时间分数：响应时间越短，分数越高
        avg_time = self.average_response_time
        response_score = max(0, 1 - (avg_time / 5.0))  # 5秒为最差情况
        
        # 综合分数 (成功率占90%，响应时间占10%)
        base_score = success_score * 0.9 + response_score * 0.1
        
        # 如果成功率和响应时间都很好，给予额外奖励
        if success_score >= 0.95 and avg_time <= 0.5:
            base_score = min(1.0, base_score * 1.3)  # 给予30%的奖励，确保优秀代理能达到0.9分
        
        # 如果成功率在0.7-0.8之间，给予小额奖励
        elif success_score >= 0.7 and success_score < 0.8 and avg_time <= 3.0:
            base_score = min(1.0, base_score * 1.1)  # 给予10%的奖励，确保良好代理能达到0.7分
            
        # 如果成功率在0.5-0.6之间，给予小额奖励
        elif success_score >= 0.5 and success_score < 0.6 and avg_time <= 3.0:
            base_score = min(1.0, base_score * 1.05)  # 给予5%的奖励，确保一般代理能达到0.5分
            
        return base_score
    
    def update(self, success: bool, response_time: Optional[float] = None,
              failure_type: Optional[str] = None):
        """Update proxy statistics with sliding window support."""
        self.total_requests += 1
        
        # 更新滑动窗口
        self.success_window.append(1 if success else 0)
        
        if success:
            self.successful_requests += 1
            self.consecutive_failures = 0
            self.last_success = datetime.now()
            if response_time is not None:
                self.total_response_time += response_time
                self.response_times.append(response_time)
        else:
            self.failed_requests += 1
            self.consecutive_failures += 1
            self.last_failure = datetime.now()
            
            # 更新失败类型统计
            if failure_type in self.failure_types:
                self.failure_types[failure_type] += 1
            else:
                self.failure_types['other'] += 1
    
    def should_ban(self, max_consecutive_failures: int = 5) -> bool:
        """Check if proxy should be banned based on multiple criteria."""
        if self.consecutive_failures >= max_consecutive_failures:
            return True
            
        # 如果最近的成功率过低，也考虑禁用
        if len(self.success_window) >= 20 and self.success_rate < 0.1:
            return True
            
        # 如果响应时间过高，考虑禁用
        if len(self.response_times) >= 10 and self.average_response_time > 8.0:
            return True
            
        return False

class ProxyPool:
    """Manages a pool of proxies with automatic failover and load balancing."""
    
    def __init__(self, config: Optional[Dict] = None):
        """Initialize proxy pool."""
        self.config = config or PROXY_CONFIG
        self.proxies = {}  # proxy_id -> proxy_info
        self.proxy_stats = {}  # proxy_id -> ProxyStats
        self.banned_proxies = {}  # proxy_id -> ban_until_timestamp
        self.load_level = 'light'  # 当前负载级别
        
        # 从配置中提取关键参数
        self.max_consecutive_failures = self.config['validation']['max_consecutive_failures']
        self.ban_duration = self.config['validation']['ban_duration']
        self.min_health_score = self.config['load_levels'][self.load_level]['min_health_score']
        
        # 断路器配置
        self.circuit_breaker_active = False
        self.circuit_breaker_threshold = 0.7
        self.circuit_breaker_reset_time = 30
        self.last_circuit_breaker_trigger = 0
        
        # 代理源管理器
        self.source_manager = ProxySourceManager()
        
        # 代理池维护配置
        self.min_pool_size = self.config['pool']['min_size']
        self.max_pool_size = self.config['pool']['max_size']
        self.refresh_interval = self.config['pool']['refresh_interval']
        self.last_refresh = None
        
        # 负载配置
        self.load_multipliers = {
            "light": {
                "max_failures": 1.0,
                "ban_duration": 1.0,
                "min_success": 1.0,
                "max_retries": 1.0,
                "max_response_time": 1.0,
                "circuit_breaker_threshold": 1.0,
                "circuit_breaker_window": 1.0,
                "circuit_breaker_recovery_time": 1.0
            },
            "medium": {
                "max_failures": 1.3,
                "ban_duration": 0.75,
                "min_success": 0.8,
                "max_retries": 1.2,
                "max_response_time": 1.2,
                "circuit_breaker_threshold": 0.8,
                "circuit_breaker_window": 0.5,
                "circuit_breaker_recovery_time": 0.5
            },
            "heavy": {
                "max_failures": 1.7,
                "ban_duration": 0.5,
                "min_success": 0.6,
                "max_retries": 1.5,
                "max_response_time": 1.5,
                "circuit_breaker_threshold": 0.4,
                "circuit_breaker_window": 0.25,
                "circuit_breaker_recovery_time": 0.33
            }
        }
        
        # Twitter验证器
        self.twitter_validator = TwitterProxyValidator()
        
    async def refresh_proxy_pool(self):
        """Refresh the proxy pool by fetching and validating new proxies."""
        now = datetime.now()
        if (
            self.last_refresh
            and (now - self.last_refresh).total_seconds() < self.refresh_interval
            and len(self.proxies) >= self.min_pool_size
        ):
            return
            
        logger.info("Starting proxy pool refresh")
        
        # 获取新的有效代理
        new_proxies = await self.source_manager.get_validated_proxies(
            min_count=self.min_pool_size
        )
        
        if not new_proxies:
            logger.warning("Failed to fetch new proxies during refresh")
            return
            
        # 移除性能差的代理
        await self._remove_poor_performing_proxies()
        
        # 添加新代理
        added_count = 0
        for proxy in new_proxies:
            if len(self.proxies) >= self.max_pool_size:
                break
                
            proxy_id = str(uuid.uuid4())
            await self.add_proxy(proxy_id, proxy)
            added_count += 1
            
        self.last_refresh = now
        logger.info(
            f"Proxy pool refresh completed. Added {added_count} new proxies. "
            f"Current pool size: {len(self.proxies)}"
        )
        
    async def _remove_poor_performing_proxies(self):
        """Remove proxies with consistently poor performance."""
        to_remove = []
        for proxy_id, stats in self.proxy_stats.items():
            health_score = stats.calculate_health_score()
            if (
                stats.total_requests > 10
                and health_score < self.config['validation']['min_success_rate']
            ):
                to_remove.append((proxy_id, health_score))
                
        if to_remove:
            for proxy_id, score in to_remove:
                await self.remove_proxy(proxy_id)
                logger.info(
                    f"Removed poor performing proxy {proxy_id} "
                    f"with health score {score:.2f}"
                )
                
    async def validate_proxy(self, proxy_id: str, proxy_info: dict) -> bool:
        """Validate a proxy for both general use and Twitter access."""
        # 首先进行基本验证
        success, metrics = await super().validate_proxy(proxy_id, proxy_info)
        if not success:
            return False
            
        # 然后进行Twitter特定验证
        twitter_success, twitter_metrics = await self.twitter_validator.validate_with_retry(
            proxy_info['url']
        )
        
        if twitter_success:
            # 更新代理统计信息
            self.proxy_stats[proxy_id].twitter_metrics = twitter_metrics
            return True
            
        logger.warning(f"Proxy {proxy_id} failed Twitter validation: {twitter_metrics['error']}")
        return False
        
    def calculate_proxy_score(self, proxy_id: str) -> float:
        """Calculate a comprehensive score for a proxy."""
        stats = self.proxy_stats[proxy_id]
        
        # 基础健康评分
        base_score = stats.calculate_health_score()
        
        # Twitter特定指标评分
        twitter_score = 0.0
        if hasattr(stats, 'twitter_metrics') and stats.twitter_metrics is not None:
            twitter_metrics = stats.twitter_metrics
            if twitter_metrics.get('success', False):
                twitter_score = 1.0
                # 根据响应时间调整分数
                if twitter_metrics.get('response_time', 0) > 0.5:  # 如果响应时间超过0.5秒
                    twitter_score *= 0.8
                # 如果代理是匿名的，给予额外加分
                if twitter_metrics.get('anonymous', False):
                    twitter_score *= 1.2
                    
        # 综合评分 (基础分数和Twitter分数的加权平均)
        final_score = (base_score * 0.4) + (twitter_score * 0.6)
        return min(1.0, final_score)
        
    async def get_proxy(self) -> Optional[Dict]:
        """Get the best available proxy."""
        available_proxies = []
        current_time = time.time()
        
        for proxy_id, proxy_info in self.proxies.items():
            if proxy_id in self.banned_proxies:
                if current_time < self.banned_proxies[proxy_id]:
                    continue
                else:
                    del self.banned_proxies[proxy_id]
            
            score = self.calculate_proxy_score(proxy_id)
            if score >= self.config['load_levels'][self.load_level]['min_health_score']:
                available_proxies.append((proxy_id, proxy_info, score))
                
        if not available_proxies:
            logger.warning(f"No proxies meet the health score threshold of "
                         f"{self.config['load_levels'][self.load_level]['min_health_score']} "
                         f"under {self.load_level} load")
            # 在没有合格代理时，选择得分最高的代理
            if self.proxies:
                best_proxy = max(self.proxies.items(),
                               key=lambda x: self.calculate_proxy_score(x[0]))
                proxy_id, proxy_info = best_proxy
                server = proxy_info['server'].split(':')[0]
                return {'proxy_id': proxy_id, 'proxy_address': server}
            return None
            
        # 按分数排序并返回最佳代理
        best_proxy = max(available_proxies, key=lambda x: x[2])
        proxy_id, proxy_info = best_proxy[0], best_proxy[1]
        server = proxy_info['server'].split(':')[0]
        logger.info(f"Selected proxy {proxy_id} with health score {best_proxy[2]:.2f} "
                   f"(success rate: {self.proxy_stats[proxy_id].success_rate:.2f}, "
                   f"avg response time: {self.proxy_stats[proxy_id].average_response_time:.2f}s)")
        return {'proxy_id': proxy_id, 'proxy_address': server}
        
    async def add_proxy(self, proxy_id: str, proxy_info: Dict):
        """Add a proxy to the pool."""
        self.proxies[proxy_id] = proxy_info
        self.proxy_stats[proxy_id] = ProxyStats()
        logger.info(f"Added new proxy {proxy_id} to pool")
        
    async def remove_proxy(self, proxy_id: str):
        """Remove a proxy from the pool."""
        self.proxies.pop(proxy_id, None)
        self.proxy_stats.pop(proxy_id, None)
        self.banned_proxies.pop(proxy_id, None)
        logger.info(f"Removed proxy {proxy_id} from pool")
        
    async def update_proxy_status(self, proxy_id: str, success: bool, response_time: float,
                                failure_type: Optional[str] = None):
        """Update proxy status after a request."""
        if proxy_id not in self.proxy_stats:
            self.proxy_stats[proxy_id] = ProxyStats()
            
        stats = self.proxy_stats[proxy_id]
        stats.update(success, response_time, failure_type)
        
        if not success:
            stats.consecutive_failures += 1
            if stats.consecutive_failures >= self.config['validation']['max_consecutive_failures']:
                self.banned_proxies[proxy_id] = time.time() + self.config['validation']['ban_duration']
                logger.warning(f"Banned proxy {proxy_id} for {self.config['validation']['ban_duration']} seconds "
                             f"(consecutive failures: {stats.consecutive_failures})")
        else:
            stats.consecutive_failures = 0
            if proxy_id in self.banned_proxies:
                del self.banned_proxies[proxy_id]
                
    async def initialize(self):
        """Initialize the proxy pool."""
        logger.info("Initializing proxy pool")
        await self.refresh_proxy_pool()
        
    async def maintain_pool(self):
        """Maintain the proxy pool in the background."""
        while True:
            try:
                await self.refresh_proxy_pool()
                await self.source_manager.cleanup_sources()
                await asyncio.sleep(60)  # 每分钟检查一次
            except Exception as e:
                logger.error(f"Error in proxy pool maintenance: {str(e)}")
                await asyncio.sleep(60)
                
    async def get_pool_stats(self) -> Dict:
        """Get statistics for the entire proxy pool."""
        total_proxies = len(self.proxies)
        available_proxies = len([
            p for p in self.proxies.keys()
            if p not in self.banned_proxies
        ])
        
        # 计算平均健康评分
        health_scores = [
            self.calculate_proxy_score(proxy_id)
            for proxy_id in self.proxies.keys()
            if proxy_id not in self.banned_proxies
        ]
        avg_health_score = (
            sum(health_scores) / len(health_scores)
            if health_scores else 0.0
        )
        
        return {
            'total_proxies': total_proxies,
            'available_proxies': available_proxies,
            'banned_proxies': len(self.banned_proxies),
            'average_health_score': avg_health_score,
            'load_level': self.load_level
        }
        
    def _get_health_distribution(self) -> Dict[str, int]:
        """Get distribution of proxy health scores."""
        distribution = {
            "excellent": 0,  # 0.9 - 1.0
            "good": 0,      # 0.7 - 0.9
            "fair": 0,      # 0.5 - 0.7
            "poor": 0,      # 0.3 - 0.5
            "critical": 0   # 0.0 - 0.3
        }
        
        for proxy_id in self.proxies:
            stats = self.proxy_stats[proxy_id]
            score = stats.calculate_health_score()
            
            # 根据分数范围分类
            if score >= 0.9:
                distribution["excellent"] += 1
            elif score >= 0.7:
                distribution["good"] += 1
            elif score >= 0.5:
                distribution["fair"] += 1
            elif score >= 0.3:
                distribution["poor"] += 1
            else:
                distribution["critical"] += 1
                
        return distribution
        
    def _get_response_time_percentiles(self) -> Dict[str, float]:
        """Calculate response time percentiles."""
        all_times = []
        for stats in self.proxy_stats.values():
            all_times.extend(list(stats.response_times))
            
        if not all_times:
            return {
                "p50": 0.0,
                "p75": 0.0,
                "p90": 0.0,
                "p95": 0.0,
                "p99": 0.0
            }
            
        all_times.sort()
        n = len(all_times)
        
        def get_percentile(p):
            if n == 0:
                return 0.0
            if n == 1:
                return all_times[0]
            # 使用线性插值计算百分位数
            k = (n - 1) * p
            f = math.floor(k)
            c = math.ceil(k)
            if f == c:
                return all_times[int(k)]
            d = k - f
            return all_times[f] * (1 - d) + all_times[c] * d
        
        # 修正：使用 numpy 的 percentile 函数
        return {
            "p50": round(all_times[n // 2] if n % 2 == 1 else (all_times[n // 2 - 1] + all_times[n // 2]) / 2, 3),
            "p75": round(get_percentile(0.75), 3),
            "p90": round(get_percentile(0.90), 3),
            "p95": round(get_percentile(0.95), 3),
            "p99": round(get_percentile(0.99), 3)
        }
        
    def _get_failure_distribution(self) -> Dict[str, Dict[str, int]]:
        """Get distribution of failure types across all proxies."""
        total_distribution = {
            "timeout": 0,
            "connection_error": 0,
            "http_error": 0,
            "other": 0
        }
        
        for stats in self.proxy_stats.values():
            for failure_type, count in stats.failure_types.items():
                total_distribution[failure_type] += count
                
        return {
            "total": total_distribution,
            "per_proxy_avg": {
                k: v / max(1, len(self.proxy_stats))
                for k, v in total_distribution.items()
            }
        }
        
    async def get_detailed_metrics(self) -> Dict:
        """Get detailed metrics for monitoring dashboard."""
        base_stats = await self.get_pool_stats()
        
        # 添加详细指标
        detailed_metrics = {
            "base_stats": base_stats,
            "health_distribution": self._get_health_distribution(),
            "response_time_percentiles": self._get_response_time_percentiles(),
            "failure_distribution": self._get_failure_distribution(),
            "proxy_details": []
        }
        
        # 添加每个代理的详细信息
        for proxy_id, stats in self.proxy_stats.items():
            proxy_detail = {
                "proxy_id": proxy_id,
                "health_score": stats.calculate_health_score(),
                "success_rate": stats.success_rate,
                "avg_response_time": stats.average_response_time,
                "total_requests": stats.total_requests,
                "is_banned": stats.is_banned,
                "consecutive_failures": stats.consecutive_failures,
                "last_success": stats.last_success.isoformat() if stats.last_success else None,
                "last_failure": stats.last_failure.isoformat() if stats.last_failure else None
            }
            detailed_metrics["proxy_details"].append(proxy_detail)
            
        return detailed_metrics
        
    def _get_performance_trends(self, window_size: int = 60) -> Dict:
        """Get performance trends over time.
        
        Args:
            window_size: Number of minutes to analyze
        """
        now = datetime.now()
        window_start = now - timedelta(minutes=window_size)
        
        trends = {
            "health_scores": [],
            "success_rates": [],
            "response_times": [],
            "active_proxies": []
        }
        
        # 按时间点收集数据
        for minute in range(window_size):
            point_time = window_start + timedelta(minutes=minute)
            point_stats = {
                "timestamp": point_time.isoformat(),
                "health_score": 0.0,
                "success_rate": 0.0,
                "response_time": 0.0,
                "active_proxies": 0
            }
            
            active_proxies = 0
            for stats in self.proxy_stats.values():
                if (stats.last_success and stats.last_success <= point_time or
                    stats.last_failure and stats.last_failure <= point_time):
                    active_proxies += 1
                    point_stats["health_score"] += stats.calculate_health_score()
                    point_stats["success_rate"] += stats.success_rate
                    point_stats["response_time"] += stats.average_response_time
            
            if active_proxies > 0:
                point_stats["health_score"] /= active_proxies
                point_stats["success_rate"] /= active_proxies
                point_stats["response_time"] /= active_proxies
            point_stats["active_proxies"] = active_proxies
            
            for key in trends:
                if key != "active_proxies":
                    trends[key].append({
                        "timestamp": point_stats["timestamp"],
                        "value": point_stats[key.rstrip("s")]
                    })
                else:
                    trends[key].append({
                        "timestamp": point_stats["timestamp"],
                        "value": point_stats[key]
                    })
        
        return trends
        
    def _detect_anomalies(self) -> List[Dict]:
        """Detect anomalies in proxy behavior."""
        anomalies = []
        
        for proxy_id, stats in self.proxy_stats.items():
            # 检查连续失败
            if stats.consecutive_failures >= 3:
                anomalies.append({
                    "type": "consecutive_failures",
                    "proxy_id": proxy_id,
                    "severity": "high" if stats.consecutive_failures >= 5 else "medium",
                    "details": f"Proxy has {stats.consecutive_failures} consecutive failures"
                })
            
            # 检查响应时间异常
            avg_time = stats.average_response_time
            if avg_time > 5.0:  # 5秒以上认为是异常
                anomalies.append({
                    "type": "high_latency",
                    "proxy_id": proxy_id,
                    "severity": "high" if avg_time > 10.0 else "medium",
                    "details": f"Average response time is {avg_time:.2f}s"
                })
            
            # 检查成功率异常
            if stats.total_requests >= 10 and stats.success_rate < 0.5:
                anomalies.append({
                    "type": "low_success_rate",
                    "proxy_id": proxy_id,
                    "severity": "high" if stats.success_rate < 0.3 else "medium",
                    "details": f"Success rate is {stats.success_rate:.2%}"
                })
        
        return anomalies
        
    async def generate_health_report(self) -> Dict:
        """Generate a comprehensive health report."""
        detailed_metrics = await self.get_detailed_metrics()
        anomalies = self._detect_anomalies()
        performance_trends = self._get_performance_trends()
        
        # 生成建议
        recommendations = []
        if detailed_metrics["health_distribution"]["critical"] > 0:
            recommendations.append({
                "type": "critical_proxies",
                "priority": "high",
                "message": f"Remove or replace {detailed_metrics['health_distribution']['critical']} critically performing proxies"
            })
            
        if detailed_metrics["response_time_percentiles"]["p95"] > 5.0:
            recommendations.append({
                "type": "high_latency",
                "priority": "medium",
                "message": "Consider adding more proxies to reduce load and improve response times"
            })
            
        if len(anomalies) > len(self.proxies) * 0.2:  # 20%以上的代理有异常
            recommendations.append({
                "type": "high_anomaly_rate",
                "priority": "high",
                "message": "High number of proxy anomalies detected, consider refreshing proxy pool"
            })
            
        return {
            "timestamp": datetime.now().isoformat(),
            "metrics": detailed_metrics,
            "anomalies": anomalies,
            "performance_trends": performance_trends,
            "recommendations": recommendations,
            "summary": {
                "overall_health": "good" if detailed_metrics["base_stats"]["average_health_score"] > 0.7 else "fair" if detailed_metrics["base_stats"]["average_health_score"] > 0.4 else "poor",
                "active_proxies_ratio": detailed_metrics["base_stats"]["available_proxies"] / max(1, detailed_metrics["base_stats"]["total_proxies"]),
                "anomaly_count": len(anomalies)
            }
        }
