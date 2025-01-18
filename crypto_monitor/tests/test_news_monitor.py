"""
Test news monitor functionality.
"""

import sys
from pathlib import Path
import asyncio
import logging
from datetime import datetime, timedelta

# Add parent directory to Python path
sys.path.append(str(Path(__file__).parent.parent))

from crypto_monitor.core.news_monitor import NewsMonitor
from config import LOGGING_CONFIG, TWITTER_USERS_TO_FOLLOW

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format=LOGGING_CONFIG['log_format'],
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger('NewsMonitorTest')

async def main():
    """Run news monitor test."""
    monitor = NewsMonitor()
    
    try:
        logger.info("Starting news monitor test...")
        
        # Get tweets from the last hour
        current_time = datetime.utcnow()
        last_hour = current_time - timedelta(hours=1)
        
        # Check tweets for each user
        for username in TWITTER_USERS_TO_FOLLOW:
            logger.info(f"\nChecking tweets from @{username}...")
            tweets = await monitor.get_user_tweets(username, last_hour)
            
            if tweets:
                logger.info(f"Found {len(tweets)} tweets:")
                for tweet in tweets:
                    if monitor.is_relevant_tweet(tweet):
                        logger.info(
                            f"[RELEVANT] {tweet['created_at']}: {tweet['text']}\n"
                            f"Metrics: {tweet['metrics']}\n"
                        )
                    else:
                        logger.debug(
                            f"[IGNORED] {tweet['created_at']}: {tweet['text']}\n"
                            f"Metrics: {tweet['metrics']}\n"
                        )
            else:
                logger.info("No new tweets found")
                
            # Sleep to respect rate limits
            await asyncio.sleep(2)
            
        logger.info("\nTest complete!")
        
    except Exception as e:
        logger.error(f"Error during test: {e}")
        raise  # Re-raise to see full traceback
        
    finally:
        await monitor.stop()

if __name__ == "__main__":
    asyncio.run(main())
