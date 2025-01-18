"""Unit tests for proxy source manager."""
import unittest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from proxy_source_manager import ProxySourceManager, ProxySource, ProxyValidationResult

class TestProxySourceManager(unittest.TestCase):
    """Test cases for ProxySourceManager."""
    
    def setUp(self):
        """Set up test environment."""
        self.manager = ProxySourceManager()
        
    def test_load_sources(self):
        """Test loading proxy sources from configuration."""
        self.assertGreater(len(self.manager.sources), 0)
        self.assertIn('proxylist', self.manager.sources)
        self.assertIn('pubproxy', self.manager.sources)
        
    def test_proxy_validation_result(self):
        """Test ProxyValidationResult functionality."""
        result = ProxyValidationResult(
            is_valid=True,
            response_time=1.5,
            anonymous=True
        )
        self.assertTrue(result.is_valid)
        self.assertEqual(result.response_time, 1.5)
        self.assertTrue(result.anonymous)
        
    @patch('aiohttp.ClientSession.get')
    async def test_validate_proxy(self, mock_get):
        """Test proxy validation."""
        # Mock successful response
        mock_response = Mock()
        mock_response.status = 200
        mock_response.json = asyncio.coroutine(lambda: {'ip': '1.2.3.4'})
        mock_get.return_value.__aenter__.return_value = mock_response
        
        proxy = {
            'server': '1.2.3.4:8080',
            'protocol': 'http'
        }
        
        result = await self.manager.validate_proxy(proxy)
        self.assertTrue(result.is_valid)
        self.assertIsNotNone(result.response_time)
        
    @patch('aiohttp.ClientSession.get')
    async def test_validate_proxy_failure(self, mock_get):
        """Test proxy validation failure."""
        # Mock failed response
        mock_get.side_effect = asyncio.TimeoutError()
        
        proxy = {
            'server': '1.2.3.4:8080',
            'protocol': 'http'
        }
        
        result = await self.manager.validate_proxy(proxy)
        self.assertFalse(result.is_valid)
        self.assertEqual(result.error_type, 'timeout')
        
    async def test_cleanup_validation_cache(self):
        """Test validation cache cleanup."""
        # Add some expired results to cache
        old_time = datetime.now() - timedelta(seconds=400)
        self.manager.validation_cache = {
            'test1': ProxyValidationResult(
                is_valid=True,
                last_checked=old_time
            ),
            'test2': ProxyValidationResult(
                is_valid=True,
                last_checked=datetime.now()
            )
        }
        
        await self.manager.cleanup_validation_cache()
        self.assertEqual(len(self.manager.validation_cache), 1)
        self.assertNotIn('test1', self.manager.validation_cache)
        self.assertIn('test2', self.manager.validation_cache)
        
    @patch('proxy_source_manager.ProxySourceManager.fetch_proxies')
    async def test_get_validated_proxies(self, mock_fetch):
        """Test getting validated proxies."""
        # Mock proxy fetching
        mock_fetch.return_value = [
            {'server': '1.2.3.4:8080', 'protocol': 'http', 'source': 'test'},
            {'server': '5.6.7.8:8080', 'protocol': 'http', 'source': 'test'}
        ]
        
        # Mock proxy validation
        with patch.object(
            self.manager,
            'validate_proxy',
            side_effect=[
                ProxyValidationResult(is_valid=True, response_time=1.0),
                ProxyValidationResult(is_valid=False, error_type='timeout')
            ]
        ):
            proxies = await self.manager.get_validated_proxies(min_count=1)
            self.assertEqual(len(proxies), 1)
            
    def test_source_success_rate(self):
        """Test source success rate calculation."""
        source = ProxySource(name='test', url='http://test.com')
        self.assertEqual(source.success_rate, 1.0)  # Initial rate
        
        # Test rate update
        asyncio.run(
            self.manager.update_source_stats(source, valid_count=8, total_count=10)
        )
        self.assertAlmostEqual(source.success_rate, 0.94)  # Using alpha=0.3
        
def async_test(coro):
    """Decorator for running async tests."""
    def wrapper(*args, **kwargs):
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(coro(*args, **kwargs))
    return wrapper

if __name__ == '__main__':
    unittest.main()
