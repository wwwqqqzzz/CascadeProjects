import asyncio
import ssl
from typing import Optional, Dict, List, Tuple
from aiohttp_socks import ProxyConnector, ProxyType
import aiohttp
import os
import random
from dotenv import load_dotenv
import sys
from datetime import datetime
import time

# Add project root to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.logger import get_logger
from tests.config import PROXY_TEST_URLS, TEST_CONFIG, USER_AGENTS, TestResult

# Configure logging
logger = get_logger('SOCKS5Test')

class ProxyTestResult:
    def __init__(self, url: str, success: bool, response_time: float, error: Optional[str] = None):
        self.url = url
        self.success = success
        self.response_time = response_time
        self.error = error
        self.timestamp = datetime.now()

class SOCKS5Tester:
    def __init__(self):
        load_dotenv()
        self.webshare_api_key = os.getenv("WEBSHARE_API_KEY")
        self.logger = logger
        self.test_results: List[ProxyTestResult] = []
        
    async def get_test_proxy(self) -> Optional[Dict[str, str]]:
        """Get a test proxy from Webshare."""
        if not self.webshare_api_key:
            self.logger.error("No Webshare API key found")
            return None
            
        self.logger.debug(f"Using Webshare API key: {self.webshare_api_key[:5]}...")
        
        try:
            headers = {
                "Authorization": f"Token {self.webshare_api_key}"
            }
            self.logger.debug("Making request to Webshare API...")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://proxy.webshare.io/api/v2/proxy/list/?mode=direct",
                    headers=headers
                ) as response:
                    self.logger.debug(f"Got response with status: {response.status}")
                    
                    if response.status == 200:
                        data = await response.json()
                        self.logger.debug(f"Response data: {data}")
                        
                        if data.get("results"):
                            proxy = data["results"][0]
                            result = {
                                "server": f"{proxy['proxy_address']}:{proxy['port']}",
                                "username": proxy["username"],
                                "password": proxy["password"]
                            }
                            self.logger.debug(f"Successfully got proxy: {result['server']}")
                            return result
                        else:
                            self.logger.error("No proxies found in response")
                    else:
                        error_text = await response.text()
                        self.logger.error(f"API request failed with status {response.status}: {error_text}")
        except Exception as e:
            self.logger.error(f"Error fetching proxy: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
        return None

    async def test_proxy(self, proxy: Dict[str, str], test_url_config: Dict[str, str]) -> ProxyTestResult:
        """Test a SOCKS5 proxy with detailed logging."""
        start_time = time.time()
        test_url = test_url_config["url"]
        
        if not proxy or 'server' not in proxy:
            self.logger.error("Invalid proxy configuration")
            return ProxyTestResult(test_url, False, 0, "Invalid proxy configuration")
            
        host, port = proxy['server'].split(':')
        port = int(port)
        username = proxy.get('username')
        password = proxy.get('password')
        
        self.logger.info(f"Testing SOCKS5 proxy: {host}:{port}")
        
        # Configure timeout based on test configuration
        timeout = aiohttp.ClientTimeout(
            total=test_url_config.get("timeout", TEST_CONFIG["test_timeout"]),
            connect=TEST_CONFIG["connection_timeout"],
            sock_connect=TEST_CONFIG["connection_timeout"],
            sock_read=TEST_CONFIG["read_timeout"]
        )
        
        try:
            # Create connector with explicit settings
            connector = ProxyConnector(
                proxy_type=ProxyType.SOCKS5,
                host=host,
                port=port,
                username=username,
                password=password,
                ssl=False,
                rdns=True
            )
            
            self.logger.debug("Created SOCKS5 connector")
            
            async with aiohttp.ClientSession(
                connector=connector,
                timeout=timeout
            ) as session:
                headers = {
                    'User-Agent': random.choice(USER_AGENTS)
                }
                
                # Try both HTTPS and HTTP
                for scheme in ['https', 'http']:
                    test_url_with_scheme = test_url.replace('http://', f'{scheme}://')
                    self.logger.debug(f"Trying {scheme.upper()}: {test_url_with_scheme}")
                    
                    try:
                        async with session.get(test_url_with_scheme, headers=headers) as response:
                            self.logger.debug(f"Response status: {response.status}")
                            
                            if response.status == 200:
                                # Try to read response data
                                try:
                                    content_type = response.headers.get('Content-Type', '')
                                    expected_type = test_url_config["expected_type"]
                                    
                                    if expected_type == "json" and 'application/json' in content_type:
                                        data = await response.json()
                                        self.logger.info(f"Successfully connected via {scheme.upper()}. Response: {data}")
                                    elif expected_type == "html" or expected_type == "any":
                                        text = await response.text()
                                        self.logger.info(f"Successfully connected via {scheme.upper()}. Response length: {len(text)} bytes")
                                    else:
                                        return ProxyTestResult(
                                            test_url,
                                            False,
                                            time.time() - start_time,
                                            f"Unexpected content type: {content_type}"
                                        )
                                        
                                    return ProxyTestResult(test_url, True, time.time() - start_time)
                                except Exception as e:
                                    self.logger.error(f"Error reading response data: {e}")
                                    return ProxyTestResult(
                                        test_url,
                                        False,
                                        time.time() - start_time,
                                        f"Error reading response: {str(e)}"
                                    )
                            else:
                                self.logger.warning(f"Got status {response.status}")
                                
                    except asyncio.TimeoutError:
                        self.logger.error(f"Timeout with {scheme}")
                        return ProxyTestResult(test_url, False, time.time() - start_time, f"Timeout with {scheme}")
                    except Exception as e:
                        self.logger.error(f"Error with {scheme}: {e}")
                        continue
                        
        except Exception as e:
            self.logger.error(f"Error creating/using connector: {e}")
            return ProxyTestResult(test_url, False, time.time() - start_time, str(e))
            
        return ProxyTestResult(test_url, False, time.time() - start_time, "All connection attempts failed")

    async def run_tests(self, proxy: Dict[str, str]) -> List[ProxyTestResult]:
        """Run all tests for a proxy."""
        tasks = []
        for test_url in PROXY_TEST_URLS:
            for _ in range(TEST_CONFIG["max_retries"]):
                tasks.append(self.test_proxy(proxy, test_url))
                await asyncio.sleep(TEST_CONFIG["retry_delay"])
                
        results = await asyncio.gather(*tasks)
        self.test_results.extend(results)
        return results
        
    def print_test_summary(self):
        """Print a summary of all test results."""
        if not self.test_results:
            self.logger.warning("No test results available")
            return
            
        self.logger.info("\n=== Test Summary ===")
        
        # Group results by URL
        results_by_url = {}
        for result in self.test_results:
            if result.url not in results_by_url:
                results_by_url[result.url] = []
            results_by_url[result.url].append(result)
            
        # Print summary for each URL
        for url, results in results_by_url.items():
            success_count = sum(1 for r in results if r.success)
            total_count = len(results)
            avg_response_time = sum(r.response_time for r in results) / total_count
            
            self.logger.info(f"\nURL: {url}")
            self.logger.info(f"Success Rate: {success_count}/{total_count} ({success_count/total_count*100:.1f}%)")
            self.logger.info(f"Average Response Time: {avg_response_time:.2f}s")
            
            if not all(r.success for r in results):
                self.logger.info("Errors:")
                for result in results:
                    if not result.success and result.error:
                        self.logger.info(f"  - {result.error}")

async def main():
    """Main test function."""
    tester = SOCKS5Tester()
    
    # Get a test proxy
    logger.info("Fetching test proxy...")
    proxy = await tester.get_test_proxy()
    
    if proxy:
        logger.info(f"Got proxy: {proxy['server']}")
        
        # Run all tests
        results = await tester.run_tests(proxy)
        
        # Print summary
        tester.print_test_summary()
    else:
        logger.error("Failed to get test proxy")

if __name__ == "__main__":
    asyncio.run(main())
