"""
性能数据可视化模块
"""

import os
import json
from typing import Dict, List
from datetime import datetime, timedelta
import plotly.graph_objects as go
from pathlib import Path

class PerformanceVisualizer:
    def __init__(self, data_dir: str = "data/performance"):
        """
        初始化性能数据可视化器
        
        Args:
            data_dir: 性能数据目录
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
    def load_metrics(self, days: float = 1) -> Dict:
        """
        加载指定天数的性能指标数据
        
        Args:
            days: 加载最近几天的数据
            
        Returns:
            性能指标数据字典
        """
        metrics = {
            'api_latency': [],
            'execution_time': [],
            'error_count': 0,
            'warning_count': 0
        }
        
        # 示例数据
        now = datetime.now()
        for i in range(100):
            timestamp = now - timedelta(hours=i*0.1)
            metrics['api_latency'].append({
                'operation': 'get_symbol_price',
                'latency': 0.2 + (i % 5) * 0.1,
                'timestamp': timestamp.isoformat()
            })
            
            if i % 3 == 0:
                metrics['execution_time'].append({
                    'operation': 'market_buy',
                    'execution_time': 1.0 + (i % 3) * 0.5,
                    'timestamp': timestamp.isoformat()
                })
                
        metrics['error_count'] = 5
        metrics['warning_count'] = 10
        
        return metrics
        
    def create_latency_chart(self, metrics: Dict) -> go.Figure:
        """创建API延迟图表"""
        if not metrics['api_latency']:
            return go.Figure()
            
        x = [datetime.fromisoformat(m['timestamp']) for m in metrics['api_latency']]
        y = [m['latency'] for m in metrics['api_latency']]
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=x,
            y=y,
            mode='lines+markers',
            name='API延迟',
            line=dict(color='#3498db')
        ))
        
        fig.update_layout(
            title='API延迟趋势',
            xaxis_title='时间',
            yaxis_title='延迟 (秒)',
            template='plotly_white'
        )
        
        return fig
        
    def create_volatility_chart(self, metrics: Dict) -> go.Figure:
        """创建价格波动图表"""
        if not metrics['api_latency']:
            return go.Figure()
            
        # 示例数据
        x = [datetime.fromisoformat(m['timestamp']) for m in metrics['api_latency']]
        y = [(i % 5) * 0.1 for i in range(len(x))]
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=x,
            y=y,
            mode='lines',
            name='价格波动',
            line=dict(color='#2ecc71')
        ))
        
        fig.update_layout(
            title='价格波动趋势',
            xaxis_title='时间',
            yaxis_title='波动率 (%)',
            template='plotly_white'
        )
        
        return fig
        
    def create_execution_time_chart(self, metrics: Dict) -> go.Figure:
        """创建执行时间图表"""
        if not metrics['execution_time']:
            return go.Figure()
            
        x = [datetime.fromisoformat(m['timestamp']) for m in metrics['execution_time']]
        y = [m['execution_time'] for m in metrics['execution_time']]
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=x,
            y=y,
            mode='lines+markers',
            name='执行时间',
            line=dict(color='#e74c3c')
        ))
        
        fig.update_layout(
            title='订单执行时间趋势',
            xaxis_title='时间',
            yaxis_title='执行时间 (秒)',
            template='plotly_white'
        )
        
        return fig
        
    def create_error_warning_chart(self, metrics: Dict) -> go.Figure:
        """创建错误和警告统计图表"""
        if not metrics['api_latency']:
            return go.Figure()
            
        # 示例数据
        x = ['错误', '警告']
        y = [metrics['error_count'], metrics['warning_count']]
        
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=x,
            y=y,
            marker_color=['#e74c3c', '#f1c40f']
        ))
        
        fig.update_layout(
            title='错误和警告统计',
            xaxis_title='类型',
            yaxis_title='数量',
            template='plotly_white'
        )
        
        return fig 