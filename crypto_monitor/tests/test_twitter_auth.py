"""
Test Twitter API authentication and basic functionality.
This script verifies that we can connect to Twitter's API and perform basic operations.
"""

import os
import sys
from pathlib import Path
import logging
from datetime import datetime
import time

# Add parent directory to Python path for importing config
sys.path.append(str(Path(__file__).parent.parent))

import tweepy
from config import (
    TWITTER_API_KEY,
    TWITTER_API_SECRET,
    TWITTER_ACCESS_TOKEN,
    TWITTER_ACCESS_TOKEN_SECRET,
    TWITTER_BEARER_TOKEN,
    TWITTER_USERS_TO_FOLLOW,
    LOGGING_CONFIG
)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format=LOGGING_CONFIG['log_format'],
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger('TwitterTest')

def test_authentication():
    """Test Twitter API v2 authentication."""
    try:
        # Test v2 authentication with Bearer Token
        client = tweepy.Client(
            bearer_token=TWITTER_BEARER_TOKEN,
            consumer_key=TWITTER_API_KEY,
            consumer_secret=TWITTER_API_SECRET,
            access_token=TWITTER_ACCESS_TOKEN,
            access_token_secret=TWITTER_ACCESS_TOKEN_SECRET,
            wait_on_rate_limit=True
        )
        
        # Verify credentials by getting own user info
        me = client.get_me()
        if me.data:
            logger.info(f"Authentication successful! Logged in as: @{me.data.username}")
            return client
        else:
            logger.error("Authentication failed: Could not get user info")
            return None
            
    except Exception as e:
        logger.error(f"Authentication failed: {str(e)}")
        return None

def test_user_lookup(client):
    """Test looking up specified users with API v2."""
    if not client:
        return
        
    logger.info("\nTesting user lookup...")
    try:
        # Look up users by usernames
        users = client.get_users(usernames=TWITTER_USERS_TO_FOLLOW)
        if users.data:
            for user in users.data:
                logger.info(f"Found user @{user.username}: {user.name} (ID: {user.id})")
        else:
            logger.warning("No users found")
    except Exception as e:
        logger.error(f"Error looking up users: {str(e)}")

def test_sample_stream(client):
    """Test stream connection with API v2."""
    if not client:
        return
        
    logger.info("\nTesting stream connection (will run for 30 seconds)...")
    
    class TestStreamingClient(tweepy.StreamingClient):
        def __init__(self, bearer_token):
            super().__init__(bearer_token)
            self.tweet_count = 0
            self.start_time = datetime.now()
            
        def on_tweet(self, tweet):
            self.tweet_count += 1
            logger.info(f"Tweet {self.tweet_count}: {tweet.text[:100]}...")
            
            # Run for 30 seconds only
            if (datetime.now() - self.start_time).seconds > 30:
                self.disconnect()
                return False
            return True
            
        def on_error(self, status):
            logger.error(f"Stream error: {status}")
            return False

    try:
        stream = TestStreamingClient(TWITTER_BEARER_TOKEN)
        
        # Delete existing rules
        rules = stream.get_rules()
        if rules.data:
            rule_ids = [rule.id for rule in rules.data]
            stream.delete_rules(rule_ids)
        
        # Add new rules
        stream.add_rules(tweepy.StreamRule("bitcoin OR crypto OR btc lang:en -is:retweet"))
        
        # Start streaming
        stream.filter(tweet_fields=["text", "created_at"])
        
        logger.info(f"Stream test complete. Collected {stream.tweet_count} tweets")
        
    except Exception as e:
        logger.error(f"Stream error: {str(e)}")

def main():
    """Run all tests."""
    logger.info("Starting Twitter API v2 tests...")
    
    # Test authentication
    client = test_authentication()
    if not client:
        logger.error("Authentication failed. Stopping tests.")
        return
    
    # Test user lookup
    test_user_lookup(client)
    
    # Test stream
    test_sample_stream(client)
    
    logger.info("\nAll tests complete!")

if __name__ == "__main__":
    main()
