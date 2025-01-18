"""Debug tool for proxy validation"""
import asyncio
import logging
import json
import argparse
import sys
import socket
import aiohttp
import dns.resolver  # 添加 DNS 解析器
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple, ClassVar
from urllib.parse import urlparse
from dataclasses import dataclass, asdict
import yaml
import psutil
import time

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

# 更新导入语句以匹配实际的项目结构
from twitter_proxy_validator import TwitterProxyValidator
from config import PROXY_CONFIG
from utils.logger import get_logger
from proxy_pool import ProxyPool

# 创建 logs 目录（如果不存在）
LOGS_DIR = PROJECT_ROOT / 'logs'
LOGS_DIR.mkdir(exist_ok=True)

# 配置日志
logger = get_logger('ProxyValidatorDebug')

@dataclass
class ProxyStats:
    """代理统计信息"""
    total_tests: int = 0
    successful_tests: int = 0
    failed_tests: int = 0
    avg_response_time: float = 0.0
    errors_by_type: Dict[str, int] = None
    memory_usage: Dict[str, float] = None
    cpu_usage: Dict[str, float] = None
    start_time: float = None
    
    # 性能监控阈值
    MEMORY_THRESHOLD: ClassVar[float] = 85.0  # 内存使用率警告阈值
    CPU_THRESHOLD: ClassVar[float] = 80.0     # CPU 使用率警告阈值

    def __post_init__(self):
        self.errors_by_type = {}
        self.memory_usage = {}
        self.cpu_usage = {}
        self.start_time = time.time()
        self._last_warning_time = 0
        self._warning_interval = 300  # 5分钟内不重复警告

    def update(self, success: bool, duration: float, error: str = None):
        """更新统计信息"""
        self.total_tests += 1
        if success:
            self.successful_tests += 1
            self.avg_response_time = (
                (self.avg_response_time * (self.successful_tests - 1) + duration)
                / self.successful_tests
            )
        else:
            self.failed_tests += 1
            if error:
                self.errors_by_type[error] = self.errors_by_type.get(error, 0) + 1
        
        # 更新系统资源使用情况
        self._update_resource_usage()
        
        # 检查资源使用是否超过阈值
        self._check_resource_thresholds()

    def _update_resource_usage(self):
        """更新系统资源使用情况"""
        process = psutil.Process()
        
        # 内存使用
        mem_info = process.memory_info()
        self.memory_usage.update({
            'rss': mem_info.rss / 1024 / 1024,  # RSS (MB)
            'vms': mem_info.vms / 1024 / 1024,  # VMS (MB)
            'percent': process.memory_percent(),
            'system_percent': psutil.virtual_memory().percent
        })
        
        # CPU 使用
        self.cpu_usage.update({
            'process': process.cpu_percent(),
            'system': psutil.cpu_percent(),
            'threads': len(process.threads())
        })

    def _check_resource_thresholds(self):
        """检查资源使用是否超过阈值"""
        current_time = time.time()
        if current_time - self._last_warning_time < self._warning_interval:
            return

        # 检查内存使用
        if self.memory_usage['system_percent'] > self.MEMORY_THRESHOLD:
            logger.warning(f"""
内存使用警告:
----------------------------------------
系统内存使用率: {self.memory_usage['system_percent']:.1f}%
进程内存使用: {self.memory_usage['rss']:.1f}MB
建议:
- 考虑减少并发数
- 检查是否存在内存泄漏
- 可能需要清理系统内存
----------------------------------------
            """)
            self._last_warning_time = current_time

        # 检查 CPU 使用
        if self.cpu_usage['system'] > self.CPU_THRESHOLD:
            logger.warning(f"""
CPU 使用警告:
----------------------------------------
系统 CPU 使用率: {self.cpu_usage['system']:.1f}%
进程 CPU 使用率: {self.cpu_usage['process']:.1f}%
活动线程数: {self.cpu_usage['threads']}
建议:
- 考虑降低并发数
- 检查是否有 CPU 密集任务
- 可能需要优化代码性能
----------------------------------------
            """)
            self._last_warning_time = current_time

    def get_summary(self) -> Dict[str, Any]:
        """获取统计摘要"""
        return {
            'total_tests': self.total_tests,
            'successful_tests': self.successful_tests,
            'failed_tests': self.failed_tests,
            'success_rate': (self.successful_tests / self.total_tests * 100) if self.total_tests > 0 else 0,
            'avg_response_time': self.avg_response_time,
            'errors_by_type': self.errors_by_type,
            'memory_usage': self.memory_usage,
            'cpu_usage': self.cpu_usage,
            'duration': time.time() - self.start_time
        }

