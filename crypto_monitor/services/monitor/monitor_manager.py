"""
实时监控管理器，负责数据源监控和任务调度
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, List
from ...utils.config import TRADING_CONFIG, BINANCE_CONFIG
from ..trading.trading_manager import TradingManager
from ..twitter.twitter_scraper import TwitterScraper

logger = logging.getLogger(__name__)

class MonitorManager:
    """实时监控管理器"""
    
    def __init__(self):
        self.trading_manager = TradingManager(
            api_key=BINANCE_CONFIG['api_key'],
            api_secret=BINANCE_CONFIG['api_secret'],
            keywords=TRADING_CONFIG.get('keywords', ['buy', 'sell'])  # 默认关键词
        )
        self.twitter_scraper = TwitterScraper()
        self._running = False
        self.performance_metrics = {
            'response_times': [],  # 响应时间记录
            'processing_times': [], # 处理时间记录
            'error_count': 0,      # 错误计数
            'success_count': 0     # 成功计数
        }
        self.max_metrics_length = 1000  # 最大指标记录数
        self.last_tweet_id = None  # 记录最后处理的推文ID
        self._monitor_task = None  # 监控任务
        
    async def _fetch_data(self) -> Optional[Dict]:
        """获取实时数据"""
        start_time = datetime.now()
        try:
            # 获取目标用户的最新推文
            tweets = await self.twitter_scraper.get_user_tweets(
                username=TRADING_CONFIG['target_user'],
                max_tweets=5  # 每次获取最新的5条推文
            )
            
            # 记录响应时间
            response_time = (datetime.now() - start_time).total_seconds()
            self.performance_metrics['response_times'].append(response_time)
            
            # 维护指标列表大小
            if len(self.performance_metrics['response_times']) > self.max_metrics_length:
                self.performance_metrics['response_times'] = self.performance_metrics['response_times'][-self.max_metrics_length:]
            
            # 过滤出新推文
            if tweets:
                new_tweets = []
                for tweet in tweets:
                    tweet_id = tweet['url'].split('/')[-1]
                    if self.last_tweet_id is None or tweet_id > self.last_tweet_id:
                        new_tweets.append(tweet)
                        
                if new_tweets:
                    self.last_tweet_id = new_tweets[0]['url'].split('/')[-1]  # 更新最后处理的推文ID
                    self.performance_metrics['success_count'] += 1
                    return {'tweets': new_tweets}
            
            return None
            
        except Exception as e:
            logger.error(f"数据获取错误: {str(e)}")
            self.performance_metrics['error_count'] += 1
            return None
            
    async def _process_data(self, data: Dict):
        """处理获取的数据"""
        start_time = datetime.now()
        try:
            if 'tweets' in data:
                for tweet in data['tweets']:
                    # 通过交易管理器处理推文
                    await self.trading_manager.process_tweet(tweet)
            
            # 记录处理时间
            processing_time = (datetime.now() - start_time).total_seconds()
            self.performance_metrics['processing_times'].append(processing_time)
            
            # 维护指标列表大小
            if len(self.performance_metrics['processing_times']) > self.max_metrics_length:
                self.performance_metrics['processing_times'] = self.performance_metrics['processing_times'][-self.max_metrics_length:]
                
        except Exception as e:
            logger.error(f"数据处理错误: {str(e)}")
            self.performance_metrics['error_count'] += 1
            
    def get_performance_stats(self) -> Dict:
        """获取性能统计信息"""
        if not self.performance_metrics['response_times']:
            return {
                'avg_response_time': 0,
                'avg_processing_time': 0,
                'error_rate': 0,
                'success_rate': 0
            }
            
        total_operations = self.performance_metrics['success_count'] + self.performance_metrics['error_count']
        
        return {
            'avg_response_time': sum(self.performance_metrics['response_times']) / len(self.performance_metrics['response_times']),
            'avg_processing_time': sum(self.performance_metrics['processing_times']) / len(self.performance_metrics['processing_times']) if self.performance_metrics['processing_times'] else 0,
            'error_rate': self.performance_metrics['error_count'] / total_operations if total_operations > 0 else 0,
            'success_rate': self.performance_metrics['success_count'] / total_operations if total_operations > 0 else 0
        }
        
    async def _monitor_loop(self):
        """监控循环任务"""
        while self._running:
            try:
                # 获取数据
                data = await self._fetch_data()
                if data:
                    # 处理数据
                    await self._process_data(data)
                    
                    # 检查性能指标
                    stats = self.get_performance_stats()
                    if stats['avg_response_time'] > 1.0:  # 如果平均响应时间超过1秒
                        logger.warning(f"性能警告: 平均响应时间 {stats['avg_response_time']:.2f}秒")
                        
                # 动态调整轮询间隔
                stats = self.get_performance_stats()
                interval = max(0.1, min(1.0, stats['avg_response_time'] * 1.5))  # 根据响应时间动态调整,最小0.1秒,最大1秒
                await asyncio.sleep(interval)
                
            except Exception as e:
                logger.error(f"监控循环错误: {str(e)}")
                self.performance_metrics['error_count'] += 1
                await asyncio.sleep(1)  # 错误后等待1秒

    async def start(self):
        """启动监控"""
        if self._running:
            return
            
        self._running = True
        logger.info("启动监控管理器")
        
        # 启动交易管理器
        await self.trading_manager.start()
        
        # 创建并启动监控任务
        self._monitor_task = asyncio.create_task(self._monitor_loop())

    async def stop(self):
        """停止监控"""
        if not self._running:
            return

        self._running = False
        
        # 取消监控任务
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None

        # 停止交易管理器
        await self.trading_manager.stop()
        # 清理 twitter scraper
        await self.twitter_scraper.cleanup()
        logger.info("停止监控管理器") 