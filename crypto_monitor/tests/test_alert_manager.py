"""
报警管理模块的单元测试
"""

import pytest
import json
from datetime import datetime, timedelta
from pathlib import Path
import aiohttp
from unittest.mock import Mock, patch
from crypto_monitor.services.monitor.alert_manager import AlertManager

@pytest.fixture
def alert_manager(tmp_path):
    """创建报警管理器实例"""
    config_path = tmp_path / "config" / "alerts.json"
    return AlertManager(str(config_path))

@pytest.fixture
def sample_metrics():
    """创建示例性能指标数据"""
    now = datetime.now()
    return {
        'api_latency': [
            {
                'operation': 'get_symbol_price',
                'latency': 0.8,
                'timestamp': now.isoformat()
            },
            {
                'operation': 'market_buy',
                'latency': 1.2,
                'timestamp': now.isoformat()
            }
        ],
        'execution_time': [
            {
                'operation': 'market_buy',
                'execution_time': 3.0,
                'timestamp': now.isoformat()
            }
        ],
        'error_count': 5
    }

def test_load_config(alert_manager):
    """测试配置加载"""
    config = alert_manager.alert_config
    assert 'thresholds' in config
    assert 'notifications' in config
    assert 'alert_rules' in config
    
    # 验证默认阈值
    assert config['thresholds']['api_latency']['warning'] == 0.5
    assert config['thresholds']['api_latency']['critical'] == 1.0

def test_update_config(alert_manager):
    """测试配置更新"""
    new_config = alert_manager.alert_config.copy()
    new_config['thresholds']['api_latency']['warning'] = 0.8
    
    assert alert_manager.update_config(new_config)
    assert alert_manager.alert_config['thresholds']['api_latency']['warning'] == 0.8
    
    # 测试无效配置
    invalid_config = {'invalid': 'config'}
    assert not alert_manager.update_config(invalid_config)

def test_validate_config(alert_manager):
    """测试配置验证"""
    valid_config = {
        'thresholds': {
            'api_latency': {
                'warning': 0.5,
                'critical': 1.0,
                'window': 60,
                'min_samples': 3
            }
        },
        'notifications': {
            'channels': ['log']
        },
        'alert_rules': {
            'cooldown': 300,
            'aggregation': 'avg'
        }
    }
    assert alert_manager._validate_config(valid_config)
    
    invalid_config = {
        'thresholds': {
            'api_latency': {
                'warning': 0.5  # 缺少必要字段
            }
        }
    }
    assert not alert_manager._validate_config(invalid_config)

@pytest.mark.asyncio
async def test_check_metrics(alert_manager, sample_metrics):
    """测试指标检查"""
    alerts = await alert_manager.check_metrics(sample_metrics)
    assert len(alerts) > 0
    
    # 验证API延迟报警
    api_latency_alerts = [a for a in alerts if a['metric'] == 'API延迟']
    assert len(api_latency_alerts) > 0
    assert api_latency_alerts[0]['type'] in ['warning', 'critical']
    
    # 验证执行时间报警
    execution_time_alerts = [a for a in alerts if a['metric'] == '执行时间']
    assert len(execution_time_alerts) > 0
    assert execution_time_alerts[0]['type'] in ['warning', 'critical']

@pytest.mark.asyncio
async def test_check_api_latency(alert_manager):
    """测试API延迟检查"""
    now = datetime.now()
    latency_data = [
        {'latency': 1.5, 'timestamp': now.isoformat()},
        {'latency': 1.2, 'timestamp': now.isoformat()},
        {'latency': 1.3, 'timestamp': now.isoformat()}
    ]
    
    alerts = await alert_manager._check_api_latency(latency_data)
    assert len(alerts) > 0
    assert alerts[0]['type'] == 'critical'
    assert alerts[0]['metric'] == 'API延迟'

@pytest.mark.asyncio
async def test_check_error_rate(alert_manager):
    """测试错误率检查"""
    metrics = {
        'api_latency': [{'latency': 0.1, 'timestamp': datetime.now().isoformat()} for _ in range(20)],
        'error_count': 4  # 20% 错误率
    }
    
    alerts = await alert_manager._check_error_rate(metrics)
    assert len(alerts) > 0
    assert alerts[0]['type'] == 'critical'
    assert alerts[0]['metric'] == '错误率'

def test_check_cooldown(alert_manager):
    """测试报警冷却时间"""
    # 第一次报警
    assert alert_manager._check_cooldown('test_metric', 'warning')
    
    # 冷却期内的报警
    assert not alert_manager._check_cooldown('test_metric', 'warning')
    
    # 不同类型的报警
    assert alert_manager._check_cooldown('test_metric', 'critical')

@pytest.mark.asyncio
async def test_send_alerts(alert_manager):
    """测试报警发送"""
    alerts = [{
        'type': 'critical',
        'metric': 'API延迟',
        'value': 1.5,
        'threshold': 1.0,
        'timestamp': datetime.now().isoformat()
    }]
    
    # 测试日志通知
    await alert_manager.send_alerts(alerts)
    assert len(alert_manager.alert_history) == 1
    
    # 测试历史记录限制
    large_alerts = [alerts[0].copy() for _ in range(1100)]
    await alert_manager.send_alerts(large_alerts)
    assert len(alert_manager.alert_history) == alert_manager.max_history_size

@pytest.mark.asyncio
async def test_telegram_notification(alert_manager):
    """测试Telegram通知"""
    # 配置Telegram
    alert_manager.alert_config['notifications']['telegram'] = {
        'bot_token': 'test_token',
        'chat_id': 'test_chat_id'
    }
    alert_manager.alert_config['notifications']['channels'] = ['telegram']
    
    alerts = [{
        'type': 'critical',
        'metric': 'API延迟',
        'value': 1.5,
        'threshold': 1.0,
        'timestamp': datetime.now().isoformat()
    }]
    
    # Mock aiohttp.ClientSession
    with patch('aiohttp.ClientSession') as mock_session:
        mock_response = Mock()
        mock_response.status = 200
        mock_session.return_value.__aenter__.return_value.post.return_value.__aenter__.return_value = mock_response
        
        await alert_manager.send_alerts(alerts)
        
        # 验证是否调用了Telegram API
        mock_session.return_value.__aenter__.return_value.post.assert_called_once()

def test_get_alert_history(alert_manager):
    """测试获取报警历史"""
    now = datetime.now()
    old_alert = {
        'type': 'warning',
        'metric': 'API延迟',
        'value': 0.8,
        'threshold': 0.5,
        'timestamp': (now - timedelta(hours=25)).isoformat()
    }
    new_alert = {
        'type': 'critical',
        'metric': 'API延迟',
        'value': 1.5,
        'threshold': 1.0,
        'timestamp': now.isoformat()
    }
    
    alert_manager.alert_history = [old_alert, new_alert]
    
    # 获取24小时内的报警
    recent_alerts = alert_manager.get_alert_history(hours=24)
    assert len(recent_alerts) == 1
    assert recent_alerts[0] == new_alert 