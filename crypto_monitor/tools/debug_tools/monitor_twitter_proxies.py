"""Monitor proxy performance for Twitter scraping."""
import asyncio
import logging
from datetime import datetime
from proxy_pool import ProxyPool
from config import PROXY_CONFIG

logger = logging.getLogger(__name__)

async def monitor_twitter_proxies():
    """Monitor and report proxy performance for Twitter scraping."""
    proxy_pool = ProxyPool(PROXY_CONFIG)
    
    while True:
        try:
            # 收集统计数据
            total_proxies = len(proxy_pool.proxies)
            banned_proxies = len(proxy_pool.banned_proxies)
            
            # 计算Twitter可用性
            twitter_capable = 0
            high_performance = 0
            
            for proxy_id in proxy_pool.proxies:
                stats = proxy_pool.proxy_stats[proxy_id]
                if hasattr(stats, 'twitter_metrics') and stats.twitter_metrics['success']:
                    twitter_capable += 1
                    if (stats.twitter_metrics['response_time'] < 1.0 and 
                        stats.twitter_metrics['anonymous']):
                        high_performance += 1
            
            # 计算健康指标
            twitter_capable_ratio = twitter_capable / total_proxies if total_proxies > 0 else 0
            high_performance_ratio = high_performance / total_proxies if total_proxies > 0 else 0
            
            # 记录状态
            logger.info(f"""
Proxy Pool Status Report ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})
----------------------------------------
Total Proxies: {total_proxies}
Banned Proxies: {banned_proxies}
Twitter Capable: {twitter_capable} ({twitter_capable_ratio:.1%})
High Performance: {high_performance} ({high_performance_ratio:.1%})
----------------------------------------
            """)
            
            # 检查是否需要触发告警
            if twitter_capable < proxy_pool.config['pool']['min_available_proxies']:
                logger.warning(
                    f"Available Twitter proxies ({twitter_capable}) below minimum threshold "
                    f"({proxy_pool.config['pool']['min_available_proxies']})"
                )
            
            # 等待下一个检查周期
            await asyncio.sleep(proxy_pool.config['pool']['health_check_interval'])
            
        except Exception as e:
            logger.error(f"Error in monitoring loop: {str(e)}")
            await asyncio.sleep(60)  # 错误后等待1分钟再重试

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(monitor_twitter_proxies())
