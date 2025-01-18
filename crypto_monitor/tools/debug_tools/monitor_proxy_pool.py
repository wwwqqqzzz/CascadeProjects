"""Proxy pool monitoring tool."""
import os
import sys
import asyncio
import json
from datetime import datetime
from pathlib import Path

# Add project root to Python path
project_root = str(Path(__file__).parent.parent)
sys.path.append(project_root)

from proxy_pool import ProxyPool
from utils.logger import get_logger

logger = get_logger('proxy_monitor')

class ProxyPoolMonitor:
    """Monitor proxy pool health and performance."""
    
    def __init__(self, log_dir: str = None):
        """Initialize monitor."""
        self.pool = ProxyPool()
        self.log_dir = log_dir or os.path.join(project_root, 'logs', 'proxy_monitor')
        os.makedirs(self.log_dir, exist_ok=True)
        
        # 性能指标阈值
        self.thresholds = {
            'min_available_proxies': 10,
            'min_health_score': 0.3,
            'min_success_rate': 0.5
        }
        
        # 统计数据
        self.stats_history = []
        self.alert_count = 0
        self.last_alert_time = None
        
    async def initialize(self):
        """Initialize proxy pool."""
        logger.info("Initializing proxy pool monitor")
        await self.pool.initialize()
        
    def save_stats(self, stats: dict):
        """Save stats to JSON file."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = os.path.join(self.log_dir, f'proxy_stats_{timestamp}.json')
        
        with open(filename, 'w') as f:
            json.dump(stats, f, indent=2)
            
    def check_alerts(self, stats: dict) -> list:
        """Check if any metrics trigger alerts."""
        alerts = []
        
        if stats['available_proxies'] < self.thresholds['min_available_proxies']:
            alerts.append(
                f"Low proxy count: {stats['available_proxies']} "
                f"(threshold: {self.thresholds['min_available_proxies']})"
            )
            
        if stats['average_health_score'] < self.thresholds['min_health_score']:
            alerts.append(
                f"Low health score: {stats['average_health_score']:.2f} "
                f"(threshold: {self.thresholds['min_health_score']})"
            )
            
        return alerts
        
    def log_alerts(self, alerts: list):
        """Log alerts with proper handling of alert frequency."""
        now = datetime.now()
        
        # 如果是第一次告警或距离上次告警超过1小时
        if (
            not self.last_alert_time
            or (now - self.last_alert_time).total_seconds() > 3600
        ):
            for alert in alerts:
                logger.warning(f"ALERT: {alert}")
            self.last_alert_time = now
            self.alert_count += 1
        
    async def monitor_loop(self):
        """Main monitoring loop."""
        logger.info("Starting proxy pool monitoring")
        
        while True:
            try:
                # 获取代理池统计信息
                stats = await self.pool.get_pool_stats()
                
                # 添加时间戳
                stats['timestamp'] = datetime.now().isoformat()
                self.stats_history.append(stats)
                
                # 保持历史记录在合理范围内
                if len(self.stats_history) > 1000:
                    self.stats_history = self.stats_history[-1000:]
                    
                # 检查告警条件
                alerts = self.check_alerts(stats)
                if alerts:
                    self.log_alerts(alerts)
                    
                # 每小时保存一次统计数据
                if len(self.stats_history) % 12 == 0:  # 每12次检查（1小时）保存一次
                    self.save_stats({
                        'current': stats,
                        'history': self.stats_history[-12:]  # 保存最近1小时的数据
                    })
                    
                # 打印当前状态
                logger.info(
                    f"Proxy Pool Status:\n"
                    f"  Total Proxies: {stats['total_proxies']}\n"
                    f"  Available Proxies: {stats['available_proxies']}\n"
                    f"  Banned Proxies: {stats['banned_proxies']}\n"
                    f"  Average Health Score: {stats['average_health_score']:.2f}\n"
                    f"  Load Level: {stats['load_level']}"
                )
                
                # 等待5分钟
                await asyncio.sleep(300)
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {str(e)}")
                await asyncio.sleep(60)  # 发生错误时等待较短时间
                
async def main():
    """Main entry point."""
    monitor = ProxyPoolMonitor()
    await monitor.initialize()
    await monitor.monitor_loop()
    
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Monitoring stopped by user")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        sys.exit(1)
