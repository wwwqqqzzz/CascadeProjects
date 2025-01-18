"""Benchmark configuration for proxy testing."""
from typing import Dict, List

# Benchmark scenarios
BENCHMARK_SCENARIOS = {
    "light_load": {
        "concurrent_requests": 5,
        "requests_per_proxy": 10,
        "delay_between_requests": 1.0,  # seconds
        "timeout": 10,  # seconds
    },
    "medium_load": {
        "concurrent_requests": 20,
        "requests_per_proxy": 50,
        "delay_between_requests": 0.5,
        "timeout": 15,
    },
    "heavy_load": {
        "concurrent_requests": 50,
        "requests_per_proxy": 100,
        "delay_between_requests": 0.2,
        "timeout": 20,
    }
}

# Performance thresholds
PERFORMANCE_THRESHOLDS = {
    "max_response_time": 5.0,  # seconds
    "min_success_rate": 0.95,  # 95%
    "max_error_rate": 0.05,    # 5%
    "max_timeout_rate": 0.03,  # 3%
}

# Test endpoints for different scenarios
BENCHMARK_ENDPOINTS = {
    "latency": {
        "url": "http://httpbin.org/delay/1",
        "method": "GET",
        "expected_status": 200,
        "timeout": 5,
    },
    "bandwidth": {
        "url": "http://httpbin.org/bytes/50000",
        "method": "GET",
        "expected_status": 200,
        "timeout": 10,
    },
    "cpu": {
        "url": "http://httpbin.org/base64/SFRUUEJJTiBpcyBhd2Vzb21l",
        "method": "GET",
        "expected_status": 200,
        "timeout": 5,
    }
}

# Statistical analysis configuration
STATS_CONFIG = {
    "percentiles": [50, 75, 90, 95, 99],  # Response time percentiles to track
    "moving_window": 300,  # seconds, for moving averages
    "min_samples": 100,    # Minimum samples for statistical significance
}

# Reporting configuration
REPORT_CONFIG = {
    "formats": ["console", "json", "html"],
    "charts": ["response_time_distribution", "success_rate_timeline", "error_distribution"],
    "metrics": [
        "avg_response_time",
        "success_rate",
        "error_rate",
        "timeout_rate",
        "throughput",
        "concurrent_connections"
    ]
}
