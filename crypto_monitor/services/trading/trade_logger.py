"""
Trade logging module for cryptocurrency trading.
"""

import logging
import json
from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

class TradeLogger:
    def __init__(self, log_dir: str = "logs/trades"):
        """
        初始化交易日志记录器
        
        Args:
            log_dir: 日志文件存储目录
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # 当日交易统计
        self.daily_stats = {
            'total_trades': 0,
            'successful_trades': 0,
            'failed_trades': 0,
            'total_amount': 0.0,
            'signals_received': 0
        }
        
        # 内存中的交易记录缓存
        self._trades_cache = []
        
    def log_trade(self, trade_result: Dict):
        """
        记录交易结果
        
        Args:
            trade_result: 交易结果详情
        """
        try:
            # 更新统计信息
            self.daily_stats['total_trades'] += 1
            if trade_result['status'] == 'success':
                self.daily_stats['successful_trades'] += 1
                self.daily_stats['total_amount'] += float(trade_result.get('amount', 0))
            else:
                self.daily_stats['failed_trades'] += 1
                
            # 生成日志文件名
            date_str = datetime.now().strftime('%Y-%m-%d')
            log_file = self.log_dir / f"trades_{date_str}.json"
            
            # 读取现有日志
            trades = []
            if log_file.exists():
                with open(log_file, 'r', encoding='utf-8') as f:
                    trades = json.load(f)
                    
            # 创建新的交易记录
            trade_record = {
                'timestamp': trade_result['timestamp'],
                'symbol': trade_result.get('symbol'),
                'side': trade_result.get('side'),
                'amount': trade_result.get('amount'),
                'price': trade_result.get('price'),
                'quantity': trade_result.get('quantity'),
                'status': trade_result['status'],
                'test_mode': trade_result['test_mode'],
                'signal': trade_result.get('signal'),
                'error': trade_result.get('error')
            }
            
            # 添加到缓存和文件
            self._trades_cache.append(trade_record)
            trades.append(trade_record)
            
            # 按时间戳倒序排序
            trades.sort(key=lambda x: x['timestamp'], reverse=True)
            self._trades_cache.sort(key=lambda x: x['timestamp'], reverse=True)
            
            # 保存日志
            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump(trades, f, indent=2, ensure_ascii=False)
                
            logger.info(f"交易记录已保存: {trade_result['timestamp']}")
            
        except Exception as e:
            logger.error(f"保存交易记录失败: {e}")
            
    def log_signal(self, signal: Dict):
        """
        记录接收到的交易信号
        
        Args:
            signal: 交易信号详情
        """
        try:
            # 更新统计信息
            self.daily_stats['signals_received'] += 1
            
            # 生成日志文件名
            date_str = datetime.now().strftime('%Y-%m-%d')
            log_file = self.log_dir / f"signals_{date_str}.json"
            
            # 读取现有日志
            signals = []
            if log_file.exists():
                with open(log_file, 'r', encoding='utf-8') as f:
                    signals = json.load(f)
                    
            # 添加新信号记录
            signals.append({
                'timestamp': signal['timestamp'],
                'source': signal['source'],
                'author': signal['author'],
                'keywords': signal['keywords'],
                'score': signal['score'],
                'text': signal['text']
            })
            
            # 按时间戳倒序排序
            signals.sort(key=lambda x: x['timestamp'], reverse=True)
            
            # 保存日志
            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump(signals, f, indent=2, ensure_ascii=False)
                
            logger.info(f"信号记录已保存: {signal['timestamp']}")
            
        except Exception as e:
            logger.error(f"保存信号记录失败: {e}")
            
    def get_daily_stats(self) -> Dict:
        """获取当日交易统计信息"""
        return {
            **self.daily_stats,
            'date': datetime.now().strftime('%Y-%m-%d'),
            'success_rate': (self.daily_stats['successful_trades'] / 
                           self.daily_stats['total_trades'] * 100 
                           if self.daily_stats['total_trades'] > 0 else 0)
        }
        
    def get_trade_history(self, days: int = 7) -> List[Dict]:
        """
        获取历史交易记录
        
        Args:
            days: 获取最近几天的记录
            
        Returns:
            交易记录列表
        """
        # 如果有缓存,直接返回
        if self._trades_cache:
            return self._trades_cache
            
        trades = []
        try:
            # 获取最近几天的日志文件
            for i in range(days):
                date = datetime.now().date()
                log_file = self.log_dir / f"trades_{date}.json"
                if log_file.exists():
                    with open(log_file, 'r', encoding='utf-8') as f:
                        trades.extend(json.load(f))
                        
            # 按时间戳倒序排序
            trades.sort(key=lambda x: x['timestamp'], reverse=True)
            
            # 更新缓存
            self._trades_cache = trades
            
        except Exception as e:
            logger.error(f"读取交易历史失败: {e}")
            
        return trades 