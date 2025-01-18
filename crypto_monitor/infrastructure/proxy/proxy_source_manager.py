"""Proxy source manager for fetching and validating proxies."""
import asyncio
import aiohttp
from typing import Dict, List, Optional, Set
from datetime import datetime, timedelta
import json
from dataclasses import dataclass, field
import logging
from config import PROXY_SOURCE_CONFIG
from utils.logger import get_logger

logger = get_logger('ProxySourceManager')

@dataclass
class ProxyValidationResult:
    """Validation result for a proxy."""
    is_valid: bool
    response_time: Optional[float] = None
    error_type: Optional[str] = None
    anonymous: bool = False
    last_checked: datetime = field(default_factory=datetime.now)

@dataclass
class ProxySource:
    """Configuration for a proxy source."""
    name: str
    url: str
    type: str = 'free'  # 'api' or 'free'
    method: str = 'GET'
    headers: Dict = field(default_factory=dict)
    data: Dict = field(default_factory=dict)
    parser: str = 'json'  # 'json', 'text', or 'html'
    active: bool = True
    last_fetch: Optional[datetime] = None
    fetch_interval: int = 3600  # seconds
    max_proxies: int = 100
    timeout: int = 10
    success_rate: float = 1.0  # 源的成功率统计
    auth: Dict = field(default_factory=dict)  # 认证信息