class ProxyValidatorDebug:
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or PROXY_CONFIG
        self.load_protocol_config()
        self.dns_servers = ['8.8.8.8', '1.1.1.1']
        self.validator = TwitterProxyValidator(config=self.config)
        self.proxy_pool = ProxyPool(self.config)
        self._init_protocol_handlers()
        self.stats = ProxyStats()
        
        # 初始化 DNS 缓存
        self._dns_cache = {}
        self._dns_cache_ttl = 300  # 5分钟
        
        # 动态并发控制
        self._concurrent_limit = 5
        self._last_adjust_time = time.time()
        self._adjust_interval = 60  # 1分钟调整一次

    def load_protocol_config(self):
        """从配置文件加载协议配置"""
        config_path = PROJECT_ROOT / 'config' / 'protocols.yaml'
        try:
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    self.SUPPORTED_PROTOCOLS = yaml.safe_load(f)
            else:
                # 使用默认配置
                self.SUPPORTED_PROTOCOLS = {
                    'http': {
                        'port': 80,
                        'test_url': 'http://www.google.com',
                        'timeout': 5,
                        'retry_count': 3,
                        'retry_delay': 1,
                        'priority': 1
                    },
                    'https': {
                        'port': 443,
                        'test_url': 'https://www.google.com',
                        'timeout': 5,
                        'retry_count': 3,
                        'retry_delay': 1,
                        'verify_ssl': False,
                        'priority': 2
                    },
                    'socks4': {
                        'port': 1080,
                        'test_url': 'http://www.google.com',
                        'timeout': 5,
                        'retry_count': 2,
                        'retry_delay': 2,
                        'priority': 3
                    },
                    'socks5': {
                        'port': 1080,
                        'test_url': 'http://www.google.com',
                        'timeout': 5,
                        'retry_count': 2,
                        'retry_delay': 2,
                        'priority': 4
                    }
                }
                # 保存默认配置
                with open(config_path, 'w', encoding='utf-8') as f:
                    yaml.safe_dump(self.SUPPORTED_PROTOCOLS, f, allow_unicode=True)
                    
        except Exception as e:
            logger.error(f"加载协议配置失败: {str(e)}, 使用默认配置")

    def _init_protocol_handlers(self):
        """初始化不同协议的处理器"""
        self.protocol_handlers = {
            'http': self._test_http_proxy,
            'https': self._test_https_proxy,
            'socks4': self._test_socks_proxy,
            'socks5': self._test_socks_proxy
        }

    async def _test_http_proxy(self, proxy_url: str, timeout: int = 5) -> Tuple[bool, str]:
        """测试 HTTP 代理"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.SUPPORTED_PROTOCOLS['http']['test_url'],
                    proxy=proxy_url,
                    timeout=timeout
                ) as response:
                    if response.status == 200:
                        return True, "HTTP 代理连接成功"
                    return False, f"HTTP 代理响应异常: {response.status}"
        except aiohttp.ClientProxyConnectionError as e:
            return False, f"HTTP 代理连接失败: {str(e)}"
        except Exception as e:
            return False, f"HTTP 代理测试失败: {str(e)}"

    async def _test_https_proxy(self, proxy_url: str, timeout: int = 5) -> Tuple[bool, str]:
        """测试 HTTPS 代理"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.SUPPORTED_PROTOCOLS['https']['test_url'],
                    proxy=proxy_url,
                    timeout=timeout,
                    ssl=False  # 禁用 SSL 验证以测试 HTTPS 代理
                ) as response:
                    if response.status == 200:
                        return True, "HTTPS 代理连接成功"
                    return False, f"HTTPS 代理响应异常: {response.status}"
        except aiohttp.ClientSSLError:
            return False, "HTTPS 代理 SSL 验证失败"
        except Exception as e:
            return False, f"HTTPS 代理测试失败: {str(e)}"

    async def _test_socks_proxy(self, proxy_url: str, timeout: int = 5) -> Tuple[bool, str]:
        """测试 SOCKS 代理"""
        try:
            import aiosocks
            proxy_host, proxy_port, protocol = self._parse_proxy_url(proxy_url)
            
            # 确定 SOCKS 版本
            proxy_type = aiosocks.SOCKS5 if protocol == 'socks5' else aiosocks.SOCKS4
            
            # 测试连接
            try:
                await asyncio.wait_for(
                    aiosocks.create_connection(
                        lambda: asyncio.Protocol(),
                        proxy=(proxy_host, proxy_port),
                        dst=(urlparse(self.SUPPORTED_PROTOCOLS[protocol]['test_url']).netloc, 80),
                        proxy_type=proxy_type,
                    ),
                    timeout=timeout
                )
                return True, f"{protocol.upper()} 代理连接成功"
            except asyncio.TimeoutError:
                return False, f"{protocol.upper()} 代理连接超时"
            except Exception as e:
                return False, f"{protocol.upper()} 代理连接失败: {str(e)}"
        except ImportError:
            return False, f"缺少 SOCKS 支持库，请安装 aiosocks"
        except Exception as e:
            return False, f"SOCKS 代理测试失败: {str(e)}"

    async def test_proxy_protocol(self, proxy_url: str, protocol: str) -> Tuple[bool, str]:
        """测试特定协议的代理连接"""
        if protocol not in self.protocol_handlers:
            return False, f"不支持的协议: {protocol}"
            
        handler = self.protocol_handlers[protocol]
        return await handler(proxy_url)

    def _handle_protocol_error(self, proxy_url: str, protocol: str, error_msg: str) -> str:
        """处理协议相关错误并提供具体建议"""
        error_patterns = {
            'timeout': {
                'pattern': 'timeout',
                'message': f"""
{protocol.upper()} 代理超时:
----------------------------------------
代理: {proxy_url}
错误: {error_msg}
建议:
1. 检查代理服务器是否响应过慢
2. 考虑增加超时时间
3. 确认代理服务器负载是否过高
----------------------------------------
                """
            },
            'connection': {
                'pattern': 'connection',
                'message': f"""
{protocol.upper()} 代理连接错误:
----------------------------------------
代理: {proxy_url}
错误: {error_msg}
建议:
1. 确认代理服务器是否支持 {protocol.upper()} 协议
2. 检查防火墙设置是否允许该协议
3. 验证代理服务器配置是否正确
----------------------------------------
                """
            },
            'ssl': {
                'pattern': 'ssl',
                'message': f"""
HTTPS 代理 SSL 错误:
----------------------------------------
代理: {proxy_url}
错误: {error_msg}
建议:
1. 检查代理服务器的 SSL 证书
2. 确认是否需要特殊的 SSL 配置
3. 考虑使用自签名证书
----------------------------------------
                """
            }
        }

        for pattern, info in error_patterns.items():
            if pattern in error_msg.lower():
                return info['message']

        return f"""
{protocol.upper()} 代理未知错误:
----------------------------------------
代理: {proxy_url}
错误: {error_msg}
建议:
1. 检查代理服务器状态
2. 验证网络连接
3. 查看代理服务器日志
----------------------------------------
        """

    def _is_ip_address(self, host: str) -> bool:
        """检查是否为 IP 地址"""
        try:
            socket.inet_aton(host)
            return True
        except socket.error:
            return False

    def _is_local_address(self, host: str) -> bool:
        """检查是否为本地地址"""
        return host in ('localhost', '127.0.0.1', '::1')

    async def check_dns_resolution(self, hostname: str) -> Tuple[bool, str]:
        """测试 DNS 解析，带缓存"""
        # 检查是否为 IP 地址或本地地址
        if self._is_ip_address(hostname) or self._is_local_address(hostname):
            return True, f"无需 DNS 解析: {hostname}"

        # 检查缓存
        cache_key = f"{hostname}"
        if cache_key in self._dns_cache:
            cache_time, result = self._dns_cache[cache_key]
            if time.time() - cache_time < self._dns_cache_ttl:
                return result

        try:
            resolver = dns.resolver.Resolver()
            resolver.nameservers = [socket.gethostbyname(dns) for dns in self.dns_servers]
            answers = resolver.resolve(hostname)
            ip_addresses = [str(answer) for answer in answers]
            result = (True, f"DNS 解析成功: {', '.join(ip_addresses)}")
            
            # 更新缓存
            self._dns_cache[cache_key] = (time.time(), result)
            return result
        except Exception as e:
            result = (False, f"DNS 解析失败: {str(e)}")
            self._dns_cache[cache_key] = (time.time(), result)
            return result

    def _parse_proxy_url(self, proxy_url: str) -> Tuple[str, int, str]:
        """解析代理URL获取主机、端口和协议"""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(proxy_url)
            protocol = parsed.scheme or 'http'
            if protocol not in self.SUPPORTED_PROTOCOLS:
                raise ValueError(f"不支持的代理协议: {protocol}")
            
            host = parsed.hostname
            port = parsed.port or self.SUPPORTED_PROTOCOLS[protocol]
            return host, port, protocol
        except Exception as e:
            raise ValueError(f"无效的代理URL格式: {proxy_url}, 错误: {str(e)}")

    async def check_proxy_connection(self, proxy_url: str) -> Tuple[bool, str, Dict[str, Any]]:
        """增强的代理连接测试"""
        try:
            proxy_host, proxy_port, protocol = self._parse_proxy_url(proxy_url)
            
            # 检查是否为本地地址或 IP 地址
            is_local = self._is_local_address(proxy_host)
            is_ip = self._is_ip_address(proxy_host)
            
            if not (is_local or is_ip):
                dns_ok, dns_msg = await self.check_dns_resolution(proxy_host)
                if not dns_ok:
                    return False, dns_msg, {
                        "dns_error": True,
                        "protocol": protocol
                    }

            # 测试协议支持
            protocol_ok, protocol_msg = await self.test_proxy_protocol(proxy_url, protocol)
            if not protocol_ok:
                return False, protocol_msg, {
                    "protocol_error": True,
                    "protocol": protocol
                }

            # TCP 连接测试
            try:
                start_time = datetime.now()
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(proxy_host, proxy_port),
                    timeout=5
                )
                connect_time = (datetime.now() - start_time).total_seconds()
                writer.close()
                await writer.wait_closed()
                
                return True, f"代理连接成功 (连接时间: {connect_time:.3f}秒)", {
                    "connect_time": connect_time,
                    "is_local": is_local,
                    "is_ip": is_ip,
                    "protocol": protocol
                }
            except asyncio.TimeoutError:
                return False, "代理连接超时", {"timeout": True, "protocol": protocol}
            except ConnectionRefusedError:
                return False, "代理连接被拒绝", {"connection_refused": True, "protocol": protocol}
            except Exception as e:
                return False, f"代理连接失败: {str(e)}", {"error": str(e), "protocol": protocol}
                
        except Exception as e:
            return False, f"代理连接测试失败: {str(e)}", {"error": str(e)}

    async def test_proxy_latency(self, proxy_url: str) -> Optional[float]:
        """测试代理延迟"""
        try:
            start_time = datetime.now()
            async with aiohttp.ClientSession() as session:
                async with session.get('http://www.google.com', 
                                     proxy=proxy_url, 
                                     timeout=5) as response:
                    await response.text()
            duration = (datetime.now() - start_time).total_seconds()
            return duration
        except:
            return None

    async def test_single_proxy(self, proxy_url: str, retries: int = 1) -> Dict[str, Any]:
        """测试单个代理的详细性能"""
        logger.info(f"开始测试代理: {proxy_url} (重试次数: {retries})")
        start_time = datetime.now()
        
        try:
            # 增强的连接测试
            connection_ok, conn_msg, conn_details = await self.check_proxy_connection(proxy_url)
            if not connection_ok:
                self._handle_connection_error(proxy_url, conn_msg, conn_details)
                return {
                    "success": False,
                    "error": conn_msg,
                    "duration": 0,
                    "timestamp": datetime.now().isoformat(),
                    "attempts": 0,
                    "connection_details": conn_details
                }

            # 测试代理延迟
            latency = await self.test_proxy_latency(proxy_url)
            if latency is not None:
                logger.info(f"代理延迟: {latency:.3f}秒")

            success = False
            metrics = {}
            last_error = None
            
            for attempt in range(retries):
                try:
                    logger.debug(f"尝试验证代理 (attempt {attempt + 1}/{retries})")
                    success, metrics = await self.validator.validate_proxy(proxy_url)
                    
                    if success:
                        logger.info(f"代理验证成功 (attempt {attempt + 1})")
                        break
                    
                    last_error = metrics.get('error', 'Unknown error')
                    self._handle_validation_error(proxy_url, last_error, attempt + 1, retries)
                    
                    if attempt < retries - 1:
                        wait_time = min(2 ** attempt, 10)  # 指数退避，最大等待10秒
                        logger.info(f"等待 {wait_time} 秒后重试... ({attempt + 1}/{retries})")
                        await asyncio.sleep(wait_time)
                        
                except Exception as e:
                    last_error = str(e)
                    logger.error(f"验证过程出错 (attempt {attempt + 1}): {last_error}")
                    if attempt < retries - 1:
                        await asyncio.sleep(2)
                    else:
                        raise

            duration = (datetime.now() - start_time).total_seconds()
            
            result = {
                "success": success,
                "metrics": metrics,
                "duration": duration,
                "timestamp": datetime.now().isoformat(),
                "attempts": attempt + 1,
                "last_error": last_error if not success else None,
                "latency": latency,
                "connection_test": {
                    "success": connection_ok,
                    "message": conn_msg
                }
            }
            
            self._print_test_result(proxy_url, result)
            return result
            
        except Exception as e:
            logger.error(f"测试过程中发生错误: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "duration": (datetime.now() - start_time).total_seconds(),
                "timestamp": datetime.now().isoformat(),
                "attempts": retries
            }

    def _handle_validation_error(self, proxy_url: str, error: str, attempt: int, retries: int):
        """处理验证错误并提供诊断信息"""
        if 'timeout' in str(error).lower():
            logger.error(f"""
超时错误诊断:
----------------------------------------
代理: {proxy_url}
尝试次数: {attempt}/{retries}
错误类型: 超时
可能原因:
1. 代理响应时间过长
2. 网络连接不稳定
3. 目标服务器响应慢
建议:
- 检查代理服务器状态
- 考虑增加超时时间
- 确认代理支持访问目标URL
----------------------------------------
            """)
        elif 'connection' in str(error).lower():
            logger.error(f"""
连接错误诊断:
----------------------------------------
代理: {proxy_url}
尝试次数: {attempt}/{retries}
错误类型: 连接错误
可能原因:
1. 代理服务器离线
2. 代理配置错误
3. 网络防火墙限制
建议:
- 验证代理服务器是否在线
- 检查代理配置是否正确
- 确认网络访问权限
----------------------------------------
            """)
        else:
            logger.error(f"""
未知错误诊断:
----------------------------------------
代理: {proxy_url}
尝试次数: {attempt}/{retries}
错误类型: {error}
建议:
- 检查错误日志获取详细信息
- 验证代理配置
- 尝试使用其他代理
----------------------------------------
            """)

    def _print_test_result(self, proxy_url: str, result: Dict[str, Any]):
        """打印格式化的测试结果"""
        metrics = result.get('metrics', {})
        logger.info(f"""
代理测试结果:
----------------------------------------
代理: {proxy_url}
验证结果: {'✅ 成功' if result['success'] else '❌ 失败'}
尝试次数: {result.get('attempts', 1)}
总耗时: {result['duration']:.2f}秒
代理延迟: {result.get('latency', 'N/A')}秒

连接测试:
- 状态: {'✅ 成功' if result.get('connection_test', {}).get('success', False) else '❌ 失败'}
- 信息: {result.get('connection_test', {}).get('message', 'N/A')}

详细信息:
- Twitter可访问: {metrics.get('twitter_accessible', False)}
- API可访问: {metrics.get('api_accessible', False)}
- 匿名性: {metrics.get('anonymous', False)}
- 响应时间: {metrics.get('response_time', 'N/A')}

错误信息:
- 最后错误: {result.get('last_error', 'N/A')}
- 验证错误: {metrics.get('error', 'N/A')}
- 验证URL: {metrics.get('validation_urls', [])}
----------------------------------------
        """)
    
    async def batch_test_proxies(self, proxy_urls: List[str], concurrent_limit: int = 5, retries: int = 1) -> Dict[str, Any]:
        """批量测试代理，使用队列控制并发"""
        logger.info(f"开始批量测试 {len(proxy_urls)} 个代理 (并发数: {concurrent_limit})")
        
        # 创建任务队列
        queue = asyncio.Queue()
        for url in proxy_urls:
            queue.put_nowait(url)
            
        # 创建工作协程
        async def worker():
            while True:
                try:
                    # 动态调整并发数
                    await self._adjust_concurrent_limit()
                    
                    proxy_url = await queue.get()
                    try:
                        result = await self.test_single_proxy(proxy_url, retries)
                    except Exception as e:
                        logger.error(f"测试代理 {proxy_url} 时发生错误: {str(e)}")
                        result = {
                            'success': False,
                            'error': str(e),
                            'proxy_url': proxy_url
                        }
                    finally:
                        queue.task_done()
                        return result
                except asyncio.CancelledError:
                    break
                    
        # 创建工作任务
        tasks = []
        for _ in range(min(self._concurrent_limit, len(proxy_urls))):
            task = asyncio.create_task(worker())
            tasks.append(task)
            
        # 等待所有任务完成
        await queue.join()
        
        # 取消剩余任务
        for task in tasks:
            task.cancel()
            
        # 等待任务取消
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理结果
        valid_results = [r for r in results if isinstance(r, dict)]
        error_results = [r for r in results if isinstance(r, Exception)]
        
        # 计算统计信息
        summary = {
            "total_proxies": len(proxy_urls),
            "successful_proxies": sum(1 for r in valid_results if r.get('success', False)),
            "failed_proxies": len(proxy_urls) - sum(1 for r in valid_results if r.get('success', False)),
            "error_count": len(error_results),
            "performance_stats": self.stats.get_summary(),
            "results": valid_results,
            "errors": [str(e) for e in error_results]
        }
        
        self._print_batch_summary(summary)
        return summary
    
    def _print_batch_summary(self, summary: Dict[str, Any]):
        """打印批量测试汇总信息"""
        logger.info(f"""
批量测试汇总:
----------------------------------------
总代理数: {summary['total_proxies']}
成功数量: {summary['successful_proxies']}
成功率: {summary['success_rate']:.1%}
平均耗时: {summary['average_duration']:.2f}秒
总耗时: {summary['total_duration']:.2f}秒
并发数: {summary['concurrent_limit']}
重试次数: {summary['retries']}
----------------------------------------
        """)
    
    async def load_proxies_from_pool(self) -> List[str]:
        """从代理池加载代理"""
        proxies = []
        async for proxy in self.proxy_pool.get_all_proxies():
            proxies.append(proxy['url'])
        return proxies

    def _handle_connection_error(self, proxy_url: str, error_msg: str, details: Dict[str, Any]):
        """处理连接错误并提供详细诊断"""
        protocol = details.get("protocol", "unknown")
        if details.get("protocol_error"):
            logger.error(f"""
协议错误诊断:
----------------------------------------
代理: {proxy_url}
协议: {protocol}
错误: {error_msg}
建议:
- 确认代理服务器支持 {protocol} 协议
- 检查代理配置是否正确
- 尝试使用其他协议
----------------------------------------
            """)
        elif details.get("dns_error"):
            proxy_host = self._parse_proxy_url(proxy_url)[0]
            if self._is_local_address(proxy_host):
                logger.error(f"""
本地代理连接错误:
----------------------------------------
代理: {proxy_url}
错误: {error_msg}
建议:
- 确认本地代理服务是否已启动
- 检查端口号是否正确
- 验证代理服务配置
----------------------------------------
                """)
            else:
                logger.error(f"""
DNS 解析错误诊断:
----------------------------------------
代理: {proxy_url}
错误: {error_msg}
可能原因:
1. DNS 服务器无法解析代理主机名
2. 代理地址格式错误
3. 网络 DNS 配置问题
建议:
- 检查代理地址是否正确
- 尝试使用 IP 地址而不是主机名
- 检查 DNS 服务器配置
- 尝试更换 DNS 服务器
----------------------------------------
                """)
        elif details.get("timeout"):
            logger.error(f"""
连接超时诊断:
----------------------------------------
代理: {proxy_url}
错误: 连接超时
可能原因:
1. 代理服务器响应过慢
2. 网络延迟过高
3. 代理服务器可能已关闭
建议:
- 检查代理服务器状态
- 尝试增加超时时间
- 检查网络连接质量
----------------------------------------
            """)
        elif details.get("connection_refused"):
            logger.error(f"""
连接被拒绝诊断:
----------------------------------------
代理: {proxy_url}
错误: 连接被拒绝
可能原因:
1. 代理服务器未运行
2. 端口号错误
3. 防火墙阻止
建议:
- 验证代理服务器是否在运行
- 检查端口号是否正确
- 检查防火墙设置
----------------------------------------
            """)
        else:
            logger.error(f"""
未知连接错误诊断:
----------------------------------------
代理: {proxy_url}
错误: {error_msg}
详细信息: {details}
建议:
- 检查代理配置
- 验证网络连接
- 尝试使用其他代理
----------------------------------------
            """)

    async def test_proxy_with_retry(self, proxy_url: str, protocol: str) -> Tuple[bool, str, Dict[str, Any]]:
        """带重试机制的代理测试"""
        protocol_config = self.SUPPORTED_PROTOCOLS[protocol]
        retry_count = protocol_config['retry_count']
        retry_delay = protocol_config['retry_delay']
        timeout = protocol_config['timeout']
        
        for attempt in range(retry_count):
            try:
                start_time = datetime.now()
                success, msg = await self.protocol_handlers[protocol](proxy_url, timeout)
                duration = (datetime.now() - start_time).total_seconds()
                
                if success:
                    self._update_stats(True, duration, protocol)
                    return True, msg, {
                        'protocol': protocol,
                        'duration': duration,
                        'attempts': attempt + 1
                    }
                
                if attempt < retry_count - 1:
                    logger.debug(f"代理测试失败 (尝试 {attempt + 1}/{retry_count}): {msg}")
                    await asyncio.sleep(retry_delay)
                    
            except Exception as e:
                if attempt < retry_count - 1:
                    logger.debug(f"代理测试出错 (尝试 {attempt + 1}/{retry_count}): {str(e)}")
                    await asyncio.sleep(retry_delay)
                else:
                    self._update_stats(False, 0, protocol, str(e))
                    return False, str(e), {
                        'protocol': protocol,
                        'error': str(e),
                        'attempts': attempt + 1
                    }
        
        self._update_stats(False, 0, protocol, msg)
        return False, msg, {
            'protocol': protocol,
            'error': msg,
            'attempts': retry_count
        }

    def _update_stats(self, success: bool, duration: float, protocol: str, error: str = None):
        """更新性能统计"""
        self.stats['total_tests'] += 1
        if success:
            self.stats['successful_tests'] += 1
            # 更新平均响应时间
            self.stats['avg_response_time'] = (
                (self.stats['avg_response_time'] * (self.stats['successful_tests'] - 1) + duration)
                / self.stats['successful_tests']
            )
        else:
            self.stats['failed_tests'] += 1
            if error:
                self.stats['errors_by_type'][error] = self.stats['errors_by_type'].get(error, 0) + 1

    async def _adjust_concurrent_limit(self):
        """动态调整并发数"""
        current_time = time.time()
        if current_time - self._last_adjust_time < self._adjust_interval:
            return

        cpu_usage = self.stats.cpu_usage.get('system', 0)
        mem_usage = self.stats.memory_usage.get('system_percent', 0)

        # 根据资源使用情况调整并发数
        if cpu_usage > 80 or mem_usage > 85:
            self._concurrent_limit = max(2, self._concurrent_limit - 1)
            logger.info(f"资源使用率较高，降低并发数至: {self._concurrent_limit}")
        elif cpu_usage < 50 and mem_usage < 70:
            self._concurrent_limit = min(10, self._concurrent_limit + 1)
            logger.info(f"资源使用率较低，增加并发数至: {self._concurrent_limit}")

        self._last_adjust_time = current_time

