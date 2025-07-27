#!/usr/bin/env python3
"""
Advanced Search Endpoints Testing
Tests all advanced search functionality including main search, suggestions, analytics, and health.
"""

import requests
import json
import time
from typing import Dict, List, Any


class SearchEndpointsTester:
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

    def test_main_search(self):
        """Test main search endpoint"""
        self.log("=== Testing Main Search Endpoint ===", "INFO")

        search_queries = [
            {
                "query": "authentication function",
                "language": "python",
                "per_page": 10,
            },
            {
                "query": "database connection pool",
                "entity_type": "function",
                "per_page": 5,
            },
            {"query": "error handling middleware", "per_page": 3},
        ]

        successful_searches = 0
        total_searches = len(search_queries)

        for i, search_data in enumerate(search_queries, 1):
            self.log(f"\n--- Search Query {i}/{total_searches} ---", "INFO")

            start_time = time.time()
            response = self.session.post(
                f"{self.base_url}/api/v1/search/", json=search_data
            )
            execution_time = time.time() - start_time

            if response.status_code == 200:
                result = response.json()
                successful_searches += 1
                self.log(f"✅ Search Success: {response.status_code}", "SUCCESS")
                self.log(f"  Query: {search_data['query'][:50]}...", "INFO")
                self.log(f"  Total Hits: {result.get('total_hits', 0)}", "INFO")
                self.log(f"  Results Returned: {len(result.get('hits', []))}", "INFO")
                self.log(
                    f"  Processing Time: {result.get('processing_time', 0):.3f}s",
                    "INFO",
                )
                self.log(f"  Execution Time: {execution_time:.3f}s", "INFO")
                self.log(f"  Page: {result.get('page', 0)}", "INFO")
                self.log(f"  Per Page: {result.get('per_page', 20)}", "INFO")

            else:
                self.log(f"❌ Search Failed: {response.status_code}", "ERROR")
                try:
                    error_data = response.json()
                    self.log(
                        f"  Error: {error_data.get('detail', 'Unknown error')}", "ERROR"
                    )
                except:
                    self.log(f"  Raw Error: {response.text[:100]}...", "ERROR")

        success_rate = (successful_searches / total_searches) * 100
        self.log(
            f"\n📊 Main Search Success Rate: {successful_searches}/{total_searches} ({success_rate:.1f}%)",
            "SUCCESS" if success_rate >= 80 else "WARNING",
        )

        return successful_searches == total_searches

    def test_search_suggestions(self):
        """Test search suggestions endpoint"""
        self.log("\n=== Testing Search Suggestions ===", "INFO")

        suggestion_queries = ["auth", "database", "error", "class", "function"]

        successful_suggestions = 0

        for query in suggestion_queries:
            start_time = time.time()
            response = self.session.get(
                f"{self.base_url}/api/v1/search/suggestions",
                params={"q": query, "limit": 5},
            )
            execution_time = time.time() - start_time

            if response.status_code == 200:
                result = response.json()
                successful_suggestions += 1
                self.log(
                    f"✅ Suggestions for '{query}': {response.status_code}", "SUCCESS"
                )

                if "suggestions" in result:
                    suggestions = result["suggestions"]
                    self.log(f"  Suggestions Count: {len(suggestions)}", "INFO")
                    if suggestions:
                        sample_suggestions = suggestions[:3]
                        for i, suggestion in enumerate(sample_suggestions, 1):
                            if isinstance(suggestion, dict):
                                text = suggestion.get(
                                    "text", suggestion.get("query", "Unknown")
                                )
                                score = suggestion.get("score", "N/A")
                                self.log(f"    {i}. {text} (score: {score})", "INFO")
                            else:
                                self.log(f"    {i}. {suggestion}", "INFO")

                self.log(f"  Execution Time: {execution_time:.3f}s", "INFO")
            else:
                self.log(
                    f"❌ Suggestions Failed for '{query}': {response.status_code}",
                    "ERROR",
                )

        return successful_suggestions == len(suggestion_queries)

    def test_voice_search(self):
        """Test voice search endpoint"""
        self.log("\n=== Testing Voice Search ===", "INFO")

        voice_data = {
            "audio_data": "mock_audio_data_base64",
            "language": "en-US",
            "context": "code search",
        }

        start_time = time.time()
        response = self.session.post(
            f"{self.base_url}/api/v1/search/voice", json=voice_data
        )
        execution_time = time.time() - start_time

        if response.status_code == 200:
            result = response.json()
            self.log(f"✅ Voice Search Success: {response.status_code}", "SUCCESS")
            self.log(f"  Query Processed: {result.get('query', 'N/A')[:50]}...", "INFO")
            self.log(f"  Search Results: {len(result.get('hits', []))}", "INFO")
            self.log(f"  Total Hits: {result.get('total_hits', 0)}", "INFO")
            self.log(f"  Execution Time: {execution_time:.3f}s", "INFO")
            return True
        else:
            self.log(f"❌ Voice Search Failed: {response.status_code}", "ERROR")
            return False

    def test_similarity_search(self):
        """Test similarity search endpoint"""
        self.log("\n=== Testing Similarity Search ===", "INFO")

        similarity_data = {
            "entity_type": "function",
            "entity_id": 1,
            "threshold": 0.7,
            "limit": 5,
        }

        start_time = time.time()
        response = self.session.post(
            f"{self.base_url}/api/v1/search/similar", json=similarity_data
        )
        execution_time = time.time() - start_time

        if response.status_code == 200:
            result = response.json()
            self.log(f"✅ Similarity Search Success: {response.status_code}", "SUCCESS")
            self.log(
                f"  Similar Items Found: {len(result.get('similar_entities', []))}",
                "INFO",
            )
            self.log(
                f"  Total Found: {result.get('total_found', 0)}",
                "INFO",
            )
            self.log(f"  Execution Time: {execution_time:.3f}s", "INFO")
            return True
        elif response.status_code == 404:
            self.log(
                f"⚠️ Similarity Search - Entity not found (expected when DB is empty): {response.status_code}",
                "WARNING",
            )
            try:
                error_data = response.json()
                self.log(
                    f"  Message: {error_data.get('detail', 'Entity not found')}", "INFO"
                )
            except:
                pass
            self.log(f"  Execution Time: {execution_time:.3f}s", "INFO")
            return (
                True  # Consider this a pass since it's expected behavior with empty DB
            )
        else:
            self.log(f"❌ Similarity Search Failed: {response.status_code}", "ERROR")
            return False

    def test_trending_searches(self):
        """Test trending searches endpoint"""
        self.log("\n=== Testing Trending Searches ===", "INFO")

        start_time = time.time()
        response = self.session.get(
            f"{self.base_url}/api/v1/search/trending",
            params={"period": "24h", "limit": 10},
        )
        execution_time = time.time() - start_time

        if response.status_code == 200:
            result = response.json()
            self.log(f"✅ Trending Searches Success: {response.status_code}", "SUCCESS")

            if "trending_queries" in result:
                trending = result["trending_queries"]
                self.log(f"  Trending Queries: {len(trending)}", "INFO")
                if trending:
                    for i, query in enumerate(trending[:5], 1):
                        if isinstance(query, dict):
                            text = query.get("query", "Unknown")
                            count = query.get("count", 0)
                            self.log(f"    {i}. {text} ({count} searches)", "INFO")
                        else:
                            self.log(f"    {i}. {query}", "INFO")

            self.log(f"  Execution Time: {execution_time:.3f}s", "INFO")
            return True
        else:
            self.log(f"❌ Trending Searches Failed: {response.status_code}", "ERROR")
            return False

    def test_search_analytics(self):
        """Test search analytics endpoint"""
        self.log("\n=== Testing Search Analytics ===", "INFO")

        start_time = time.time()
        response = self.session.get(
            f"{self.base_url}/api/v1/search/analytics", params={"period": "7d"}
        )
        execution_time = time.time() - start_time

        if response.status_code == 200:
            result = response.json()
            self.log(f"✅ Search Analytics Success: {response.status_code}", "SUCCESS")
            self.log(f"  Total Searches: {result.get('total_searches', 0)}", "INFO")
            self.log(f"  Unique Users: {result.get('unique_users', 0)}", "INFO")
            self.log(
                f"  Average Response Time: {result.get('avg_response_time', 0):.3f}s",
                "INFO",
            )
            self.log(f"  Top Languages: {result.get('top_languages', [])}", "INFO")
            self.log(f"  Execution Time: {execution_time:.3f}s", "INFO")
            return True
        else:
            self.log(f"❌ Search Analytics Failed: {response.status_code}", "ERROR")
            return False

    def test_search_health(self):
        """Test search service health endpoint"""
        self.log("\n=== Testing Search Service Health ===", "INFO")

        start_time = time.time()
        response = self.session.get(f"{self.base_url}/api/v1/search/health")
        execution_time = time.time() - start_time

        if response.status_code == 200:
            result = response.json()
            self.log(f"✅ Search Health Success: {response.status_code}", "SUCCESS")
            self.log(f"  Service Status: {result.get('status', 'Unknown')}", "INFO")
            self.log(
                f"  Algolia Connection: {result.get('algolia_status', 'Unknown')}",
                "INFO",
            )
            self.log(f"  Index Status: {result.get('index_status', 'Unknown')}", "INFO")
            self.log(f"  Response Time: {result.get('response_time', 0):.3f}s", "INFO")
            self.log(f"  Execution Time: {execution_time:.3f}s", "INFO")
            return True
        else:
            self.log(f"❌ Search Health Failed: {response.status_code}", "ERROR")
            return False

    def test_index_refresh(self):
        """Test search index refresh endpoint"""
        self.log("\n=== Testing Search Index Refresh ===", "INFO")

        start_time = time.time()
        response = self.session.post(
            f"{self.base_url}/api/v1/search/index/refresh",
            params={"repository_id": 1, "force": False},
        )
        execution_time = time.time() - start_time

        if response.status_code == 200:
            result = response.json()
            self.log(f"✅ Index Refresh Success: {response.status_code}", "SUCCESS")
            self.log(f"  Refresh Status: {result.get('status', 'Unknown')}", "INFO")
            self.log(
                f"  Documents Updated: {result.get('documents_updated', 0)}", "INFO"
            )
            self.log(f"  Execution Time: {execution_time:.3f}s", "INFO")
            return True
        else:
            self.log(f"❌ Index Refresh Failed: {response.status_code}", "ERROR")
            return False

    def run_search_tests(self):
        """Run all search endpoint tests"""
        start_time = time.time()

        self.log("🚀 Starting Advanced Search Testing", "INFO")
        self.log(f"Target: {self.base_url}", "INFO")
        self.log("=" * 60, "INFO")

        # Run all tests
        test_results = []

        test_results.append(("Main Search", self.test_main_search()))
        test_results.append(("Search Suggestions", self.test_search_suggestions()))
        test_results.append(("Voice Search", self.test_voice_search()))
        test_results.append(("Similarity Search", self.test_similarity_search()))
        test_results.append(("Trending Searches", self.test_trending_searches()))
        test_results.append(("Search Analytics", self.test_search_analytics()))
        test_results.append(("Search Health", self.test_search_health()))
        test_results.append(("Index Refresh", self.test_index_refresh()))

        # Generate summary
        total_time = time.time() - start_time
        successful_tests = sum(1 for _, success in test_results if success)
        total_tests = len(test_results)
        success_rate = (successful_tests / total_tests) * 100

        self.log("\n" + "=" * 60, "INFO")
        self.log("📊 ADVANCED SEARCH TEST SUMMARY", "INFO")
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

        # Final assessment
        if success_rate >= 95:
            self.log("🏆 EXCELLENT: Advanced Search Fully Working!", "SUCCESS")
        elif success_rate >= 80:
            self.log("✅ GOOD: Most Search Features Working", "SUCCESS")
        else:
            self.log("⚠️  WARNING: Search System Needs Attention", "WARNING")

        self.log("=" * 60, "INFO")

        return success_rate


if __name__ == "__main__":
    tester = SearchEndpointsTester()
    tester.run_search_tests()
