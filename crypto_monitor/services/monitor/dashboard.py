"""
实时性能监控面板，使用 Dash 构建 Web 界面
"""

import logging
from typing import Dict, Optional
from datetime import datetime, timedelta
import dash
from dash import html, dcc
from dash.dependencies import Input, Output, State
import plotly.graph_objects as go
from pathlib import Path
import threading
import time
import json

from .performance_visualizer import PerformanceVisualizer
from .alert_manager import AlertManager
from ...utils.config import MONITOR_CONFIG

logger = logging.getLogger(__name__)

class PerformanceDashboard:
    def __init__(self, data_dir: str = "data/performance", host: str = "localhost", port: int = 8050):
        """
        初始化性能监控面板
        
        Args:
            data_dir: 性能数据目录
            host: 服务器主机名
            port: 服务器端口
        """
        # 更新间隔（秒）
        self.update_interval = MONITOR_CONFIG.get('dashboard_update_interval', 5)
        
        self.visualizer = PerformanceVisualizer(data_dir)
        self.alert_manager = AlertManager()
        self.host = host
        self.port = port
        
        # 最近更新时间
        self.last_update = None
        
        # 创建Dash应用
        self.app = dash.Dash(__name__, 
                           assets_folder=str(Path(__file__).parent / 'assets'))
        self._setup_layout()
        self._setup_callbacks()
        
    def _setup_layout(self):
        """设置仪表板布局"""
        self.app.layout = html.Div([
            # 标题
            html.H1('加密货币交易系统性能监控', style={'textAlign': 'center'}),
            
            # 时间范围选择和报警配置按钮
            html.Div([
                html.Div([
                    html.Label('选择时间范围：'),
                    dcc.Dropdown(
                        id='time-range',
                        options=[
                            {'label': '最近1小时', 'value': '1H'},
                            {'label': '最近6小时', 'value': '6H'},
                            {'label': '最近24小时', 'value': '24H'},
                            {'label': '最近7天', 'value': '7D'}
                        ],
                        value='1H'
                    )
                ], style={'width': '200px', 'display': 'inline-block', 'marginRight': '20px'}),
                
                html.Button('报警配置', id='alert-config-button', n_clicks=0,
                           style={'marginRight': '10px'})
            ], style={'margin': '10px'}),
            
            # 报警配置模态框
            html.Div(id='alert-config-modal', style={'display': 'none'}, children=[
                html.Div([
                    html.H3('报警配置'),
                    
                    # 添加报警规则配置标签页
                    dcc.Tabs([
                        dcc.Tab(label='基本配置', children=[
                            # API延迟阈值
                            html.Div([
                                html.H4('API延迟阈值'),
                                html.Div([
                                    html.Label('警告阈值（秒）：'),
                                    dcc.Input(
                                        id='api-latency-warning',
                                        type='number',
                                        min=0,
                                        step=0.1,
                                        value=0.5
                                    )
                                ]),
                                html.Div([
                                    html.Label('严重阈值（秒）：'),
                                    dcc.Input(
                                        id='api-latency-critical',
                                        type='number',
                                        min=0,
                                        step=0.1,
                                        value=1.0
                                    )
                                ])
                            ]),
                            
                            # 错误率阈值
                            html.Div([
                                html.H4('错误率阈值'),
                                html.Div([
                                    html.Label('警告阈值（%）：'),
                                    dcc.Input(
                                        id='error-rate-warning',
                                        type='number',
                                        min=0,
                                        max=100,
                                        step=1,
                                        value=5
                                    )
                                ]),
                                html.Div([
                                    html.Label('严重阈值（%）：'),
                                    dcc.Input(
                                        id='error-rate-critical',
                                        type='number',
                                        min=0,
                                        max=100,
                                        step=1,
                                        value=10
                                    )
                                ])
                            ])
                        ]),
                        
                        dcc.Tab(label='升级规则', children=[
                            html.Div([
                                html.H4('报警升级配置'),
                                html.Div([
                                    html.Label('连续警告次数：'),
                                    dcc.Input(
                                        id='consecutive-warnings',
                                        type='number',
                                        min=1,
                                        step=1,
                                        value=3
                                    )
                                ]),
                                html.Div([
                                    html.Label('时间窗口（分钟）：'),
                                    dcc.Input(
                                        id='time-window',
                                        type='number',
                                        min=1,
                                        step=1,
                                        value=30
                                    )
                                ]),
                                html.Div([
                                    html.Label('升级冷却时间（分钟）：'),
                                    dcc.Input(
                                        id='upgrade-cooldown',
                                        type='number',
                                        min=1,
                                        step=1,
                                        value=60
                                    )
                                ])
                            ])
                        ]),
                        
                        dcc.Tab(label='通知设置', children=[
                            html.Div([
                                html.H4('通知渠道'),
                                dcc.Checklist(
                                    id='notification-channels',
                                    options=[
                                        {'label': '日志', 'value': 'log'},
                                        {'label': 'Telegram', 'value': 'telegram'},
                                        {'label': '邮件', 'value': 'email'}
                                    ],
                                    value=['log']
                                ),
                                
                                # Telegram配置
                                html.Div(id='telegram-config', style={'display': 'none'}, children=[
                                    html.H4('Telegram配置'),
                                    html.Div([
                                        html.Label('Bot Token：'),
                                        dcc.Input(
                                            id='telegram-bot-token',
                                            type='text',
                                            placeholder='输入Bot Token'
                                        )
                                    ]),
                                    html.Div([
                                        html.Label('Chat ID：'),
                                        dcc.Input(
                                            id='telegram-chat-id',
                                            type='text',
                                            placeholder='输入Chat ID'
                                        )
                                    ])
                                ]),
                                
                                # 邮件配置
                                html.Div(id='email-config', style={'display': 'none'}, children=[
                                    html.H4('邮件配置'),
                                    html.Div([
                                        html.Label('SMTP服务器：'),
                                        dcc.Input(
                                            id='smtp-server',
                                            type='text',
                                            placeholder='smtp.example.com'
                                        )
                                    ]),
                                    html.Div([
                                        html.Label('SMTP端口：'),
                                        dcc.Input(
                                            id='smtp-port',
                                            type='number',
                                            value=587
                                        )
                                    ]),
                                    html.Div([
                                        html.Label('用户名：'),
                                        dcc.Input(
                                            id='email-username',
                                            type='text',
                                            placeholder='your@email.com'
                                        )
                                    ]),
                                    html.Div([
                                        html.Label('密码：'),
                                        dcc.Input(
                                            id='email-password',
                                            type='password',
                                            placeholder='输入密码'
                                        )
                                    ]),
                                    html.Div([
                                        html.Label('发件人：'),
                                        dcc.Input(
                                            id='email-from',
                                            type='text',
                                            placeholder='your@email.com'
                                        )
                                    ]),
                                    html.Div([
                                        html.Label('收件人（用逗号分隔）：'),
                                        dcc.Input(
                                            id='email-to',
                                            type='text',
                                            placeholder='user1@example.com, user2@example.com'
                                        )
                                    ])
                                ])
                            ])
                        ])
                    ], style={'margin': '20px 0'})
                ], style={'padding': '20px'})
            ]),
            
            # 性能指标概览
            html.Div([
                html.H3('性能指标概览'),
                html.Div(id='performance-summary')
            ]),
            
            # 报警历史
            html.Div([
                html.H3('报警历史'),
                html.Div(id='alert-history')
            ]),
            
            # API延迟图表
            html.Div([
                html.H3('API延迟分析'),
                dcc.Graph(id='latency-chart')
            ]),
            
            # 价格波动图表
            html.Div([
                html.H3('价格波动分析'),
                dcc.Graph(id='volatility-chart')
            ]),
            
            # 执行时间图表
            html.Div([
                html.H3('订单执行时间分析'),
                dcc.Graph(id='execution-time-chart')
            ]),
            
            # 错误和警告图表
            html.Div([
                html.H3('错误和警告统计'),
                dcc.Graph(id='error-warning-chart')
            ]),
            
            # 自动刷新间隔
            dcc.Interval(
                id='interval-component',
                interval=self.update_interval * 1000,  # 毫秒
                n_intervals=0
            ),
            
            # 最后更新时间
            html.Div(id='last-update-time')
        ])
        
    def _setup_callbacks(self):
        """设置回调函数"""
        # 更新性能概览和检查报警
        @self.app.callback(
            [Output('performance-summary', 'children'),
             Output('alert-history', 'children')],
            [Input('interval-component', 'n_intervals'),
             Input('time-range', 'value')]
        )
        def update_summary_and_alerts(n, time_range):
            days = self._get_days_from_range(time_range)
            metrics = self.visualizer.load_metrics(days)
            if not metrics:
                return html.P('无数据'), html.P('无报警历史')
                
            # 更新性能概览
            stats = self._calculate_summary_stats(metrics)
            summary_cards = self._create_summary_cards(stats)
            
            # 更新报警历史
            alert_history = self._create_alert_history()
            
            return summary_cards, alert_history
            
        # 更新API延迟图表
        @self.app.callback(
            Output('latency-chart', 'figure'),
            [Input('interval-component', 'n_intervals'),
             Input('time-range', 'value')]
        )
        def update_latency_chart(n, time_range):
            days = self._get_days_from_range(time_range)
            metrics = self.visualizer.load_metrics(days)
            if not metrics:
                return go.Figure()
            return self.visualizer.create_latency_chart(metrics)
            
        # 更新价格波动图表
        @self.app.callback(
            Output('volatility-chart', 'figure'),
            [Input('interval-component', 'n_intervals'),
             Input('time-range', 'value')]
        )
        def update_volatility_chart(n, time_range):
            days = self._get_days_from_range(time_range)
            metrics = self.visualizer.load_metrics(days)
            if not metrics:
                return go.Figure()
            return self.visualizer.create_volatility_chart(metrics)
            
        # 更新执行时间图表
        @self.app.callback(
            Output('execution-time-chart', 'figure'),
            [Input('interval-component', 'n_intervals'),
             Input('time-range', 'value')]
        )
        def update_execution_time_chart(n, time_range):
            days = self._get_days_from_range(time_range)
            metrics = self.visualizer.load_metrics(days)
            if not metrics:
                return go.Figure()
            return self.visualizer.create_execution_time_chart(metrics)
            
        # 更新错误警告图表
        @self.app.callback(
            Output('error-warning-chart', 'figure'),
            [Input('interval-component', 'n_intervals'),
             Input('time-range', 'value')]
        )
        def update_error_warning_chart(n, time_range):
            days = self._get_days_from_range(time_range)
            metrics = self.visualizer.load_metrics(days)
            if not metrics:
                return go.Figure()
            return self.visualizer.create_error_warning_chart(metrics)
            
        # 更新最后更新时间
        @self.app.callback(
            Output('last-update-time', 'children'),
            [Input('interval-component', 'n_intervals')]
        )
        def update_time(n):
            self.last_update = datetime.now()
            return f'最后更新时间: {self.last_update.strftime("%Y-%m-%d %H:%M:%S")}'
            
        # 打开/关闭报警配置模态框
        @self.app.callback(
            Output('alert-config-modal', 'style'),
            [Input('alert-config-button', 'n_clicks'),
             Input('close-alert-config', 'n_clicks'),
             Input('save-alert-config', 'n_clicks')]
        )
        def toggle_modal(n1, n2, n3):
            ctx = dash.callback_context
            if not ctx.triggered:
                return {'display': 'none'}
            else:
                button_id = ctx.triggered[0]['prop_id'].split('.')[0]
                if button_id == 'alert-config-button':
                    return {'display': 'block'}
                return {'display': 'none'}
            
        # 显示/隐藏Telegram配置
        @self.app.callback(
            Output('telegram-config', 'style'),
            [Input('notification-channels', 'value')]
        )
        def toggle_telegram_config(channels):
            if channels and 'telegram' in channels:
                return {'display': 'block'}
            return {'display': 'none'}
            
        # 显示/隐藏邮件配置
        @self.app.callback(
            Output('email-config', 'style'),
            [Input('notification-channels', 'value')]
        )
        def toggle_email_config(channels):
            if channels and 'email' in channels:
                return {'display': 'block'}
            return {'display': 'none'}
            
        # 保存报警配置
        @self.app.callback(
            Output('alert-config-button', 'children'),
            [Input('save-alert-config', 'n_clicks')],
            [State('api-latency-warning', 'value'),
             State('api-latency-critical', 'value'),
             State('error-rate-warning', 'value'),
             State('error-rate-critical', 'value'),
             State('consecutive-warnings', 'value'),
             State('time-window', 'value'),
             State('upgrade-cooldown', 'value'),
             State('notification-channels', 'value'),
             State('telegram-bot-token', 'value'),
             State('telegram-chat-id', 'value'),
             State('smtp-server', 'value'),
             State('smtp-port', 'value'),
             State('email-username', 'value'),
             State('email-password', 'value'),
             State('email-from', 'value'),
             State('email-to', 'value')]
        )
        def save_alert_config(n_clicks, lat_warn, lat_crit, err_warn, err_crit,
                            cons_warn, time_window, upgrade_cooldown,
                            channels, bot_token, chat_id,
                            smtp_server, smtp_port, email_user, email_pass,
                            email_from, email_to):
            if not n_clicks:
                return '报警配置'
                
            new_config = {
                'thresholds': {
                    'api_latency': {
                        'warning': lat_warn,
                        'critical': lat_crit,
                        'window': 60,
                        'min_samples': 3
                    },
                    'error_rate': {
                        'warning': err_warn / 100,
                        'critical': err_crit / 100,
                        'window': 300,
                        'min_samples': 10
                    }
                },
                'notifications': {
                    'channels': channels,
                    'telegram': {
                        'bot_token': bot_token,
                        'chat_id': chat_id
                    },
                    'email': {
                        'smtp_server': smtp_server,
                        'smtp_port': smtp_port,
                        'use_tls': True,
                        'username': email_user,
                        'password': email_pass,
                        'from_addr': email_from,
                        'to_addrs': [addr.strip() for addr in email_to.split(',') if addr.strip()]
                    }
                },
                'alert_rules': {
                    'cooldown': 300,
                    'aggregation': 'avg',
                    'severity_upgrade': {
                        'consecutive_warnings': cons_warn,
                        'time_window': time_window * 60,  # 转换为秒
                        'upgrade_cooldown': upgrade_cooldown * 60  # 转换为秒
                    }
                }
            }
            
            if self.alert_manager.update_config(new_config):
                return '报警配置 ✓'
            return '报警配置 ✗'
            
    def _get_days_from_range(self, time_range: str) -> float:
        """根据时间范围获取天数"""
        if time_range == '1H':
            return 1/24
        elif time_range == '6H':
            return 0.25
        elif time_range == '24H':
            return 1
        elif time_range == '7D':
            return 7
        return 1
        
    def _calculate_summary_stats(self, metrics: Dict) -> Dict:
        """计算性能指标概览"""
        if not metrics['api_latency']:
            return {}
            
        latencies = [m['latency'] for m in metrics['api_latency']]
        return {
            'avg_latency': sum(latencies) / len(latencies),
            'max_latency': max(latencies),
            'total_requests': len(metrics['api_latency']),
            'error_count': metrics['error_count'],
            'warning_count': metrics['warning_count']
        }
        
    def _create_summary_cards(self, stats: Dict) -> html.Div:
        """创建性能指标卡片"""
        if not stats:
            return html.P('无数据')
            
        return html.Div([
            html.Div([
                html.H4('平均延迟'),
                html.P(f"{stats['avg_latency']:.3f} 秒")
            ], className='summary-card'),
            html.Div([
                html.H4('最大延迟'),
                html.P(f"{stats['max_latency']:.3f} 秒")
            ], className='summary-card'),
            html.Div([
                html.H4('总请求数'),
                html.P(str(stats['total_requests']))
            ], className='summary-card'),
            html.Div([
                html.H4('错误数'),
                html.P(str(stats['error_count']))
            ], className='summary-card'),
            html.Div([
                html.H4('警告数'),
                html.P(str(stats['warning_count']))
            ], className='summary-card')
        ], style={'display': 'flex', 'justifyContent': 'space-around'})
        
    def _create_alert_history(self) -> html.Div:
        """创建报警历史展示"""
        alerts = self.alert_manager.get_alert_history(hours=24)
        stats = self.alert_manager.get_alert_stats(hours=24)
        
        if not alerts:
            return html.P('无报警历史')
            
        # 创建统计信息卡片
        stats_cards = html.Div([
            html.Div([
                html.H4('报警统计 (24小时)'),
                html.Div([
                    html.Div([
                        html.P('总报警数'),
                        html.H3(str(stats['total']))
                    ], className='summary-card'),
                    html.Div([
                        html.P('警告数'),
                        html.H3(str(stats['by_type']['warning']))
                    ], className='summary-card'),
                    html.Div([
                        html.P('严重报警数'),
                        html.H3(str(stats['by_type']['critical']))
                    ], className='summary-card'),
                    html.Div([
                        html.P('升级报警数'),
                        html.H3(str(stats['upgraded']))
                    ], className='summary-card')
                ], style={'display': 'flex', 'justifyContent': 'space-around', 'marginBottom': '20px'})
            ]),
            
            # 按指标统计
            html.Div([
                html.H4('按指标统计'),
                html.Table([
                    html.Thead(html.Tr([
                        html.Th('指标'),
                        html.Th('总数'),
                        html.Th('警告'),
                        html.Th('严重')
                    ])),
                    html.Tbody([
                        html.Tr([
                            html.Td(metric),
                            html.Td(str(data['total'])),
                            html.Td(str(data['warning'])),
                            html.Td(str(data['critical']))
                        ]) for metric, data in stats['by_metric'].items()
                    ])
                ], style={'width': '100%', 'marginBottom': '20px'})
            ])
        ])
        
        # 报警历史表格
        history_table = html.Div([
            html.H4('报警历史记录'),
            html.Table([
                html.Thead(html.Tr([
                    html.Th('时间'),
                    html.Th('级别'),
                    html.Th('指标'),
                    html.Th('当前值'),
                    html.Th('阈值'),
                    html.Th('状态')
                ])),
                html.Tbody([
                    html.Tr([
                        html.Td(datetime.fromisoformat(alert['timestamp']).strftime('%Y-%m-%d %H:%M:%S')),
                        html.Td('严重' if alert['type'] == 'critical' else '警告',
                               style={'color': 'red' if alert['type'] == 'critical' else 'orange'}),
                        html.Td(alert['metric']),
                        html.Td(f"{alert['value']:.3f}"),
                        html.Td(f"{alert['threshold']:.3f}"),
                        html.Td('已升级' if alert.get('upgraded') else '-',
                               style={'color': 'purple'} if alert.get('upgraded') else {})
                    ]) for alert in reversed(alerts)
                ])
            ], style={'width': '100%', 'textAlign': 'left'})
        ])
        
        return html.Div([stats_cards, history_table])
        
    def start(self):
        """启动监控面板"""
        try:
            logger.info(f"启动性能监控面板: http://{self.host}:{self.port}")
            self.app.run_server(host=self.host, port=self.port)
        except Exception as e:
            logger.error(f"启动性能监控面板时出错: {e}")
            
    def stop(self):
        """停止监控面板"""
        # Dash服务器会在主线程退出时自动停止
        pass 