class ProxySourceManager:
    """Manages multiple proxy sources and proxy validation."""
    
    def __init__(self):
        self.sources: Dict[str, ProxySource] = {}
        self.validation_semaphore = asyncio.Semaphore(10)
        self.last_cleanup: Optional[datetime] = None
        self.cleanup_interval = 3600  # 每小时清理一次
        self.validation_cache: Dict[str, ProxyValidationResult] = {}
        self.validation_ttl = 300  # 验证结果缓存5分钟
        
        # 从配置加载代理源
        self._load_sources()
        
    def _load_sources(self):
        """Load proxy sources from configuration."""
        for source_name, config in PROXY_SOURCE_CONFIG.items():
            self.sources[source_name] = ProxySource(
                name=source_name,
                **config
            )
            
    async def validate_proxy(self, proxy: Dict, test_urls: List[str] = None) -> ProxyValidationResult:
        """Validate a proxy against multiple test URLs."""
        if not test_urls:
            test_urls = [
                "http://httpbin.org/ip",
                "https://api.ipify.org?format=json"
            ]
            
        # 检查缓存
        cache_key = f"{proxy['server']}_{proxy.get('protocol', 'http')}"
        cached_result = self.validation_cache.get(cache_key)
        if cached_result and (datetime.now() - cached_result.last_checked).total_seconds() < self.validation_ttl:
            return cached_result
            
        async with self.validation_semaphore:
            start_time = datetime.now()
            for test_url in test_urls:
                try:
                    proxy_url = f"{proxy.get('protocol', 'http')}://{proxy['server']}"
                    auth = None
                    if proxy.get('username') and proxy.get('password'):
                        auth = aiohttp.BasicAuth(proxy['username'], proxy['password'])
                        
                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            test_url,
                            proxy=proxy_url,
                            proxy_auth=auth,
                            timeout=10
                        ) as response:
                            if response.status == 200:
                                # 检查匿名性
                                response_ip = await self._get_response_ip(response)
                                anonymous = await self._check_anonymity(response_ip, proxy_url)
                                
                                result = ProxyValidationResult(
                                    is_valid=True,
                                    response_time=(datetime.now() - start_time).total_seconds(),
                                    anonymous=anonymous
                                )
                                self.validation_cache[cache_key] = result
                                return result
                                
                except asyncio.TimeoutError:
                    error_type = 'timeout'
                except aiohttp.ClientConnectorError:
                    error_type = 'connection_error'
                except Exception as e:
                    error_type = 'other'
                    logger.debug(f"Proxy validation error: {str(e)}")
                    
            result = ProxyValidationResult(
                is_valid=False,
                error_type=error_type
            )
            self.validation_cache[cache_key] = result
            return result
            
    async def _get_response_ip(self, response: aiohttp.ClientResponse) -> Optional[str]:
        """Extract IP address from response."""
        try:
            data = await response.json()
            return data.get('ip') or data.get('origin')
        except:
            return None
            
    async def _check_anonymity(self, response_ip: Optional[str], proxy_url: str) -> bool:
        """Check if the proxy is anonymous by comparing IPs."""
        if not response_ip:
            return False
            
        try:
            # 获取真实IP
            async with aiohttp.ClientSession() as session:
                async with session.get('https://api.ipify.org?format=json') as response:
                    data = await response.json()
                    real_ip = data.get('ip')
                    return real_ip != response_ip
        except:
            return False
            
    async def cleanup_validation_cache(self):
        """Clean up expired validation results."""
        now = datetime.now()
        expired = []
        for key, result in self.validation_cache.items():
            if (now - result.last_checked).total_seconds() >= self.validation_ttl:
                expired.append(key)
                
        for key in expired:
            self.validation_cache.pop(key)
            
    async def update_source_stats(self, source: ProxySource, valid_count: int, total_count: int):
        """Update source success rate statistics."""
        if total_count > 0:
            # 使用指数移动平均来平滑统计
            alpha = 0.3  # 平滑因子
            current_rate = valid_count / total_count
            source.success_rate = (alpha * current_rate) + ((1 - alpha) * source.success_rate)
            
            logger.info(
                f"Source {source.name} success rate: {source.success_rate:.2f} "
                f"({valid_count}/{total_count} valid proxies)"
            )
            
    async def get_validated_proxies(self, min_count: int = 10) -> List[Dict]:
        """Get a list of validated proxies."""
        all_proxies = []
        for source in self.sources.values():
            if not source.active:
                continue
                
            proxies = await self.fetch_proxies(source)
            if proxies:
                all_proxies.extend(proxies)
                
        if not all_proxies:
            return []
            
        # 并发验证代理
        validation_tasks = [
            self.validate_proxy(proxy) for proxy in all_proxies
        ]
        results = await asyncio.gather(*validation_tasks)
        
        # 过滤出有效代理并更新源统计
        valid_proxies = []
        source_stats = {}
        for proxy, result in zip(all_proxies, results):
            source_name = proxy.get('source')
            if source_name:
                stats = source_stats.get(source_name, {'valid': 0, 'total': 0})
                stats['total'] += 1
                if result.is_valid:
                    stats['valid'] += 1
                    valid_proxies.append(proxy)
                source_stats[source_name] = stats
                
        # 更新源统计
        for source_name, stats in source_stats.items():
            if source := self.sources.get(source_name):
                await self.update_source_stats(source, stats['valid'], stats['total'])
                
        logger.info(f"Validated {len(valid_proxies)} out of {len(all_proxies)} proxies")
        
        # 如果有效代理数量不足，尝试获取更多
        if len(valid_proxies) < min_count:
            logger.warning(
                f"Only found {len(valid_proxies)} valid proxies, "
                f"minimum required is {min_count}"
            )
            
        return valid_proxies
        
    async def fetch_proxies(self, source: ProxySource) -> List[Dict]:
        """Fetch proxies from a single source."""
        if (
            source.last_fetch
            and datetime.now() - source.last_fetch < timedelta(seconds=source.fetch_interval)
        ):
            logger.debug(f"Skipping fetch for {source.name}, not yet due")
            return []
            
        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method=source.method,
                    url=source.url,
                    headers=source.headers,
                    json=source.data if source.method == 'POST' else None,
                    timeout=source.timeout
                ) as response:
                    if response.status != 200:
                        logger.error(
                            f"Failed to fetch from {source.name}: "
                            f"HTTP {response.status}"
                        )
                        return []
                        
                    if source.parser == 'json':
                        data = await response.json()
                    else:
                        data = await response.text()
                        
                    # 更新最后获取时间
                    source.last_fetch = datetime.now()
                    
                    # 解析代理列表
                    proxies = self._parse_proxies(data, source.parser)
                    logger.info(
                        f"Fetched {len(proxies)} proxies from {source.name}"
                    )
                    return proxies[:source.max_proxies]
                    
        except Exception as e:
            logger.error(f"Error fetching from {source.name}: {str(e)}")
            return []
            
    def _parse_proxies(self, data: any, parser: str) -> List[Dict]:
        """Parse proxies from raw response data."""
        proxies = []
        try:
            if parser == 'json':
                # 假设数据格式为 [{"ip": "1.2.3.4", "port": 8080, ...}, ...]
                if isinstance(data, list):
                    for item in data:
                        proxy = self._normalize_proxy(item)
                        if proxy:
                            proxies.append(proxy)
                            
            elif parser == 'text':
                # 假设格式为每行一个代理，格式：ip:port
                lines = data.split('\n')
                for line in lines:
                    line = line.strip()
                    if ':' in line:
                        ip, port = line.split(':')
                        proxy = self._normalize_proxy({
                            'ip': ip,
                            'port': port
                        })
                        if proxy:
                            proxies.append(proxy)
                            
        except Exception as e:
            logger.error(f"Error parsing proxies: {str(e)}")
            
        return proxies
        
    def _normalize_proxy(self, data: Dict) -> Optional[Dict]:
        """Normalize proxy data to standard format."""
        try:
            # 提取必要字段
            ip = data.get('ip') or data.get('host') or data.get('address')
            port = data.get('port')
            if not ip or not port:
                return None
                
            # 构建标准格式
            proxy = {
                'server': f"{ip}:{port}",
                'username': data.get('username'),
                'password': data.get('password'),
                'protocol': data.get('protocol', 'http'),
                'source': data.get('source'),
                'added_time': datetime.now().isoformat()
            }
            
            return proxy
            
        except Exception:
            return None
            
    async def cleanup_sources(self):
        """Clean up inactive or consistently failing sources."""
        now = datetime.now()
        if (
            self.last_cleanup
            and (now - self.last_cleanup).total_seconds() < self.cleanup_interval
        ):
            return
            
        for source_name, source in list(self.sources.items()):
            if (
                source.last_fetch
                and (now - source.last_fetch).total_seconds() > source.fetch_interval * 3
            ):
                logger.warning(f"Deactivating consistently failing source: {source_name}")
                source.active = False
                
        self.last_cleanup = now
