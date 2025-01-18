"""
Test proxy manager functionality.
"""

import sys
from pathlib import Path
import asyncio
import logging
import os
from dotenv import load_dotenv
from functools import partial
import unittest

# Add parent directory to Python path
sys.path.append(str(Path(__file__).parent.parent))

from proxy_manager import ProxyManager
from config import LOGGING_CONFIG

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,  # Change to DEBUG level
    format=LOGGING_CONFIG['log_format']
)
logger = logging.getLogger('ProxyTest')

# Also enable debug for ProxyManager
logging.getLogger('ProxyManager').setLevel(logging.DEBUG)

class TestProxy(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        """Set up test fixtures."""
        self.proxy_manager = ProxyManager()
        self.test_urls = [
            "http://httpbin.org/status/200",  # Fast response
            "http://1.1.1.1",  # Cloudflare DNS, very fast
            "http://httpbin.org/ip"  # IP check
        ]
        self.test_timeout = 5  # Shorter timeout for tests

    async def test_proxy_manager(self):
        """Test the proxy manager functionality."""
        logger.info("Testing proxy manager...")
        
        # Test proxy retrieval
        logger.info("Testing proxy retrieval...")
        proxy = await self.proxy_manager.get_proxy()
        self.assertIsNotNone(proxy)
        logger.info(f"Successfully retrieved proxy: {proxy['server']}")
        
        # Test the proxy with multiple URLs
        for test_url in self.test_urls:
            logger.info(f"Testing proxy {proxy['server']} with {test_url}...")
            success, response_time = await self.proxy_manager.test_proxy(proxy, test_url, timeout=self.test_timeout)
            if success:
                logger.info(f"Successfully connected to {test_url} in {response_time:.2f}s")
                break
            else:
                logger.warning(f"Connection failed for {test_url}")
        
        if not success:
            logger.warning("Initial proxy failed, trying another one...")
            proxy = await self.proxy_manager.get_proxy()
            self.assertIsNotNone(proxy)
            logger.info(f"Trying alternate proxy: {proxy['server']}")
            
            for test_url in self.test_urls:
                logger.info(f"Testing proxy {proxy['server']} with {test_url}...")
                success, response_time = await self.proxy_manager.test_proxy(proxy, test_url, timeout=self.test_timeout)
                if success:
                    logger.info(f"Successfully connected to {test_url} in {response_time:.2f}s")
                    break
                else:
                    logger.warning(f"Connection failed for {test_url}")

if __name__ == "__main__":
    try:
        # Check for required environment variables
        if not os.getenv('WEBSHARE_API_KEY'):
            logger.error("WEBSHARE_API_KEY not found in environment variables")
            logger.error("Please set WEBSHARE_API_KEY in your .env file")
            sys.exit(1)
            
        # Run test with timeout
        unittest.main(argv=['first-arg-is-ignored'], exit=False)
        
    except KeyboardInterrupt:
        logger.info("\nTest interrupted by user")
    except Exception as e:
        logger.error(f"Test failed: {e}")
        sys.exit(1)
