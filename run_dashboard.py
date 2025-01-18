from crypto_monitor.services.monitor.dashboard import PerformanceDashboard

if __name__ == "__main__":
    dashboard = PerformanceDashboard(
        data_dir="data/performance",  # 性能数据目录
        host="localhost",             # 主机名
        port=8050                     # 端口号
    )
    dashboard.start() 