#!/usr/bin/env python3
"""
Focused MCP Protocol Endpoint Testing
Tests the core Model Context Protocol endpoints for compliance and functionality.
"""

import requests
import json
import time
from typing import Dict, List, Any


class MCPProtocolTester:
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

    def test_mcp_capabilities(self):
        """Test MCP server capabilities endpoint"""
        self.log("=== Testing MCP Capabilities ===", "INFO")

        response = self.session.get(f"{self.base_url}/api/v1/ai/mcp/capabilities")

        if response.status_code == 200:
            capabilities = response.json()
            self.log(f"✅ Capabilities Retrieved: {response.status_code}", "SUCCESS")

            # Validate MCP capabilities structure
            required_fields = ["implementation", "capabilities", "server_info"]
            for field in required_fields:
                if field in capabilities:
                    self.log(f"  ✓ {field}: Present", "SUCCESS")
                else:
                    self.log(f"  ✗ {field}: Missing", "ERROR")

            # Show implementation details
            if "implementation" in capabilities:
                impl = capabilities["implementation"]
                self.log(
                    f"  Implementation: {impl.get('name')} v{impl.get('version')}",
                    "INFO",
                )

            # Show capabilities
            if "capabilities" in capabilities:
                caps = capabilities["capabilities"]
                self.log(f"  Tools Enabled: {caps.get('tools', False)}", "INFO")
                self.log(f"  Resources Enabled: {caps.get('resources', False)}", "INFO")
                self.log(f"  Prompts Enabled: {caps.get('prompts', False)}", "INFO")

            return capabilities
        else:
            self.log(f"❌ Capabilities Failed: {response.status_code}", "ERROR")
            return None

    def test_mcp_tools(self):
        """Test MCP tools listing endpoint"""
        self.log("\n=== Testing MCP Tools ===", "INFO")

        response = self.session.get(f"{self.base_url}/api/v1/ai/mcp/tools")

        if response.status_code == 200:
            tools_data = response.json()
            self.log(f"✅ Tools Retrieved: {response.status_code}", "SUCCESS")

            if "tools" in tools_data:
                tools = tools_data["tools"]
                self.log(f"  Available Tools: {len(tools)}", "INFO")

                for i, tool in enumerate(tools, 1):
                    if isinstance(tool, dict):
                        name = tool.get("name", "Unknown")
                        description = tool.get("description", "No description")[:50]
                        self.log(f"  {i}. {name}: {description}...", "INFO")
                    else:
                        self.log(f"  {i}. {tool}", "INFO")

            return tools_data
        else:
            self.log(f"❌ Tools Failed: {response.status_code}", "ERROR")
            return None

    def test_mcp_tool_execution(self):
        """Test MCP tool execution endpoint"""
        self.log("\n=== Testing MCP Tool Execution ===", "INFO")

        # Test valid tool call
        tool_request = {
            "tool_name": "search_code",
            "arguments": {"query": "authentication function", "language": "python"},
        }

        start_time = time.time()
        response = self.session.post(
            f"{self.base_url}/api/v1/ai/mcp/tools/call", json=tool_request
        )
        execution_time = time.time() - start_time

        if response.status_code == 200:
            result = response.json()
            self.log(f"✅ Tool Execution Success: {response.status_code}", "SUCCESS")
            self.log(f"  Tool: {result.get('tool')}", "INFO")
            self.log(f"  Success: {result.get('success')}", "INFO")
            self.log(f"  Execution Time: {execution_time:.3f}s", "INFO")

            if "result" in result:
                tool_result = result["result"]
                if isinstance(tool_result, dict):
                    self.log(f"  Result Keys: {list(tool_result.keys())}", "INFO")
                    if "total_hits" in tool_result:
                        self.log(
                            f"  Search Results: {tool_result.get('total_hits')} hits",
                            "INFO",
                        )
        else:
            self.log(f"❌ Tool Execution Failed: {response.status_code}", "ERROR")

        # Test invalid tool call (should return 400)
        invalid_request = {"tool_name": "nonexistent_tool", "arguments": {}}

        response = self.session.post(
            f"{self.base_url}/api/v1/ai/mcp/tools/call", json=invalid_request
        )

        if response.status_code == 400:
            self.log("✅ Invalid Tool Properly Rejected: 400", "SUCCESS")
        else:
            self.log(
                f"❌ Invalid Tool Should Return 400, Got: {response.status_code}",
                "ERROR",
            )

    def test_mcp_resources(self):
        """Test MCP resources endpoint"""
        self.log("\n=== Testing MCP Resources ===", "INFO")

        response = self.session.get(f"{self.base_url}/api/v1/ai/mcp/resources")

        if response.status_code == 200:
            resources_data = response.json()
            self.log(f"✅ Resources Retrieved: {response.status_code}", "SUCCESS")

            if "resources" in resources_data:
                resources = resources_data["resources"]
                self.log(f"  Available Resources: {len(resources)}", "INFO")

                for i, resource in enumerate(resources, 1):
                    if isinstance(resource, dict):
                        uri = resource.get("uri", "Unknown")
                        name = resource.get("name", "Unknown")
                        self.log(f"  {i}. {name}: {uri}", "INFO")
                    else:
                        self.log(f"  {i}. {resource}", "INFO")

            return resources_data
        else:
            self.log(f"❌ Resources Failed: {response.status_code}", "ERROR")
            return None

    def test_mcp_resource_reading(self):
        """Test MCP resource reading endpoint"""
        self.log("\n=== Testing MCP Resource Reading ===", "INFO")

        # Test valid resource URI
        test_uri = "codesage://repositories"
        response = self.session.get(
            f"{self.base_url}/api/v1/ai/mcp/resources/read?uri={test_uri}"
        )

        if response.status_code == 200:
            resource_data = response.json()
            self.log(f"✅ Resource Read Success: {response.status_code}", "SUCCESS")
            self.log(f"  URI: {test_uri}", "INFO")

            if isinstance(resource_data, dict):
                self.log(f"  Response Keys: {list(resource_data.keys())}", "INFO")
                if "data" in resource_data:
                    data = resource_data["data"]
                    if isinstance(data, list):
                        self.log(f"  Data Items: {len(data)}", "INFO")
        else:
            self.log(f"❌ Resource Read Failed: {response.status_code}", "ERROR")

        # Test invalid resource URI (should return 400)
        invalid_uri = "invalid://resource"
        response = self.session.get(
            f"{self.base_url}/api/v1/ai/mcp/resources/read?uri={invalid_uri}"
        )

        if response.status_code == 400:
            self.log("✅ Invalid URI Properly Rejected: 400", "SUCCESS")
        else:
            self.log(
                f"❌ Invalid URI Should Return 400, Got: {response.status_code}",
                "ERROR",
            )

    def test_mcp_protocol_compliance(self):
        """Test overall MCP protocol compliance"""
        self.log("\n=== Testing MCP Protocol Compliance ===", "INFO")

        # Test required MCP endpoints
        endpoints = [
            ("/api/v1/ai/mcp/capabilities", "GET", "MCP Capabilities"),
            ("/api/v1/ai/mcp/tools", "GET", "MCP Tools"),
            ("/api/v1/ai/mcp/resources", "GET", "MCP Resources"),
        ]

        compliance_score = 0
        total_checks = len(endpoints)

        for endpoint, method, name in endpoints:
            if method == "GET":
                response = self.session.get(f"{self.base_url}{endpoint}")
            else:
                response = self.session.post(f"{self.base_url}{endpoint}")

            if response.status_code == 200:
                compliance_score += 1
                self.log(f"  ✅ {name}: Compliant", "SUCCESS")
            else:
                self.log(f"  ❌ {name}: Failed ({response.status_code})", "ERROR")

        # Additional compliance checks
        additional_checks = [
            ("Tool Execution", "POST", "/api/v1/ai/mcp/tools/call"),
            ("Resource Reading", "GET", "/api/v1/ai/mcp/resources/read"),
        ]

        # Test tool execution compliance
        tool_request = {"tool_name": "search_code", "arguments": {"query": "test"}}
        response = self.session.post(
            f"{self.base_url}/api/v1/ai/mcp/tools/call", json=tool_request
        )
        if response.status_code == 200:
            compliance_score += 1
            self.log("  ✅ Tool Execution: Compliant", "SUCCESS")
        else:
            self.log(f"  ❌ Tool Execution: Failed ({response.status_code})", "ERROR")

        total_checks += 1

        # Test resource reading compliance
        response = self.session.get(
            f"{self.base_url}/api/v1/ai/mcp/resources/read?uri=codesage://repositories"
        )
        if response.status_code == 200:
            compliance_score += 1
            self.log("  ✅ Resource Reading: Compliant", "SUCCESS")
        else:
            self.log(f"  ❌ Resource Reading: Failed ({response.status_code})", "ERROR")

        total_checks += 1

        compliance_percentage = (compliance_score / total_checks) * 100
        self.log(
            f"\n🎯 MCP Compliance Score: {compliance_score}/{total_checks} ({compliance_percentage:.1f}%)",
            "SUCCESS" if compliance_percentage >= 80 else "WARNING",
        )

        return compliance_percentage

    def run_mcp_protocol_tests(self):
        """Run all MCP protocol tests"""
        start_time = time.time()

        self.log("🚀 Starting MCP Protocol Compliance Testing", "INFO")
        self.log(f"Target: {self.base_url}", "INFO")
        self.log("=" * 60, "INFO")

        # Run individual tests
        capabilities = self.test_mcp_capabilities()
        tools = self.test_mcp_tools()
        self.test_mcp_tool_execution()
        resources = self.test_mcp_resources()
        self.test_mcp_resource_reading()
        compliance_score = self.test_mcp_protocol_compliance()

        # Generate summary
        total_time = time.time() - start_time

        self.log("\n" + "=" * 60, "INFO")
        self.log("📊 MCP PROTOCOL TEST SUMMARY", "INFO")
        self.log("=" * 60, "INFO")

        self.log(f"🕐 Total Test Time: {total_time:.2f}s", "INFO")
        self.log(
            f"🎯 Compliance Score: {compliance_score:.1f}%",
            "SUCCESS" if compliance_score >= 90 else "WARNING",
        )

        # Show capabilities summary
        if capabilities:
            impl = capabilities.get("implementation", {})
            self.log(
                f"🏷️  Server: {impl.get('name', 'Unknown')} v{impl.get('version', 'Unknown')}",
                "INFO",
            )

        # Show tools summary
        if tools and "tools" in tools:
            tool_count = len(tools["tools"])
            self.log(f"🔧 Available Tools: {tool_count}", "INFO")

        # Show resources summary
        if resources and "resources" in resources:
            resource_count = len(resources["resources"])
            self.log(f"📁 Available Resources: {resource_count}", "INFO")

        # Final assessment
        if compliance_score >= 95:
            self.log("🏆 EXCELLENT: MCP Protocol Fully Compliant!", "SUCCESS")
        elif compliance_score >= 80:
            self.log("✅ GOOD: MCP Protocol Mostly Compliant", "SUCCESS")
        else:
            self.log("⚠️  WARNING: MCP Protocol Compliance Issues", "WARNING")

        self.log("=" * 60, "INFO")

        return compliance_score


if __name__ == "__main__":
    tester = MCPProtocolTester()
    tester.run_mcp_protocol_tests()
