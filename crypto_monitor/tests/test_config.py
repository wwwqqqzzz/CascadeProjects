"""Test configuration file."""
import os

# 测试用的Twitter配置
TWITTER_CONFIG = {
    'validation_urls': [
        'https://twitter.com/home',
        'https://twitter.com/search?q=bitcoin',
        'https://twitter.com/api/graphql'
    ],
    'request_interval': 1,
    'max_retries': 2,
    'timeout': 5,
    'bearer_token': 'test_bearer_token',
    'api_key': 'test_api_key',
    'api_secret': 'test_api_secret',
    'access_token': 'test_access_token',
    'access_token_secret': 'test_access_token_secret'
}

# 测试用的代理源配置
PROXY_SOURCE_CONFIG = {
    'sources': [
        {
            'name': 'test_source',
            'type': 'test',
            'url': 'http://test.proxy/api',
            'auth': {
                'username': 'test_user',
                'password': 'test_pass'
            }
        }
    ],
    'validation': {
        'timeout': 5,
        'test_urls': [
            'https://api.ipify.org?format=json',
            'https://lumtest.com/myip.json'
        ]
    }
}

# 测试用的代理池配置
PROXY_CONFIG = {
    'validation': {
        'test_urls': [
            'https://api.ipify.org?format=json',
            'https://twitter.com/robots.txt',
            'https://lumtest.com/myip.json'
        ],
        'timeout': 2,
        'cache_ttl': 60,
        'concurrent_validations': 5,
        'min_success_rate': 0.8,
        'max_response_time': 1.0,
        'ban_duration': 60,
        'max_consecutive_failures': 3
    },
    'pool': {
        'min_size': 5,
        'max_size': 20,
        'refresh_interval': 30,
        'cleanup_interval': 60,
        'min_available_proxies': 3,
        'health_check_interval': 15
    },
    'load_levels': {
        'light': {
            'min_health_score': 0.8,
            'max_concurrent_requests': 10
        },
        'medium': {
            'min_health_score': 0.7,
            'max_concurrent_requests': 20
        },
        'heavy': {
            'min_health_score': 0.6,
            'max_concurrent_requests': 30
        }
    }
}

# 测试用的日志配置
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
        }
    },
    'loggers': {
        '': {
            'handlers': ['console'],
            'level': 'INFO'
        }
    }
}

# 测试用的技术分析参数
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
    'ma': {
        'short_period': 20,
        'long_period': 50
    }
}

# 测试用的Binance API配置
BINANCE_CONFIG = {
    'api_key': 'test_api_key',
    'api_secret': 'test_api_secret',
    'base_url': 'https://testnet.binance.vision',
    'timeout': 5,
    'recv_window': 5000
}
