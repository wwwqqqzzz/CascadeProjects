"""
Combined monitor for market data and important crypto news/tweets.
Focuses on high-quality information sources while respecting API limits.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import tweepy
from binance import AsyncClient

from config import (
    TWITTER_BEARER_TOKEN,
    TWITTER_USERS_TO_FOLLOW,
    LOGGING_CONFIG,
    TRADING_CONFIG
)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format=LOGGING_CONFIG['log_format'],
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger('NewsMonitor')

class NewsMonitor:
    def __init__(self):
        """Initialize news monitor."""
        self.twitter_client = tweepy.Client(
            bearer_token=TWITTER_BEARER_TOKEN,
            wait_on_rate_limit=True
        )
        self.user_ids = {}  # Cache for user IDs
        self.last_check_time = {}  # Track last check time for each user
        self._running = False
        
    async def get_user_id(self, username: str) -> Optional[str]:
        """Get Twitter user ID from username."""
        if username in self.user_ids:
            return self.user_ids[username]
            
        try:
            user = self.twitter_client.get_user(username=username)
            if user.data:
                self.user_ids[username] = user.data.id
                return user.data.id
        except Exception as e:
            logger.error(f"Error getting user ID for {username}: {e}")
        return None
        
    async def get_user_tweets(self, username: str, since: datetime) -> List[Dict]:
        """Get tweets from a specific user since given time."""
        user_id = await self.get_user_id(username)
        if not user_id:
            return []
            
        tweets = []
        try:
            # Get user's tweets
            response = self.twitter_client.get_users_tweets(
                id=user_id,
                max_results=10,
                tweet_fields=['created_at', 'public_metrics'],
                exclude=['retweets', 'replies']
            )
            
            if response.data:
                for tweet in response.data:
                    created_at = tweet.created_at
                    if created_at > since:
                        tweets.append({
                            'id': tweet.id,
                            'text': tweet.text,
                            'created_at': created_at,
                            'metrics': tweet.public_metrics,
                            'user': username
                        })
                        
        except Exception as e:
            logger.error(f"Error getting tweets for {username}: {e}")
            
        return tweets
        
    def is_relevant_tweet(self, tweet: Dict) -> bool:
        """Check if tweet is relevant for crypto trading."""
        # Keywords that indicate important information
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
            # Tweets with high engagement are likely important
            if (metrics['retweet_count'] > 100 or
                metrics['like_count'] > 500 or
                metrics['reply_count'] > 50):
                return True
                
        return False
        
    async def check_new_tweets(self) -> List[Dict]:
        """Check for new relevant tweets from important users."""
        current_time = datetime.utcnow()
        all_relevant_tweets = []
        
        for username in TWITTER_USERS_TO_FOLLOW:
            try:
                # Get last check time or default to 1 hour ago
                last_check = self.last_check_time.get(
                    username,
                    current_time - timedelta(hours=1)
                )
                
                # Get new tweets
                tweets = await self.get_user_tweets(username, last_check)
                
                # Filter relevant tweets
                relevant_tweets = [
                    tweet for tweet in tweets
                    if self.is_relevant_tweet(tweet)
                ]
                
                if relevant_tweets:
                    logger.info(
                        f"Found {len(relevant_tweets)} relevant tweets "
                        f"from {username}"
                    )
                    all_relevant_tweets.extend(relevant_tweets)
                    
                # Update last check time
                self.last_check_time[username] = current_time
                
            except Exception as e:
                logger.error(f"Error checking tweets for {username}: {e}")
                
            # Sleep to respect rate limits
            await asyncio.sleep(2)
            
        return all_relevant_tweets
        
    async def start(self):
        """Start monitoring tweets."""
        if self._running:
            return
            
        self._running = True
        logger.info(f"Started monitoring tweets from {len(TWITTER_USERS_TO_FOLLOW)} users")
        
        while self._running:
            try:
                relevant_tweets = await self.check_new_tweets()
                
                for tweet in relevant_tweets:
                    logger.info(
                        f"Important tweet from @{tweet['user']}:\n"
                        f"{tweet['text']}\n"
                        f"Engagement: {tweet['metrics']}"
                    )
                    
                # Wait before next check (5 minutes)
                await asyncio.sleep(300)
                
            except Exception as e:
                logger.error(f"Error in tweet monitoring loop: {e}")
                await asyncio.sleep(60)  # Wait before retry
                
    async def stop(self):
        """Stop monitoring tweets."""
        self._running = False
        logger.info("Stopped tweet monitoring")

# Example usage
async def main():
    monitor = NewsMonitor()
    
    try:
        await monitor.start()
    except KeyboardInterrupt:
        await monitor.stop()

if __name__ == "__main__":
    asyncio.run(main())