async def main():
    parser = argparse.ArgumentParser(description='代理验证调试工具')
    parser.add_argument('--proxy', help='单个代理URL进行测试')
    parser.add_argument('--file', help='包含代理列表的文件')
    parser.add_argument('--pool', action='store_true', help='测试代理池中的所有代理')
    parser.add_argument('--concurrent', type=int, default=5, help='并发测试数量')
    parser.add_argument('--retries', type=int, default=1, help='每个代理的重试次数')
    parser.add_argument('--output', help='测试结果输出文件')
    
    args = parser.parse_args()
    debug_tool = ProxyValidatorDebug()
    
    if args.proxy:
        # 测试单个代理
        await debug_tool.test_single_proxy(args.proxy, args.retries)
    else:
        # 获取要测试的代理列表
        proxy_urls = []
        if args.file:
            try:
                with open(args.file, encoding='utf-8') as f:
                    # 过滤掉空行和注释行
                    proxy_urls = [
                        line.strip() 
                        for line in f 
                        if line.strip() and not line.strip().startswith('#')
                    ]
                logger.info(f"从文件加载了 {len(proxy_urls)} 个代理")
            except Exception as e:
                logger.error(f"读取代理文件失败: {str(e)}")
                return
        elif args.pool:
            proxy_urls = await debug_tool.load_proxies_from_pool()
        else:
            proxy_urls = [
                "http://127.0.0.1:8080",
                "http://localhost:8080"
            ]
        
        if not proxy_urls:
            logger.warning("没有找到要测试的代理")
            return
            
        # 执行批量测试
        summary = await debug_tool.batch_test_proxies(
            proxy_urls,
            concurrent_limit=args.concurrent,
            retries=args.retries
        )
        
        # 保存测试结果
        if args.output:
            output_file = args.output
        else:
            output_file = f'proxy_test_results_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(summary, f, indent=2, ensure_ascii=False)
            logger.info(f"测试结果已保存到: {output_path}")
        except Exception as e:
            logger.error(f"保存测试结果失败: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main()) 







#     # 测试单个代理
# python proxy_validator_debug.py --proxy http://test-proxy:8080 --retries 3

# # 测试文件中的代理列表
# python proxy_validator_debug.py --file proxies.txt --concurrent 10 --retries 2

# # 测试代理池中的所有代理
# python proxy_validator_debug.py --pool --concurrent 5 --output results/test_results.json