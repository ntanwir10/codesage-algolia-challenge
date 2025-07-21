#!/usr/bin/env python3
"""
Repository Management Endpoints Testing
Tests all repository CRUD operations, file uploads, processing, and statistics.
"""

import requests
import json
import time
import os
from typing import Dict, List, Any


class RepositoryEndpointsTester:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update(
            {"Content-Type": "application/json", "Accept": "application/json"}
        )
        self.created_repo_id = None

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

    def test_create_repository(self):
        """Test repository creation"""
        self.log("=== Testing Repository Creation ===", "INFO")

        # Create unique repository name
        timestamp = int(time.time())
        repo_data = {
            "name": f"test-repository-{timestamp}",
            "description": "Test repository for endpoint testing",
            "language": "python",
            "url": "https://github.com/test/test-repo",
            "is_public": True,
        }

        start_time = time.time()
        response = self.session.post(
            f"{self.base_url}/api/v1/repositories/", json=repo_data
        )
        execution_time = time.time() - start_time

        if response.status_code == 201:
            result = response.json()
            self.created_repo_id = result.get("id")
            self.log(f"✅ Repository Created: {response.status_code}", "SUCCESS")
            self.log(f"  Repository ID: {self.created_repo_id}", "INFO")
            self.log(f"  Name: {result.get('name')}", "INFO")
            self.log(f"  Language: {result.get('language')}", "INFO")
            self.log(f"  Execution Time: {execution_time:.3f}s", "INFO")
            return True, result
        else:
            self.log(f"❌ Repository Creation Failed: {response.status_code}", "ERROR")
            try:
                error_data = response.json()
                self.log(
                    f"  Error: {error_data.get('detail', 'Unknown error')}", "ERROR"
                )
            except:
                self.log(f"  Raw Error: {response.text[:100]}...", "ERROR")
            return False, None

    def test_list_repositories(self):
        """Test repository listing"""
        self.log("\n=== Testing Repository Listing ===", "INFO")

        start_time = time.time()
        response = self.session.get(f"{self.base_url}/api/v1/repositories/")
        execution_time = time.time() - start_time

        if response.status_code == 200:
            result = response.json()
            self.log(f"✅ Repositories Listed: {response.status_code}", "SUCCESS")

            if isinstance(result, list):
                self.log(f"  Total Repositories: {len(result)}", "INFO")
                if result:
                    first_repo = result[0]
                    self.log(
                        f"  Sample Repository Keys: {list(first_repo.keys())}", "INFO"
                    )
                    self.log(
                        f"  First Repository: {first_repo.get('name', 'Unknown')}",
                        "INFO",
                    )
            elif isinstance(result, dict) and "repositories" in result:
                repos = result["repositories"]
                self.log(f"  Total Repositories: {len(repos)}", "INFO")

            self.log(f"  Execution Time: {execution_time:.3f}s", "INFO")
            return True
        else:
            self.log(f"❌ Repository Listing Failed: {response.status_code}", "ERROR")
            return False

    def test_get_repository(self):
        """Test getting specific repository"""
        if not self.created_repo_id:
            self.log("\n❌ Skipping Get Repository - No repository created", "ERROR")
            return False

        self.log("\n=== Testing Get Repository ===", "INFO")

        start_time = time.time()
        response = self.session.get(
            f"{self.base_url}/api/v1/repositories/{self.created_repo_id}"
        )
        execution_time = time.time() - start_time

        if response.status_code == 200:
            result = response.json()
            self.log(f"✅ Repository Retrieved: {response.status_code}", "SUCCESS")
            self.log(f"  Repository ID: {result.get('id')}", "INFO")
            self.log(f"  Name: {result.get('name')}", "INFO")
            self.log(f"  Created At: {result.get('created_at')}", "INFO")
            self.log(f"  Execution Time: {execution_time:.3f}s", "INFO")
            return True
        else:
            self.log(f"❌ Get Repository Failed: {response.status_code}", "ERROR")
            return False

    def test_update_repository(self):
        """Test repository update"""
        if not self.created_repo_id:
            self.log("\n❌ Skipping Update Repository - No repository created", "ERROR")
            return False

        self.log("\n=== Testing Repository Update ===", "INFO")

        update_data = {
            "description": "Updated test repository description",
            "language": "typescript",
            "is_public": False,
        }

        start_time = time.time()
        response = self.session.put(
            f"{self.base_url}/api/v1/repositories/{self.created_repo_id}",
            json=update_data,
        )
        execution_time = time.time() - start_time

        if response.status_code == 200:
            result = response.json()
            self.log(f"✅ Repository Updated: {response.status_code}", "SUCCESS")
            self.log(f"  New Description: {result.get('description')}", "INFO")
            self.log(f"  New Language: {result.get('language')}", "INFO")
            self.log(f"  Execution Time: {execution_time:.3f}s", "INFO")
            return True
        else:
            self.log(f"❌ Repository Update Failed: {response.status_code}", "ERROR")
            return False

    def test_repository_upload(self):
        """Test file upload to repository"""
        if not self.created_repo_id:
            self.log("\n❌ Skipping File Upload - No repository created", "ERROR")
            return False

        self.log("\n=== Testing Repository File Upload ===", "INFO")

        # Create a test file
        test_content = """
def hello_world():
    \"\"\"A simple hello world function\"\"\"
    print("Hello, World!")
    return "success"

class TestClass:
    def __init__(self):
        self.message = "test"
    
    def get_message(self):
        return self.message
"""

        # Test with form data instead of JSON for file upload
        files = {"files": ("test_file.py", test_content, "text/plain")}

        # Remove JSON content type for file upload
        upload_session = requests.Session()
        upload_session.headers.update({"Accept": "application/json"})

        start_time = time.time()
        response = upload_session.post(
            f"{self.base_url}/api/v1/repositories/{self.created_repo_id}/upload",
            files=files,
        )
        execution_time = time.time() - start_time

        if response.status_code == 200:
            result = response.json()
            self.log(f"✅ File Upload Success: {response.status_code}", "SUCCESS")
            self.log(f"  Files Uploaded: {result.get('files_uploaded', 0)}", "INFO")
            self.log(f"  Execution Time: {execution_time:.3f}s", "INFO")
            return True
        else:
            self.log(f"❌ File Upload Failed: {response.status_code}", "ERROR")
            try:
                error_data = response.json()
                self.log(
                    f"  Error: {error_data.get('detail', 'Unknown error')}", "ERROR"
                )
            except:
                self.log(f"  Raw Error: {response.text[:100]}...", "ERROR")
            return False

    def test_repository_processing(self):
        """Test repository processing trigger"""
        if not self.created_repo_id:
            self.log("\n❌ Skipping Processing - No repository created", "ERROR")
            return False

        self.log("\n=== Testing Repository Processing ===", "INFO")

        start_time = time.time()
        response = self.session.post(
            f"{self.base_url}/api/v1/repositories/{self.created_repo_id}/process?force_reprocess=false"
        )
        execution_time = time.time() - start_time

        if response.status_code == 200:
            result = response.json()
            self.log(f"✅ Processing Started: {response.status_code}", "SUCCESS")
            self.log(f"  Job ID: {result.get('job_id', 'N/A')}", "INFO")
            self.log(f"  Status: {result.get('status', 'N/A')}", "INFO")
            self.log(f"  Execution Time: {execution_time:.3f}s", "INFO")
            return True
        else:
            self.log(f"❌ Processing Failed: {response.status_code}", "ERROR")
            return False

    def test_repository_status(self):
        """Test repository status check"""
        if not self.created_repo_id:
            self.log("\n❌ Skipping Status Check - No repository created", "ERROR")
            return False

        self.log("\n=== Testing Repository Status ===", "INFO")

        start_time = time.time()
        response = self.session.get(
            f"{self.base_url}/api/v1/repositories/{self.created_repo_id}/status"
        )
        execution_time = time.time() - start_time

        if response.status_code == 200:
            result = response.json()
            self.log(f"✅ Status Retrieved: {response.status_code}", "SUCCESS")
            self.log(
                f"  Processing Status: {result.get('processing_status', 'N/A')}", "INFO"
            )
            self.log(f"  Files Count: {result.get('file_count', 0)}", "INFO")
            self.log(f"  Last Updated: {result.get('last_updated', 'N/A')}", "INFO")
            self.log(f"  Execution Time: {execution_time:.3f}s", "INFO")
            return True
        else:
            self.log(f"❌ Status Check Failed: {response.status_code}", "ERROR")
            return False

    def test_repository_stats(self):
        """Test repository statistics"""
        if not self.created_repo_id:
            self.log("\n❌ Skipping Stats - No repository created", "ERROR")
            return False

        self.log("\n=== Testing Repository Statistics ===", "INFO")

        start_time = time.time()
        response = self.session.get(
            f"{self.base_url}/api/v1/repositories/{self.created_repo_id}/stats"
        )
        execution_time = time.time() - start_time

        if response.status_code == 200:
            result = response.json()
            self.log(f"✅ Stats Retrieved: {response.status_code}", "SUCCESS")
            self.log(f"  Total Files: {result.get('total_files', 0)}", "INFO")
            self.log(f"  Total Lines: {result.get('total_lines', 0)}", "INFO")
            self.log(f"  Languages: {result.get('languages', [])}", "INFO")
            self.log(f"  Execution Time: {execution_time:.3f}s", "INFO")
            return True
        else:
            self.log(f"❌ Stats Failed: {response.status_code}", "ERROR")
            return False

    def test_delete_repository(self):
        """Test repository deletion"""
        if not self.created_repo_id:
            self.log("\n❌ Skipping Delete Repository - No repository created", "ERROR")
            return False

        self.log("\n=== Testing Repository Deletion ===", "INFO")

        start_time = time.time()
        response = self.session.delete(
            f"{self.base_url}/api/v1/repositories/{self.created_repo_id}"
        )
        execution_time = time.time() - start_time

        if response.status_code == 200:
            self.log(f"✅ Repository Deleted: {response.status_code}", "SUCCESS")
            self.log(f"  Execution Time: {execution_time:.3f}s", "INFO")
            self.created_repo_id = None  # Clear the ID
            return True
        else:
            self.log(f"❌ Repository Deletion Failed: {response.status_code}", "ERROR")
            return False

    def run_repository_tests(self):
        """Run all repository management tests"""
        start_time = time.time()

        self.log("🚀 Starting Repository Management Testing", "INFO")
        self.log(f"Target: {self.base_url}", "INFO")
        self.log("=" * 60, "INFO")

        # Run all tests in sequence
        test_results = []

        test_results.append(("Create Repository", self.test_create_repository()[0]))
        test_results.append(("List Repositories", self.test_list_repositories()))
        test_results.append(("Get Repository", self.test_get_repository()))
        test_results.append(("Update Repository", self.test_update_repository()))
        test_results.append(("Upload Files", self.test_repository_upload()))
        test_results.append(("Process Repository", self.test_repository_processing()))
        test_results.append(("Check Status", self.test_repository_status()))
        test_results.append(("Get Statistics", self.test_repository_stats()))
        test_results.append(("Delete Repository", self.test_delete_repository()))

        # Generate summary
        total_time = time.time() - start_time
        successful_tests = sum(1 for _, success in test_results if success)
        total_tests = len(test_results)
        success_rate = (successful_tests / total_tests) * 100

        self.log("\n" + "=" * 60, "INFO")
        self.log("📊 REPOSITORY MANAGEMENT TEST SUMMARY", "INFO")
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
            self.log("🏆 EXCELLENT: Repository Management Fully Working!", "SUCCESS")
        elif success_rate >= 80:
            self.log("✅ GOOD: Most Repository Operations Working", "SUCCESS")
        else:
            self.log("⚠️  WARNING: Repository Management Needs Attention", "WARNING")

        self.log("=" * 60, "INFO")

        return success_rate


if __name__ == "__main__":
    tester = RepositoryEndpointsTester()
    tester.run_repository_tests()
