"""
性能监控模块，负责性能数据的收集、分析和持久化
"""

import logging
import json
import asyncio
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np
from ...utils.config import MONITOR_CONFIG

logger = logging.getLogger(__name__)

class PerformanceMonitor:
    def __init__(self, data_dir: str = "data/performance"):
        """
        初始化性能监控器
        
        Args:
            data_dir: 性能数据存储目录
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # 性能指标
        self.metrics = {
            'api_latency': [],           # API 调用延迟
            'price_volatility': [],      # 价格波动率
            'execution_time': [],        # 执行时间
            'error_count': 0,            # 错误计数
            'warning_count': 0,          # 警告计数
        }
        
        # 缓存配置
        self.cache_config = {
            'base_ttl': 1.0,            # 基础缓存时间（秒）
            'min_ttl': 0.1,             # 最小缓存时间
            'max_ttl': 5.0,             # 最大缓存时间
            'volatility_factor': 2.0,    # 波动率影响因子
        }
        
        # 性能阈值
        self.thresholds = MONITOR_CONFIG.get('thresholds', {
            'high_latency': 1.0,         # 高延迟阈值（秒）
            'error_rate': 0.1,           # 错误率阈值
            'warning_rate': 0.2,         # 警告率阈值
        })
        
        # 启动自动保存任务
        self._save_interval = 300  # 5分钟保存一次
        self._save_task = None
        
    async def start(self):
        """启动性能监控"""
        self._save_task = asyncio.create_task(self._auto_save())
        logger.info("性能监控已启动")
        
    async def stop(self):
        """停止性能监控"""
        if self._save_task:
            self._save_task.cancel()
            try:
                await self._save_task
            except asyncio.CancelledError:
                pass
        await self.save_metrics()
        logger.info("性能监控已停止")
        
    def calculate_cache_ttl(self, symbol: str) -> float:
        """
        根据市场状况动态计算缓存时间
        
        Args:
            symbol: 交易对符号
            
        Returns:
            建议的缓存时间（秒）
        """
        # 获取最近的价格波动率
        recent_volatility = self._get_recent_volatility(symbol)
        if not recent_volatility:
            return self.cache_config['base_ttl']
            
        # 根据波动率调整缓存时间
        # 波动率越大，缓存时间越短
        adjusted_ttl = self.cache_config['base_ttl'] / (1 + recent_volatility * self.cache_config['volatility_factor'])
        
        # 确保在合理范围内
        return max(self.cache_config['min_ttl'], 
                  min(self.cache_config['max_ttl'], adjusted_ttl))
                  
    def _get_recent_volatility(self, symbol: str, window: int = 10) -> Optional[float]:
        """计算最近的价格波动率"""
        volatility_data = [v for v in self.metrics['price_volatility'] 
                          if v['symbol'] == symbol][-window:]
        
        if not volatility_data:
            return None
            
        return np.std([v['value'] for v in volatility_data])
        
    def record_api_latency(self, operation: str, latency: float):
        """记录API调用延迟"""
        self.metrics['api_latency'].append({
            'operation': operation,
            'latency': latency,
            'timestamp': datetime.now().isoformat()
        })
        
        if latency > self.thresholds['high_latency']:
            self.metrics['warning_count'] += 1
            logger.warning(f"API调用延迟过高: {operation}, 延迟: {latency:.2f}秒")
            
    def record_price_volatility(self, symbol: str, price: float):
        """记录价格波动率"""
        self.metrics['price_volatility'].append({
            'symbol': symbol,
            'value': price,
            'timestamp': datetime.now().isoformat()
        })
        
    def record_execution_time(self, operation: str, execution_time: float):
        """记录执行时间"""
        self.metrics['execution_time'].append({
            'operation': operation,
            'execution_time': execution_time,
            'timestamp': datetime.now().isoformat()
        })
        
    def record_error(self, error_type: str, error_msg: str):
        """记录错误"""
        self.metrics['error_count'] += 1
        logger.error(f"{error_type}: {error_msg}")
        
    async def _auto_save(self):
        """自动保存性能数据的后台任务"""
        while True:
            try:
                await asyncio.sleep(self._save_interval)
                await self.save_metrics()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"自动保存性能数据时出错: {e}")
                
    async def save_metrics(self):
        """保存性能指标到文件"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = self.data_dir / f"metrics_{timestamp}.json"
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(self.metrics, f, ensure_ascii=False, indent=2)
                
            logger.info(f"性能指标已保存到: {filename}")
            
            # 清理旧数据
            await self._cleanup_old_files()
            
        except Exception as e:
            logger.error(f"保存性能指标时出错: {e}")
            
    async def _cleanup_old_files(self, max_age_days: int = 7):
        """清理旧的性能数据文件"""
        try:
            cutoff = datetime.now() - timedelta(days=max_age_days)
            for file in self.data_dir.glob("metrics_*.json"):
                # 从文件名中提取时间戳
                timestamp_str = file.stem.split('_')[1]
                file_time = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                
                if file_time < cutoff:
                    file.unlink()
                    logger.info(f"已删除旧的性能数据文件: {file}")
                    
        except Exception as e:
            logger.error(f"清理旧文件时出错: {e}")
            
    def get_performance_stats(self) -> Dict:
        """获取性能统计信息"""
        if not self.metrics['api_latency']:
            return {
                'avg_latency': 0,
                'max_latency': 0,
                'error_rate': 0,
                'warning_rate': 0
            }
            
        # 计算API延迟统计
        latencies = [m['latency'] for m in self.metrics['api_latency']]
        total_calls = len(latencies)
        
        return {
            'avg_latency': sum(latencies) / total_calls,
            'max_latency': max(latencies),
            'error_rate': self.metrics['error_count'] / total_calls,
            'warning_rate': self.metrics['warning_count'] / total_calls,
            'total_calls': total_calls
        } 