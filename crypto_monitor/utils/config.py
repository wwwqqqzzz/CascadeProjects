"""
Configuration settings for the crypto monitor application.
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Binance API Configuration
BINANCE_API_KEY = os.getenv('BINANCE_API_KEY')
BINANCE_API_SECRET = os.getenv('BINANCE_API_SECRET')

# Trading Configuration
TRADING_CONFIG = {
    'trading_pairs': [
        'BTCUSDT',  # Bitcoin
        'ETHUSDT',  # Ethereum
        'BNBUSDT',  # Binance Coin
        'ADAUSDT',  # Cardano
        'DOGEUSDT'  # Dogecoin
    ],
    'default_trade_size': 100,  # in USDT
    'max_trade_size': 1000,     # in USDT
    'stop_loss_percentage': 2,  # 2%
    'take_profit_percentage': 4,  # 4%
    'exchange': 'binance',
    'test_mode': True,  # Use testnet for development
    'max_trades_per_day': 10,  # 每日最大交易次数
    'min_trade_interval': 300,  # 最小交易间隔(秒)
    'min_signal_score': 0.8,  # 最低信号分数要求
    'trade_timeout': 30,  # 交易超时时间(秒)
    'retry_attempts': 3,  # 交易重试次数
    'price_deviation_limit': 0.02,  # 价格偏差限制(2%)
    'trade_amount': 1000  # 每笔交易金额(USDT)
}

# Logging Configuration
LOGGING_CONFIG = {
    'version': 1,
    'formatters': {
        'detailed': {
            'class': 'logging.Formatter',
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        }
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'detailed',
            'level': 'INFO'
        },
        'file': {
            'class': 'logging.FileHandler',
            'filename': 'crypto_monitor.log',
            'formatter': 'detailed',
            'level': 'DEBUG'
        }
    },
    'loggers': {
        '': {
            'handlers': ['console', 'file'],
            'level': 'INFO'
        }
    }
}

# Market Monitor Parameters
UPDATE_INTERVAL_MS = 100  # Market data update interval in milliseconds
MAX_RETRIES = 3  # Maximum number of retries for failed operations
RETRY_DELAY_SEC = 1  # Delay between retries in seconds
TRADE_SIZE_USDT = 100.0  # Size of each trade in USDT
MAX_TRADES_PER_DAY = 10  # Maximum number of trades per day
STOP_LOSS_PERCENTAGE = 2.0  # Stop loss percentage
TAKE_PROFIT_PERCENTAGE = 4.0  # Take profit percentage

# Technical Analysis Parameters
TECHNICAL_PARAMS = {
    'rsi': {
        'period': 14,
        'overbought': 70,
        'oversold': 30
    },
    'macd': {
        'fast_period': 12,
        'slow_period': 26,
        'signal_period': 9
    },
    'bollinger': {
        'period': 20,
        'std_dev': 2
    },
    'volume': {
        'period': 20,
        'threshold': 2.0  # Volume surge threshold
    },
    'ma': {
        'short_period': 20,
        'long_period': 50
    }
}

# Twitter 爬取相关配置
TWITTER_CONFIG = {
    'validation_urls': [
        'https://twitter.com/home',  # Twitter主页
        'https://twitter.com/search?q=bitcoin',  # 搜索页面
        'https://twitter.com/api/graphql'  # API端点
    ],
    'request_interval': 2,  # 请求间隔（秒）
    'max_retries': 3,  # 最大重试次数
    'timeout': 30,  # 请求超时时间（秒）
    'bearer_token': os.getenv('TWITTER_BEARER_TOKEN'),
    'api_key': os.getenv('TWITTER_API_KEY'),
    'api_secret': os.getenv('TWITTER_API_SECRET'),
    'access_token': os.getenv('TWITTER_ACCESS_TOKEN'),
    'access_token_secret': os.getenv('TWITTER_ACCESS_TOKEN_SECRET')
}

# 代理源配置
PROXY_SOURCE_CONFIG = {
    'luminati': {
        'type': 'api',
        'url': 'https://luminati.io/api/proxy_list',
        'auth': {
            'username': os.getenv('LUMINATI_USERNAME'),
            'password': os.getenv('LUMINATI_PASSWORD')
        }
    },
    'proxyscrape': {
        'type': 'free',
        'url': 'https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=elite'
    },
    'proxylist': {
        'type': 'free',
        'url': 'https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all',
        'method': 'GET',
        'parser': 'text',
        'fetch_interval': 1800,  # 30分钟
        'max_proxies': 100,
        'timeout': 10,
        'headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
    },
    'pubproxy': {
        'type': 'free',
        'url': 'http://pubproxy.com/api/proxy?limit=20&format=json&https=true',
        'method': 'GET',
        'parser': 'json',
        'fetch_interval': 3600,  # 1小时
        'max_proxies': 50,
        'timeout': 10,
        'headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
    },
    'freeproxy': {
        'type': 'free',
        'url': 'https://www.proxy-list.download/api/v1/get?type=https',
        'method': 'GET',
        'parser': 'text',
        'fetch_interval': 2400,  # 40分钟
        'max_proxies': 75,
        'timeout': 10,
        'headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
    }
}

# 代理池配置
PROXY_CONFIG = {
    # 代理验证设置
    'validation': {
        'test_urls': [
            'https://api.ipify.org?format=json',  # IP检查
            'https://twitter.com/robots.txt',     # Twitter可访问性测试
            'https://lumtest.com/myip.json'       # 匿名性测试
        ],
        'timeout': 5,  # 降低超时时间到5秒
        'cache_ttl': 300,
        'concurrent_validations': 10,
        'min_success_rate': 0.8,  # 提高成功率要求
        'max_response_time': 1.0,  # 降低最大响应时间到1秒
        'ban_duration': 1800,  # 增加禁用时长到30分钟
        'max_consecutive_failures': 3  # 降低连续失败容忍度
    },
    
    # 代理池维护设置
    'pool': {
        'min_size': 30,  # 增加最小代理数量
        'max_size': 150,  # 增加最大代理数量
        'refresh_interval': 900,  # 缩短刷新间隔到15分钟
        'cleanup_interval': 1800,  # 缩短清理间隔到30分钟
        'min_available_proxies': 10,  # 最小可用代理数量（触发告警）
        'health_check_interval': 300  # 健康检查间隔（秒）
    },
    
    # 负载级别配置
    'load_levels': {
        'light': {
            'min_health_score': 0.8,
            'max_concurrent_requests': 50
        },
        'medium': {
            'min_health_score': 0.7,
            'max_concurrent_requests': 100
        },
        'heavy': {
            'min_health_score': 0.6,
            'max_concurrent_requests': 200
        }
    }
}

# Binance API配置
BINANCE_CONFIG = {
    'api_key': os.getenv('BINANCE_API_KEY'),
    'api_secret': os.getenv('BINANCE_API_SECRET'),
    'base_url': 'https://api.binance.com',
    'timeout': 10,
    'recv_window': 5000
}

# 监控面板配置
MONITOR_CONFIG = {
    'dashboard_update_interval': 5,  # 仪表盘更新间隔（秒）
    'data_retention_days': 7,        # 数据保留天数
    'performance_metrics': {
        'api_latency_warning': 0.5,   # API延迟警告阈值（秒）
        'api_latency_critical': 1.0,  # API延迟严重阈值（秒）
        'error_rate_warning': 0.05,   # 错误率警告阈值（5%）
        'error_rate_critical': 0.1,   # 错误率严重阈值（10%）
        'min_samples': 10             # 最小样本数
    },
    'chart_config': {
        'max_points': 1000,           # 图表最大数据点
        'rolling_window': 20          # 移动平均窗口大小
    }
}
