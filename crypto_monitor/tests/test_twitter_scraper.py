"""
Test Twitter scraper functionality.
"""

import sys
from pathlib import Path
import time
import logging
from datetime import datetime
import asyncio
import os
from dotenv import load_dotenv

# Add parent directory to Python path
sys.path.append(str(Path(__file__).parent.parent))

from twitter_scraper import TwitterScraper
from config import LOGGING_CONFIG

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format=LOGGING_CONFIG['log_format']
)
logger = logging.getLogger('TwitterScraperTest')

# Test configuration
TEST_CONFIG = {
    'users': ['cz_binance', 'VitalikButerin'],
    'tweets_per_user': 3,
    'monitoring_duration': 30,  # seconds
    'check_interval': 10,  # seconds between monitoring checks
    'user_delay': 2,  # seconds between checking different users
}

async def test_proxy_setup():
    """Test proxy configuration and connection."""
    logger.info("Testing proxy setup...")
    
    scraper = TwitterScraper()
    try:
        # Initialize browser to test proxy
        await scraper.init_browser()
        if scraper.current_proxy:
            logger.info("Successfully initialized browser with proxy")
            logger.info(f"Using proxy: {scraper.current_proxy['server']}")
        else:
            logger.warning("No proxy available, browser initialized without proxy")
            
    except Exception as e:
        logger.error(f"Failed to initialize browser: {e}")
        raise
    finally:
        await scraper.cleanup()

async def test_tweet_retrieval(scraper: TwitterScraper, username: str, max_tweets: int) -> bool:
    """
    Test tweet retrieval for a specific user.
    
    Args:
        scraper: TwitterScraper instance
        username: Twitter username to test
        max_tweets: Maximum number of tweets to retrieve
        
    Returns:
        bool: True if tweets were successfully retrieved
    """
    logger.info(f"\nTesting tweet retrieval for @{username}")
    
    try:
        # Get recent tweets
        tweets = await scraper.get_user_tweets(username, max_tweets=max_tweets)
        
        if tweets:
            logger.info(f"Found {len(tweets)} tweets:")
            for tweet in tweets:
                relevance = "RELEVANT" if scraper.is_relevant_tweet(tweet) else "NOT RELEVANT"
                logger.info(
                    f"\n[{relevance}] Tweet from @{tweet['username']}:"
                    f"\nTime: {tweet['timestamp']}"
                    f"\nText: {tweet['text']}"
                    f"\nMetrics: {tweet['metrics']}"
                    f"\nURL: {tweet['url']}"
                    f"\nHashtags: {', '.join(tweet['hashtags'])}"
                    f"\n{'-'*50}"
                )
            return True
        else:
            logger.warning(f"No tweets found for @{username}")
            return False
            
    except Exception as e:
        logger.error(f"Error retrieving tweets for @{username}: {e}")
        return False

async def test_continuous_monitoring(scraper: TwitterScraper, duration: int, check_interval: int, user_delay: int):
    """
    Test continuous monitoring of tweets.
    
    Args:
        scraper: TwitterScraper instance
        duration: Duration to monitor in seconds
        check_interval: Time between monitoring checks in seconds
        user_delay: Time between checking different users in seconds
    """
    logger.info(f"\nTesting continuous monitoring ({duration} seconds)...")
    
    start_time = datetime.now()
    check_count = 0
    
    try:
        while (datetime.now() - start_time).seconds < duration:
            check_count += 1
            logger.info(f"\nMonitoring check #{check_count}")
            
            for username in TEST_CONFIG['users']:
                try:
                    tweets = await scraper.get_user_tweets(username, max_tweets=1)
                    for tweet in tweets:
                        if scraper.is_relevant_tweet(tweet):
                            logger.info(
                                f"\nNew relevant tweet from @{username}:"
                                f"\nText: {tweet['text']}"
                                f"\nTime: {tweet['timestamp']}"
                                f"\nMetrics: {tweet['metrics']}"
                                f"\nURL: {tweet['url']}"
                                f"\nHashtags: {', '.join(tweet['hashtags'])}"
                            )
                except Exception as e:
                    logger.error(f"Error monitoring @{username}: {e}")
                    continue
                    
                # Sleep between users
                await asyncio.sleep(user_delay)
                
            remaining = duration - (datetime.now() - start_time).seconds
            if remaining > 0:
                logger.info(f"Waiting {min(check_interval, remaining)} seconds before next check...")
                await asyncio.sleep(min(check_interval, remaining))
                
    except asyncio.CancelledError:
        logger.info("Monitoring test cancelled")
    except Exception as e:
        logger.error(f"Error during monitoring: {e}")
        raise

async def test_scraper():
    """Run all Twitter scraper tests."""
    scraper = None
    
    try:
        logger.info("Starting Twitter scraper test suite...")
        
        # Test proxy setup first
        await test_proxy_setup()
        
        # Create scraper instance for remaining tests
        scraper = TwitterScraper()
        
        # Test individual users
        success_count = 0
        for username in TEST_CONFIG['users']:
            if await test_tweet_retrieval(scraper, username, TEST_CONFIG['tweets_per_user']):
                success_count += 1
                
        if success_count == 0:
            logger.error("Failed to retrieve tweets for any user")
            return
            
        # Test continuous monitoring
        await test_continuous_monitoring(
            scraper,
            TEST_CONFIG['monitoring_duration'],
            TEST_CONFIG['check_interval'],
            TEST_CONFIG['user_delay']
        )
        
        logger.info("\nTest suite completed successfully!")
        
    except Exception as e:
        logger.error(f"Test suite failed: {e}")
        raise
        
    finally:
        if scraper:
            await scraper.cleanup()

if __name__ == "__main__":
    try:
        # Check for required environment variables
        if not os.getenv('WEBSHARE_API_KEY'):
            logger.error("WEBSHARE_API_KEY not found in environment variables")
            logger.error("Please set WEBSHARE_API_KEY in your .env file")
            sys.exit(1)
            
        asyncio.run(test_scraper())
        
    except KeyboardInterrupt:
        logger.info("\nTest interrupted by user")
    except Exception as e:
        logger.error(f"Test failed: {e}")
        sys.exit(1)
