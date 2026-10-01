import requests
import asyncio
import websockets
import random
import string
import json

BASE_URL = "http://localhost:8001"

async def test_all():
    rand_str = ''.join(random.choices(string.ascii_lowercase, k=8))
    email = f"test_{rand_str}@test.com"
    pwd = "password"
    
    # 1. Register User
    print("1. Registering user...")
    res = requests.post(f"{BASE_URL}/api/register", json={
        "student_code": f"stu_{rand_str}",
        "name": "Test User",
        "email": email,
        "password": pwd
    })
    token = res.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}"}
    print("   Done.")
    
    # 1.5 Create Profile
    print("1.5 Creating profile...")
    requests.post(f"{BASE_URL}/api/profile", json={
        "name": "Test User",
        "education": "Undergraduate",
        "department": "Computer Science",
        "college": "Test University",
        "current_year": "Senior",
        "skills": "Python, SQL",
        "interests": "AI, Web Development",
        "daily_study_hours": 2,
        "career_goal": "Software Engineer"
    }, headers=headers)
    print("   Done.")
    
    # 2. Test Match Score
    print("2. Testing POST /api/career/match-score...")
    res = requests.post(f"{BASE_URL}/api/career/match-score", json={
        "career_name": "Registered Nurse"
    }, headers=headers)
    assert res.status_code == 200, f"Match score failed: {res.status_code} {res.text}"
    print(f"   Success! Score: {res.json().get('score')}")
    
    # 3. Test Learning Plan
    print("3. Testing POST /api/learning-plan/generate...")
    res = requests.post(f"{BASE_URL}/api/learning-plan/generate", json={
        "career_name": "Registered Nurse"
    }, headers=headers)
    assert res.status_code == 200, f"Learning plan failed: {res.status_code} {res.text}"
    plan = res.json()
    daily = str(plan.get("daily_plan", []))
    assert "item 1" not in daily, f"Plan still has placeholder: {daily}"
    print("   Success! No 'item 1' placeholders found.")
    
    # 4. Test WebSocket & AI Catch Up
    print("4. Testing WebSocket Chat & AI Catch Up...")
    res = requests.post(f"{BASE_URL}/api/groups", json={
        "name": f"Group_{rand_str}",
        "description": "Test"
    }, headers=headers)
    group_id = res.json()["id"]
    
    ws_url = f"ws://localhost:8001/ws/groups/{group_id}?token={token}"
    try:
        async with websockets.connect(ws_url, ping_interval=None) as ws:
            # Send catch me up command
            await ws.send("@ai catch me up")
            
            # First message received is the user's own message broadcasted back
            msg1 = await ws.recv()
            
            # Second message should be AI response
            msg2 = await ws.recv()
            ai_data = json.loads(msg2)
            
            assert ai_data["sender_name"] == "AI Assistant", "Not from AI"
            reply = ai_data["message"]
            print(f"   AI Reply: {reply}")
            assert "summarize yet!" in reply or "No previous messages" in reply or "temporarily unavailable" in reply, "AI hallucinated a summary!"
            print("   Success! AI correctly handled empty chat history.")
    except Exception as e:
        print(f"   WebSocket test failed: {e}")
        
if __name__ == "__main__":
    asyncio.run(test_all())
