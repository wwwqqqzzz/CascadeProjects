"""Test configuration file."""
from typing import List, Dict

# Test URLs for different purposes
PROXY_TEST_URLS: List[Dict[str, str]] = [
    {
        "url": "http://httpbin.org/ip",
        "description": "IP address check",
        "expected_type": "json",
        "timeout": 10
    },
    {
        "url": "http://1.1.1.1",
        "description": "Basic connectivity check",
        "expected_type": "html",
        "timeout": 5
    },
    {
        "url": "http://httpbin.org/status/200",
        "description": "Status code check",
        "expected_type": "any",
        "timeout": 5
    },
    {
        "url": "https://api.ipify.org?format=json",
        "description": "Alternative IP check",
        "expected_type": "json",
        "timeout": 10
    }
]

# Test configurations
TEST_CONFIG = {
    "max_retries": 3,
    "retry_delay": 1,  # seconds
    "concurrent_tests": 2,  # number of concurrent test runs
    "test_timeout": 30,  # seconds
    "connection_timeout": 10,  # seconds
    "read_timeout": 10,  # seconds
}

# User agents for testing
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15"
]

# Test result codes
class TestResult:
    SUCCESS = "SUCCESS"
    TIMEOUT = "TIMEOUT"
    CONNECTION_ERROR = "CONNECTION_ERROR"
    RESPONSE_ERROR = "RESPONSE_ERROR"
    INVALID_RESPONSE = "INVALID_RESPONSE"
