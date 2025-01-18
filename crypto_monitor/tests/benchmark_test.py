import asyncio
import time
import statistics
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
import aiohttp
from aiohttp_socks import ProxyConnector, ProxyType
import numpy as np
import pandas as pd
from plotly import graph_objects as go
from plotly.subplots import make_subplots
import sys
import os
import uuid

# Add project root to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.logger import get_logger
from proxy_pool import ProxyPool
from tests.benchmark_config import (
    BENCHMARK_SCENARIOS,
    PERFORMANCE_THRESHOLDS,
    BENCHMARK_ENDPOINTS,
    STATS_CONFIG,
    REPORT_CONFIG
)

logger = get_logger('ProxyBenchmark')

class BenchmarkResult:
    """Container for benchmark test results."""
    def __init__(self, scenario: str, endpoint: str):
        self.scenario = scenario
        self.endpoint = endpoint
        self.start_time = datetime.now()
        self.response_times: List[float] = []
        self.errors: List[str] = []
        self.timeouts: int = 0
        self.total_requests: int = 0
        self.successful_requests: int = 0
        self.proxy_stats: Dict[str, Dict] = {}  # proxy_id -> stats
        
    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        return self.successful_requests / self.total_requests if self.total_requests > 0 else 0
        
    @property
    def error_rate(self) -> float:
        """Calculate error rate."""
        return len(self.errors) / self.total_requests if self.total_requests > 0 else 0
        
    @property
    def timeout_rate(self) -> float:
        """Calculate timeout rate."""
        return self.timeouts / self.total_requests if self.total_requests > 0 else 0
        
    @property
    def avg_response_time(self) -> float:
        """Calculate average response time."""
        return statistics.mean(self.response_times) if self.response_times else 0
        
    @property
    def percentiles(self) -> Dict[int, float]:
        """Calculate response time percentiles."""
        if not self.response_times:
            return {p: 0 for p in STATS_CONFIG["percentiles"]}
        return {
            p: np.percentile(self.response_times, p)
            for p in STATS_CONFIG["percentiles"]
        }
        
    def to_dict(self) -> Dict:
        """Convert results to dictionary."""
        return {
            "scenario": self.scenario,
            "endpoint": self.endpoint,
            "start_time": self.start_time.isoformat(),
            "duration": (datetime.now() - self.start_time).total_seconds(),
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "success_rate": self.success_rate,
            "error_rate": self.error_rate,
            "timeout_rate": self.timeout_rate,
            "avg_response_time": self.avg_response_time,
            "percentiles": self.percentiles,
            "errors": self.errors[:10],  # Only include first 10 errors
            "proxy_stats": self.proxy_stats
        }

