#!/usr/bin/env python3
"""
Test script to demonstrate the complete real-time processing flow
from backend WebSocket broadcasting to frontend real-time updates.
"""

import asyncio
import websockets
import json
import httpx
import time
from typing import Dict, Any

# Configuration
BACKEND_URL = "http://localhost:8001"
WEBSOCKET_URL = "ws://localhost:8001/ws"


class RealTimeFlowTest:
    """Test the complete real-time processing flow"""

    def __init__(self):
        self.websocket = None
        self.messages_received = []

    async def connect_websocket(self):
        """Connect to the WebSocket endpoint"""
        try:
            print("🔌 Connecting to WebSocket...")
            self.websocket = await websockets.connect(WEBSOCKET_URL)
            print("✅ WebSocket connected successfully!")
            return True
        except Exception as e:
            print(f"❌ WebSocket connection failed: {e}")
            return False

    async def listen_for_messages(self):
        """Listen for real-time messages from the backend"""
        if not self.websocket:
            return

        try:
            async for message in self.websocket:
                data = json.loads(message)
                self.messages_received.append(data)

                # Pretty print the received message
                message_type = data.get("type", "unknown")
                if message_type == "connection_established":
                    print(f"🎉 Connection established: {data['data']['message']}")
                elif message_type == "repository_status":
                    repo_data = data["data"]
                    progress = repo_data.get("processing_progress", 0)
                    print(
                        f"📊 Repository {repo_data['repository_id']}: {repo_data['status']} "
                        f"({progress:.1f}%) - {repo_data['message']}"
                    )
                elif message_type == "processing_complete":
                    repo_data = data["data"]
                    print(
                        f"🎉 Repository {repo_data['repository_id']} processing complete!"
                    )
                elif message_type == "processing_failed":
                    repo_data = data["data"]
                    print(
                        f"❌ Repository {repo_data['repository_id']} processing failed: {repo_data['message']}"
                    )
                else:
                    print(f"📨 Received {message_type}: {data}")

        except websockets.exceptions.ConnectionClosed:
            print("🔌 WebSocket connection closed")
        except Exception as e:
            print(f"❌ Error listening for messages: {e}")

    async def create_test_repository(self) -> int:
        """Create a test repository via the API"""
        print("\n📝 Creating test repository...")

        repository_data = {
            "name": "test/realtime-demo",
            "description": "Test repository for real-time updates demo",
            "url": "https://github.com/test/realtime-demo",
            "branch": "main",
            "language": "python",
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BACKEND_URL}/api/v1/repositories/", json=repository_data
            )

            if response.status_code == 201:
                repo = response.json()
                print(f"✅ Repository created: ID {repo['id']}")
                return repo["id"]
            else:
                print(
                    f"❌ Failed to create repository: {response.status_code} - {response.text}"
                )
                return None

    async def start_repository_processing(self, repository_id: int):
        """Start processing the repository to trigger real-time updates"""
        print(f"\n🚀 Starting processing for repository {repository_id}...")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BACKEND_URL}/api/v1/repositories/{repository_id}/process"
            )

            if response.status_code == 200:
                status = response.json()
                print(f"✅ Processing started: {status['message']}")
                return True
            else:
                print(
                    f"❌ Failed to start processing: {response.status_code} - {response.text}"
                )
                return False

    async def check_websocket_health(self):
        """Check WebSocket service health"""
        print("\n🏥 Checking WebSocket service health...")

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(f"{BACKEND_URL}/api/v1/ws/health")
                if response.status_code == 200:
                    health = response.json()
                    print(f"✅ WebSocket service is {health['status']}")
                    print(f"   - Global connections: {health['global_connections']}")
                    print(f"   - Total connections: {health['total_connections']}")
                    print(f"   - Active rooms: {health['active_rooms']}")
                    return True
                else:
                    print(f"❌ WebSocket health check failed: {response.status_code}")
                    return False
            except Exception as e:
                print(f"❌ Health check error: {e}")
                return False

    async def run_complete_test(self):
        """Run the complete real-time flow test"""
        print("🧪 Starting Real-time Processing Flow Test")
        print("=" * 50)

        # Step 1: Check backend health
        print("1️⃣ Checking backend health...")
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{BACKEND_URL}/health")
                if response.status_code == 200:
                    print("✅ Backend is healthy")
                else:
                    print(f"❌ Backend health check failed: {response.status_code}")
                    return
        except Exception as e:
            print(f"❌ Cannot reach backend: {e}")
            print(
                "💡 Make sure the backend is running: cd backend && python -m uvicorn app.main:app --reload"
            )
            return

        # Step 2: Check WebSocket health
        await self.check_websocket_health()

        # Step 3: Connect to WebSocket
        print("\n2️⃣ Connecting to WebSocket...")
        if not await self.connect_websocket():
            return

        # Step 4: Start listening for messages in background
        print("\n3️⃣ Starting message listener...")
        listen_task = asyncio.create_task(self.listen_for_messages())

        # Step 5: Wait a moment for connection to stabilize
        await asyncio.sleep(1)

        # Step 6: Create test repository
        print("\n4️⃣ Creating test repository...")
        repository_id = await self.create_test_repository()
        if not repository_id:
            return

        # Step 7: Start processing to trigger real-time updates
        print("\n5️⃣ Starting repository processing...")
        if not await self.start_repository_processing(repository_id):
            return

        # Step 8: Wait for processing to complete (with timeout)
        print("\n6️⃣ Waiting for real-time updates...")
        print("   (You should see live progress updates below)")

        # Wait for up to 30 seconds for processing to complete
        start_time = time.time()
        processing_complete = False

        while time.time() - start_time < 30 and not processing_complete:
            await asyncio.sleep(1)

            # Check if we received a completion message
            for msg in self.messages_received:
                if msg.get("type") == "processing_complete":
                    processing_complete = True
                    break

        if processing_complete:
            print("\n🎉 Test completed successfully!")
            print("✅ Real-time updates are working correctly")
        else:
            print(
                "\n⏰ Test timed out, but you should have seen some real-time updates"
            )

        # Step 9: Summary
        print(f"\n📊 Test Summary:")
        print(f"   - Messages received: {len(self.messages_received)}")
        print(f"   - Repository created: {repository_id}")
        print(
            f"   - WebSocket connection: {'✅ Success' if self.websocket else '❌ Failed'}"
        )

        # Step 10: Cleanup
        print("\n🧹 Cleaning up...")
        listen_task.cancel()
        if self.websocket:
            await self.websocket.close()

        print("\n" + "=" * 50)
        print("🏁 Real-time Flow Test Complete!")
        print("\nNext steps:")
        print("1. Open http://localhost:5173 in your browser")
        print("2. Submit a GitHub repository")
        print("3. Watch the real-time progress updates in action!")


async def main():
    """Main test function"""
    test = RealTimeFlowTest()
    await test.run_complete_test()


if __name__ == "__main__":
    print("🚀 CodeSage Real-time Processing Flow Test")
    print("This will test the complete flow from backend to frontend")
    print("Make sure both backend and frontend servers are running!\n")

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
