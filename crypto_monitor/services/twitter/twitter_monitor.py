"""
Twitter Monitor Module

This module handles real-time monitoring of Twitter feeds for cryptocurrency-related content.
It implements tweet collection, keyword matching, and data storage functionality.
"""

import os
import re
import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Set

import tweepy
from logging.handlers import RotatingFileHandler

# Import configuration
from config import (
    TWITTER_API_KEY,
    TWITTER_API_SECRET,
    TWITTER_ACCESS_TOKEN,
    TWITTER_ACCESS_TOKEN_SECRET,
    TWITTER_USERS_TO_FOLLOW,
    KEYWORDS,
    DB_CONFIG,
    LOGGING_CONFIG,
    SYSTEM_CONFIG
)

class TwitterStreamClient(tweepy.StreamingClient):
    """Custom StreamingClient for handling Twitter stream data."""
    
    def __init__(self, bearer_token: str, db_manager: 'DatabaseManager', logger: logging.Logger):
        super().__init__(bearer_token)
        self.db_manager = db_manager
        self.logger = logger
        self.processed_tweets: Set[str] = set()  # Cache for deduplication
        
    def on_tweet(self, tweet) -> bool:
        """Process incoming tweet."""
        try:
            # Skip if we've seen this tweet
            if tweet.id in self.processed_tweets:
                return True
                
            # Add to processed set
            self.processed_tweets.add(tweet.id)
            
            # Maintain cache size
            if len(self.processed_tweets) > 10000:
                self.processed_tweets.clear()
            
            # Extract tweet data
            tweet_data = {
                'id': tweet.id,
                'text': tweet.text,
                'author': tweet.author_id,  # We'll need to look up the username separately
                'author_id': tweet.author_id,
                'created_at': tweet.created_at.isoformat(),
                'lang': tweet.lang,
                'retweet_count': tweet.public_metrics.get('retweet_count', 0),
                'favorite_count': tweet.public_metrics.get('like_count', 0),
                'hashtags': [tag['tag'] for tag in tweet.entities.get('hashtags', [])],
                'urls': [url['expanded_url'] for url in tweet.entities.get('urls', [])]
            }
            
            # Check for keyword matches
            matched_keywords = self._match_keywords(tweet_data['text'])
            if not matched_keywords:
                return True
                
            # Add matched keywords to tweet data
            tweet_data['keywords'] = matched_keywords
            
            # Store in database
            self.db_manager.store_tweet(tweet_data)
            
            # Log the match
            self.logger.info(
                f"Keyword match in tweet from author {tweet_data['author']}: "
                f"Categories: {', '.join(matched_keywords)}"
            )
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error processing tweet: {str(e)}", exc_info=True)
            return True
    
    def on_error(self, status) -> bool:
        """Handle stream errors."""
        self.logger.error(f"Stream error: {status}")
        return True  # Keep the stream alive
    
    def _match_keywords(self, text: str) -> List[str]:
        """Match keywords in tweet text."""
        matched_categories = set()
        for category, patterns in KEYWORDS.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    matched_categories.add(category)
                    break
        return list(matched_categories)

