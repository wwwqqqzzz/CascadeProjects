"""
性能数据可视化模块的单元测试
"""

import pytest
import json
from datetime import datetime, timedelta
from pathlib import Path
import plotly.graph_objects as go
from crypto_monitor.services.monitor.performance_visualizer import PerformanceVisualizer

@pytest.fixture
def sample_metrics():
    """创建示例性能指标数据"""
    return {
        'api_latency': [
            {
                'operation': 'get_symbol_price',
                'latency': 0.5,
                'timestamp': datetime.now().isoformat()
            },
            {
                'operation': 'market_buy',
                'latency': 1.2,
                'timestamp': datetime.now().isoformat()
            }
        ],
        'price_volatility': [
            {
                'symbol': 'BTCUSDT',
                'value': 50000.0,
                'timestamp': datetime.now().isoformat()
            },
            {
                'symbol': 'BTCUSDT',
                'value': 50100.0,
                'timestamp': datetime.now().isoformat()
            }
        ],
        'execution_time': [
            {
                'operation': 'market_buy',
                'execution_time': 0.8,
                'timestamp': datetime.now().isoformat()
            }
        ],
        'error_count': 1,
        'warning_count': 2
    }

@pytest.fixture
def test_data_dir(tmp_path, sample_metrics):
    """创建测试数据目录和示例数据文件"""
    data_dir = tmp_path / "test_performance"
    data_dir.mkdir()
    
    # 创建两个测试文件
    for i in range(2):
        timestamp = datetime.now() - timedelta(hours=i)
        filename = data_dir / f"metrics_{timestamp.strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(sample_metrics, f)
            
    return data_dir

@pytest.fixture
def visualizer(test_data_dir):
    """创建可视化器实例"""
    return PerformanceVisualizer(data_dir=str(test_data_dir))

def test_load_metrics(visualizer, sample_metrics):
    """测试加载性能指标数据"""
    metrics = visualizer.load_metrics(days=1)
    assert metrics is not None
    assert len(metrics['api_latency']) == len(sample_metrics['api_latency']) * 2
    assert len(metrics['price_volatility']) == len(sample_metrics['price_volatility']) * 2
    assert metrics['error_count'] == sample_metrics['error_count'] * 2

def test_create_latency_chart(visualizer, sample_metrics):
    """测试创建延迟分析图表"""
    fig = visualizer.create_latency_chart(sample_metrics)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) > 0  # 确保图表包含数据
    
def test_create_volatility_chart(visualizer, sample_metrics):
    """测试创建波动率分析图表"""
    fig = visualizer.create_volatility_chart(sample_metrics)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) > 0
    
def test_create_execution_time_chart(visualizer, sample_metrics):
    """测试创建执行时间分析图表"""
    fig = visualizer.create_execution_time_chart(sample_metrics)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) > 0
    
def test_create_error_warning_chart(visualizer, sample_metrics):
    """测试创建错误和警告统计图表"""
    fig = visualizer.create_error_warning_chart(sample_metrics)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) > 0

def test_generate_report(visualizer):
    """测试生成完整报告"""
    report = visualizer.generate_report(days=1)
    assert report is not None
    assert 'latency' in report
    assert 'volatility' in report
    assert 'execution_time' in report
    assert 'errors' in report
    
def test_save_report(visualizer, tmp_path):
    """测试保存报告"""
    # 生成报告
    report = visualizer.generate_report(days=1)
    assert report is not None
    
    # 保存报告
    output_dir = tmp_path / "test_reports"
    visualizer.save_report(report, str(output_dir))
    
    # 验证文件是否创建
    assert output_dir.exists()
    files = list(output_dir.glob("performance_*.html"))
    assert len(files) > 0

def test_empty_metrics(visualizer):
    """测试处理空数据的情况"""
    empty_metrics = {
        'api_latency': [],
        'price_volatility': [],
        'execution_time': [],
        'error_count': 0,
        'warning_count': 0
    }
    
    # 测试各个图表函数
    assert visualizer.create_latency_chart(empty_metrics) is None
    assert visualizer.create_volatility_chart(empty_metrics) is None
    assert visualizer.create_execution_time_chart(empty_metrics) is None
    
def test_invalid_data_dir(tmp_path):
    """测试无效数据目录的情况"""
    invalid_dir = tmp_path / "nonexistent"
    visualizer = PerformanceVisualizer(str(invalid_dir))
    metrics = visualizer.load_metrics()
    assert metrics is None 