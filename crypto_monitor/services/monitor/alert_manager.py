"""
报警管理模块，负责性能指标监控和报警通知
"""

import logging
import json
import asyncio
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, List, Optional, Callable
from datetime import datetime, timedelta
from pathlib import Path
import aiohttp
from ...utils.config import MONITOR_CONFIG

logger = logging.getLogger(__name__)

class AlertManager:
    def __init__(self, config_path: str = "config/alerts.json"):
        """
        初始化报警管理器
        
        Args:
            config_path: 报警配置文件路径
        """
        self.config_path = Path(config_path)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 加载配置
        self.alert_config = self._load_config()
        
        # 报警状态
        self.alert_status = {}
        
        # 通知渠道
        self.notification_channels = {
            'telegram': self._send_telegram_notification,
            'email': self._send_email_notification,
            'log': self._send_log_notification
        }
        
        # 报警历史
        self.alert_history = []
        self.max_history_size = 1000
        
    def _load_config(self) -> Dict:
        """加载报警配置"""
        if not self.config_path.exists():
            default_config = {
                'thresholds': {
                    'api_latency': {
                        'warning': 0.5,    # 警告阈值（秒）
                        'critical': 1.0,   # 严重阈值（秒）
                        'window': 60,      # 检查窗口（秒）
                        'min_samples': 3   # 最小样本数
                    },
                    'error_rate': {
                        'warning': 0.05,   # 5% 错误率
                        'critical': 0.1,   # 10% 错误率
                        'window': 300,     # 5分钟窗口
                        'min_samples': 10
                    },
                    'execution_time': {
                        'warning': 2.0,    # 警告阈值（秒）
                        'critical': 5.0,   # 严重阈值（秒）
                        'window': 300,     # 5分钟窗口
                        'min_samples': 5
                    }
                },
                'notifications': {
                    'channels': ['log'],  # 默认只启用日志通知
                    'telegram': {
                        'bot_token': '',
                        'chat_id': ''
                    },
                    'email': {
                        'smtp_server': '',
                        'smtp_port': 587,
                        'use_tls': True,
                        'username': '',
                        'password': '',
                        'from_addr': '',
                        'to_addrs': []
                    }
                },
                'alert_rules': {
                    'cooldown': 300,  # 报警冷却时间（秒）
                    'aggregation': 'avg',  # 聚合方式：avg, max, min
                    'severity_upgrade': {  # 报警升级规则
                        'consecutive_warnings': 3,  # 连续警告次数触发升级
                        'time_window': 1800,  # 升级判断时间窗口（秒）
                        'upgrade_cooldown': 3600  # 升级冷却时间（秒）
                    }
                }
            }
            
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=4)
                
            return default_config
            
        with open(self.config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
            
    def update_config(self, new_config: Dict) -> bool:
        """
        更新报警配置
        
        Args:
            new_config: 新的配置数据
            
        Returns:
            是否更新成功
        """
        try:
            # 验证新配置
            if not self._validate_config(new_config):
                return False
                
            self.alert_config = new_config
            
            # 保存到文件
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(new_config, f, indent=4)
                
            logger.info("报警配置已更新")
            return True
            
        except Exception as e:
            logger.error(f"更新报警配置时出错: {e}")
            return False
            
    def _validate_config(self, config: Dict) -> bool:
        """验证配置有效性"""
        required_fields = ['thresholds', 'notifications', 'alert_rules']
        if not all(field in config for field in required_fields):
            return False
            
        # 验证阈值配置
        for metric, threshold in config['thresholds'].items():
            if not all(k in threshold for k in ['warning', 'critical', 'window', 'min_samples']):
                return False
                
        return True
        
    async def check_metrics(self, metrics: Dict) -> List[Dict]:
        """
        检查性能指标是否触发报警
        
        Args:
            metrics: 性能指标数据
            
        Returns:
            触发的报警列表
        """
        alerts = []
        now = datetime.now()
        
        # 检查API延迟
        if metrics['api_latency']:
            alerts.extend(await self._check_api_latency(metrics['api_latency']))
            
        # 检查错误率
        if len(metrics['api_latency']) > 0:
            alerts.extend(await self._check_error_rate(metrics))
            
        # 检查执行时间
        if metrics['execution_time']:
            alerts.extend(await self._check_execution_time(metrics['execution_time']))
            
        # 检查是否需要升级报警级别
        alerts = self._check_alert_upgrade(alerts)
        
        return alerts
        
    async def _check_api_latency(self, latency_data: List[Dict]) -> List[Dict]:
        """检查API延迟"""
        alerts = []
        config = self.alert_config['thresholds']['api_latency']
        
        # 获取时间窗口内的数据
        window_start = datetime.now() - timedelta(seconds=config['window'])
        window_data = [
            d['latency'] for d in latency_data
            if datetime.fromisoformat(d['timestamp']) > window_start
        ]
        
        if len(window_data) < config['min_samples']:
            return alerts
            
        # 计算聚合值
        if self.alert_config['alert_rules']['aggregation'] == 'max':
            value = max(window_data)
        else:
            value = sum(window_data) / len(window_data)
            
        # 检查阈值
        alert_key = 'api_latency'
        if value >= config['critical'] and self._check_cooldown(alert_key, 'critical'):
            alerts.append({
                'type': 'critical',
                'metric': 'API延迟',
                'value': value,
                'threshold': config['critical'],
                'timestamp': datetime.now().isoformat()
            })
        elif value >= config['warning'] and self._check_cooldown(alert_key, 'warning'):
            alerts.append({
                'type': 'warning',
                'metric': 'API延迟',
                'value': value,
                'threshold': config['warning'],
                'timestamp': datetime.now().isoformat()
            })
            
        return alerts
        
    async def _check_error_rate(self, metrics: Dict) -> List[Dict]:
        """检查错误率"""
        alerts = []
        config = self.alert_config['thresholds']['error_rate']
        
        total_requests = len(metrics['api_latency'])
        if total_requests < config['min_samples']:
            return alerts
            
        error_rate = metrics['error_count'] / total_requests
        
        # 检查阈值
        alert_key = 'error_rate'
        if error_rate >= config['critical'] and self._check_cooldown(alert_key, 'critical'):
            alerts.append({
                'type': 'critical',
                'metric': '错误率',
                'value': error_rate,
                'threshold': config['critical'],
                'timestamp': datetime.now().isoformat()
            })
        elif error_rate >= config['warning'] and self._check_cooldown(alert_key, 'warning'):
            alerts.append({
                'type': 'warning',
                'metric': '错误率',
                'value': error_rate,
                'threshold': config['warning'],
                'timestamp': datetime.now().isoformat()
            })
            
        return alerts
        
    async def _check_execution_time(self, execution_data: List[Dict]) -> List[Dict]:
        """检查执行时间"""
        alerts = []
        config = self.alert_config['thresholds']['execution_time']
        
        # 获取时间窗口内的数据
        window_start = datetime.now() - timedelta(seconds=config['window'])
        window_data = [
            d['execution_time'] for d in execution_data
            if datetime.fromisoformat(d['timestamp']) > window_start
        ]
        
        if len(window_data) < config['min_samples']:
            return alerts
            
        # 计算聚合值
        if self.alert_config['alert_rules']['aggregation'] == 'max':
            value = max(window_data)
        else:
            value = sum(window_data) / len(window_data)
            
        # 检查阈值
        alert_key = 'execution_time'
        if value >= config['critical'] and self._check_cooldown(alert_key, 'critical'):
            alerts.append({
                'type': 'critical',
                'metric': '执行时间',
                'value': value,
                'threshold': config['critical'],
                'timestamp': datetime.now().isoformat()
            })
        elif value >= config['warning'] and self._check_cooldown(alert_key, 'warning'):
            alerts.append({
                'type': 'warning',
                'metric': '执行时间',
                'value': value,
                'threshold': config['warning'],
                'timestamp': datetime.now().isoformat()
            })
            
        return alerts
        
    def _check_cooldown(self, alert_key: str, alert_type: str) -> bool:
        """检查报警冷却时间"""
        now = datetime.now()
        status_key = f"{alert_key}_{alert_type}"
        
        if status_key in self.alert_status:
            last_alert_time = self.alert_status[status_key]
            if (now - last_alert_time).total_seconds() < self.alert_config['alert_rules']['cooldown']:
                return False
                
        self.alert_status[status_key] = now
        return True
        
    async def send_alerts(self, alerts: List[Dict]):
        """发送报警通知"""
        if not alerts:
            return
            
        # 更新报警历史
        self.alert_history.extend(alerts)
        if len(self.alert_history) > self.max_history_size:
            self.alert_history = self.alert_history[-self.max_history_size:]
            
        # 发送通知
        for channel in self.alert_config['notifications']['channels']:
            if channel in self.notification_channels:
                await self.notification_channels[channel](alerts)
                
        # 记录升级的报警
        upgraded_alerts = [a for a in alerts if a.get('upgraded')]
        if upgraded_alerts:
            logger.warning(f"以下报警已升级为严重级别: {[a['metric'] for a in upgraded_alerts]}")
            
    async def _send_telegram_notification(self, alerts: List[Dict]):
        """发送Telegram通知"""
        if not self.alert_config['notifications']['telegram']['bot_token']:
            return
            
        config = self.alert_config['notifications']['telegram']
        bot_token = config['bot_token']
        chat_id = config['chat_id']
        
        async with aiohttp.ClientSession() as session:
            for alert in alerts:
                message = (
                    f"🚨 性能监控报警\n"
                    f"级别: {'🔴 严重' if alert['type'] == 'critical' else '⚠️ 警告'}\n"
                    f"指标: {alert['metric']}\n"
                    f"当前值: {alert['value']:.3f}\n"
                    f"阈值: {alert['threshold']:.3f}\n"
                    f"时间: {alert['timestamp']}"
                )
                
                try:
                    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                    async with session.post(url, json={
                        'chat_id': chat_id,
                        'text': message,
                        'parse_mode': 'HTML'
                    }) as response:
                        if response.status != 200:
                            logger.error(f"发送Telegram通知失败: {await response.text()}")
                except Exception as e:
                    logger.error(f"发送Telegram通知时出错: {e}")
                    
    async def _send_email_notification(self, alerts: List[Dict]):
        """发送邮件通知"""
        if not self.alert_config['notifications']['email']['smtp_server']:
            return
            
        config = self.alert_config['notifications']['email']
        
        try:
            # 创建邮件内容
            msg = MIMEMultipart()
            msg['From'] = config['from_addr']
            msg['To'] = ', '.join(config['to_addrs'])
            msg['Subject'] = '性能监控报警通知'
            
            # 构建HTML内容
            html_content = """
            <html>
            <head>
                <style>
                    table { border-collapse: collapse; width: 100%; }
                    th, td { padding: 8px; text-align: left; border: 1px solid #ddd; }
                    th { background-color: #f2f2f2; }
                    .critical { color: red; }
                    .warning { color: orange; }
                </style>
            </head>
            <body>
                <h2>性能监控报警通知</h2>
                <table>
                    <tr>
                        <th>时间</th>
                        <th>级别</th>
                        <th>指标</th>
                        <th>当前值</th>
                        <th>阈值</th>
                    </tr>
            """
            
            for alert in alerts:
                level_class = 'critical' if alert['type'] == 'critical' else 'warning'
                level_text = '严重' if alert['type'] == 'critical' else '警告'
                html_content += f"""
                    <tr>
                        <td>{datetime.fromisoformat(alert['timestamp']).strftime('%Y-%m-%d %H:%M:%S')}</td>
                        <td class="{level_class}">{level_text}</td>
                        <td>{alert['metric']}</td>
                        <td>{alert['value']:.3f}</td>
                        <td>{alert['threshold']:.3f}</td>
                    </tr>
                """
                
            html_content += """
                </table>
                <p>请及时检查系统状态并采取必要的措施。</p>
            </body>
            </html>
            """
            
            msg.attach(MIMEText(html_content, 'html'))
            
            # 连接SMTP服务器并发送
            with smtplib.SMTP(config['smtp_server'], config['smtp_port']) as server:
                if config['use_tls']:
                    server.starttls()
                server.login(config['username'], config['password'])
                server.send_message(msg)
                
            logger.info(f"已发送邮件通知到 {', '.join(config['to_addrs'])}")
            
        except Exception as e:
            logger.error(f"发送邮件通知时出错: {e}")
            
    async def _send_log_notification(self, alerts: List[Dict]):
        """发送日志通知"""
        for alert in alerts:
            log_level = logging.ERROR if alert['type'] == 'critical' else logging.WARNING
            logger.log(log_level, 
                      f"性能监控报警 - {alert['metric']}: "
                      f"当前值 {alert['value']:.3f} >= {alert['threshold']:.3f} ({alert['type']})")
            
    def get_alert_history(self, hours: int = 24) -> List[Dict]:
        """获取报警历史"""
        cutoff = datetime.now() - timedelta(hours=hours)
        return [
            alert for alert in self.alert_history
            if datetime.fromisoformat(alert['timestamp']) > cutoff
        ] 
        
    def _check_alert_upgrade(self, alerts: List[Dict]) -> List[Dict]:
        """检查是否需要升级报警级别"""
        if not alerts:
            return alerts
            
        now = datetime.now()
        upgrade_rules = self.alert_config['alert_rules']['severity_upgrade']
        
        # 按指标分组检查连续警告
        metrics_alerts = {}
        for alert in alerts:
            if alert['metric'] not in metrics_alerts:
                metrics_alerts[alert['metric']] = []
            metrics_alerts[alert['metric']].append(alert)
            
        # 检查每个指标的警告是否需要升级
        for metric, metric_alerts in metrics_alerts.items():
            warnings = [a for a in metric_alerts if a['type'] == 'warning']
            if len(warnings) >= upgrade_rules['consecutive_warnings']:
                # 检查时间窗口内的警告数
                window_start = now - timedelta(seconds=upgrade_rules['time_window'])
                recent_warnings = [
                    w for w in self.alert_history 
                    if w['metric'] == metric 
                    and w['type'] == 'warning'
                    and datetime.fromisoformat(w['timestamp']) > window_start
                ]
                
                if len(recent_warnings) >= upgrade_rules['consecutive_warnings']:
                    # 检查升级冷却期
                    upgrade_key = f"upgrade_{metric}"
                    if upgrade_key not in self.alert_status:
                        self.alert_status[upgrade_key] = now
                    elif (now - self.alert_status[upgrade_key]).total_seconds() >= upgrade_rules['upgrade_cooldown']:
                        # 升级为严重级别
                        for alert in metric_alerts:
                            if alert['type'] == 'warning':
                                alert['type'] = 'critical'
                                alert['upgraded'] = True
                        self.alert_status[upgrade_key] = now
                        
        return alerts
        
    def get_alert_stats(self, hours: int = 24) -> Dict:
        """获取报警统计信息"""
        cutoff = datetime.now() - timedelta(hours=hours)
        recent_alerts = [
            alert for alert in self.alert_history
            if datetime.fromisoformat(alert['timestamp']) > cutoff
        ]
        
        stats = {
            'total': len(recent_alerts),
            'by_type': {
                'warning': len([a for a in recent_alerts if a['type'] == 'warning']),
                'critical': len([a for a in recent_alerts if a['type'] == 'critical'])
            },
            'by_metric': {},
            'upgraded': len([a for a in recent_alerts if a.get('upgraded')])
        }
        
        # 按指标统计
        for alert in recent_alerts:
            metric = alert['metric']
            if metric not in stats['by_metric']:
                stats['by_metric'][metric] = {
                    'total': 0,
                    'warning': 0,
                    'critical': 0
                }
            stats['by_metric'][metric]['total'] += 1
            stats['by_metric'][metric][alert['type']] += 1
            
        return stats 