"""
交易系统集成测试脚本
"""

import asyncio
import logging
from datetime import datetime
from crypto_monitor.services.trading.trading_manager import TradingManager
from crypto_monitor.utils.config import TRADING_CONFIG

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_trading_flow():
    """测试完整的交易流程"""
    try:
        # 初始化交易管理器（使用测试网络）
        trading_manager = TradingManager(
            api_key=TRADING_CONFIG['binance_test_api_key'],
            api_secret=TRADING_CONFIG['binance_test_api_secret'],
            test_mode=True
        )
        
        # 启动交易管理器
        await trading_manager.start()
        logger.info("交易管理器启动成功")
        
        # 模拟交易信号
        test_signals = [
            {
                'text': 'Looking bullish on $BTC, time to buy! #BTCUSDT',
                'author': 'test_trader',
                'timestamp': datetime.now().isoformat(),
                'score': 0.95
            },
            {
                'text': 'ETH showing strong momentum! #ETHUSDT',
                'author': 'test_trader',
                'timestamp': datetime.now().isoformat(),
                'score': 0.92
            }
        ]
        
        # 处理每个测试信号
        for signal in test_signals:
            logger.info(f"处理交易信号: {signal['text']}")
            
            # 执行交易
            result = await trading_manager.process_tweet(signal)
            
            if result:
                logger.info(f"交易执行成功: {result}")
                
                # 等待一段时间观察订单状态
                await asyncio.sleep(10)
                
                # 获取当前状态
                status = trading_manager.get_status()
                logger.info(f"当前交易状态: {status}")
            else:
                logger.warning(f"交易执行失败: {signal}")
            
            # 等待一段时间再处理下一个信号
            await asyncio.sleep(5)
        
        # 获取最终状态
        final_status = trading_manager.get_status()
        logger.info(f"测试完成，最终状态: {final_status}")
        
    except Exception as e:
        logger.error(f"测试过程中出错: {str(e)}")
        raise
    finally:
        # 清理资源
        await trading_manager.stop()
        logger.info("交易管理器已停止")

async def main():
    """主函数"""
    try:
        await test_trading_flow()
    except Exception as e:
        logger.error(f"集成测试失败: {str(e)}")
        raise

if __name__ == "__main__":
    asyncio.run(main()) 