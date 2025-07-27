#!/usr/bin/env python3
"""
MCP Wrapper for CodeSage - Bridges Claude Desktop to CodeSage MCP Server
This script implements the Model Context Protocol to connect Claude Desktop
to the CodeSage backend server with robust error handling and logging.
"""

import sys
import json
import asyncio
import aiohttp
import os
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime


class BackendHealthMonitor:
    """Monitor backend health and implement circuit breaker pattern"""

    def __init__(self, server_url: str):
        self.server_url = server_url
        self.consecutive_failures = 0
        self.last_failure_time = None
        self.circuit_open = False
        self.failure_threshold = 3
        self.recovery_timeout = 30  # seconds

    async def check_health(self, session: aiohttp.ClientSession) -> bool:
        """Check backend health with circuit breaker logic"""

        # If circuit is open, check if we should try to close it
        if self.circuit_open:
            if (
                datetime.now() - self.last_failure_time
            ).seconds < self.recovery_timeout:
                return False  # Still in recovery period
            else:
                # Try to close circuit
                self.circuit_open = False
                self.consecutive_failures = 0

        try:
            async with session.get(
                f"{self.server_url}/health", timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status == 200:
                    self.consecutive_failures = 0
                    self.circuit_open = False
                    return True
                else:
                    self._record_failure()
                    return False
        except Exception:
            self._record_failure()
            return False

    def _record_failure(self):
        """Record a health check failure"""
        self.consecutive_failures += 1
        self.last_failure_time = datetime.now()

        if self.consecutive_failures >= self.failure_threshold:
            self.circuit_open = True

    def is_healthy(self) -> bool:
        """Check if backend is considered healthy"""
        return not self.circuit_open


class CodeSageMCPClient:
    def __init__(self):
        self.server_url = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8001")
        self.session = None
        self.tools_cache = None
        self.tools_cache_time = None
        self.cache_ttl = 300  # 5 minutes
        self.health_monitor = BackendHealthMonitor(self.server_url)

        # Setup logging
        self.setup_logging()
        self.logger.info(
            f"Initializing CodeSage MCP Client with server URL: {self.server_url}"
        )

    def setup_logging(self):
        """Setup logging to file for debugging"""
        log_file = os.path.join(os.path.dirname(__file__), "mcp_wrapper.log")
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[logging.FileHandler(log_file), logging.StreamHandler(sys.stderr)],
        )
        self.logger = logging.getLogger(__name__)

    async def initialize(self):
        """Initialize the MCP client with timeout and error handling"""
        try:
            # Use more robust session configuration with longer timeouts
            timeout = aiohttp.ClientTimeout(total=60, connect=10, sock_read=30)
            connector = aiohttp.TCPConnector(
                limit=10,  # Limit concurrent connections
                limit_per_host=5,  # Limit per host
                ttl_dns_cache=300,  # DNS cache TTL
                use_dns_cache=True,
            )
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                headers={"User-Agent": "CodeSage-MCP-Client/1.0.0"},
                connector=connector,
            )

            # Test connection to backend with health monitor
            is_healthy = await self.health_monitor.check_health(self.session)
            if is_healthy:
                self.logger.info(
                    "MCP client initialized successfully - backend healthy"
                )
            else:
                self.logger.warning("MCP client initialized - backend may have issues")

        except Exception as e:
            self.logger.error(f"Failed to initialize MCP client: {str(e)}")
            raise

    async def get_tools_from_backend(self) -> List[Dict[str, Any]]:
        """Get tools with proper schemas from the backend server"""
        try:
            # Check cache first
            if self.tools_cache and self.tools_cache_time:
                if (datetime.now() - self.tools_cache_time).seconds < self.cache_ttl:
                    return self.tools_cache

            # Check backend health before making request
            if not await self.health_monitor.check_health(self.session):
                self.logger.warning("Backend unhealthy, using fallback tools")
                return self._get_fallback_tools()

            async with self.session.get(
                f"{self.server_url}/api/v1/ai/mcp/tools"
            ) as resp:
                if resp.status == 200:
                    tools_data = await resp.json()
                    self.tools_cache = tools_data.get("tools", [])
                    self.tools_cache_time = datetime.now()
                    self.logger.info(
                        f"Retrieved {len(self.tools_cache)} tools from backend"
                    )
                    return self.tools_cache
                else:
                    self.logger.error(
                        f"Failed to get tools from backend: HTTP {resp.status}"
                    )
                    return self._get_fallback_tools()

        except Exception as e:
            self.logger.error(f"Error fetching tools from backend: {str(e)}")
            return self._get_fallback_tools()

    async def handle_tools_list(self, request_id=None):
        """Get available tools from CodeSage server with proper schemas"""
        try:
            backend_tools = await self.get_tools_from_backend()

            if backend_tools:
                # Use tools from backend with their proper schemas
                tools = backend_tools
            else:
                # Fallback to simplified tools if backend is unavailable
                self.logger.warning("Using fallback tool definitions")
                tools = self._get_fallback_tools()

            response = {"jsonrpc": "2.0", "result": {"tools": tools}}
            if request_id is not None:
                response["id"] = request_id

            self.send_response(response)
            self.logger.info(f"Listed {len(tools)} tools successfully")

        except Exception as e:
            self.logger.error(f"Error in handle_tools_list: {str(e)}")
            self.send_error(f"Failed to list tools: {str(e)}", request_id)

    def _get_fallback_tools(self) -> List[Dict[str, Any]]:
        """Fallback tool definitions when backend is unavailable"""
        return [
            {
                "name": "search_code",
                "description": "Search code using natural language queries",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural language search query",
                        },
                        "repository": {
                            "type": "string",
                            "description": "Optional repository filter",
                        },
                        "language": {
                            "type": "string",
                            "description": "Optional programming language filter",
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "analyze_repository",
                "description": "Analyze repository structure and patterns",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "repository_id": {
                            "type": "string",
                            "description": "Repository ID to analyze",
                        },
                        "analysis_type": {
                            "type": "string",
                            "description": "Type of analysis (overview, security, complexity)",
                        },
                    },
                    "required": ["repository_id"],
                },
            },
        ]

    async def handle_tool_call(
        self, tool_name: str, arguments: Dict[str, Any], request_id=None
    ):
        """Execute a tool call with enhanced error handling and circuit breaker"""
        try:
            self.logger.info(f"Executing tool call: {tool_name} with args: {arguments}")

            # Check circuit breaker before attempting call
            if not self.health_monitor.is_healthy():
                self.logger.warning("Circuit breaker open - backend unavailable")
                self.send_error(
                    f"Backend temporarily unavailable. Tool '{tool_name}' cannot be executed right now. Please try again in a few moments.",
                    request_id,
                )
                return

            payload = {"tool_name": tool_name, "arguments": arguments}

            # Enhanced retry logic with exponential backoff
            max_retries = 3
            base_delay = 1

            for attempt in range(max_retries + 1):
                try:
                    # Use longer timeout for tool calls
                    async with self.session.post(
                        f"{self.server_url}/api/v1/ai/mcp/tools/call",
                        json=payload,
                        headers={"Content-Type": "application/json"},
                        timeout=aiohttp.ClientTimeout(total=45),  # Longer timeout
                    ) as resp:
                        if resp.status == 200:
                            result = await resp.json()

                            # Format response according to MCP protocol
                            mcp_response = {
                                "jsonrpc": "2.0",
                                "result": {
                                    "content": [
                                        {
                                            "type": "text",
                                            "text": self._format_tool_result(
                                                result, tool_name
                                            ),
                                        }
                                    ]
                                },
                            }
                            if request_id is not None:
                                mcp_response["id"] = request_id

                            self.send_response(mcp_response)
                            self.logger.info(
                                f"Tool call {tool_name} completed successfully"
                            )
                            return

                        elif resp.status == 503:  # Service unavailable
                            if attempt < max_retries:
                                wait_time = base_delay * (2**attempt)
                                self.logger.warning(
                                    f"Backend service unavailable (503), retrying in {wait_time}s (attempt {attempt + 1}/{max_retries + 1})"
                                )
                                await asyncio.sleep(wait_time)
                                continue
                            else:
                                self.send_error(
                                    f"Backend service is temporarily overloaded. Tool '{tool_name}' cannot be executed right now. Please try again in a moment.",
                                    request_id,
                                )
                                return

                        elif resp.status == 429:  # Rate limited
                            if attempt < max_retries:
                                wait_time = base_delay * (2**attempt)
                                self.logger.warning(
                                    f"Rate limited, retrying in {wait_time}s"
                                )
                                await asyncio.sleep(wait_time)
                                continue
                            else:
                                self.send_error("Rate limit exceeded", request_id)
                                return
                        else:
                            error_text = await resp.text()
                            self.logger.error(
                                f"Tool execution failed: HTTP {resp.status}, {error_text}"
                            )
                            self.send_error(
                                f"Tool execution failed: HTTP {resp.status}", request_id
                            )
                            return

                except asyncio.TimeoutError:
                    if attempt < max_retries:
                        wait_time = base_delay * (2**attempt)
                        self.logger.warning(
                            f"Request timed out, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries + 1})"
                        )
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        self.send_error(
                            f"Tool '{tool_name}' execution timed out. The backend may be busy processing your request.",
                            request_id,
                        )
                        return

                except aiohttp.ClientError as e:
                    if attempt < max_retries:
                        wait_time = base_delay * (2**attempt)
                        self.logger.warning(
                            f"Connection error, retrying in {wait_time}s: {str(e)}"
                        )
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        self.send_error(
                            f"Connection error - backend may be temporarily unavailable: {str(e)}",
                            request_id,
                        )
                        return

        except Exception as e:
            self.logger.error(f"Error executing tool {tool_name}: {str(e)}")
            self.send_error(f"Unexpected error executing tool: {str(e)}", request_id)

    def _format_tool_result(self, result: Dict[str, Any], tool_name: str) -> str:
        """Format tool result for better readability"""
        if isinstance(result, dict) and "error" in result:
            return f"Error in {tool_name}: {result['error']}"

        if tool_name == "search_code":
            return self._format_search_result(result)
        elif tool_name == "analyze_repository":
            return self._format_analysis_result(result)
        else:
            return json.dumps(result, indent=2, ensure_ascii=False)

    def _format_search_result(self, result: Dict[str, Any]) -> str:
        """Format search results for better readability"""
        if not isinstance(result, dict):
            return str(result)

        formatted = []

        # Handle the nested result structure
        if "result" in result and "data" in result["result"]:
            data = result["result"]["data"]
            if "results" in data and "total_hits" in data:
                formatted.append(
                    f"Found {data['total_hits']} total matches, showing top results:"
                )
                for i, item in enumerate(data["results"][:5], 1):  # Limit to top 5
                    formatted.append(f"\n{i}. {item.get('entity_name', 'Unknown')}")
                    if item.get("file_path"):
                        formatted.append(f"   File: {item['file_path']}")
                    if item.get("description"):
                        formatted.append(
                            f"   Description: {item['description'][:100]}..."
                        )
                    if item.get("content"):
                        formatted.append(f"   Content: {item['content'][:80]}...")

        return "\n".join(formatted) if formatted else json.dumps(result, indent=2)

    def _format_analysis_result(self, result: Dict[str, Any]) -> str:
        """Format analysis results for better readability"""
        if not isinstance(result, dict):
            return str(result)

        formatted = []
        if "summary" in result:
            formatted.append(f"Repository Analysis Summary:")
            formatted.append(f"Name: {result['summary'].get('name', 'Unknown')}")
            formatted.append(
                f"Language: {result['summary'].get('language', 'Unknown')}"
            )
            formatted.append(f"Files: {result['summary'].get('total_files', 0)}")

        return "\n".join(formatted) if formatted else json.dumps(result, indent=2)

    def send_response(self, response: Dict[str, Any]):
        """Send a JSON-RPC response"""
        try:
            output = json.dumps(response, ensure_ascii=False)
            print(output)
            sys.stdout.flush()
        except Exception as e:
            self.logger.error(f"Error sending response: {str(e)}")

    def send_error(self, message: str, request_id=None):
        """Send an error response"""
        response = {"jsonrpc": "2.0", "error": {"code": -1, "message": message}}
        if request_id is not None:
            response["id"] = request_id
        self.send_response(response)

    async def close(self):
        """Close the session"""
        if self.session:
            await self.session.close()
            self.logger.info("MCP client session closed")


