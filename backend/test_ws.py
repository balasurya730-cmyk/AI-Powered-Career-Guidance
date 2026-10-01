import asyncio
import websockets
import json
import requests

import random
import string
def test_chat():
    rand_str = ''.join(random.choices(string.ascii_lowercase, k=8))
    # 1. Login or create user
    email = f"wstest_{rand_str}@test.com"
    pwd = "password"
    res = requests.post("http://localhost:8000/api/register", json={
        "student_code": f"ws_{rand_str}",
        "name": "WS Test",
        "email": email,
        "password": pwd
    })
    
    if res.status_code == 400:
        res = requests.post("http://localhost:8000/api/login", json={
            "email": email,
            "password": pwd
        })
    token = res.json().get("access_token")
    if not token:
        print("Failed to get token:", res.text)
        return
    print("Got token!")
    
    # 2. Create a group
    res = requests.post("http://localhost:8000/api/groups", json={
        "name": "WS Group",
        "description": "Test"
    }, headers={"Authorization": f"Bearer {token}"})
    if res.status_code != 200:
        print("Failed to create group:", res.text)
        return
    group_id = res.json()["id"]
    
    # 3. Connect to WS
    async def run_ws():
        uri = f"ws://localhost:8000/ws/groups/{group_id}?token={token}"
        async with websockets.connect(uri) as websocket:
            print("Connected!")
            await websocket.send("hi")
            response = await websocket.recv()
            print("Received:", response)
            
            await websocket.send("@ai summarize")
            response = await websocket.recv()
            print("Received:", response)
            response2 = await websocket.recv()
            print("Received2:", response2)

    asyncio.run(run_ws())

if __name__ == "__main__":
    test_chat()
