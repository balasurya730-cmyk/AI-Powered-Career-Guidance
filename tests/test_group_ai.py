import requests
import json
import websockets
import asyncio
import time
import string
import random

BASE_URL = "http://localhost:8000"

async def test_group_ai():
    # 1. Register a user
    email = f"user_{''.join(random.choices(string.ascii_lowercase, k=6))}@test.com"
    pw = "password123"
    r = requests.post(f"{BASE_URL}/api/register", json={"name": "Test User", "email": email, "password": pw})
    if r.status_code != 200:
        print("Register failed:", r.text)
        return
    token = r.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Create a group
    r = requests.post(f"{BASE_URL}/api/groups", headers=headers, json={"name": "Test Group", "description": ""})
    if r.status_code != 200:
        print("Create group failed:", r.text)
        return
    group_id = r.json()["id"]

    # 3. Connect to websocket
    uri = f"ws://localhost:8000/ws/groups/{group_id}?token={token}"
    async with websockets.connect(uri) as ws:
        print("Connected to WebSocket.")
        
        # 4. Send a message with @ai
        await ws.send("Hello @ai, what is 2+2?")
        
        # 5. Wait for the broadcasted message from myself
        my_msg = await ws.recv()
        print("Received my msg:", my_msg)
        
        # 6. Wait for the AI's response
        try:
            ai_msg = await asyncio.wait_for(ws.recv(), timeout=10.0)
            print("Received AI msg:", ai_msg.encode('ascii', 'backslashreplace').decode('ascii'))
            msg_data = json.loads(ai_msg)
            if msg_data.get("sender_name") == "AI Assistant":
                print("SUCCESS: AI responded!")
            else:
                print("FAIL: Sender is not AI Assistant")
        except asyncio.TimeoutError:
            print("FAIL: Timed out waiting for AI response.")

if __name__ == "__main__":
    asyncio.run(test_group_ai())
