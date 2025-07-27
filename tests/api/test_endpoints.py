#!/usr/bin/env python3
"""
Comprehensive API Endpoint Testing Script for CodeSage MCP Server
Tests all enhanced endpoints systematically with proper error handling.
"""

import requests
import json
import time
import sys
from typing import Dict, List, Any
from dataclasses import dataclass


@dataclass
class TestResult:
    endpoint: str
    method: str
    status_code: int
    success: bool
    response_time: float
    error: str = None
    response_data: Dict = None


class CodeSageAPITester:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update(
            {"Content-Type": "application/json", "Accept": "application/json"}
        )
        self.results: List[TestResult] = []

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

    def test_endpoint(
        self,
        method: str,
        endpoint: str,
        data: Dict = None,
        expected_status: int = 200,
        timeout: int = 30,
    ) -> TestResult:
        """Test a single endpoint with comprehensive error handling"""
        url = f"{self.base_url}{endpoint}"
        start_time = time.time()

        try:
            if method.upper() == "GET":
                response = self.session.get(url, timeout=timeout)
            elif method.upper() == "POST":
                response = self.session.post(url, json=data, timeout=timeout)
            elif method.upper() == "PUT":
                response = self.session.put(url, json=data, timeout=timeout)
            elif method.upper() == "DELETE":
                response = self.session.delete(url, timeout=timeout)
            else:
                raise ValueError(f"Unsupported method: {method}")

            response_time = time.time() - start_time

            # Try to parse JSON response
            try:
                response_data = response.json()
            except:
                response_data = {"raw_content": response.text[:200]}

            success = response.status_code == expected_status
            error = (
                None
                if success
                else f"Expected {expected_status}, got {response.status_code}"
            )

            result = TestResult(
                endpoint=endpoint,
                method=method.upper(),
                status_code=response.status_code,
                success=success,
                response_time=response_time,
                error=error,
                response_data=response_data,
            )

            # Log result
            status = "SUCCESS" if success else "ERROR"
            self.log(
                f"{method.upper()} {endpoint} -> {response.status_code} ({response_time:.3f}s)",
                status,
            )

            if not success and response_data:
                self.log(
                    f"Response: {json.dumps(response_data, indent=2)[:200]}...",
                    "WARNING",
                )

        except Exception as e:
            response_time = time.time() - start_time
            result = TestResult(
                endpoint=endpoint,
                method=method.upper(),
                status_code=0,
                success=False,
                response_time=response_time,
                error=str(e),
            )
            self.log(f"{method.upper()} {endpoint} -> EXCEPTION: {str(e)}", "ERROR")

        self.results.append(result)
        return result

    def test_basic_connectivity(self):
        """Test 1: Basic server connectivity and health"""
        self.log("=== Testing Basic Connectivity ===", "INFO")

        # Test root endpoint
        self.test_endpoint("GET", "/")

        # Test health endpoint
        self.test_endpoint("GET", "/health")

        # Test docs endpoint
        self.test_endpoint("GET", "/docs", expected_status=200)

        # Test OpenAPI spec
        self.test_endpoint("GET", "/openapi.json")

    def test_mcp_protocol_endpoints(self):
        """Test 2: Core MCP Protocol endpoints"""
        self.log("=== Testing MCP Protocol Endpoints ===", "INFO")

        # Test MCP capabilities
        self.test_endpoint("GET", "/api/v1/ai/mcp/capabilities")

        # Test MCP tools listing
        self.test_endpoint("GET", "/api/v1/ai/mcp/tools")

        # Test MCP resources listing
        self.test_endpoint("GET", "/api/v1/ai/mcp/resources")

        # Test MCP tool execution (with simple test)
        tool_call_data = {"tool_name": "search_code", "arguments": {"query": "test"}}
        self.test_endpoint("POST", "/api/v1/ai/mcp/tools/call", data=tool_call_data)

        # Test invalid tool call
        invalid_tool_data = {"tool_name": "invalid_tool", "arguments": {}}
        self.test_endpoint(
            "POST",
            "/api/v1/ai/mcp/tools/call",
            data=invalid_tool_data,
            expected_status=400,
        )

        # Test MCP resource reading (with test URI)
        self.test_endpoint(
            "GET", "/api/v1/ai/mcp/resources/read?uri=codesage://repositories"
        )

    def test_mcp_convenience_tools(self):
        """Test 3: Convenience MCP tool endpoints"""
        self.log("=== Testing MCP Convenience Tools ===", "INFO")

        # Test search endpoint
        search_data = {
            "query": "authentication",
            "language": "python",
            "repository": None,
            "entity_type": "function",
        }
        self.test_endpoint("POST", "/api/v1/ai/search", data=search_data)

        # Test analyze endpoint
        analyze_data = {"repository_id": "test-repo", "analysis_type": "overview"}
        self.test_endpoint("POST", "/api/v1/ai/analyze", data=analyze_data)

        # Test explore endpoint
        explore_data = {
            "entity_name": "main",
            "repository": None,
            "similarity_search": False,
        }
        self.test_endpoint("POST", "/api/v1/ai/explore", data=explore_data)

        # Test explain endpoint
        explain_data = {
            "code_snippet": "def hello_world(): return 'Hello, World!'",
            "context": "Simple Python function",
            "detail_level": "brief",
        }
        self.test_endpoint("POST", "/api/v1/ai/explain", data=explain_data)

        # Test patterns endpoint
        patterns_data = {"repository_id": "test-repo", "pattern_type": "security"}
        self.test_endpoint("POST", "/api/v1/ai/patterns", data=patterns_data)

        # Test MCP server status
        self.test_endpoint("GET", "/api/v1/ai/status")

    def test_repository_endpoints(self):
        """Test 4: Repository management endpoints"""
        self.log("=== Testing Repository Endpoints ===", "INFO")

        # Test list repositories
        self.test_endpoint("GET", "/api/v1/repositories/")

        # Test list with filters
        self.test_endpoint("GET", "/api/v1/repositories/?language=python&limit=10")

        # Test create repository
        repo_data = {
            "name": f"test-repository-{int(time.time())}",  # Use timestamp to avoid conflicts
            "description": "Test repository for API testing",
            "language": "python",
            "url": "https://github.com/test/test-repo",
        }
        create_result = self.test_endpoint(
            "POST", "/api/v1/repositories/", data=repo_data, expected_status=201
        )

        # Store repository ID for subsequent tests
        repo_id = None
        if create_result.success and create_result.response_data:
            repo_id = create_result.response_data.get("id")

        if repo_id:
            # Test get specific repository
            self.test_endpoint("GET", f"/api/v1/repositories/{repo_id}")

            # Test update repository
            update_data = {"description": "Updated test repository description"}
            self.test_endpoint(
                "PUT", f"/api/v1/repositories/{repo_id}", data=update_data
            )

            # Test repository status
            self.test_endpoint("GET", f"/api/v1/repositories/{repo_id}/status")

            # Test repository stats
            self.test_endpoint("GET", f"/api/v1/repositories/{repo_id}/stats")

            # Test process repository
            self.test_endpoint("POST", f"/api/v1/repositories/{repo_id}/process")

        # Test non-existent repository
        self.test_endpoint("GET", "/api/v1/repositories/99999", expected_status=404)

    def test_search_endpoints(self):
        """Test 5: Advanced search endpoints"""
        self.log("=== Testing Search Endpoints ===", "INFO")

        # Test main search endpoint
        search_data = {
            "query": "authentication function",
            "repository_id": None,
            "language": "python",
            "entity_type": "function",
            "page": 0,
            "per_page": 10,
            "include_content": True,
        }
        self.test_endpoint("POST", "/api/v1/search/", data=search_data)

        # Test search suggestions
        self.test_endpoint("GET", "/api/v1/search/suggestions?q=auth&limit=5")

        # Test voice search
        voice_data = {
            "audio_data": "fake_base64_encoded_audio_data_for_testing_purposes_only",
            "language": "en",
            "format": "wav",
        }
        self.test_endpoint(
            "POST", "/api/v1/search/voice", data=voice_data, expected_status=400
        )  # Should fail with fake data

        # Test similarity search
        similarity_data = {
            "entity_type": "function",
            "entity_id": 1,
            "limit": 10,
            "threshold": 0.8,
            "include_repository": None,
        }
        self.test_endpoint(
            "POST", "/api/v1/search/similar", data=similarity_data, expected_status=404
        )  # Likely no entity with ID 1

        # Test trending searches
        self.test_endpoint("GET", "/api/v1/search/trending?hours=24&limit=10")

        # Test search analytics
        self.test_endpoint("GET", "/api/v1/search/analytics?days=7")

        # Test index refresh
        self.test_endpoint("POST", "/api/v1/search/index/refresh")

        # Test search health
        self.test_endpoint("GET", "/api/v1/search/health")

    def test_file_endpoints(self):
        """Test 6: File operations endpoints"""
        self.log("=== Testing File Endpoints ===", "INFO")

        # Test list repository files (using repository ID 1, should exist after creation)
        self.test_endpoint("GET", "/api/v1/files/repositories/1", expected_status=200)

        # Test get file content (file ID 1, might not exist)
        self.test_endpoint("GET", "/api/v1/files/1", expected_status=404)

        # Test get file entities (file ID 1, might not exist)
        self.test_endpoint("GET", "/api/v1/files/1/entities", expected_status=404)

        # Test file summary (file ID 1, might not exist)
        self.test_endpoint("GET", "/api/v1/files/1/summary", expected_status=404)

        # Test bulk analysis with empty data
        bulk_data = {
            "file_ids": [],
            "force_reanalysis": False,
            "parallel_processing": True,
        }
        self.test_endpoint(
            "POST", "/api/v1/files/analyze/bulk", data=bulk_data, expected_status=400
        )

        # Test repository file stats (repository ID 1, should exist after creation)
        self.test_endpoint(
            "GET", "/api/v1/files/stats/repository/1", expected_status=200
        )

    def test_error_handling(self):
        """Test 7: Error handling and edge cases"""
        self.log("=== Testing Error Handling ===", "INFO")

        # Test invalid endpoints
        self.test_endpoint("GET", "/api/v1/invalid/endpoint", expected_status=404)

        # Test malformed JSON
        try:
            response = requests.post(
                f"{self.base_url}/api/v1/ai/mcp/tools/call",
                data="invalid json",
                headers={"Content-Type": "application/json"},
                timeout=30,
            )
            self.log(f"Malformed JSON test -> {response.status_code}", "INFO")
        except Exception as e:
            self.log(f"Malformed JSON test -> EXCEPTION: {str(e)}", "WARNING")

        # Test missing required fields
        incomplete_data = {"tool_name": "search_code"}  # Missing arguments
        self.test_endpoint(
            "POST",
            "/api/v1/ai/mcp/tools/call",
            data=incomplete_data,
            expected_status=422,
        )

        # Test invalid query parameters
        self.test_endpoint(
            "GET", "/api/v1/search/suggestions?q=a", expected_status=422
        )  # Too short query

    def run_all_tests(self):
        """Run all test suites"""
        start_time = time.time()
        self.log("🚀 Starting Comprehensive API Endpoint Testing", "INFO")
        self.log(f"Target: {self.base_url}", "INFO")

        # Wait for server to be ready
        self.log("Waiting for server to be ready...", "INFO")
        time.sleep(5)

        # Run all test suites
        test_suites = [
            self.test_basic_connectivity,
            self.test_mcp_protocol_endpoints,
            self.test_mcp_convenience_tools,
            self.test_repository_endpoints,
            self.test_search_endpoints,
            self.test_file_endpoints,
            self.test_error_handling,
        ]

        for test_suite in test_suites:
            try:
                test_suite()
                time.sleep(1)  # Brief pause between test suites
            except Exception as e:
                self.log(f"Test suite failed: {str(e)}", "ERROR")

        # Generate summary report
        self.generate_report(time.time() - start_time)

    def generate_report(self, total_time: float):
        """Generate comprehensive test report"""
        self.log("\n" + "=" * 80, "INFO")
        self.log("📊 COMPREHENSIVE TEST REPORT", "INFO")
        self.log("=" * 80, "INFO")

        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results if r.success)
        failed_tests = total_tests - passed_tests

        # Overall statistics
        self.log(f"Total Tests: {total_tests}", "INFO")
        self.log(f"Passed: {passed_tests}", "SUCCESS")
        self.log(f"Failed: {failed_tests}", "ERROR" if failed_tests > 0 else "INFO")
        self.log(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%", "INFO")
        self.log(f"Total Time: {total_time:.2f}s", "INFO")

        # Average response times
        response_times = [r.response_time for r in self.results if r.response_time > 0]
        if response_times:
            avg_response_time = sum(response_times) / len(response_times)
            self.log(f"Average Response Time: {avg_response_time:.3f}s", "INFO")

        # Failed tests details
        if failed_tests > 0:
            self.log("\n❌ FAILED TESTS:", "ERROR")
            for result in self.results:
                if not result.success:
                    self.log(
                        f"  {result.method} {result.endpoint} -> {result.error}",
                        "ERROR",
                    )

        # Performance insights
        slow_tests = [r for r in self.results if r.response_time > 5.0]
        if slow_tests:
            self.log("\n⚠️  SLOW TESTS (>5s):", "WARNING")
            for result in slow_tests:
                self.log(
                    f"  {result.method} {result.endpoint} -> {result.response_time:.3f}s",
                    "WARNING",
                )

        # Endpoint coverage by category
        categories = {
            "Health": [
                r for r in self.results if "/health" in r.endpoint or r.endpoint == "/"
            ],
            "MCP Protocol": [r for r in self.results if "/mcp/" in r.endpoint],
            "MCP Tools": [
                r
                for r in self.results
                if "/ai/" in r.endpoint and "/mcp/" not in r.endpoint
            ],
            "Repositories": [r for r in self.results if "/repositories/" in r.endpoint],
            "Search": [r for r in self.results if "/search/" in r.endpoint],
            "Files": [r for r in self.results if "/files/" in r.endpoint],
        }

        self.log("\n📈 CATEGORY BREAKDOWN:", "INFO")
        for category, results in categories.items():
            if results:
                passed = sum(1 for r in results if r.success)
                total = len(results)
                self.log(
                    f"  {category}: {passed}/{total} ({(passed/total)*100:.1f}%)",
                    "INFO",
                )

        self.log("\n" + "=" * 80, "INFO")

        # Save detailed report to file
        self.save_detailed_report()

    def save_detailed_report(self):
        """Save detailed test results to JSON file"""
        report_data = {
            "timestamp": time.time(),
            "total_tests": len(self.results),
            "passed_tests": sum(1 for r in self.results if r.success),
            "failed_tests": sum(1 for r in self.results if not r.success),
            "results": [
                {
                    "endpoint": r.endpoint,
                    "method": r.method,
                    "status_code": r.status_code,
                    "success": r.success,
                    "response_time": r.response_time,
                    "error": r.error,
                }
                for r in self.results
            ],
        }

        try:
            with open("test_results.json", "w") as f:
                json.dump(report_data, f, indent=2)
            self.log("📄 Detailed report saved to test_results.json", "SUCCESS")
        except Exception as e:
            self.log(f"Failed to save report: {str(e)}", "ERROR")


if __name__ == "__main__":
    # Allow custom base URL
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"

    tester = CodeSageAPITester(base_url)
    tester.run_all_tests()
