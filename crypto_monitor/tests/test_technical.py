"""
Test technical analysis functionality.
"""

import sys
from pathlib import Path
import logging
import numpy as np

# Add parent directory to Python path
sys.path.append(str(Path(__file__).parent.parent))

from crypto_monitor.core.technical_analysis import TechnicalAnalyzer
from config import LOGGING_CONFIG

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format=LOGGING_CONFIG['log_format']
)
logger = logging.getLogger('TechnicalTest')

def test_indicators():
    """Test technical indicators calculation."""
    analyzer = TechnicalAnalyzer()
    
    # Generate sample price data (uptrend followed by downtrend)
    prices = [100.0]
    for i in range(1, 50):
        if i < 25:
            # Uptrend with some noise
            change = np.random.normal(0.5, 0.2)
        else:
            # Downtrend with some noise
            change = np.random.normal(-0.5, 0.2)
        prices.append(prices[-1] * (1 + change/100))
    
    # Generate sample volume data with occasional spikes
    volumes = []
    base_volume = 1000000
    for i in range(50):
        if i % 10 == 0:
            # Volume spike every 10 periods
            volume = base_volume * np.random.uniform(2, 3)
        else:
            volume = base_volume * np.random.uniform(0.8, 1.2)
        volumes.append(volume)
    
    # Test RSI
    logger.info("\nTesting RSI calculation...")
    rsi = analyzer.calculate_rsi(prices)
    logger.info(f"RSI: {rsi:.2f}")
    
    # Test MACD
    logger.info("\nTesting MACD calculation...")
    macd_line, signal_line, hist = analyzer.calculate_macd(prices)
    logger.info(
        f"MACD Line: {macd_line:.4f}, "
        f"Signal Line: {signal_line:.4f}, "
        f"Histogram: {hist:.4f}"
    )
    
    # Test Bollinger Bands
    logger.info("\nTesting Bollinger Bands calculation...")
    upper, middle, lower = analyzer.calculate_bollinger_bands(prices)
    logger.info(
        f"Upper Band: {upper:.2f}, "
        f"Middle Band: {middle:.2f}, "
        f"Lower Band: {lower:.2f}"
    )
    
    # Test Volume Surge Detection
    logger.info("\nTesting Volume Surge detection...")
    surge = analyzer.detect_volume_surge(volumes)
    logger.info(f"Volume Surge Detected: {surge}")
    
    # Test complete market analysis
    logger.info("\nTesting complete market analysis...")
    analysis = analyzer.analyze_market(prices, volumes)
    
    logger.info("\nMarket Analysis Results:")
    logger.info("Indicators:")
    logger.info(f"  RSI: {analysis['indicators']['rsi']:.2f}")
    logger.info("  MACD:")
    logger.info(f"    Line: {analysis['indicators']['macd']['line']:.4f}")
    logger.info(f"    Signal: {analysis['indicators']['macd']['signal']:.4f}")
    logger.info(f"    Histogram: {analysis['indicators']['macd']['histogram']:.4f}")
    logger.info("  Bollinger Bands:")
    logger.info(f"    Upper: {analysis['indicators']['bollinger_bands']['upper']:.2f}")
    logger.info(f"    Middle: {analysis['indicators']['bollinger_bands']['middle']:.2f}")
    logger.info(f"    Lower: {analysis['indicators']['bollinger_bands']['lower']:.2f}")
    logger.info(f"  Volume Surge: {analysis['indicators']['volume_surge']}")
    
    logger.info("\nSignals:")
    for signal, value in analysis['signals'].items():
        logger.info(f"  {signal}: {value}")

if __name__ == "__main__":
    test_indicators()
