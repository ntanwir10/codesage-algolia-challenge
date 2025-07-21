#!/usr/bin/env python3
"""
File Operations Endpoints Testing
Tests all file operations including listing, content retrieval, entity extraction, analysis, and statistics.
"""

import requests
import json
import time
from typing import Dict, List, Any


class FileEndpointsTester:
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

    def test_list_repository_files(self):
        """Test listing files in a repository"""
        self.log("=== Testing Repository Files Listing ===", "INFO")

        repository_ids = ["1", "2", "3"]  # Test multiple repositories

        successful_lists = 0

        for repo_id in repository_ids:
            self.log(f"\n--- Repository {repo_id} Files ---", "INFO")

            start_time = time.time()
            response = self.session.get(
                f"{self.base_url}/api/v1/files/repositories/{repo_id}",
                params={
                    "page": 1,
                    "size": 10,
                    "file_extension": "py",
                    "include_content": False,
                },
            )
            execution_time = time.time() - start_time

            if response.status_code == 200:
                result = response.json()
                successful_lists += 1
                self.log(f"✅ Files Listed: {response.status_code}", "SUCCESS")

                if isinstance(result, list):
                    files = result
                elif isinstance(result, dict) and "files" in result:
                    files = result["files"]
                else:
                    files = []

                self.log(f"  Files Found: {len(files)}", "INFO")
                if files:
                    first_file = files[0]
                    if isinstance(first_file, dict):
                        self.log(
                            f"  Sample File: {first_file.get('name', 'Unknown')}",
                            "INFO",
                        )
                        self.log(
                            f"  File Size: {first_file.get('size', 0)} bytes", "INFO"
                        )
                        self.log(
                            f"  File Type: {first_file.get('file_type', 'Unknown')}",
                            "INFO",
                        )

                self.log(f"  Execution Time: {execution_time:.3f}s", "INFO")

            elif response.status_code == 404:
                self.log(
                    f"⚠️  Repository {repo_id} not found (expected for some IDs)",
                    "WARNING",
                )
            else:
                self.log(f"❌ Files Listing Failed: {response.status_code}", "ERROR")

        return successful_lists > 0

    def test_get_file_content(self):
        """Test getting file content and metadata"""
        self.log("\n=== Testing File Content Retrieval ===", "INFO")

        file_ids = ["1", "2", "3"]  # Test multiple files

        successful_gets = 0

        for file_id in file_ids:
            self.log(f"\n--- File {file_id} Content ---", "INFO")

            start_time = time.time()
            response = self.session.get(
                f"{self.base_url}/api/v1/files/{file_id}",
                params={"include_raw_content": True, "include_entities": True},
            )
            execution_time = time.time() - start_time

            if response.status_code == 200:
                result = response.json()
                successful_gets += 1
                self.log(
                    f"✅ File Content Retrieved: {response.status_code}", "SUCCESS"
                )
                self.log(f"  File Name: {result.get('name', 'Unknown')}", "INFO")
                self.log(f"  File Path: {result.get('path', 'Unknown')}", "INFO")
                self.log(f"  Language: {result.get('language', 'Unknown')}", "INFO")
                self.log(f"  Lines of Code: {result.get('lines_of_code', 0)}", "INFO")

                if "content" in result:
                    content = result["content"]
                    content_length = len(content) if isinstance(content, str) else 0
                    self.log(f"  Content Length: {content_length} chars", "INFO")

                if "entities" in result:
                    entities = result["entities"]
                    self.log(f"  Entities Found: {len(entities)}", "INFO")

                self.log(f"  Execution Time: {execution_time:.3f}s", "INFO")

            elif response.status_code == 404:
                self.log(
                    f"⚠️  File {file_id} not found (expected for some IDs)", "WARNING"
                )
            else:
                self.log(f"❌ File Content Failed: {response.status_code}", "ERROR")

        return successful_gets > 0

    def test_get_file_entities(self):
        """Test getting file entities (functions, classes, etc.)"""
        self.log("\n=== Testing File Entities Extraction ===", "INFO")

        file_id = "1"

        start_time = time.time()
        response = self.session.get(
            f"{self.base_url}/api/v1/files/{file_id}/entities",
            params={"entity_types": "function,class", "include_private": False},
        )
        execution_time = time.time() - start_time

        if response.status_code == 200:
            result = response.json()
            self.log(f"✅ File Entities Retrieved: {response.status_code}", "SUCCESS")

            if "entities" in result:
                entities = result["entities"]
                self.log(f"  Total Entities: {len(entities)}", "INFO")

                # Group by type
                entity_types = {}
                for entity in entities:
                    if isinstance(entity, dict):
                        entity_type = entity.get("type", "unknown")
                        entity_types[entity_type] = entity_types.get(entity_type, 0) + 1

                for entity_type, count in entity_types.items():
                    self.log(f"    {entity_type.title()}s: {count}", "INFO")

                # Show sample entity
                if entities:
                    sample_entity = entities[0]
                    if isinstance(sample_entity, dict):
                        self.log(
                            f"  Sample Entity: {sample_entity.get('name', 'Unknown')}",
                            "INFO",
                        )
                        self.log(
                            f"    Type: {sample_entity.get('type', 'Unknown')}", "INFO"
                        )
                        self.log(
                            f"    Line: {sample_entity.get('line_number', 'Unknown')}",
                            "INFO",
                        )

            self.log(f"  Execution Time: {execution_time:.3f}s", "INFO")
            return True
        else:
            self.log(f"❌ File Entities Failed: {response.status_code}", "ERROR")
            return False

    def test_get_file_summary(self):
        """Test getting AI-generated file summary"""
        self.log("\n=== Testing File Summary Generation ===", "INFO")

        file_id = "1"

        start_time = time.time()
        response = self.session.get(f"{self.base_url}/api/v1/files/{file_id}/summary")
        execution_time = time.time() - start_time

        if response.status_code == 200:
            result = response.json()
            self.log(f"✅ File Summary Generated: {response.status_code}", "SUCCESS")
            self.log(f"  File ID: {result.get('file_id', 'Unknown')}", "INFO")

            if "summary" in result:
                summary = result["summary"]
                if isinstance(summary, str):
                    self.log(f"  Summary Length: {len(summary)} chars", "INFO")
                    self.log(f"  Summary Preview: {summary[:100]}...", "INFO")
                elif isinstance(summary, dict):
                    self.log(f"  Summary Keys: {list(summary.keys())}", "INFO")

            if "key_functions" in result:
                key_functions = result["key_functions"]
                self.log(f"  Key Functions: {len(key_functions)}", "INFO")

            self.log(f"  Execution Time: {execution_time:.3f}s", "INFO")
            return True
        else:
            self.log(f"❌ File Summary Failed: {response.status_code}", "ERROR")
            return False

    def test_analyze_file(self):
        """Test individual file analysis"""
        self.log("\n=== Testing Individual File Analysis ===", "INFO")

        file_id = "1"
        analysis_data = {
            "analysis_types": ["complexity", "security", "documentation"],
            "include_suggestions": True,
        }

        start_time = time.time()
        response = self.session.post(
            f"{self.base_url}/api/v1/files/{file_id}/analyze", json=analysis_data
        )
        execution_time = time.time() - start_time

        if response.status_code == 200:
            result = response.json()
            self.log(f"✅ File Analysis Completed: {response.status_code}", "SUCCESS")
            self.log(f"  File ID: {result.get('file_id', 'Unknown')}", "INFO")

            if "analysis" in result:
                analysis = result["analysis"]
                if isinstance(analysis, dict):
                    self.log(f"  Analysis Keys: {list(analysis.keys())}", "INFO")

                    if "complexity_score" in analysis:
                        self.log(
                            f"  Complexity Score: {analysis['complexity_score']}",
                            "INFO",
                        )

                    if "security_issues" in analysis:
                        issues = analysis["security_issues"]
                        self.log(f"  Security Issues: {len(issues)}", "INFO")

                    if "suggestions" in analysis:
                        suggestions = analysis["suggestions"]
                        self.log(f"  Suggestions: {len(suggestions)}", "INFO")

            self.log(f"  Execution Time: {execution_time:.3f}s", "INFO")
            return True
        else:
            self.log(f"❌ File Analysis Failed: {response.status_code}", "ERROR")
            return False

    def test_bulk_analyze_files(self):
        """Test bulk file analysis"""
        self.log("\n=== Testing Bulk File Analysis ===", "INFO")

        bulk_data = {
            "file_ids": ["1", "2", "3"],
            "analysis_types": ["complexity", "maintainability"],
            "batch_size": 2,
        }

        start_time = time.time()
        response = self.session.post(
            f"{self.base_url}/api/v1/files/analyze/bulk", json=bulk_data
        )
        execution_time = time.time() - start_time

        if response.status_code == 200:
            result = response.json()
            self.log(f"✅ Bulk Analysis Started: {response.status_code}", "SUCCESS")
            self.log(f"  Job ID: {result.get('job_id', 'Unknown')}", "INFO")
            self.log(f"  Files Queued: {result.get('files_queued', 0)}", "INFO")
            self.log(
                f"  Estimated Time: {result.get('estimated_completion', 'Unknown')}",
                "INFO",
            )
            self.log(f"  Execution Time: {execution_time:.3f}s", "INFO")
            return True
        else:
            self.log(f"❌ Bulk Analysis Failed: {response.status_code}", "ERROR")
            return False

    def test_repository_file_stats(self):
        """Test repository file statistics"""
        self.log("\n=== Testing Repository File Statistics ===", "INFO")

        repository_id = "1"

        start_time = time.time()
        response = self.session.get(
            f"{self.base_url}/api/v1/files/stats/repository/{repository_id}"
        )
        execution_time = time.time() - start_time

        if response.status_code == 200:
            result = response.json()
            self.log(f"✅ File Statistics Retrieved: {response.status_code}", "SUCCESS")
            self.log(
                f"  Repository ID: {result.get('repository_id', 'Unknown')}", "INFO"
            )
            self.log(f"  Total Files: {result.get('total_files', 0)}", "INFO")
            self.log(f"  Total Lines: {result.get('total_lines', 0)}", "INFO")
            self.log(
                f"  Average File Size: {result.get('average_file_size', 0):.1f} bytes",
                "INFO",
            )

            if "file_types" in result:
                file_types = result["file_types"]
                self.log(f"  File Types Distribution:", "INFO")
                for file_type, count in file_types.items():
                    self.log(f"    {file_type}: {count} files", "INFO")

            if "languages" in result:
                languages = result["languages"]
                self.log(f"  Languages: {list(languages.keys())}", "INFO")

            self.log(f"  Execution Time: {execution_time:.3f}s", "INFO")
            return True
        else:
            self.log(f"❌ File Statistics Failed: {response.status_code}", "ERROR")
            return False

    def test_raw_file_content(self):
        """Test getting raw file content"""
        self.log("\n=== Testing Raw File Content ===", "INFO")

        file_id = "1"

        start_time = time.time()
        response = self.session.get(f"{self.base_url}/api/v1/files/{file_id}/raw")
        execution_time = time.time() - start_time

        if response.status_code == 200:
            # Check if response is text or JSON
            content_type = response.headers.get("content-type", "")

            if "application/json" in content_type:
                result = response.json()
                self.log(f"✅ Raw Content (JSON): {response.status_code}", "SUCCESS")
                self.log(f"  Content Length: {len(result.get('content', ''))}", "INFO")
            else:
                content = response.text
                self.log(f"✅ Raw Content (Text): {response.status_code}", "SUCCESS")
                self.log(f"  Content Length: {len(content)} chars", "INFO")
                self.log(f"  Content Preview: {content[:100]}...", "INFO")

            self.log(f"  Execution Time: {execution_time:.3f}s", "INFO")
            return True
        else:
            self.log(f"❌ Raw Content Failed: {response.status_code}", "ERROR")
            return False

    def run_file_tests(self):
        """Run all file operation tests"""
        start_time = time.time()

        self.log("🚀 Starting File Operations Testing", "INFO")
        self.log(f"Target: {self.base_url}", "INFO")
        self.log("=" * 60, "INFO")

        # Run all tests
        test_results = []

        test_results.append(
            ("List Repository Files", self.test_list_repository_files())
        )
        test_results.append(("Get File Content", self.test_get_file_content()))
        test_results.append(("Get File Entities", self.test_get_file_entities()))
        test_results.append(("Get File Summary", self.test_get_file_summary()))
        test_results.append(("Analyze File", self.test_analyze_file()))
        test_results.append(("Bulk Analyze Files", self.test_bulk_analyze_files()))
        test_results.append(
            ("Repository File Stats", self.test_repository_file_stats())
        )
        test_results.append(("Raw File Content", self.test_raw_file_content()))

        # Generate summary
        total_time = time.time() - start_time
        successful_tests = sum(1 for _, success in test_results if success)
        total_tests = len(test_results)
        success_rate = (successful_tests / total_tests) * 100

        self.log("\n" + "=" * 60, "INFO")
        self.log("📊 FILE OPERATIONS TEST SUMMARY", "INFO")
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
            self.log("🏆 EXCELLENT: File Operations Fully Working!", "SUCCESS")
        elif success_rate >= 80:
            self.log("✅ GOOD: Most File Operations Working", "SUCCESS")
        else:
            self.log("⚠️  WARNING: File Operations Need Attention", "WARNING")

        self.log("=" * 60, "INFO")

        return success_rate


if __name__ == "__main__":
    tester = FileEndpointsTester()
    tester.run_file_tests()