class ProxyBenchmark:
    """Benchmark tester for proxy performance."""
    
    def __init__(self, proxy_pool: ProxyPool):
        self.proxy_pool = proxy_pool
        self.logger = logger
        self.results: Dict[str, Dict[str, BenchmarkResult]] = {}
        
    async def _make_request(
        self,
        endpoint: Dict,
        scenario: Dict,
        max_retries: int = 3
    ) -> Tuple[float, bool, Optional[str], Optional[str]]:
        """Make a single request with retries and return response time, success status, error, and proxy_id."""
        for retry in range(max_retries):
            proxy = await self.proxy_pool.get_proxy()
            if not proxy:
                return 0.0, False, "No proxy available", None
                
            proxy_id = proxy['id']
            proxy_url = f"socks5://{proxy['username']}:{proxy['password']}@{proxy['proxy_address']}:{proxy['port']}"
            
            try:
                connector = ProxyConnector.from_url(proxy_url)
                async with aiohttp.ClientSession(connector=connector) as session:
                    start_time = time.time()
                    async with session.get(
                        endpoint['url'],
                        timeout=scenario['timeout']
                    ) as response:
                        await response.text()
                        response_time = time.time() - start_time
                        
                        if response.status == 200:
                            return response_time, True, None, proxy_id
                        else:
                            error = f"HTTP {response.status}"
                            await self.proxy_pool.update_proxy_status(proxy_id, False, response_time)
                            continue
                            
            except Exception as e:
                error = str(e)
                await self.proxy_pool.update_proxy_status(proxy_id, False, None)
                continue
                
        return 0.0, False, "All retries failed", None
            
    async def _run_scenario(
        self,
        scenario_name: str,
        scenario: Dict,
        endpoint: Dict,
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """Run a single benchmark scenario."""
        logger.info(f"Running {scenario_name} benchmark for latency")
        
        # Initialize results
        results = {
            "latency": {
                "mean": 0.0,
                "min": float('inf'),
                "max": 0.0,
                "p50": 0.0,
                "p90": 0.0,
                "p99": 0.0
            },
            "success_rate": 0.0,
            "error_rate": 0.0,
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "errors": {}
        }
        
        # Create batches of requests
        total_requests = scenario["concurrent_requests"] * scenario["requests_per_proxy"]
        batch_size = scenario["concurrent_requests"]
        num_batches = total_requests // batch_size
        
        response_times = []
        
        for batch_num in range(num_batches):
            # Create batch of requests
            batch = [
                self._make_request(endpoint, scenario, max_retries)
                for _ in range(batch_size)
            ]
            
            # Wait for all requests in batch to complete
            responses = await asyncio.gather(*batch)
            
            # Process responses
            for response_time, success, error, proxy_id in responses:
                results["total_requests"] += 1
                
                if success:
                    results["successful_requests"] += 1
                    response_times.append(response_time)
                else:
                    results["failed_requests"] += 1
                    if error not in results["errors"]:
                        results["errors"][error] = 0
                    results["errors"][error] += 1
                    
            # Add delay between batches if specified
            if scenario.get("delay_between_requests", 0) > 0:
                await asyncio.sleep(scenario["delay_between_requests"])
                
        # Calculate statistics
        if response_times:
            results["latency"]["mean"] = statistics.mean(response_times)
            results["latency"]["min"] = min(response_times)
            results["latency"]["max"] = max(response_times)
            results["latency"]["p50"] = np.percentile(response_times, 50)
            results["latency"]["p90"] = np.percentile(response_times, 90)
            results["latency"]["p99"] = np.percentile(response_times, 99)
            
        results["success_rate"] = (
            results["successful_requests"] / results["total_requests"]
            if results["total_requests"] > 0
            else 0.0
        )
        results["error_rate"] = 1.0 - results["success_rate"]
        
        return results
        
    async def run_benchmark(self, load_type="light_load"):
        """Run benchmark with specified load type."""
        # Set load level in proxy pool
        if "heavy" in load_type:
            self.proxy_pool.set_load_level("heavy")
        elif "medium" in load_type:
            self.proxy_pool.set_load_level("medium")
        else:
            self.proxy_pool.set_load_level("light")
            
        # Run the benchmark
        logger.info(f"Running {load_type} benchmark for latency")
        latency_result = await self._run_scenario(
            load_type,
            BENCHMARK_SCENARIOS[load_type],
            BENCHMARK_ENDPOINTS["latency"]
        )
        
        logger.info(f"Running {load_type} benchmark for bandwidth")
        bandwidth_result = await self._run_scenario(
            load_type,
            BENCHMARK_SCENARIOS[load_type],
            BENCHMARK_ENDPOINTS["bandwidth"]
        )
        
        if "heavy" in load_type:
            logger.info(f"Running {load_type} benchmark for cpu")
            cpu_result = await self._run_scenario(
                load_type,
                BENCHMARK_SCENARIOS[load_type],
                BENCHMARK_ENDPOINTS["cpu"]
            )
        
        return {
            "latency": latency_result,
            "bandwidth": bandwidth_result,
            "cpu": cpu_result if "heavy" in load_type else None
        }
        
    async def run_benchmarks(self) -> Dict[str, Dict[str, Any]]:
        """Run all benchmark scenarios."""
        results = {}
        for load_type in ["light_load", "medium_load", "heavy_load"]:
            results[load_type] = await self.run_benchmark(load_type)
            
        return results
        
    def generate_report(self, output_dir: str):
        """Generate benchmark report."""
        if not self.results:
            self.logger.error("No benchmark results available")
            return
            
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        # Convert results to pandas DataFrame
        records = []
        for load_type, endpoints in self.results.items():
            for endpoint_name, result in endpoints.items():
                records.append({
                    "load_type": load_type,
                    "endpoint": endpoint_name,
                    "mean_latency": result["latency"]["mean"],
                    "success_rate": result["success_rate"],
                    "error_rate": result["error_rate"],
                    "total_requests": result["total_requests"],
                    "successful_requests": result["successful_requests"],
                    "failed_requests": result["failed_requests"],
                    "errors": result["errors"]
                })
        df = pd.DataFrame(records)
        
        # Generate plots
        fig = make_subplots(
            rows=3, cols=2,
            subplot_titles=(
                'Response Time Distribution',
                'Success Rate by Load Type',
                'Error Distribution',
                'Response Time Percentiles',
                'Proxy Performance Comparison',
                'Request Distribution by Proxy'
            ),
            specs=[
                [{"type": "xy"}, {"type": "xy"}],
                [{"type": "xy"}, {"type": "xy"}],
                [{"type": "xy"}, {"type": "domain"}]  # Use domain for pie chart
            ]
        )
        
        # Response Time Distribution
        for load_type in df['load_type'].unique():
            load_type_data = df[df['load_type'] == load_type]
            fig.add_trace(
                go.Histogram(
                    x=load_type_data['mean_latency'],
                    name=load_type,
                    nbinsx=20
                ),
                row=1, col=1
            )
            
        # Success Rate by Load Type
        fig.add_trace(
            go.Bar(
                x=df['load_type'],
                y=df['success_rate'],
                name='Success Rate'
            ),
            row=1, col=2
        )
        
        # Error Distribution
        error_rates = df.groupby('load_type')[['error_rate', 'success_rate']].mean()
        fig.add_trace(
            go.Bar(
                x=error_rates.index,
                y=error_rates['error_rate'],
                name='Error Rate'
            ),
            row=2, col=1
        )
        fig.add_trace(
            go.Bar(
                x=error_rates.index,
                y=error_rates['success_rate'],
                name='Success Rate'
            ),
            row=2, col=1
        )
        
        # Response Time Percentiles
        for load_type in df['load_type'].unique():
            load_type_data = df[df['load_type'] == load_type]
            percentiles = load_type_data['mean_latency'].quantile([0.5, 0.9, 0.99]).to_dict()
            fig.add_trace(
                go.Scatter(
                    x=list(percentiles.keys()),
                    y=list(percentiles.values()),
                    name=f"{load_type} Percentiles"
                ),
                row=2, col=2
            )
            
        # Proxy Performance Comparison
        # fig.add_trace(
        #     go.Bar(
        #         x=list(proxy_success_rates.keys()),
        #         y=list(proxy_success_rates.values()),
        #         name='Proxy Success Rate'
        #     ),
        #     row=3, col=1
        # )
        
        # Request Distribution by Proxy
        # fig.add_trace(
        #     go.Pie(
        #         labels=list(total_requests.keys()),
        #         values=list(total_requests.values()),
        #         name='Request Distribution'
        #     ),
        #     row=3, col=2
        # )
        
        # Update layout
        fig.update_layout(
            height=1200,
            title_text="Proxy Performance Benchmark Results",
            showlegend=True
        )
        
        # Save plots
        fig.write_html(os.path.join(output_dir, 'benchmark_report.html'))
        
        # Save raw data
        df.to_json(os.path.join(output_dir, 'benchmark_results.json'))
        
        # Generate summary report
        with open(os.path.join(output_dir, 'benchmark_summary.txt'), 'w') as f:
            f.write("Proxy Performance Benchmark Summary\n")
            f.write("==================================\n\n")
            
            for load_type, endpoints in self.results.items():
                f.write(f"\nLoad Type: {load_type}\n")
                f.write("-" * (len(load_type) + 10) + "\n")
                
                for endpoint_name, result in endpoints.items():
                    f.write(f"\nEndpoint: {endpoint_name}\n")
                    f.write(f"Success Rate: {result['success_rate']:.2%}\n")
                    f.write(f"Average Response Time: {result['latency']['mean']:.3f}s\n")
                    f.write(f"Error Rate: {result['error_rate']:.2%}\n")
                    
                    f.write("\nResponse Time Percentiles:\n")
                    f.write(f"  50th: {result['latency']['p50']:.3f}s\n")
                    f.write(f"  90th: {result['latency']['p90']:.3f}s\n")
                    f.write(f"  99th: {result['latency']['p99']:.3f}s\n")
                    
                    if result["errors"]:
                        f.write("\nSample Errors:\n")
                        for error, count in result["errors"].items():
                            f.write(f"  - {error}: {count}\n")
                    f.write("\n")
                    
        self.logger.info(f"Benchmark report generated in {output_dir}")

import pytest
import pytest_asyncio

@pytest_asyncio.fixture(scope="function")
def event_loop():
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.mark.asyncio
class TestProxyBenchmark:
    @pytest_asyncio.fixture(scope="class")
    async def proxy_pool(self):
        """Create and initialize proxy pool for tests."""
        pool = ProxyPool()
        await pool.initialize()
        yield pool
        await pool.close()
    
    @pytest_asyncio.fixture(scope="function")
    async def benchmark(self, proxy_pool):
        """Create benchmark instance for each test."""
        return ProxyBenchmark(proxy_pool)

    async def test_light_load(self, benchmark, proxy_pool):
        """Test proxy performance under light load."""
        # Configure proxy pool for light load
        proxy_pool.set_load_level("light")
        proxy_pool.max_consecutive_failures = 30
        proxy_pool.ban_duration = 20
        proxy_pool.min_success_rate = 0.15
        
        results = await benchmark.run_benchmark("light_load")
        assert results is not None
        assert "latency" in results
        assert "bandwidth" in results
        
        # Verify proxy pool behavior
        pool_stats = proxy_pool.get_pool_stats()
        assert pool_stats["total_proxies"] > 0, "Should have proxies in pool"
        
    async def test_medium_load(self, benchmark, proxy_pool):
        """Test proxy performance under medium load."""
        # Configure proxy pool for medium load
        proxy_pool.set_load_level("medium")
        proxy_pool.max_consecutive_failures = 40  # More lenient for medium load
        proxy_pool.ban_duration = 15  # Shorter ban duration to recover faster
        proxy_pool.min_success_rate = 0.12
        
        results = await benchmark.run_benchmark("medium_load")
        assert results is not None
        assert "latency" in results
        assert "bandwidth" in results
        
        # Verify proxy pool behavior
        pool_stats = proxy_pool.get_pool_stats()
        assert pool_stats["total_proxies"] > 0, "Should have proxies in pool"
        
    async def test_heavy_load(self, benchmark, proxy_pool):
        """Test proxy performance under heavy load."""
        # Configure proxy pool for heavy load
        proxy_pool.set_load_level("heavy")
        proxy_pool.max_consecutive_failures = 50  # Most lenient for heavy load
        proxy_pool.ban_duration = 10  # Shortest ban duration
        proxy_pool.min_success_rate = 0.10
        
        results = await benchmark.run_benchmark("heavy_load")
        assert results is not None
        assert "latency" in results
        assert "bandwidth" in results
        assert "cpu" in results
        
        # Verify proxy pool behavior
        pool_stats = proxy_pool.get_pool_stats()
        assert pool_stats["total_proxies"] > 0, "Should have proxies in pool"
        assert not proxy_pool.circuit_breaker_active, "Circuit breaker should not be active after test completion"

if __name__ == "__main__":
    asyncio.run(main())
