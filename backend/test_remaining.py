import requests, json

BASE_URL = "http://localhost:8001"

import random, string
rand_str = ''.join(random.choices(string.ascii_lowercase, k=8))
res = requests.post(f"{BASE_URL}/api/register", json={
    "student_code": f"stu_{rand_str}", "name": "Test User", "email": f"test_{rand_str}@test.com", "password": "pwd"
})
token = res.json().get("access_token")
headers = {"Authorization": f"Bearer {token}"}
requests.post(f"{BASE_URL}/api/profile", json={"name": "Test User", "education": "Undergraduate", "department": "Computer Science", "college": "Test University", "current_year": "Senior", "skills": "Python, SQL", "interests": "AI", "daily_study_hours": 2, "career_goal": "Software Engineer"}, headers=headers)

print("Testing /api/career/options...")
res = requests.post(f"{BASE_URL}/api/career/options", json={"favorite_subjects": "math", "strengths": "logic", "preferred_work_style": "Remote"}, headers=headers)
print("Status:", res.status_code)

print("Testing /api/skill-gap/analyze...")
res = requests.post(f"{BASE_URL}/api/skill-gap/analyze", json={"career_name": "Data Scientist", "required_skills": ["Python", "Machine Learning"]}, headers=headers)
print("Status:", res.status_code)

print("Testing /api/interview/start...")
res = requests.post(f"{BASE_URL}/api/interview/start", json={"career_name": "Data Scientist"}, headers=headers)
print("Status:", res.status_code)
if res.status_code == 200:
    q = res.json().get("questions", [])
    if q:
        print("Testing /api/interview/answer...")
        res = requests.post(f"{BASE_URL}/api/interview/answer", json={"question": q[0]["question"], "type": q[0]["type"], "ideal_points": q[0]["ideal_points"], "answer": "I know python."}, headers=headers)
        print("Status:", res.status_code)
