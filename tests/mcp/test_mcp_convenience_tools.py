#!/usr/bin/env python3
"""
Convenience MCP Tool Endpoints Testing
Tests the direct access MCP tool endpoints for ease of use and functionality.
"""

import requests
import json
import time
from typing import Dict, List, Any


class MCPConvenienceToolsTester:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update(
            {"Content-Type": "application/json", "Accept": "application/json"}
        )

    def log(self, message: str, level: str = "INFO"):
        """Enhanced logging with colors"""
        colors = {
            "INFO": "\033[94m",  # Blue
            "SUCCESS": "\033[92m",  # Green
            "WARNING": "\033[93m",  # Yellow
            "ERROR": "\033[91m",  # Red
            "RESET": "\033[0m",  # Reset
        }
        print(f"{colors.get(level, '')}{level}: {message}{colors['RESET']}")

    def test_mcp_search_endpoint(self):
        """Test convenience search endpoint"""
        self.log("=== Testing MCP Search Convenience Endpoint ===", "INFO")

        # Test basic search
        search_request = {
            "query": "authentication function",
            "language": "python",
            "max_results": 10,
        }

        start_time = time.time()
        response = self.session.post(
            f"{self.base_url}/api/v1/ai/search", json=search_request
        )
        execution_time = time.time() - start_time

        if response.status_code == 200:
            result = response.json()
            self.log(f"✅ Search Success: {response.status_code}", "SUCCESS")
            self.log(f"  Query: {result.get('query', 'N/A')}", "INFO")
            self.log(f"  Total Hits: {result.get('total_hits', 0)}", "INFO")
            self.log(f"  Execution Time: {execution_time:.3f}s", "INFO")

            if "hits" in result:
                hits = result["hits"]
                self.log(f"  Results Returned: {len(hits)}", "INFO")
                if hits:
                    first_hit = hits[0]
                    if isinstance(first_hit, dict):
                        self.log(
                            f"  Sample Result Keys: {list(first_hit.keys())}", "INFO"
                        )

            return True
        else:
            self.log(f"❌ Search Failed: {response.status_code}", "ERROR")
            try:
                error_data = response.json()
                self.log(
                    f"  Error: {error_data.get('detail', 'Unknown error')}", "ERROR"
                )
            except:
                self.log(f"  Raw Error: {response.text[:100]}...", "ERROR")
            return False

    def test_mcp_analyze_endpoint(self):
        """Test convenience analyze endpoint"""
        self.log("\n=== Testing MCP Analyze Convenience Endpoint ===", "INFO")

        # Test repository analysis
        analyze_request = {
            "repository_id": "1",
            "analysis_type": "structure",
            "include_dependencies": True,
        }

        start_time = time.time()
        response = self.session.post(
            f"{self.base_url}/api/v1/ai/analyze", json=analyze_request
        )
        execution_time = time.time() - start_time

        if response.status_code == 200:
            result = response.json()
            self.log(f"✅ Analyze Success: {response.status_code}", "SUCCESS")
            self.log(f"  Repository ID: {result.get('repository_id', 'N/A')}", "INFO")
            self.log(f"  Analysis Type: {result.get('analysis_type', 'N/A')}", "INFO")
            self.log(f"  Execution Time: {execution_time:.3f}s", "INFO")

            if "analysis" in result:
                analysis = result["analysis"]
                if isinstance(analysis, dict):
                    self.log(f"  Analysis Keys: {list(analysis.keys())}", "INFO")

            return True
        else:
            self.log(f"❌ Analyze Failed: {response.status_code}", "ERROR")
            try:
                error_data = response.json()
                self.log(
                    f"  Error: {error_data.get('detail', 'Unknown error')}", "ERROR"
                )
            except:
                self.log(f"  Raw Error: {response.text[:100]}...", "ERROR")
            return False

    def test_mcp_explore_endpoint(self):
        """Test convenience explore endpoint"""
        self.log("\n=== Testing MCP Explore Convenience Endpoint ===", "INFO")

        # Test function exploration
        explore_request = {
            "repository_id": "1",
            "entity_type": "function",
            "pattern": "auth",
            "include_documentation": True,
        }

        start_time = time.time()
        response = self.session.post(
            f"{self.base_url}/api/v1/ai/explore", json=explore_request
        )
        execution_time = time.time() - start_time

        if response.status_code == 200:
            result = response.json()
            self.log(f"✅ Explore Success: {response.status_code}", "SUCCESS")
            self.log(f"  Repository ID: {result.get('repository_id', 'N/A')}", "INFO")
            self.log(f"  Entity Type: {result.get('entity_type', 'N/A')}", "INFO")
            self.log(f"  Execution Time: {execution_time:.3f}s", "INFO")

            if "entities" in result:
                entities = result["entities"]
                if isinstance(entities, list):
                    self.log(f"  Entities Found: {len(entities)}", "INFO")
                    if entities:
                        sample_entity = entities[0]
                        if isinstance(sample_entity, dict):
                            self.log(
                                f"  Sample Entity Keys: {list(sample_entity.keys())}",
                                "INFO",
                            )

            return True
        else:
            self.log(f"❌ Explore Failed: {response.status_code}", "ERROR")
            try:
                error_data = response.json()
                self.log(
                    f"  Error: {error_data.get('detail', 'Unknown error')}", "ERROR"
                )
            except:
                self.log(f"  Raw Error: {response.text[:100]}...", "ERROR")
            return False

    def test_mcp_explain_endpoint(self):
        """Test convenience explain endpoint"""
        self.log("\n=== Testing MCP Explain Convenience Endpoint ===", "INFO")

        # Test code explanation
        explain_request = {
            "code_snippet": "def fibonacci(n):\n    if n <= 1:\n        return n\n    return fibonacci(n-1) + fibonacci(n-2)",
            "context": "recursive function",
            "detail_level": "comprehensive",
        }

        start_time = time.time()
        response = self.session.post(
            f"{self.base_url}/api/v1/ai/explain", json=explain_request
        )
        execution_time = time.time() - start_time

        if response.status_code == 200:
            result = response.json()
            self.log(f"✅ Explain Success: {response.status_code}", "SUCCESS")
            self.log(
                f"  Code Length: {len(explain_request['code_snippet'])} chars", "INFO"
            )
            self.log(f"  Detail Level: {result.get('detail_level', 'N/A')}", "INFO")
            self.log(f"  Execution Time: {execution_time:.3f}s", "INFO")

            if "explanation" in result:
                explanation = result["explanation"]
                if isinstance(explanation, str):
                    self.log(f"  Explanation Length: {len(explanation)} chars", "INFO")
                elif isinstance(explanation, dict):
                    self.log(f"  Explanation Keys: {list(explanation.keys())}", "INFO")

            return True
        else:
            self.log(f"❌ Explain Failed: {response.status_code}", "ERROR")
            try:
                error_data = response.json()
                self.log(
                    f"  Error: {error_data.get('detail', 'Unknown error')}", "ERROR"
                )
            except:
                self.log(f"  Raw Error: {response.text[:100]}...", "ERROR")
            return False

    def test_mcp_patterns_endpoint(self):
        """Test convenience patterns endpoint"""
        self.log("\n=== Testing MCP Patterns Convenience Endpoint ===", "INFO")

        # Test pattern detection
        patterns_request = {
            "repository_id": "1",
            "pattern_types": ["design_patterns", "anti_patterns"],
            "severity_threshold": "medium",
        }

        start_time = time.time()
        response = self.session.post(
            f"{self.base_url}/api/v1/ai/patterns", json=patterns_request
        )
        execution_time = time.time() - start_time

        if response.status_code == 200:
            result = response.json()
            self.log(f"✅ Patterns Success: {response.status_code}", "SUCCESS")
            self.log(f"  Repository ID: {result.get('repository_id', 'N/A')}", "INFO")
            self.log(f"  Execution Time: {execution_time:.3f}s", "INFO")

            if "patterns" in result:
                patterns = result["patterns"]
                if isinstance(patterns, list):
                    self.log(f"  Patterns Found: {len(patterns)}", "INFO")
                    if patterns:
                        sample_pattern = patterns[0]
                        if isinstance(sample_pattern, dict):
                            self.log(
                                f"  Sample Pattern Keys: {list(sample_pattern.keys())}",
                                "INFO",
                            )
                            pattern_type = sample_pattern.get("type", "Unknown")
                            self.log(f"  First Pattern Type: {pattern_type}", "INFO")

            return True
        else:
            self.log(f"❌ Patterns Failed: {response.status_code}", "ERROR")
            try:
                error_data = response.json()
                self.log(
                    f"  Error: {error_data.get('detail', 'Unknown error')}", "ERROR"
                )
            except:
                self.log(f"  Raw Error: {response.text[:100]}...", "ERROR")
            return False

    def test_mcp_status_endpoint(self):
        """Test convenience status endpoint"""
        self.log("\n=== Testing MCP Status Convenience Endpoint ===", "INFO")

        start_time = time.time()
        response = self.session.get(f"{self.base_url}/api/v1/ai/status")
        execution_time = time.time() - start_time

        if response.status_code == 200:
            result = response.json()
            self.log(f"✅ Status Success: {response.status_code}", "SUCCESS")
            self.log(f"  Execution Time: {execution_time:.3f}s", "INFO")

            # Check status components
            if "mcp_server" in result:
                mcp_status = result["mcp_server"]
                if isinstance(mcp_status, dict):
                    self.log(
                        f"  MCP Server Status: {mcp_status.get('status', 'Unknown')}",
                        "INFO",
                    )
                    self.log(
                        f"  Tools Available: {mcp_status.get('tools_count', 0)}", "INFO"
                    )
                    self.log(
                        f"  Resources Available: {mcp_status.get('resources_count', 0)}",
                        "INFO",
                    )

            if "algolia" in result:
                algolia_status = result["algolia"]
                if isinstance(algolia_status, dict):
                    self.log(
                        f"  Algolia Status: {algolia_status.get('status', 'Unknown')}",
                        "INFO",
                    )

            return True
        else:
            self.log(f"❌ Status Failed: {response.status_code}", "ERROR")
            try:
                error_data = response.json()
                self.log(
                    f"  Error: {error_data.get('detail', 'Unknown error')}", "ERROR"
                )
            except:
                self.log(f"  Raw Error: {response.text[:100]}...", "ERROR")
            return False

    def test_endpoint_performance(self):
        """Test performance of convenience endpoints"""
        self.log("\n=== Testing Convenience Endpoint Performance ===", "INFO")

        endpoints = [
            ("/api/v1/ai/status", "GET", "Status Check"),
            ("/api/v1/ai/search", "POST", "Search Tool"),
            ("/api/v1/ai/explain", "POST", "Explain Tool"),
        ]

        performance_results = []

        for endpoint, method, name in endpoints:
            times = []

            for i in range(3):  # Run 3 times for average
                start_time = time.time()

                if method == "GET":
                    response = self.session.get(f"{self.base_url}{endpoint}")
                else:
                    # Use simple test data
                    if "search" in endpoint:
                        data = {"query": "test", "max_results": 5}
                    elif "explain" in endpoint:
                        data = {
                            "code_snippet": "print('hello')",
                            "detail_level": "brief",
                        }
                    else:
                        data = {}

                    response = self.session.post(
                        f"{self.base_url}{endpoint}", json=data
                    )

                execution_time = time.time() - start_time
                times.append(execution_time)

            avg_time = sum(times) / len(times)
            min_time = min(times)
            max_time = max(times)

            performance_results.append(
                {
                    "endpoint": name,
                    "avg_time": avg_time,
                    "min_time": min_time,
                    "max_time": max_time,
                    "success": response.status_code == 200,
                }
            )

            status_icon = "✅" if response.status_code == 200 else "❌"
            self.log(
                f"  {status_icon} {name}: avg={avg_time:.3f}s, min={min_time:.3f}s, max={max_time:.3f}s",
                "SUCCESS" if response.status_code == 200 else "ERROR",
            )

        # Performance summary
        successful_tests = [r for r in performance_results if r["success"]]
        if successful_tests:
            avg_overall = sum(r["avg_time"] for r in successful_tests) / len(
                successful_tests
            )
            self.log(f"  📊 Overall Average Response Time: {avg_overall:.3f}s", "INFO")

            # Performance rating
            if avg_overall < 0.5:
                self.log("  🚀 Performance Rating: EXCELLENT (< 0.5s)", "SUCCESS")
            elif avg_overall < 1.0:
                self.log("  ⚡ Performance Rating: GOOD (< 1.0s)", "SUCCESS")
            else:
                self.log("  ⏱️  Performance Rating: ACCEPTABLE (> 1.0s)", "WARNING")

        return performance_results

    def run_convenience_tools_tests(self):
        """Run all convenience MCP tool tests"""
        start_time = time.time()

        self.log("🚀 Starting MCP Convenience Tools Testing", "INFO")
        self.log(f"Target: {self.base_url}", "INFO")
        self.log("=" * 60, "INFO")

        # Run individual endpoint tests
        test_results = []

        test_results.append(("Search", self.test_mcp_search_endpoint()))
        test_results.append(("Analyze", self.test_mcp_analyze_endpoint()))
        test_results.append(("Explore", self.test_mcp_explore_endpoint()))
        test_results.append(("Explain", self.test_mcp_explain_endpoint()))
        test_results.append(("Patterns", self.test_mcp_patterns_endpoint()))
        test_results.append(("Status", self.test_mcp_status_endpoint()))

        # Performance testing
        performance_results = self.test_endpoint_performance()

        # Generate summary
        total_time = time.time() - start_time
        successful_tests = sum(1 for _, success in test_results if success)
        total_tests = len(test_results)
        success_rate = (successful_tests / total_tests) * 100

        self.log("\n" + "=" * 60, "INFO")
        self.log("📊 MCP CONVENIENCE TOOLS TEST SUMMARY", "INFO")
        self.log("=" * 60, "INFO")

        self.log(f"🕐 Total Test Time: {total_time:.2f}s", "INFO")
        self.log(
            f"🎯 Success Rate: {successful_tests}/{total_tests} ({success_rate:.1f}%)",
            "SUCCESS" if success_rate >= 80 else "WARNING",
        )

        # Individual test results
        self.log("📋 Individual Test Results:", "INFO")
        for test_name, success in test_results:
            status_icon = "✅" if success else "❌"
            status_color = "SUCCESS" if success else "ERROR"
            self.log(
                f"  {status_icon} {test_name}: {'PASSED' if success else 'FAILED'}",
                status_color,
            )

        # Performance summary
        if performance_results:
            successful_perf = [r for r in performance_results if r["success"]]
            if successful_perf:
                avg_performance = sum(r["avg_time"] for r in successful_perf) / len(
                    successful_perf
                )
                self.log(f"⚡ Average Response Time: {avg_performance:.3f}s", "INFO")

        # Final assessment
        if success_rate >= 95:
            self.log(
                "🏆 EXCELLENT: All Convenience Tools Working Perfectly!", "SUCCESS"
            )
        elif success_rate >= 80:
            self.log("✅ GOOD: Most Convenience Tools Working", "SUCCESS")
        else:
            self.log("⚠️  WARNING: Some Convenience Tools Need Attention", "WARNING")

        self.log("=" * 60, "INFO")

        return success_rate


if __name__ == "__main__":
    tester = MCPConvenienceToolsTester()
    tester.run_convenience_tools_tests()
