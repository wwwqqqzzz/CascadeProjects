import os
import pytest
import logging
from ..utils.config import PROXY_CONFIG, TWITTER_CONFIG, TRADING_CONFIG
from ..utils.logger import setup_logger, get_logger

def test_config_loading():
    """测试配置加载"""
    # 测试代理池配置
    assert PROXY_CONFIG['pool']['max_size'] == 150
    assert PROXY_CONFIG['validation']['timeout'] == 5
    
    # 测试Twitter配置
    assert 'request_interval' in TWITTER_CONFIG
    assert TWITTER_CONFIG['max_retries'] == 3
    
    # 测试交易配置
    assert 'BTCUSDT' in TRADING_CONFIG['trading_pairs']
    assert TRADING_CONFIG['stop_loss_percentage'] == 2

def test_logger_setup(tmp_path):
    """测试日志系统设置"""
    # 创建临时日志文件
    test_log_file = os.path.join(tmp_path, "test.log")
    
    # 设置测试日志器
    logger = setup_logger("test_logger", test_log_file)
    
    # 测试日志记录
    test_message = "测试日志消息"
    logger.info(test_message)
    
    # 验证日志文件内容
    with open(test_log_file, "r", encoding="utf-8") as f:
        log_content = f.read()
        assert test_message in log_content

def test_get_logger():
    """测试获取日志器"""
    logger_name = "test_get_logger"
    logger = get_logger(logger_name)
    
    # 验证日志器配置
    assert logger.name == logger_name
    assert logger.level == logging.DEBUG
    assert len(logger.handlers) > 0  # 至少有一个handler 