"""
Signal detection module for cryptocurrency trading based on social media signals.
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class SignalDetector:
    def __init__(self, keywords: List[str], threshold: float = 0.8):
        """
        初始化信号检测器
        
        Args:
            keywords: 需要监测的关键词列表
            threshold: 触发信号的阈值分数
        """
        self.keywords = keywords
        self.threshold = threshold
        self.last_detection = {}  # 记录每个关键词最后一次触发时间
        self.last_text = None  # 记录最后一次检测的文本
        
    def detect_signal(self, tweet_data: Dict) -> Optional[Dict]:
        """
        检测推文中是否包含交易信号
        
        Args:
            tweet_data: 包含推文内容和元数据的字典
            
        Returns:
            如果检测到信号则返回信号详情,否则返回 None
        """
        try:
            text = tweet_data.get('text', '').lower()
            author = tweet_data.get('author', '')
            timestamp = tweet_data.get('timestamp')
            
            # 检查是否是重复文本
            if text == self.last_text:
                logger.debug("检测到重复文本")
                return None
                
            # 检查是否包含关键词
            matched_keywords = [kw for kw in self.keywords if kw.lower() in text]
            if not matched_keywords:
                return None
                
            # 计算信号分数
            signal_score = self._calculate_signal_score(text, matched_keywords)
            
            if signal_score >= self.threshold:
                # 生成交易信号
                signal = {
                    'timestamp': timestamp or datetime.now().isoformat(),
                    'author': author,
                    'keywords': matched_keywords,
                    'score': signal_score,
                    'text': text,
                    'source': 'twitter'
                }
                
                # 更新检测记录
                for kw in matched_keywords:
                    self.last_detection[kw] = datetime.now()
                self.last_text = text
                    
                logger.info(f"检测到交易信号: {signal}")
                return signal
                
        except Exception as e:
            logger.error(f"信号检测出错: {e}")
            
        return None
        
    def _calculate_signal_score(self, text: str, matched_keywords: List[str]) -> float:
        """
        计算信号分数
        
        评分维度:
        1. 基础分数: 匹配关键词的数量 (50%)
        2. 临近性分数: 关键词是否靠近出现 (30%)
        3. 时效性分数: 避免重复触发 (20%)
        """
        # 基础分数: 只要匹配到关键词就给较高的基础分
        base_score = min(1.0, len(matched_keywords) / 2)  # 匹配2个或以上关键词就是满分
        
        # 临近性分数: 检查关键词是否在文本中靠近出现
        words = text.split()
        positions = []
        for kw in matched_keywords:
            try:
                pos = words.index(kw.lower())
                positions.append(pos)
            except ValueError:
                continue
                
        if len(positions) >= 2:
            # 计算关键词之间的最大距离
            max_distance = max(positions) - min(positions)
            proximity_score = 1.0 if max_distance <= 5 else 0.8  # 如果关键词间距小于5个词,给满分
        else:
            proximity_score = 0.8  # 只匹配到一个关键词时给较低的临近性分数
            
        # 时效性分数: 避免重复触发
        recency_score = 1.0
        recent_detections = 0
        for kw in matched_keywords:
            if kw in self.last_detection:
                time_diff = (datetime.now() - self.last_detection[kw]).total_seconds()
                if time_diff < 300:  # 5分钟内的重复信号
                    recent_detections += 1
                    
        # 根据最近检测到的关键词数量降低分数
        if recent_detections > 0:
            recency_score = max(0.1, 1.0 - (recent_detections * 0.4))  # 每个重复关键词降低40%,最低0.1
            
        # 计算加权平均分
        final_score = (
            base_score * 0.5 +
            proximity_score * 0.3 +
            recency_score * 0.2
        )
        
        logger.debug(f"信号评分详情: base={base_score}, proximity={proximity_score}, recency={recency_score}, final={final_score}")
        return final_score 