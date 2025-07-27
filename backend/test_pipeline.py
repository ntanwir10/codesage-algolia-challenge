#!/usr/bin/env python3
"""
Comprehensive Pipeline Test for CodeSage
Tests: GitHub API → Code Parser → Algolia Indexing → MCP Tools

This script tests the complete end-to-end pipeline to ensure all components work together.
"""

import asyncio
import sys
import time
from typing import Dict, Any

# Add app to path for imports
sys.path.insert(0, "/Users/ntanwir/Developer/codesage-algolia-challenge/backend")

from app.core.database import SessionLocal, engine, Base
from app.services.github_service import GitHubService
from app.services.code_parser import CodeParser
from app.services.algolia_service import AlgoliaService
from app.services.ai_service import MCPToolsService
from app.services.repository_service import RepositoryService
from app.services.performance_monitor import performance_monitor
from app.models.repository import Repository
from app.schemas.repository import RepositoryCreate
import structlog

# Set up logging
logger = structlog.get_logger()


class PipelineTest:
    """Comprehensive pipeline testing suite"""

    def __init__(self):
        self.db = SessionLocal()
        self.results = {
            "github_test": False,
            "parser_test": False,
            "algolia_test": False,
            "mcp_test": False,
            "integration_test": False,
            "performance_test": False,
            "errors": [],
        }

    async def cleanup(self):
        """Cleanup test data and connections"""
        try:
            # Clean up test repositories
            test_repos = (
                self.db.query(Repository).filter(Repository.name.like("test-%")).all()
            )

            for repo in test_repos:
                self.db.delete(repo)
            self.db.commit()

            self.db.close()
            logger.info("🧹 Cleanup completed")

        except Exception as e:
            logger.error(f"Cleanup failed: {e}")

    async def test_github_integration(self) -> bool:
        """Test GitHub API integration"""
        logger.info("🐙 Testing GitHub Integration...")

        try:
            async with performance_monitor.monitor_operation("github_test") as metrics:
                github_service = GitHubService()

                # Test with a small, known repository
                test_url = "https://github.com/octocat/Hello-World"

                logger.info(f"Fetching files from {test_url}")
                files = await github_service.get_repository_files(test_url)

                metrics.items_processed = len(files)

                if not files:
                    self.results["errors"].append("GitHub: No files retrieved")
                    return False

                logger.info(f"✅ GitHub: Retrieved {len(files)} files")

                # Test file content
                has_content = any(f.content for f in files if f.language != "text")
                if not has_content:
                    self.results["errors"].append("GitHub: No file content retrieved")
                    return False

                logger.info("✅ GitHub: File content retrieved successfully")
                return True

        except Exception as e:
            error_msg = f"GitHub integration failed: {str(e)}"
            logger.error(error_msg)
            self.results["errors"].append(error_msg)
            return False

    async def test_code_parser(self) -> bool:
        """Test code parsing functionality"""
        logger.info("🔍 Testing Code Parser...")

        try:
            async with performance_monitor.monitor_operation("parser_test") as metrics:
                parser = CodeParser()

                # Test with sample code
                test_files = [
                    {
                        "path": "test.py",
                        "content": '''
def hello_world():
    """Say hello to the world"""
    print("Hello, World!")

class TestClass:
    def __init__(self):
        self.value = 42
                        ''',
                        "language": "python",
                    },
                    {
                        "path": "test.js",
                        "content": """
function greet(name) {
    return `Hello, ${name}!`;
}

class Calculator {
    add(a, b) {
        return a + b;
    }
}
                        """,
                        "language": "javascript",
                    },
                ]

                total_entities = 0

                for test_file in test_files:
                    entities = await parser.extract_entities(
                        test_file["path"], test_file["content"], test_file["language"]
                    )

                    total_entities += len(entities)

                    if not entities:
                        self.results["errors"].append(
                            f"Parser: No entities found in {test_file['path']}"
                        )
                        return False

                    logger.info(
                        f"✅ Parser: {len(entities)} entities found in {test_file['path']}"
                    )

                metrics.items_processed = total_entities
                logger.info(
                    f"✅ Code Parser: Total {total_entities} entities extracted"
                )
                return True

        except Exception as e:
            error_msg = f"Code parser failed: {str(e)}"
            logger.error(error_msg)
            self.results["errors"].append(error_msg)
            return False

    async def test_algolia_integration(self) -> bool:
        """Test Algolia indexing"""
        logger.info("🔍 Testing Algolia Integration...")

        try:
            async with performance_monitor.monitor_operation("algolia_test") as metrics:
                algolia_service = AlgoliaService()

                # Test connection
                if not algolia_service.client:
                    self.results["errors"].append("Algolia: Client not initialized")
                    return False

                # Test search (should work even with empty index)
                search_results = await algolia_service.search_code("function")
                logger.info(
                    f"✅ Algolia: Search test completed ({len(search_results.get('hits', []))} results)"
                )

                # Test health check
                is_healthy = await algolia_service.health_check()
                if not is_healthy:
                    self.results["errors"].append("Algolia: Health check failed")
                    return False

                logger.info("✅ Algolia: Health check passed")
                metrics.items_processed = len(search_results.get("hits", []))
                return True

        except Exception as e:
            error_msg = f"Algolia integration failed: {str(e)}"
            logger.error(error_msg)
            self.results["errors"].append(error_msg)
            return False

    async def test_mcp_tools(self) -> bool:
        """Test MCP tools functionality"""
        logger.info("🛠️  Testing MCP Tools...")

        try:
            async with performance_monitor.monitor_operation("mcp_test") as metrics:
                mcp_service = MCPToolsService(self.db)

                # Test each MCP tool
                tools_to_test = [
                    ("search_code", {"query": "function"}),
                    ("analyze_repository", {"repository": "test-repo"}),
                    ("explore_functions", {"query": "hello"}),
                    ("explain_code", {"code": "def hello(): pass"}),
                    ("find_patterns", {"pattern": "class"}),
                ]

                successful_tools = 0

                for tool_name, args in tools_to_test:
                    try:
                        result = await getattr(mcp_service, tool_name)(**args)
                        if result and result.get("status") != "error":
                            successful_tools += 1
                            logger.info(f"✅ MCP Tool '{tool_name}' working")
                        else:
                            logger.warning(
                                f"⚠️ MCP Tool '{tool_name}' returned empty/error result"
                            )
                    except Exception as tool_error:
                        logger.warning(f"⚠️ MCP Tool '{tool_name}' failed: {tool_error}")

                metrics.items_processed = successful_tools

                if successful_tools == 0:
                    self.results["errors"].append("MCP: No tools are working")
                    return False

                logger.info(
                    f"✅ MCP Tools: {successful_tools}/{len(tools_to_test)} tools working"
                )
                return True

        except Exception as e:
            error_msg = f"MCP tools test failed: {str(e)}"
            logger.error(error_msg)
            self.results["errors"].append(error_msg)
            return False

    async def test_integration_pipeline(self) -> bool:
        """Test complete integration pipeline"""
        logger.info("🔄 Testing Complete Integration Pipeline...")

        try:
            async with performance_monitor.monitor_operation(
                "integration_test", {"test_repo": "hello-world"}
            ) as metrics:

                # Create repository service
                repo_service = RepositoryService(self.db)

                # Create test repository entry
                repo_data = RepositoryCreate(
                    name="test-integration-repo",
                    url="https://github.com/octocat/Hello-World",
                    description="Integration test repository",
                )

                # Test repository creation and processing
                repository = await repo_service.create_repository(repo_data)

                if not repository:
                    self.results["errors"].append(
                        "Integration: Repository creation failed"
                    )
                    return False

                logger.info(
                    f"✅ Integration: Repository created with ID {repository.id}"
                )

                # Wait a moment for any background processing
                await asyncio.sleep(2)

                # Verify repository in database
                db_repo = (
                    self.db.query(Repository)
                    .filter(Repository.id == repository.id)
                    .first()
                )
                if not db_repo:
                    self.results["errors"].append(
                        "Integration: Repository not found in database"
                    )
                    return False

                logger.info(f"✅ Integration: Repository verified in database")
                metrics.items_processed = 1

                return True

        except Exception as e:
            error_msg = f"Integration pipeline failed: {str(e)}"
            logger.error(error_msg)
            self.results["errors"].append(error_msg)
            return False

    async def test_performance_monitoring(self) -> bool:
        """Test performance monitoring system"""
        logger.info("📊 Testing Performance Monitoring...")

        try:
            # Get performance report
            report = performance_monitor.get_performance_report()

            if not report:
                self.results["errors"].append("Performance: No report generated")
                return False

            # Check if we have operation data from previous tests
            if report.get("total_operations", 0) == 0:
                logger.warning("⚠️ Performance: No operations recorded yet")
            else:
                logger.info(
                    f"✅ Performance: {report['total_operations']} operations recorded"
                )

            # Test system metrics
            system_metrics = performance_monitor.get_system_metrics()
            if not system_metrics:
                self.results["errors"].append(
                    "Performance: No system metrics available"
                )
                return False

            logger.info("✅ Performance: System metrics available")
            logger.info(f"   CPU: {system_metrics.get('cpu_percent', 0):.1f}%")
            logger.info(
                f"   Memory: {system_metrics.get('memory', {}).get('used_percent', 0):.1f}%"
            )
            logger.info(
                f"   Process Memory: {system_metrics.get('process', {}).get('memory_mb', 0):.1f}MB"
            )

            return True

        except Exception as e:
            error_msg = f"Performance monitoring test failed: {str(e)}"
            logger.error(error_msg)
            self.results["errors"].append(error_msg)
            return False

    async def run_all_tests(self) -> Dict[str, Any]:
        """Run all pipeline tests"""
        logger.info("🚀 Starting CodeSage Pipeline Tests...")
        start_time = time.time()

        try:
            # Initialize database
            Base.metadata.create_all(bind=engine)

            # Run individual tests
            self.results["github_test"] = await self.test_github_integration()
            self.results["parser_test"] = await self.test_code_parser()
            self.results["algolia_test"] = await self.test_algolia_integration()
            self.results["mcp_test"] = await self.test_mcp_tools()
            self.results["integration_test"] = await self.test_integration_pipeline()
            self.results["performance_test"] = await self.test_performance_monitoring()

            # Calculate overall results
            total_tests = 6
            passed_tests = sum(1 for test in self.results.values() if test is True)

            test_duration = time.time() - start_time

            # Generate final report
            report = {
                "timestamp": time.time(),
                "duration_seconds": test_duration,
                "total_tests": total_tests,
                "passed_tests": passed_tests,
                "failed_tests": total_tests - passed_tests,
                "success_rate": (passed_tests / total_tests) * 100,
                "test_results": self.results,
                "performance_summary": performance_monitor.get_performance_report(),
                "overall_status": "PASS" if passed_tests == total_tests else "FAIL",
            }

            return report

        finally:
            await self.cleanup()

    def print_results(self, report: Dict[str, Any]):
        """Print formatted test results"""
        print("\n" + "=" * 80)
        print("🧪 CODESAGE PIPELINE TEST RESULTS")
        print("=" * 80)

        print(f"📊 Overall Status: {report['overall_status']}")
        print(f"⏱️  Duration: {report['duration_seconds']:.2f} seconds")
        print(
            f"✅ Passed: {report['passed_tests']}/{report['total_tests']} ({report['success_rate']:.1f}%)"
        )

        print("\n📋 Individual Test Results:")
        for test_name, result in report["test_results"].items():
            if isinstance(result, bool):
                status = "✅ PASS" if result else "❌ FAIL"
                print(f"   {test_name:<20}: {status}")

        if report["test_results"]["errors"]:
            print("\n❌ Errors Encountered:")
            for error in report["test_results"]["errors"]:
                print(f"   • {error}")

        print("\n📈 Performance Summary:")
        perf = report["performance_summary"]
        print(f"   Total Operations: {perf.get('total_operations', 0)}")
        print(f"   Active Operations: {perf.get('active_operations', 0)}")

        if perf.get("operations_summary"):
            print("   Operation Stats:")
            for op_name, stats in perf["operations_summary"].items():
                if stats.get("count", 0) > 0:
                    print(
                        f"     {op_name}: {stats['count']} ops, {stats.get('success_rate', 0):.1f}% success"
                    )

        print("\n" + "=" * 80)

        if report["overall_status"] == "PASS":
            print("🎉 ALL TESTS PASSED! CodeSage pipeline is working correctly.")
        else:
            print("⚠️  SOME TESTS FAILED. Please check the errors above.")

        print("=" * 80)


async def main():
    """Main test execution"""
    tester = PipelineTest()

    try:
        report = await tester.run_all_tests()
        tester.print_results(report)

        # Exit with appropriate code
        exit_code = 0 if report["overall_status"] == "PASS" else 1
        sys.exit(exit_code)

    except KeyboardInterrupt:
        print("\n⏹️  Tests interrupted by user")
        await tester.cleanup()
        sys.exit(1)

    except Exception as e:
        print(f"\n💥 Test execution failed: {e}")
        await tester.cleanup()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