async def main():
    """Main MCP server loop with improved error handling"""
    client = CodeSageMCPClient()

    try:
        await client.initialize()

        # Process stdin line by line
        for line in sys.stdin:
            try:
                line = line.strip()
                if not line:
                    continue

                # Parse JSON request
                try:
                    request = json.loads(line)
                except json.JSONDecodeError as e:
                    client.logger.error(f"Invalid JSON request: {str(e)}")
                    client.send_error(f"Invalid JSON request: {str(e)}", None)
                    continue

                method = request.get("method")
                params = request.get("params", {})
                request_id = request.get("id")

                # Validate required fields
                if not method:
                    client.send_error("Missing required 'method' field", request_id)
                    continue

                client.logger.debug(f"Processing method: {method}")

                if method == "initialize":
                    # Handle initialize method
                    response = {
                        "jsonrpc": "2.0",
                        "result": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {"tools": {}},
                            "serverInfo": {"name": "codesage", "version": "1.0.0"},
                        },
                    }
                    if request_id is not None:
                        response["id"] = request_id
                    client.send_response(response)

                elif method == "tools/list":
                    await client.handle_tools_list(request_id)

                elif method == "tools/call":
                    tool_name = params.get("name")
                    arguments = params.get("arguments", {})

                    if not tool_name:
                        client.send_error("Missing tool name", request_id)
                        continue

                    await client.handle_tool_call(tool_name, arguments, request_id)

                else:
                    client.send_error(f"Unknown method: {method}", request_id)

            except Exception as e:
                client.logger.error(f"Request processing error: {str(e)}")
                client.send_error(f"Request processing error: {str(e)}", None)
                break

    except Exception as e:
        client.logger.error(f"Fatal error in main loop: {str(e)}")
        print(
            f'{{"jsonrpc": "2.0", "error": {{"code": -32000, "message": "Fatal error: {str(e)}"}}}}',
            file=sys.stderr,
        )
    finally:
        await client.close()


if __name__ == "__main__":
    # Ensure we can import required modules
    try:
        import aiohttp
        import asyncio
    except ImportError as e:
        print(
            f'{{"jsonrpc": "2.0", "error": {{"code": -32001, "message": "Missing required dependency: {str(e)}"}}}}',
            file=sys.stderr,
        )
        sys.exit(1)

    asyncio.run(main())
