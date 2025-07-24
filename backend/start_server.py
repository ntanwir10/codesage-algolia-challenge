#!/usr/bin/env python3
"""
Simple startup script for CodeSage MCP Server
Ensures dependencies are met and starts server with proper error handling
"""

import os
import sys
import time
import subprocess
import requests
from pathlib import Path


def check_requirements():
    """Check if all requirements are installed"""
    try:
        import fastapi
        import uvicorn
        import sqlalchemy
        import structlog

        print("✅ All required packages found")
        return True
    except ImportError as e:
        print(f"❌ Missing required package: {e}")
        print("Run: pip install -r requirements.txt")
        return False


def check_database():
    """Check database connection"""
    try:
        from app.core.database import engine
        from sqlalchemy import text

        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("✅ Database connection successful")
        return True
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print("Make sure PostgreSQL is running and credentials are correct")
        return False


def check_env_vars():
    """Check essential environment variables"""
    required_vars = {
        "ALGOLIA_APP_ID": os.getenv("ALGOLIA_APP_ID"),
        "ALGOLIA_ADMIN_API_KEY": os.getenv("ALGOLIA_ADMIN_API_KEY"),
    }

    missing = [var for var, val in required_vars.items() if not val]

    if missing:
        print(f"⚠️  Missing environment variables: {missing}")
        print("Server will start but some features may not work properly")
    else:
        print("✅ Environment variables configured")

    return True


def start_server():
    """Start the uvicorn server"""
    print("\n🚀 Starting CodeSage MCP Server...")

    try:
        # Change to backend directory
        backend_dir = Path(__file__).parent
        os.chdir(backend_dir)

        # Start uvicorn with proper configuration
        cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8001",
            "--reload",
            "--log-level",
            "info",
        ]

        print(f"Running: {' '.join(cmd)}")
        process = subprocess.Popen(cmd)

        # Wait a moment for server to start
        time.sleep(3)

        # Check if server is responding
        try:
            response = requests.get("http://localhost:8001/health", timeout=5)
            if response.status_code == 200:
                print("✅ Server started successfully!")
                print("📊 Health check: http://localhost:8001/health")
                print("📚 API docs: http://localhost:8001/docs")
                print("🔌 WebSocket: ws://localhost:8001/ws")
                print("\nPress Ctrl+C to stop the server")
            else:
                print(
                    f"⚠️  Server started but health check failed: {response.status_code}"
                )
        except requests.RequestException:
            print("⚠️  Server starting, health check not yet available")

        # Wait for the process
        process.wait()

    except KeyboardInterrupt:
        print("\n🛑 Server shutdown requested")
        if "process" in locals():
            process.terminate()
            process.wait()
        print("✅ Server stopped")
    except Exception as e:
        print(f"❌ Failed to start server: {e}")
        return False

    return True


def main():
    """Main startup routine"""
    print("🧠 CodeSage MCP Server Startup")
    print("=" * 40)

    # Run all checks
    checks = [
        ("Requirements", check_requirements),
        ("Environment", check_env_vars),
        ("Database", check_database),
    ]

    for check_name, check_func in checks:
        print(f"\n🔍 Checking {check_name}...")
        if not check_func():
            print(f"\n❌ {check_name} check failed. Please fix the issues above.")
            return False

    print("\n✅ All checks passed!")
    return start_server()


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
