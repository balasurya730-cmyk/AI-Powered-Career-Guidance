import requests, sys, json, random, string, time

BASE = "http://localhost:8000"
errors = []

def check(name, resp, expect=200):
    ok = resp.status_code == expect
    if not ok:
        try:
            body = resp.json()
        except Exception:
            body = resp.text[:300]
        errors.append(f"[{name}] expected {expect}, got {resp.status_code}: {body}")
    return ok, resp

def run_user(i, verbose=False):
    email = f"user{i}_{''.join(random.choices(string.ascii_lowercase, k=6))}@test.com"
    pw = "password123"
    local_errors = []

    r = requests.post(f"{BASE}/api/register", json={"name": f"User {i}", "email": email, "password": pw})
    if r.status_code != 200:
        local_errors.append(f"register: {r.status_code} {r.text[:200]}")
        return local_errors
    token = r.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}"}

    r = requests.post(f"{BASE}/api/profile", headers=headers, json={
        "name": f"User {i}", "education": "B.Tech", "department": "IT", "college": "KLN College",
        "current_year": str(random.randint(1,4)), "skills": "Python, JavaScript, SQL",
        "interests": "AI, Web Development", "daily_study_hours": random.choice([1,2,3,4,5]),
        "career_goal": ""
    })
    if r.status_code != 200:
        local_errors.append(f"profile create: {r.status_code} {r.text[:300]}")

    r = requests.post(f"{BASE}/api/career/recommend", headers=headers, json={
        "favorite_subjects": "Math, CS", "strengths": "problem solving, logic",
        "preferred_work_style": "remote"
    })
    if r.status_code != 200:
        local_errors.append(f"career/recommend: {r.status_code} {r.text[:300]}")
        careers = []
    else:
        r_opt = requests.get(f"{BASE}/api/career/options", headers=headers)
        if r_opt.status_code == 200:
            careers = r_opt.json()
        else:
            local_errors.append(f"career/options: {r_opt.status_code} {r_opt.text[:300]}")
            careers = []

    if careers:
        chosen = careers[0]
        r = requests.post(f"{BASE}/api/career/select", headers=headers, json={
            "career_id": chosen.get("id"),
        })
        if r.status_code != 200:
            local_errors.append(f"career/select: {r.status_code} {r.text[:300]}")

    plan_id = None
    r = requests.post(f"{BASE}/api/learning-plan/generate", headers=headers, json={})
    if r.status_code != 200:
        local_errors.append(f"learning-plan/generate: {r.status_code} {r.text[:300]}")
    else:
        plan = r.json()
        plan_id = plan.get("id")
        for key in ("daily_plan", "weekly_plan", "monthly_roadmap"):
            if key not in plan or not plan[key]:
                local_errors.append(f"learning-plan missing/empty '{key}'")

    r = requests.get(f"{BASE}/api/dashboard", headers=headers)
    if r.status_code != 200:
        local_errors.append(f"dashboard: {r.status_code} {r.text[:300]}")

    # AI Mentor / chat -- the reported broken feature
    r = requests.post(f"{BASE}/api/chat", headers=headers, json={
        "message": "Can you give me today's study plan?", "history": []
    })
    if r.status_code != 200:
        local_errors.append(f"chat: {r.status_code} {r.text[:300]}")
    else:
        reply = r.json().get("reply", "")
        if not reply or len(reply.strip()) < 2:
            local_errors.append(f"chat: empty/short reply: {reply!r}")

    # second chat turn with history (context)
    r = requests.post(f"{BASE}/api/chat", headers=headers, json={
        "message": "Can you break that into daily, weekly and monthly steps?",
        "history": [{"role": "user", "text": "Can you give me today's study plan?"},
                    {"role": "assistant", "text": "Sure, here is a plan."}]
    })
    if r.status_code != 200:
        local_errors.append(f"chat turn2: {r.status_code} {r.text[:300]}")

    r = requests.get(f"{BASE}/api/notifications", headers=headers)
    if r.status_code != 200:
        local_errors.append(f"notifications: {r.status_code} {r.text[:300]}")

    r = requests.get(f"{BASE}/api/leaderboard", headers=headers)
    if r.status_code != 200:
        local_errors.append(f"leaderboard: {r.status_code} {r.text[:300]}")

    if plan_id is not None:
        r = requests.post(f"{BASE}/api/phases/generate", headers=headers, json={"learning_plan_id": plan_id})
        if r.status_code != 200:
            local_errors.append(f"phases/generate: {r.status_code} {r.text[:300]}")
    else:
        local_errors.append("phases/generate skipped: no learning plan generated")

    r = requests.get(f"{BASE}/api/phases", headers=headers)
    if r.status_code != 200:
        local_errors.append(f"phases get: {r.status_code} {r.text[:300]}")

    r = requests.post(f"{BASE}/api/skill-gap/analyze", headers=headers, json={
        "career_name": (careers[0].get("career_name") if careers else "Software Engineer"),
        "student_skills": "Python, HTML"
    })
    if r.status_code != 200:
        local_errors.append(f"skill-gap/analyze: {r.status_code} {r.text[:300]}")

    return local_errors

if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    all_errors = {}
    t0 = time.time()
    for i in range(n):
        errs = run_user(i)
        if errs:
            all_errors[i] = errs
    dt = time.time() - t0
    print(f"Ran {n} simulated users in {dt:.1f}s")
    print(f"Users with errors: {len(all_errors)} / {n}")
    for uid, errs in all_errors.items():
        print(f"--- user {uid} ---")
        for e in errs:
            print("   ", e)
    with open("e2e_errors.json", "w") as f:
        json.dump(all_errors, f, indent=2)
