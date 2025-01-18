"""
Basic Twitter API v2 functionality test.
Tests only the endpoints available in Essential access level.
"""

import os
import sys
from pathlib import Path
import logging
from datetime import datetime, timedelta

# Add parent directory to Python path for importing config
sys.path.append(str(Path(__file__).parent.parent))

import tweepy
from config import (
    TWITTER_BEARER_TOKEN,
    LOGGING_CONFIG
)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format=LOGGING_CONFIG['log_format'],
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger('TwitterBasicTest')

def test_authentication():
    """Test basic Twitter API v2 authentication."""
    try:
        # Create client with only Bearer Token for read-only access
        client = tweepy.Client(
            bearer_token=TWITTER_BEARER_TOKEN,
            wait_on_rate_limit=True
        )
        
        # Test connection by searching for a tweet
        test_search = client.search_recent_tweets(
            query="bitcoin",
            max_results=10  # Changed from 1 to 10 to meet API requirements
        )
        if test_search.data:
            logger.info("Authentication successful! API connection working.")
            return client
        else:
            logger.warning("Authentication successful but no test data retrieved")
            return client
        
    except Exception as e:
        logger.error(f"Authentication failed: {str(e)}")
        return None

def test_search_tweets(client):
    """Test searching recent tweets."""
    if not client:
        return
        
    logger.info("\nTesting tweet search...")
    try:
        # Search for recent tweets about Bitcoin
        query = "bitcoin lang:en -is:retweet"
        tweets = client.search_recent_tweets(
            query=query,
            max_results=10,
            tweet_fields=['created_at', 'public_metrics', 'author_id']
        )
        
        if tweets.data:
            logger.info(f"Found {len(tweets.data)} tweets about Bitcoin:")
            for tweet in tweets.data:
                logger.info(f"- [{tweet.created_at}] {tweet.text[:100]}...")
                metrics = tweet.public_metrics
                if metrics:
                    logger.info(f"  Metrics: Retweets={metrics['retweet_count']}, "
                              f"Likes={metrics['like_count']}, "
                              f"Replies={metrics['reply_count']}")
        else:
            logger.warning("No tweets found")
            
    except Exception as e:
        logger.error(f"Error searching tweets: {str(e)}")

def test_tweet_counts(client):
    """Test getting tweet counts."""
    if not client:
        return
        
    logger.info("\nTesting tweet counts...")
    try:
        # Get tweet counts for the last 24 hours, ending 10 seconds ago
        end_time = datetime.utcnow() - timedelta(seconds=10)
        start_time = end_time - timedelta(days=1)
        
        counts = client.get_recent_tweets_count(
            query="bitcoin",
            start_time=start_time,
            end_time=end_time,
            granularity='hour'
        )
        
        if counts.data:
            total_count = sum(count['tweet_count'] for count in counts.data)
            logger.info(f"Found {total_count} tweets about Bitcoin in the last 24 hours")
            logger.info("Hourly breakdown (last 5 hours):")
            for count in counts.data[-5:]:  # Show last 5 hours
                logger.info(f"- {count['start']}: {count['tweet_count']} tweets")
        else:
            logger.warning("No tweet counts available")
            
    except Exception as e:
        logger.error(f"Error getting tweet counts: {str(e)}")

def main():
    """Run basic API tests."""
    logger.info("Starting Twitter API v2 basic tests...")
    
    # Test authentication
    client = test_authentication()
    if not client:
        logger.error("Authentication failed. Stopping tests.")
        return
    
    # Test tweet search
    test_search_tweets(client)
    
    # Test tweet counts
    test_tweet_counts(client)
    
    logger.info("\nAll basic tests complete!")

if __name__ == "__main__":
    main()
