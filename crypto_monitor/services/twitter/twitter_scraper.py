"""
Twitter scraper module for cryptocurrency monitoring.
Uses Playwright to scrape tweets without API.
"""

import time
import logging
import random
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
import asyncio
from playwright.async_api import async_playwright, Page, Browser, BrowserContext
import os
from dotenv import load_dotenv
from bs4 import BeautifulSoup

from ...utils.config import LOGGING_CONFIG, TWITTER_CONFIG
from ...utils.logger import setup_logger
from ...infrastructure.proxy.proxy_manager import ProxyManager

# Load environment variables
load_dotenv()

# Set up logging
logger = setup_logger(
    name='twitter_scraper',
    level=logging.INFO
)

class TwitterScraper:
    def __init__(self):
        """Initialize Twitter scraper."""
        self.important_users = [
            'cz_binance',      # Binance CEO
            'VitalikButerin',  # Ethereum founder
            'SBF_FTX',        # FTX CEO
            'elonmusk',       # Elon Musk
        ]
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.proxy_manager = ProxyManager()
        self.current_proxy = None
        self.max_retries = 3
        self.rate_limit_delay = 2  # Base delay between requests in seconds
        self.rate_limit_multiplier = 1.5  # Multiplier for exponential backoff
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.131 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
        ]
        
    async def init_browser(self):
        """Initialize browser if not already initialized."""
        if not self.browser:
            try:
                # Get a working proxy
                self.current_proxy = await self.proxy_manager.get_proxy()
                if not self.current_proxy:
                    logger.warning("No proxy available, initializing browser without proxy")
                else:
                    logger.info(f"Using proxy: {self.current_proxy['server']}")
                    
                # Format proxy for Playwright
                proxy_config = None
                if self.current_proxy:
                    proxy_config = {
                        'server': self.current_proxy['server'],
                        'username': self.current_proxy.get('username'),
                        'password': self.current_proxy.get('password'),
                    }
                    # Remove None values
                    proxy_config = {k: v for k, v in proxy_config.items() if v is not None}
                
                playwright = await async_playwright().start()
                browser_args = [
                    '--disable-blink-features=AutomationControlled',
                    '--disable-features=IsolateOrigins,site-per-process',
                    '--disable-site-isolation-trials',
                    '--disable-web-security',
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-accelerated-2d-canvas',
                    '--disable-gpu',
                    '--hide-scrollbars',
                ]
                
                self.browser = await playwright.chromium.launch(
                    headless=True,
                    proxy=proxy_config,
                    args=browser_args
                )
                
                # Enhanced stealth mode
                context_options = {
                    'viewport': {'width': 1920, 'height': 1080},
                    'user_agent': random.choice(self.user_agents),
                    'java_script_enabled': True,
                    'bypass_csp': True,
                    'ignore_https_errors': True,
                    'extra_http_headers': {
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.5',
                        'Accept-Encoding': 'gzip, deflate, br',
                        'DNT': '1',
                        'Connection': 'keep-alive',
                        'Upgrade-Insecure-Requests': '1',
                        'Sec-Fetch-Dest': 'document',
                        'Sec-Fetch-Mode': 'navigate',
                        'Sec-Fetch-Site': 'none',
                        'Sec-Fetch-User': '?1',
                        'Cache-Control': 'max-age=0'
                    }
                }
                
                # Add proxy authentication if needed
                if proxy_config and proxy_config.get('username'):
                    context_options['proxy'] = proxy_config
                
                self.context = await self.browser.new_context(**context_options)
                
                # Add stealth scripts
                await self.context.add_init_script("""
                    // Override navigator properties
                    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                    Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
                    Object.defineProperty(navigator, 'productSub', { get: () => '20100101' });
                    Object.defineProperty(navigator, 'vendor', { get: () => 'Google Inc.' });
                    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                    
                    // Add fake web APIs
                    window.chrome = {
                        app: {
                            InstallState: {
                                DISABLED: 'DISABLED',
                                INSTALLED: 'INSTALLED',
                                NOT_INSTALLED: 'NOT_INSTALLED'
                            },
                            RunningState: {
                                CANNOT_RUN: 'CANNOT_RUN',
                                READY_TO_RUN: 'READY_TO_RUN',
                                RUNNING: 'RUNNING'
                            },
                            getDetails: function() {},
                            getIsInstalled: function() {},
                            installState: function() {},
                            isInstalled: false,
                            runningState: function() {}
                        },
                        runtime: {
                            OnInstalledReason: {
                                CHROME_UPDATE: 'chrome_update',
                                INSTALL: 'install',
                                SHARED_MODULE_UPDATE: 'shared_module_update',
                                UPDATE: 'update'
                            },
                            OnRestartRequiredReason: {
                                APP_UPDATE: 'app_update',
                                OS_UPDATE: 'os_update',
                                PERIODIC: 'periodic'
                            },
                            PlatformArch: {
                                ARM: 'arm',
                                ARM64: 'arm64',
                                MIPS: 'mips',
                                MIPS64: 'mips64',
                                X86_32: 'x86-32',
                                X86_64: 'x86-64'
                            },
                            PlatformNaclArch: {
                                ARM: 'arm',
                                MIPS: 'mips',
                                MIPS64: 'mips64',
                                X86_32: 'x86-32',
                                X86_64: 'x86-64'
                            },
                            PlatformOs: {
                                ANDROID: 'android',
                                CROS: 'cros',
                                LINUX: 'linux',
                                MAC: 'mac',
                                OPENBSD: 'openbsd',
                                WIN: 'win'
                            },
                            RequestUpdateCheckStatus: {
                                NO_UPDATE: 'no_update',
                                THROTTLED: 'throttled',
                                UPDATE_AVAILABLE: 'update_available'
                            }
                        }
                    };
                    
                    // Modify iframe behavior
                    HTMLIFrameElement.prototype.contentWindow.Object.defineProperty = function() {};
                """)
                
                logger.info(f"Browser initialized successfully with proxy: {bool(proxy_config)}")
                
            except Exception as e:
                logger.error(f"Failed to initialize browser: {e}")
                if self.current_proxy:
                    await self.proxy_manager.mark_proxy_failed(self.current_proxy)
                await self.cleanup()
                raise
            
    async def get_user_tweets(self, username: str, max_tweets: int = 5) -> List[Dict]:
        """
        Get recent tweets from a user's profile using Playwright.
        
        Args:
            username: Twitter username
            max_tweets: Maximum number of tweets to retrieve
            
        Returns:
            List of tweets with text and metadata
        """
        tweets = []
        retry_count = 0
        current_delay = self.rate_limit_delay
        
        while retry_count < self.max_retries:
            try:
                logger.info(f"Fetching tweets from @{username}")
                
                await self.init_browser()
                page = await self.context.new_page()
                
                # Add additional page-level stealth
                await page.add_init_script("""
                    Object.defineProperty(navigator, 'platform', {
                        get: () => 'Win32'
                    });
                    Object.defineProperty(navigator, 'productSub', {
                        get: () => '20100101'
                    });
                    Object.defineProperty(navigator, 'vendor', {
                        get: () => 'Google Inc.'
                    });
                """)
                
                # Set default timeout
                page.set_default_timeout(45000)  # 45 seconds
                
                # Navigate to user's profile with retry logic
                max_nav_retries = 2
                nav_retry = 0
                while nav_retry < max_nav_retries:
                    try:
                        response = await page.goto(
                            f'https://twitter.com/{username}',
                            wait_until='domcontentloaded',
                            timeout=30000
                        )
                        
                        if response and response.ok():
                            break
                        elif response and response.status == 429:
                            logger.warning("Rate limited, increasing delay...")
                            current_delay *= self.rate_limit_multiplier
                            await asyncio.sleep(current_delay)
                            
                        nav_retry += 1
                        if nav_retry < max_nav_retries:
                            await asyncio.sleep(random.uniform(2, 4))
                            
                    except Exception as e:
                        logger.error(f"Navigation error (attempt {nav_retry + 1}): {e}")
                        nav_retry += 1
                        if nav_retry < max_nav_retries:
                            await asyncio.sleep(random.uniform(2, 4))
                        else:
                            raise
                
                # Wait for tweets with retry logic
                max_wait_retries = 2
                wait_retry = 0
                while wait_retry < max_wait_retries:
                    try:
                        await page.wait_for_selector(
                            'article[data-testid="tweet"]',
                            timeout=30000,
                            state='attached'
                        )
                        break
                    except Exception as e:
                        logger.error(f"Wait error (attempt {wait_retry + 1}): {e}")
                        wait_retry += 1
                        if wait_retry < max_wait_retries:
                            await asyncio.sleep(random.uniform(2, 4))
                        else:
                            raise
                
                # Get tweets
                tweet_elements = await page.query_selector_all('article[data-testid="tweet"]')
                
                for element in tweet_elements[:max_tweets]:
                    try:
                        # Extract tweet text
                        text_element = await element.query_selector('div[data-testid="tweetText"]')
                        tweet_text = await text_element.inner_text() if text_element else ''
                        
                        # Extract timestamp
                        time_element = await element.query_selector('time')
                        timestamp = await time_element.get_attribute('datetime') if time_element else ''
                        
                        # Extract metrics
                        metrics = {
                            'replies': await self._get_metric(element, 'reply'),
                            'retweets': await self._get_metric(element, 'retweet'),
                            'likes': await self._get_metric(element, 'like')
                        }
                        
                        # Extract media presence
                        media_element = await element.query_selector('div[data-testid="tweetPhoto"], div[data-testid="videoPlayer"]')
                        has_media = bool(media_element)
                        
                        # Extract hashtags
                        hashtags = []
                        hashtag_elements = await element.query_selector_all('a[href^="/hashtag/"]')
                        for hashtag_el in hashtag_elements:
                            tag = await hashtag_el.inner_text()
                            if tag.startswith('#'):
                                hashtags.append(tag[1:])  # Remove '#' prefix
                                
                        # Get tweet URL
                        link_element = await element.query_selector('a[href*="/status/"]')
                        url = await link_element.get_attribute('href') if link_element else ''
                        if url:
                            url = f'https://twitter.com{url}'
                            
                        tweets.append({
                            'username': username,
                            'text': tweet_text,
                            'timestamp': timestamp,
                            'metrics': metrics,
                            'url': url,
                            'media': has_media,
                            'hashtags': hashtags
                        })
                        
                    except Exception as e:
                        logger.error(f"Error parsing tweet: {e}")
                        continue
                        
                await page.close()
                
                # Update proxy score on success
                if self.current_proxy:
                    await self.proxy_manager.update_proxy_score(
                        self.current_proxy,
                        success=True,
                        response_time=random.uniform(0.5, 2.0)  # Approximate response time
                    )
                    
                # Reset delay on success
                current_delay = self.rate_limit_delay
                break  # Success, exit retry loop
                
            except Exception as e:
                logger.error(f"Error fetching tweets for @{username}: {e}")
                retry_count += 1
                
                if self.current_proxy:
                    await self.proxy_manager.mark_proxy_failed(self.current_proxy)
                    
                # Clean up and try with a new proxy
                await self.cleanup()
                self.browser = None
                self.context = None
                
                if retry_count < self.max_retries:
                    logger.info(f"Retrying with new proxy (attempt {retry_count + 1}/{self.max_retries})")
                    await asyncio.sleep(current_delay)  # Wait before retry
                    current_delay *= self.rate_limit_multiplier  # Increase delay for next retry
                    
        return tweets
        
    async def _get_metric(self, element: Page, metric_type: str) -> int:
        """Extract metric value from tweet element."""
        try:
            metric_element = await element.query_selector(f'div[data-testid="{metric_type}"]')
            if metric_element:
                metric_text = await metric_element.inner_text()
                # Convert K/M to actual numbers
                if 'K' in metric_text:
                    return int(float(metric_text.replace('K', '')) * 1000)
                elif 'M' in metric_text:
                    return int(float(metric_text.replace('M', '')) * 1000000)
                else:
                    return int(metric_text) if metric_text else 0
            return 0
        except (ValueError, TypeError):
            return 0
            
    def is_relevant_tweet(self, tweet: Dict) -> bool:
        """
        Check if a tweet is relevant for crypto trading.
        
        Args:
            tweet: Tweet dictionary with text and metrics
            
        Returns:
            True if tweet is relevant, False otherwise
        """
        # Keywords indicating important information
        important_keywords = [
            'announcement', 'launch', 'partnership',
            'listing', 'update', 'upgrade',
            'mainnet', 'trading', 'airdrop',
            'token', 'blockchain', 'crypto',
            'bitcoin', 'ethereum', 'binance',
            'regulation', 'sec', 'breaking'
        ]
        
        text = tweet['text'].lower()
        
        # Check for important keywords
        if any(keyword in text for keyword in important_keywords):
            return True
            
        # Check for significant engagement
        metrics = tweet['metrics']
        if metrics:
            if (metrics['retweets'] > 100 or
                metrics['likes'] > 500 or
                metrics['replies'] > 50):
                return True
                
        # Check for media content (images/videos often indicate important announcements)
        if tweet.get('media', False):
            return True
            
        # Check for relevant hashtags
        crypto_hashtags = {
            'crypto', 'bitcoin', 'ethereum', 'blockchain',
            'defi', 'nft', 'web3', 'cryptocurrency'
        }
        tweet_hashtags = {tag.lower() for tag in tweet.get('hashtags', [])}
        if crypto_hashtags & tweet_hashtags:  # Set intersection
            return True
            
        return False
        
    async def monitor_tweets(self, interval_seconds: int = 300):
        """
        Continuously monitor tweets from important users.
        
        Args:
            interval_seconds: Time between checks in seconds
        """
        try:
            while True:
                try:
                    for username in self.important_users:
                        tweets = await self.get_user_tweets(username)
                        
                        for tweet in tweets:
                            if self.is_relevant_tweet(tweet):
                                logger.info(
                                    f"\nRelevant tweet from @{username}:"
                                    f"\nText: {tweet['text']}"
                                    f"\nTime: {tweet['timestamp']}"
                                    f"\nMetrics: {tweet['metrics']}"
                                    f"\nURL: {tweet['url']}"
                                    f"\nHashtags: {', '.join(tweet['hashtags'])}"
                                )
                                
                        # Random delay between users
                        await asyncio.sleep(random.uniform(2, 4))
                        
                    # Random delay between checks
                    delay = random.uniform(
                        interval_seconds * 0.8,
                        interval_seconds * 1.2
                    )
                    logger.info(f"Sleeping for {int(delay)} seconds...")
                    await asyncio.sleep(delay)
                    
                except Exception as e:
                    logger.error(f"Error in tweet monitoring: {e}")
                    await asyncio.sleep(60)  # Sleep on error
                    
        finally:
            await self.cleanup()
            
    async def cleanup(self):
        """Clean up resources."""
        try:
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
        finally:
            self.context = None
            self.browser = None

# Example usage
if __name__ == "__main__":
    scraper = TwitterScraper()
    try:
        asyncio.run(scraper.monitor_tweets())
    finally:
        # We need to run cleanup in the event loop
        asyncio.run(scraper.cleanup())
