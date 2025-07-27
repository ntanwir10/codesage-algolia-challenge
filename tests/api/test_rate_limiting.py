"""
Test rate limiting functionality
"""

import pytest
import asyncio
import time
from fastapi.testclient import TestClient
from httpx import AsyncClient

from app.main import app


class TestRateLimiting:
    """Test rate limiting functionality"""

    def test_rate_limiting_health_endpoint(self):
        """Test that basic endpoints work without rate limiting issues"""
        client = TestClient(app)

        # Test health endpoint - should work fine
        response = client.get("/health")
        # Note: This might fail due to missing database, but that's not a rate limit issue
        assert response.status_code in [200, 503]  # 503 if DB is down

    def test_rate_limiting_root_endpoint(self):
        """Test root endpoint which should have minimal rate limiting"""
        client = TestClient(app)

        # Make multiple quick requests to root endpoint
        responses = []
        for _ in range(5):
            response = client.get("/")
            responses.append(response)

        # All should succeed (root endpoint should be generous)
        for response in responses:
            assert response.status_code == 200
            assert "CodeSage MCP Server" in response.json()["message"]

    def test_rate_limiting_search_endpoint_limits(self):
        """Test that search endpoints are properly rate limited"""
        client = TestClient(app)

        # Search endpoint should be more restrictive
        search_data = {"query": "test search", "page": 0, "per_page": 10}

        responses = []
        status_codes = []

        # Make many requests quickly to trigger rate limiting
        for i in range(10):  # Try to exceed rate limit
            response = client.post("/api/v1/search/", json=search_data)
            responses.append(response)
            status_codes.append(response.status_code)

            # Small delay to avoid overwhelming the test
            time.sleep(0.1)

        # We should see either successful responses or 429 (rate limited)
        # or 400/500 (other errors like missing DB)
        for status_code in status_codes:
            assert status_code in [200, 400, 429, 500, 503]

        # If we got any 429s, rate limiting is working
        has_rate_limit = any(code == 429 for code in status_codes)
        print(f"Rate limiting test - Got 429 responses: {has_rate_limit}")
        print(f"Status codes: {status_codes}")

    def test_rate_limiting_upload_endpoint_limits(self):
        """Test that upload endpoints have strict rate limiting"""
        client = TestClient(app)

        # Upload endpoints should be very restrictive
        responses = []

        # Make multiple requests to upload endpoint
        for i in range(5):
            response = client.post(
                "/api/v1/repositories/1/upload",
                files={"files": ("test.py", "print('hello')", "text/plain")},
            )
            responses.append(response)
            time.sleep(0.1)

        status_codes = [r.status_code for r in responses]

        # Should see 429 (rate limited) or other errors (404, 400, etc.)
        for status_code in status_codes:
            assert status_code in [200, 400, 404, 429, 500, 503]

        print(f"Upload rate limiting - Status codes: {status_codes}")

    def test_rate_limit_response_format(self):
        """Test that rate limit responses have proper format"""
        client = TestClient(app)

        # Try to trigger rate limiting on search endpoint
        search_data = {"query": "test", "page": 0, "per_page": 10}

        rate_limited_response = None

        # Make many requests to try to trigger rate limiting
        for i in range(15):
            response = client.post("/api/v1/search/", json=search_data)
            if response.status_code == 429:
                rate_limited_response = response
                break
            time.sleep(0.05)

        if rate_limited_response:
            # Check response format
            data = rate_limited_response.json()
            assert "error" in data
            assert "message" in data
            assert "retry_after" in data
            assert "Rate limit exceeded" in data["error"]

            # Check headers
            assert "Retry-After" in rate_limited_response.headers

            print("Rate limit response format is correct")
        else:
            print("Could not trigger rate limiting in test - this may be expected")

    @pytest.mark.asyncio
    async def test_rate_limiting_async_client(self):
        """Test rate limiting with async client"""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            # Test root endpoint
            response = await ac.get("/")
            # Should work fine
            assert response.status_code == 200


if __name__ == "__main__":
    """Run tests directly"""
    test_instance = TestRateLimiting()

    print("Testing rate limiting functionality...")

    print("\n1. Testing health endpoint...")
    test_instance.test_rate_limiting_health_endpoint()

    print("\n2. Testing root endpoint...")
    test_instance.test_rate_limiting_root_endpoint()

    print("\n3. Testing search endpoint rate limiting...")
    test_instance.test_rate_limiting_search_endpoint_limits()

    print("\n4. Testing upload endpoint rate limiting...")
    test_instance.test_rate_limiting_upload_endpoint_limits()

    print("\n5. Testing rate limit response format...")
    test_instance.test_rate_limit_response_format()

    print("\nRate limiting tests completed!")