class DatabaseManager:
    """Handle database operations for storing tweets and trading signals."""
    
    def __init__(self, db_path: Path, logger: logging.Logger):
        self.db_path = db_path
        self.logger = logger
        self._initialize_db()
    
    def _initialize_db(self):
        """Initialize database tables."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Create tweets table
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS tweets (
                    id TEXT PRIMARY KEY,
                    text TEXT NOT NULL,
                    author TEXT NOT NULL,
                    author_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    lang TEXT,
                    retweet_count INTEGER,
                    favorite_count INTEGER,
                    hashtags TEXT,
                    urls TEXT,
                    keywords TEXT,
                    sentiment REAL,
                    created_timestamp TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """)
                
                # Create trading signals table
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS trading_signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tweet_id TEXT NOT NULL,
                    signal_type TEXT NOT NULL,
                    confidence REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (tweet_id) REFERENCES tweets (id)
                )
                """)
                
                conn.commit()
                
        except Exception as e:
            self.logger.error(f"Database initialization error: {str(e)}", exc_info=True)
            raise
    
    def store_tweet(self, tweet_data: Dict):
        """Store tweet data in database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Convert lists to JSON strings
                tweet_data['hashtags'] = json.dumps(tweet_data['hashtags'])
                tweet_data['urls'] = json.dumps(tweet_data['urls'])
                tweet_data['keywords'] = json.dumps(tweet_data['keywords'])
                
                cursor.execute("""
                INSERT OR IGNORE INTO tweets (
                    id, text, author, author_id, created_at, lang,
                    retweet_count, favorite_count, hashtags, urls, keywords
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    tweet_data['id'], tweet_data['text'], tweet_data['author'],
                    tweet_data['author_id'], tweet_data['created_at'], tweet_data['lang'],
                    tweet_data['retweet_count'], tweet_data['favorite_count'],
                    tweet_data['hashtags'], tweet_data['urls'], tweet_data['keywords']
                ))
                
                conn.commit()
                
        except Exception as e:
            self.logger.error(f"Error storing tweet: {str(e)}", exc_info=True)

class TwitterMonitor:
    """Main class for monitoring Twitter feeds."""
    
    def __init__(self):
        self.logger = self._setup_logging()
        self.db_manager = DatabaseManager(
            Path(DB_CONFIG['db_path']),
            self.logger
        )
        self.api = self._setup_api()
        self.stream = None
    
    def _setup_logging(self) -> logging.Logger:
        """Configure logging with rotation."""
        logger = logging.getLogger('TwitterMonitor')
        logger.setLevel(logging.INFO)
        
        # Create logs directory if it doesn't exist
        log_dir = Path(LOGGING_CONFIG['log_dir'])
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # Create rotating file handler
        log_file = log_dir / LOGGING_CONFIG['log_files']['twitter']
        handler = RotatingFileHandler(
            log_file,
            maxBytes=LOGGING_CONFIG['max_log_size'],
            backupCount=LOGGING_CONFIG['backup_count']
        )
        
        # Set format
        formatter = logging.Formatter(LOGGING_CONFIG['log_format'])
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
        return logger
    
    def _setup_api(self) -> tweepy.API:
        """Set up Twitter API authentication."""
        auth = tweepy.OAuthHandler(TWITTER_API_KEY, TWITTER_API_SECRET)
        auth.set_access_token(TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET)
        
        api = tweepy.API(
            auth,
            wait_on_rate_limit=True
        )
        
        try:
            api.verify_credentials()
            self.logger.info("Twitter API authentication successful")
            return api
        except Exception as e:
            self.logger.error("Twitter API authentication failed", exc_info=True)
            raise
    
    def start_streaming(self):
        """Start the Twitter stream."""
        try:
            # Create streaming client
            self.stream = TwitterStreamClient(
                TWITTER_API_KEY,
                self.db_manager,
                self.logger
            )
            
            # Delete existing rules
            rules = self.stream.get_rules()
            if rules.data:
                rule_ids = [rule.id for rule in rules.data]
                self.stream.delete_rules(rule_ids)
            
            # Add new rules for cryptocurrency monitoring
            rules = [
                tweepy.StreamRule("bitcoin OR btc OR ethereum OR eth lang:en -is:retweet"),
                tweepy.StreamRule(f"from:{' OR from:'.join(TWITTER_USERS_TO_FOLLOW)} -is:retweet")
            ]
            
            for rule in rules:
                self.stream.add_rules(rule)
            
            self.logger.info("Starting Twitter stream...")
            self.stream.filter(
                tweet_fields=['author_id', 'created_at', 'public_metrics', 'entities', 'lang'],
                expansions=['author_id'],
                threaded=True
            )
            
        except Exception as e:
            self.logger.error("Error starting stream", exc_info=True)
            raise
    
    def stop_streaming(self):
        """Stop the Twitter stream."""
        if self.stream:
            self.stream.disconnect()
            self.logger.info("Twitter stream stopped")

if __name__ == "__main__":
    # Create and start monitor
    monitor = TwitterMonitor()
    try:
        monitor.start_streaming()
    except KeyboardInterrupt:
        monitor.stop_streaming()
        print("\nTwitter monitor stopped by user")
