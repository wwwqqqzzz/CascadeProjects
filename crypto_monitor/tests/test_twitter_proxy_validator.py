"""Tests for Twitter proxy validator."""
import unittest
import asyncio
import logging
import json
from unittest.mock import patch, AsyncMock, MagicMock as Mock
from playwright.async_api import TimeoutError, Error as PlaywrightError
from twitter_proxy_validator import TwitterProxyValidator
import test_config

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def async_test(coro):
    """Decorator for running async tests."""
    def wrapper(*args, **kwargs):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro(*args, **kwargs))
        finally:
            loop.close()
    return wrapper

class TestTwitterProxyValidator(unittest.TestCase):
    """Test cases for TwitterProxyValidator."""
    
    def setUp(self):
        """Set up test environment."""
        self.validator = TwitterProxyValidator(config=test_config.TWITTER_CONFIG)

    @patch('twitter_proxy_validator.TwitterProxyValidator._check_twitter_access')
    @patch('twitter_proxy_validator.TwitterProxyValidator._check_api_access')
    @patch('twitter_proxy_validator.TwitterProxyValidator._check_anonymity')
    @async_test
    async def test_validate_proxy_success(self, mock_anonymity, mock_api, mock_twitter):
        """Test successful proxy validation by mocking internal methods."""
        # 设置所有检查都返回成功
        mock_twitter.return_value = True
        mock_api.return_value = True
        mock_anonymity.return_value = True
        
        proxy_url = 'http://test-proxy:8080'
        success, metrics = await self.validator.validate_proxy(proxy_url)
        
        self.assertTrue(success)
        self.assertTrue(metrics['twitter_accessible'])
        self.assertTrue(metrics['api_accessible'])
        self.assertTrue(metrics['anonymous'])

    @patch('twitter_proxy_validator.TwitterProxyValidator._check_twitter_access')
    @async_test
    async def test_validate_proxy_failure(self, mock_twitter):
        """Test failed proxy validation."""
        # 设置Twitter检查失败
        mock_twitter.side_effect = TimeoutError("Connection timed out")
        
        proxy_url = 'http://test-proxy:8080'
        success, metrics = await self.validator.validate_proxy(proxy_url)
        
        self.assertFalse(success)
        self.assertFalse(metrics['twitter_accessible'])
        self.assertFalse(metrics['api_accessible'])
        self.assertFalse(metrics['anonymous'])
        self.assertIn('timeout', metrics['error'].lower())

    @patch('twitter_proxy_validator.TwitterProxyValidator.validate_proxy')
    @async_test
    async def test_validate_with_retry(self, mock_validate):
        """Test proxy validation retry mechanism."""
        proxy_url = 'http://test-proxy:8080'
        
        # 设置第一次失败，第二次成功
        mock_validate.side_effect = [
            (False, {'error': 'First attempt failed', 'twitter_accessible': False}),
            (True, {
                'twitter_accessible': True,
                'api_accessible': True,
                'anonymous': True,
                'response_time': 0.5
            })
        ]
        
        success, metrics = await self.validator.validate_with_retry(proxy_url)
        
        self.assertTrue(success)
        self.assertTrue(metrics['twitter_accessible'])
        self.assertTrue(metrics['api_accessible'])
        self.assertTrue(metrics['anonymous'])
        self.assertIsNotNone(metrics['response_time'])
        
        # 验证重试次数
        self.assertEqual(mock_validate.call_count, 2)

if __name__ == '__main__':
    unittest.main()
