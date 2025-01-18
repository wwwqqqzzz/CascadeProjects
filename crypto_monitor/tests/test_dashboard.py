"""
性能监控面板的单元测试
"""

import pytest
from datetime import datetime
import dash
from dash.testing.composite import DashComposite
from crypto_monitor.services.monitor.dashboard import PerformanceDashboard

@pytest.fixture
def dashboard(tmp_path):
    """创建仪表板实例"""
    return PerformanceDashboard(
        data_dir=str(tmp_path / "performance"),
        host="localhost",
        port=8050
    )

def test_dashboard_initialization(dashboard):
    """测试仪表板初始化"""
    assert isinstance(dashboard.app, dash.Dash)
    assert dashboard.host == "localhost"
    assert dashboard.port == 8050
    assert dashboard.update_interval > 0

def test_get_days_from_range(dashboard):
    """测试时间范围转换"""
    assert dashboard._get_days_from_range('1H') == 1/24
    assert dashboard._get_days_from_range('6H') == 0.25
    assert dashboard._get_days_from_range('24H') == 1
    assert dashboard._get_days_from_range('7D') == 7
    assert dashboard._get_days_from_range('invalid') == 1  # 默认值

def test_calculate_summary_stats(dashboard):
    """测试性能指标统计计算"""
    # 测试空数据
    empty_metrics = {
        'api_latency': [],
        'error_count': 0,
        'warning_count': 0
    }
    assert dashboard._calculate_summary_stats(empty_metrics) == {}
    
    # 测试有效数据
    metrics = {
        'api_latency': [
            {'latency': 0.1, 'timestamp': datetime.now().isoformat()},
            {'latency': 0.2, 'timestamp': datetime.now().isoformat()},
            {'latency': 0.3, 'timestamp': datetime.now().isoformat()}
        ],
        'error_count': 1,
        'warning_count': 2
    }
    
    stats = dashboard._calculate_summary_stats(metrics)
    assert stats['avg_latency'] == 0.2
    assert stats['max_latency'] == 0.3
    assert stats['total_requests'] == 3
    assert stats['error_count'] == 1
    assert stats['warning_count'] == 2

def test_create_summary_cards(dashboard):
    """测试性能指标卡片创建"""
    # 测试空数据
    empty_cards = dashboard._create_summary_cards({})
    assert empty_cards.children == '无数据'
    
    # 测试有效数据
    stats = {
        'avg_latency': 0.2,
        'max_latency': 0.3,
        'total_requests': 100,
        'error_count': 5,
        'warning_count': 10
    }
    
    cards = dashboard._create_summary_cards(stats)
    assert len(cards.children) == 5  # 5个指标卡片
    
    # 验证卡片内容
    card_texts = [card.children[1].children for card in cards.children]
    assert '0.200 秒' in card_texts  # 平均延迟
    assert '0.300 秒' in card_texts  # 最大延迟
    assert '100' in card_texts       # 总请求数
    assert '5' in card_texts         # 错误数
    assert '10' in card_texts        # 警告数

@pytest.mark.asyncio
async def test_dashboard_callbacks(dashboard, tmp_path):
    """测试仪表板回调函数"""
    # 创建测试数据
    metrics = {
        'api_latency': [
            {
                'operation': 'test_op',
                'latency': 0.1,
                'timestamp': datetime.now().isoformat()
            }
        ],
        'price_volatility': [
            {
                'symbol': 'BTCUSDT',
                'value': 50000.0,
                'timestamp': datetime.now().isoformat()
            }
        ],
        'execution_time': [
            {
                'operation': 'test_op',
                'execution_time': 0.2,
                'timestamp': datetime.now().isoformat()
            }
        ],
        'error_count': 1,
        'warning_count': 2
    }
    
    # 保存测试数据
    data_file = tmp_path / "performance" / f"metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    data_file.parent.mkdir(parents=True, exist_ok=True)
    with open(data_file, 'w') as f:
        import json
        json.dump(metrics, f)
    
    # 测试更新回调
    summary = await dashboard.app.callback_map['performance-summary']['callback'](1, '1H')
    assert summary is not None
    
    latency_chart = await dashboard.app.callback_map['latency-chart']['callback'](1, '1H')
    assert latency_chart is not None
    
    volatility_chart = await dashboard.app.callback_map['volatility-chart']['callback'](1, '1H')
    assert volatility_chart is not None
    
    execution_chart = await dashboard.app.callback_map['execution-time-chart']['callback'](1, '1H')
    assert execution_chart is not None
    
    error_chart = await dashboard.app.callback_map['error-warning-chart']['callback'](1, '1H')
    assert error_chart is not None
    
    # 测试时间更新
    time_text = await dashboard.app.callback_map['last-update-time']['callback'](1)
    assert '最后更新时间' in time_text 