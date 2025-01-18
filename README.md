# Crypto Monitor 加密货币交易监控系统

## 项目简介

Crypto Monitor 是一个功能强大的加密货币交易监控系统，集成了社交媒体信号检测、自动交易执行、性能监控和风险管理等功能。该系统能够实时监控Twitter上的加密货币相关信息，自动识别潜在的交易信号，并在符合预设条件时执行交易。

## 主要功能

### 1. 社交媒体监控
- 实时监控Twitter上的加密货币相关讨论
- 智能识别和分析交易信号
- 支持自定义关键词和信号评分机制

### 2. 自动交易执行
- 与Binance交易所API集成
- 支持市价买入和卖出
- 自动设置止损和止盈订单
- 智能风险管理和仓位控制

### 3. 性能监控
- 实时监控API调用延迟
- 追踪交易执行时间
- 记录错误和警告信息
- 可视化性能指标展示

### 4. 风险管理
- 每日交易量限制
- 最大持仓限制
- 滑点监控
- 自动止损机制

## 安装说明

1. 克隆项目仓库：
```bash
git clone [repository_url]
cd crypto_monitor
```

2. 安装依赖：
```bash
pip install -r requirements.txt
```

3. 配置环境变量：
创建 `.env` 文件并设置以下参数：
```
BINANCE_API_KEY=your_api_key
BINANCE_API_SECRET=your_api_secret
TWITTER_BEARER_TOKEN=your_twitter_token
```

## 使用说明

### 启动监控系统
```bash
python run_dashboard.py
```

### 访问监控面板
打开浏览器访问：`http://localhost:8050`

### 配置说明

1. 交易配置 (`config/trading.json`)：
- 设置交易对
- 配置信号阈值
- 调整风险参数

2. 监控配置 (`config/monitor.json`)：
- 设置性能阈值
- 配置报警规则
- 自定义通知方式

## 项目结构

```
crypto_monitor/
├── services/
│   ├── monitor/         # 监控服务
│   ├── trading/         # 交易服务
│   └── twitter/         # Twitter服务
├── tests/               # 测试用例
├── utils/               # 工具函数
└── data/                # 数据存储
```

## 开发说明

### 运行测试
```bash
pytest crypto_monitor/tests/
```

### 代码风格
遵循 PEP 8 规范，使用 pylint 进行代码质量检查：
```bash
pylint crypto_monitor
```

## 注意事项

1. 请确保在使用真实账户前，先在测试网络上充分测试
2. 定期检查和更新API密钥
3. 监控系统日志，及时处理异常情况
4. 根据市场情况调整交易参数

## 贡献指南

1. Fork 项目仓库
2. 创建功能分支
3. 提交变更
4. 发起 Pull Request

## 许可证

MIT License

## 联系方式

如有问题或建议，请提交 Issue 或联系项目维护者。 