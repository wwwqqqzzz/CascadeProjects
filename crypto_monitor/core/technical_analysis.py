"""
Technical analysis module for cryptocurrency trading.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
import logging
from config import TECHNICAL_PARAMS, LOGGING_CONFIG

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format=LOGGING_CONFIG['log_format']
)
logger = logging.getLogger('TechnicalAnalysis')

class TechnicalAnalyzer:
    def __init__(self):
        """Initialize technical analyzer."""
        self.params = TECHNICAL_PARAMS
        
    def calculate_rsi(self, prices: List[float], period: int = None) -> float:
        """
        Calculate Relative Strength Index (RSI).
        
        Args:
            prices: List of closing prices
            period: RSI period (default: from config)
            
        Returns:
            Current RSI value
        """
        if period is None:
            period = self.params['rsi']['period']
            
        if len(prices) < period + 1:
            return None
            
        # Convert to numpy array for calculations
        prices = np.array(prices)
        deltas = np.diff(prices)
        
        # Calculate gains and losses
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        # Calculate average gains and losses
        avg_gain = np.mean(gains[:period])
        avg_loss = np.mean(losses[:period])
        
        if avg_loss == 0:
            return 100.0
            
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
        
    def calculate_macd(
        self,
        prices: List[float],
        fast_period: int = None,
        slow_period: int = None,
        signal_period: int = None
    ) -> Tuple[float, float, float]:
        """
        Calculate Moving Average Convergence Divergence (MACD).
        
        Args:
            prices: List of closing prices
            fast_period: Fast EMA period
            slow_period: Slow EMA period
            signal_period: Signal line period
            
        Returns:
            Tuple of (MACD line, Signal line, MACD histogram)
        """
        if fast_period is None:
            fast_period = self.params['macd']['fast_period']
        if slow_period is None:
            slow_period = self.params['macd']['slow_period']
        if signal_period is None:
            signal_period = self.params['macd']['signal_period']
            
        if len(prices) < slow_period + signal_period:
            return None, None, None
            
        # Calculate EMAs
        prices_series = pd.Series(prices)
        fast_ema = prices_series.ewm(span=fast_period).mean()
        slow_ema = prices_series.ewm(span=slow_period).mean()
        
        # Calculate MACD line
        macd_line = fast_ema - slow_ema
        
        # Calculate Signal line
        signal_line = macd_line.ewm(span=signal_period).mean()
        
        # Calculate MACD histogram
        macd_histogram = macd_line - signal_line
        
        return (
            macd_line.iloc[-1],
            signal_line.iloc[-1],
            macd_histogram.iloc[-1]
        )
        
    def calculate_bollinger_bands(
        self,
        prices: List[float],
        period: int = None,
        std_dev: int = None
    ) -> Tuple[float, float, float]:
        """
        Calculate Bollinger Bands.
        
        Args:
            prices: List of closing prices
            period: Moving average period
            std_dev: Number of standard deviations
            
        Returns:
            Tuple of (Upper Band, Middle Band, Lower Band)
        """
        if period is None:
            period = self.params['bollinger']['period']
        if std_dev is None:
            std_dev = self.params['bollinger']['std_dev']
            
        if len(prices) < period:
            return None, None, None
            
        prices_series = pd.Series(prices)
        
        # Calculate middle band (SMA)
        middle_band = prices_series.rolling(window=period).mean()
        
        # Calculate standard deviation
        rolling_std = prices_series.rolling(window=period).std()
        
        # Calculate upper and lower bands
        upper_band = middle_band + (rolling_std * std_dev)
        lower_band = middle_band - (rolling_std * std_dev)
        
        return (
            upper_band.iloc[-1],
            middle_band.iloc[-1],
            lower_band.iloc[-1]
        )
        
    def detect_volume_surge(
        self,
        volumes: List[float],
        period: int = None,
        threshold: float = None
    ) -> bool:
        """
        Detect if there's a volume surge.
        
        Args:
            volumes: List of trading volumes
            period: Period for average volume calculation
            threshold: Volume surge threshold multiplier
            
        Returns:
            True if volume surge detected, False otherwise
        """
        if period is None:
            period = self.params['volume']['period']
        if threshold is None:
            threshold = self.params['volume']['threshold']
            
        if len(volumes) < period + 1:
            return False
            
        # Calculate average volume
        avg_volume = np.mean(volumes[-period-1:-1])
        current_volume = volumes[-1]
        
        return current_volume > (avg_volume * threshold)
        
    def analyze_market(
        self,
        prices: List[float],
        volumes: List[float]
    ) -> Dict[str, any]:
        """
        Perform comprehensive market analysis.
        
        Args:
            prices: List of closing prices
            volumes: List of trading volumes
            
        Returns:
            Dictionary containing analysis results
        """
        try:
            # Calculate all indicators
            rsi = self.calculate_rsi(prices)
            macd_line, signal_line, macd_hist = self.calculate_macd(prices)
            upper_bb, middle_bb, lower_bb = self.calculate_bollinger_bands(prices)
            volume_surge = self.detect_volume_surge(volumes)
            
            # Determine market conditions
            overbought = rsi > self.params['rsi']['overbought'] if rsi else False
            oversold = rsi < self.params['rsi']['oversold'] if rsi else False
            
            # MACD crossover signals
            macd_bullish = (
                macd_line is not None and
                signal_line is not None and
                macd_line > signal_line and
                macd_hist > 0
            )
            
            macd_bearish = (
                macd_line is not None and
                signal_line is not None and
                macd_line < signal_line and
                macd_hist < 0
            )
            
            # Bollinger Band signals
            price = prices[-1]
            bb_upper_break = (
                upper_bb is not None and
                price > upper_bb
            )
            bb_lower_break = (
                lower_bb is not None and
                price < lower_bb
            )
            
            return {
                'indicators': {
                    'rsi': rsi,
                    'macd': {
                        'line': macd_line,
                        'signal': signal_line,
                        'histogram': macd_hist
                    },
                    'bollinger_bands': {
                        'upper': upper_bb,
                        'middle': middle_bb,
                        'lower': lower_bb
                    },
                    'volume_surge': volume_surge
                },
                'signals': {
                    'overbought': overbought,
                    'oversold': oversold,
                    'macd_bullish': macd_bullish,
                    'macd_bearish': macd_bearish,
                    'bb_upper_break': bb_upper_break,
                    'bb_lower_break': bb_lower_break,
                    'volume_surge': volume_surge
                }
            }
            
        except Exception as e:
            logger.error(f"Error in market analysis: {e}")
            return None
