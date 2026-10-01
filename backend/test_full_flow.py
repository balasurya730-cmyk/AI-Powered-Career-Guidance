import requests
import json
import random
import string

BASE_URL = "http://localhost:8001"

rand_str = ''.join(random.choices(string.ascii_lowercase, k=8))
reg_payload = {
    "student_code": f"S-{rand_str.upper()}", 
    "name": "Test User", 
    "email": f"test_{rand_str}@test.com", 
    "password": "pwd123"
}
res = requests.post(f"{BASE_URL}/api/register", json=reg_payload)
print("Register Status:", res.status_code)
if res.status_code != 200:
    print(res.text)
    exit(1)

token = res.json().get("access_token")
headers = {"Authorization": f"Bearer {token}"}
prof = requests.post(f"{BASE_URL}/api/profile", json={"name": "Test User", "education": "Undergraduate", "department": "Computer Science", "college": "Test University", "current_year": "Senior", "skills": "Python, SQL", "interests": "AI", "daily_study_hours": 2, "career_goal": "Software Engineer"}, headers=headers)
print("Profile Status:", prof.status_code)

print("\n1. Testing /api/career/recommend...")
res = requests.post(f"{BASE_URL}/api/career/recommend", json={"favorite_subjects": "math", "strengths": "logic", "preferred_work_style": "Remote"}, headers=headers)
print("Status:", res.status_code)

print("\n2. Getting options...")
res = requests.get(f"{BASE_URL}/api/career/options", headers=headers)
if res.status_code == 200:
    options = res.json()
    if options:
        career_id = options[0]['id']
        print(f"Selected career id: {career_id}")
        print("\n3. Selecting career...")
        sel = requests.post(f"{BASE_URL}/api/career/select", json={"career_id": career_id}, headers=headers)
        print("Select Status:", sel.status_code)

        print("\n4. Testing /api/skill-gap/analyze...")
        res = requests.post(f"{BASE_URL}/api/skill-gap/analyze", json={}, headers=headers)
        print("Status:", res.status_code)
        if res.status_code == 200:
            print("Response snippet:", str(res.json())[:200])
        else:
            print(res.text)

        print("\n5. Testing /api/interview/start...")
        res = requests.post(f"{BASE_URL}/api/interview/start", json={}, headers=headers)
        print("Status:", res.status_code)
        if res.status_code == 200:
            q = res.json().get("questions", [])
            if q:
                print("\n6. Testing /api/interview/answer...")
                res = requests.post(f"{BASE_URL}/api/interview/answer", json={"question": q[0]["question"], "type": q[0]["type"], "ideal_points": q[0].get("ideal_points", []), "answer": "I know python."}, headers=headers)
                print("Status:", res.status_code)
                if res.status_code == 200:
                    print("Response snippet:", str(res.json())[:200])
                else:
                    print(res.text)
        else:
            print(res.text)
    else:
        print("No careers returned!")
else:
    print(res.text)
