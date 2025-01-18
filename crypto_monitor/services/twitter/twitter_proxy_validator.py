"""Twitter proxy validator module."""
import asyncio
import time
import logging
from typing import Dict, Tuple, Any
from playwright.async_api import async_playwright, TimeoutError
try:
    from config import TWITTER_CONFIG
except ImportError:
    from tests.test_config import TWITTER_CONFIG

class TwitterProxyValidator:
    """Validates proxies for Twitter scraping compatibility."""

    def __init__(self, config: Dict[str, Any] = None):
        """Initialize the validator with configuration.
        
        Args:
            config: Configuration dictionary. If None, uses default TWITTER_CONFIG.
        """
        self.config = config or TWITTER_CONFIG
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)

    async def _check_twitter_access(self, page) -> bool:
        """Check if Twitter homepage is accessible.
        
        Args:
            page: Playwright page object.
            
        Returns:
            bool: True if Twitter is accessible, False otherwise.
            
        Raises:
            TimeoutError: If the page load times out.
            PlaywrightError: If there's a connection or other error.
        """
        url = next(url for url in self.config['validation_urls'] if 'home' in url)
        self.logger.debug(f"Accessing {url}")
        response = await page.goto(url, timeout=self.config['timeout'] * 1000)
        return response and response.ok

    async def _check_api_access(self, page) -> bool:
        """Check if Twitter API endpoints are accessible.
        
        Args:
            page: Playwright page object.
            
        Returns:
            bool: True if API is accessible, False otherwise.
            
        Raises:
            TimeoutError: If the page load times out.
            PlaywrightError: If there's a connection or other error.
        """
        api_urls = [url for url in self.config['validation_urls'] if 'graphql' in url or 'search' in url]
        for url in api_urls:
            self.logger.debug(f"Accessing {url}")
            response = await page.goto(url, timeout=self.config['timeout'] * 1000)
            if not (response and response.ok):
                return False
        return True

    async def _check_anonymity(self, page) -> bool:
        """Check if the proxy provides anonymity.
        
        Args:
            page: Playwright page object.
            
        Returns:
            bool: True if proxy is anonymous, False otherwise.
            
        Raises:
            TimeoutError: If the page load times out.
            PlaywrightError: If there's a connection or other error.
        """
        self.logger.debug("Checking proxy anonymity")
        response = await page.goto('https://lumtest.com/myip.json', timeout=self.config['timeout'] * 1000)
        if response and response.ok:
            content = await page.content()
            return '"type": "anonymous"' in content or '"type": "elite"' in content
        return False

    async def validate_proxy(self, proxy_url: str) -> Tuple[bool, Dict[str, Any]]:
        """Validate a single proxy for Twitter compatibility.
        
        Args:
            proxy_url: The proxy URL to validate.
            
        Returns:
            Tuple of (success, metrics) where metrics contains validation details.
        """
        metrics = {
            'twitter_accessible': False,
            'api_accessible': False,
            'anonymous': False,
            'response_time': None,
            'error': None
        }
        
        start_time = time.time()
        browser = None
        
        try:
            self.logger.debug(f"Starting proxy validation for {proxy_url}")
            async with async_playwright() as p:
                browser = await p.chromium.launch(proxy={'server': proxy_url})
                page = await browser.new_page()
                
                # 检查Twitter访问
                metrics['twitter_accessible'] = await self._check_twitter_access(page)
                if not metrics['twitter_accessible']:
                    return False, metrics
                
                # 检查API访问
                metrics['api_accessible'] = await self._check_api_access(page)
                if not metrics['api_accessible']:
                    return False, metrics
                
                # 检查匿名性
                metrics['anonymous'] = await self._check_anonymity(page)
                if not metrics['anonymous']:
                    metrics['error'] = "Proxy is not anonymous"
                    return False, metrics
                
                metrics['response_time'] = time.time() - start_time
                self.logger.debug(f"Proxy validation successful. Response time: {metrics['response_time']}s")
                return True, metrics
                
        except TimeoutError as e:
            error_msg = f"Timeout during validation: {str(e)}"
            self.logger.warning(error_msg)
            metrics['error'] = error_msg
            return False, metrics
        except Exception as e:
            error_msg = f"Validation failed: {str(e)}"
            self.logger.error(error_msg)
            metrics['error'] = str(e)
            return False, metrics
        finally:
            if browser:
                await browser.close()

    async def validate_with_retry(self, proxy_url: str) -> Tuple[bool, Dict[str, Any]]:
        """Validate a proxy with retry mechanism.
        
        Args:
            proxy_url: The proxy URL to validate.
            
        Returns:
            Tuple of (success, metrics) where metrics contains validation details.
        """
        last_metrics = None
        for attempt in range(self.config['max_retries']):
            self.logger.info(f"Validation attempt {attempt + 1}/{self.config['max_retries']}")
            success, metrics = await self.validate_proxy(proxy_url)
            if success:
                self.logger.info("Proxy validation successful")
                return True, metrics
            
            last_metrics = metrics
            if attempt < self.config['max_retries'] - 1:
                self.logger.info(f"Retrying proxy validation in {self.config['request_interval']} seconds")
                await asyncio.sleep(self.config['request_interval'])
                self.logger.info(f"Starting retry attempt {attempt + 2}/{self.config['max_retries']}")
        
        self.logger.warning("All retry attempts failed")
        return False, last_metrics
