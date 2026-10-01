"""
load_test.py
------------
Simulates 50 full user journeys against the running backend, hitting every
endpoint (auth, profile, career advisor, skill gap, mock interview, learning
plan, phases, project submission, proctored test, chat, notifications,
certificate, leaderboard). Prints a PASS/FAIL summary and full error detail
for anything that didn't behave as expected.
"""
import requests
import json
import random
import string
import sys
import traceback

BASE = "http://localhost:8000"
NUM_USERS = 100

errors = []
passes = 0
fails = 0


def rand_email(i):
    return f"loadtest_user_{i}_{''.join(random.choices(string.ascii_lowercase, k=5))}@example.com"


def record(step, ok, detail=""):
    global passes, fails
    if ok:
        passes += 1
    else:
        fails += 1
        errors.append(f"[{step}] {detail}")


def run_user_journey(i):
    email = rand_email(i)
    session = requests.Session()
    token = None

    # ---- Register ----
    try:
        r = session.post(f"{BASE}/api/register", json={
            "name": f"Load Test User {i}", "email": email, "password": "password123",
        }, timeout=30)
        ok = r.status_code == 200 and "access_token" in r.json()
        record(f"user{i}.register", ok, f"status={r.status_code} body={r.text[:300]}")
        if ok:
            token = r.json()["access_token"]
        else:
            return
    except Exception as e:
        record(f"user{i}.register", False, str(e))
        return

    headers = {"Authorization": f"Bearer {token}"}

    # ---- Login (verify separately too) ----
    try:
        r = session.post(f"{BASE}/api/login", json={"email": email, "password": "password123"}, timeout=30)
        record(f"user{i}.login", r.status_code == 200, f"status={r.status_code} body={r.text[:300]}")
    except Exception as e:
        record(f"user{i}.login", False, str(e))

    # ---- Profile ----
    try:
        skills_pool = ["Python", "HTML", "CSS", "JavaScript", "SQL", "Java", "C++", "Excel"]
        interests_pool = ["Web Dev", "AI", "Robotics", "Data Science", "Cybersecurity", "Cloud"]
        payload = {
            "name": f"Load Test User {i}",
            "education": "B.Tech", "department": "Information Technology",
            "college": "KLN College of Engineering", "current_year": "3rd Year",
            "skills": ", ".join(random.sample(skills_pool, 3)),
            "interests": ", ".join(random.sample(interests_pool, 2)),
            "daily_study_hours": random.choice([1.5, 2, 3, 4]),
            "career_goal": None if i % 2 == 0 else "Data Scientist",
        }
        r = session.post(f"{BASE}/api/profile", json=payload, headers=headers, timeout=30)
        record(f"user{i}.profile", r.status_code == 200, f"status={r.status_code} body={r.text[:300]}")
    except Exception as e:
        record(f"user{i}.profile", False, str(e))

    # ---- Career recommend ----
    try:
        body = None
        if i % 2 == 0:
            body = {
                "favorite_subjects": "Math, Computer Science",
                "strengths": "Problem solving, logical thinking",
                "preferred_work_style": "independent",
            }
        r = session.post(f"{BASE}/api/career/recommend", json=body, headers=headers, timeout=40)
        ok = r.status_code == 200 and len(r.json().get("careers", [])) > 0
        record(f"user{i}.career_recommend", ok, f"status={r.status_code} body={r.text[:400]}")
    except Exception as e:
        record(f"user{i}.career_recommend", False, str(e))

    # ---- Career options + select ----
    career_id = None
    try:
        r = session.get(f"{BASE}/api/career/options", headers=headers, timeout=30)
        ok = r.status_code == 200 and len(r.json()) > 0
        record(f"user{i}.career_options", ok, f"status={r.status_code} body={r.text[:300]}")
        if ok:
            career_id = r.json()[0]["id"]
    except Exception as e:
        record(f"user{i}.career_options", False, str(e))

    if career_id:
        try:
            r = session.post(f"{BASE}/api/career/select", json={"career_id": career_id}, headers=headers, timeout=30)
            record(f"user{i}.career_select", r.status_code == 200, f"status={r.status_code} body={r.text[:300]}")
        except Exception as e:
            record(f"user{i}.career_select", False, str(e))

    # ---- Skill gap analyze + courses ----
    skill_gap_id = None
    try:
        r = session.post(f"{BASE}/api/skill-gap/analyze", json={}, headers=headers, timeout=40)
        ok = r.status_code == 200
        record(f"user{i}.skill_gap_analyze", ok, f"status={r.status_code} body={r.text[:400]}")
        if ok:
            skill_gap_id = r.json()["id"]
    except Exception as e:
        record(f"user{i}.skill_gap_analyze", False, str(e))

    if skill_gap_id:
        try:
            r = session.post(f"{BASE}/api/skill-gap/courses", json={"skill_gap_id": skill_gap_id}, headers=headers, timeout=40)
            record(f"user{i}.skill_gap_courses", r.status_code == 200, f"status={r.status_code} body={r.text[:400]}")
        except Exception as e:
            record(f"user{i}.skill_gap_courses", False, str(e))

    # ---- Learning plan generate ----
    plan_id = None
    try:
        r = session.post(f"{BASE}/api/learning-plan/generate", json={}, headers=headers, timeout=40)
        ok = r.status_code == 200 and all(k in r.json() for k in ("daily_plan", "weekly_plan", "monthly_roadmap"))
        record(f"user{i}.learning_plan_generate", ok, f"status={r.status_code} body={r.text[:400]}")
        if r.status_code == 200:
            plan_id = r.json()["id"]
    except Exception as e:
        record(f"user{i}.learning_plan_generate", False, str(e))

    # ---- Dashboard ----
    try:
        r = session.get(f"{BASE}/api/dashboard", headers=headers, timeout=30)
        record(f"user{i}.dashboard", r.status_code == 200, f"status={r.status_code} body={r.text[:300]}")
    except Exception as e:
        record(f"user{i}.dashboard", False, str(e))

    # ---- Phases generate ----
    phase_id = None
    if plan_id:
        try:
            r = session.post(f"{BASE}/api/phases/generate", json={"learning_plan_id": plan_id}, headers=headers, timeout=40)
            ok = r.status_code == 200 and len(r.json()) > 0
            record(f"user{i}.phases_generate", ok, f"status={r.status_code} body={r.text[:400]}")
            if ok:
                phase_id = r.json()[0]["id"]
        except Exception as e:
            record(f"user{i}.phases_generate", False, str(e))

    try:
        r = session.get(f"{BASE}/api/phases", headers=headers, timeout=30)
        record(f"user{i}.phases_get", r.status_code == 200, f"status={r.status_code} body={r.text[:300]}")
    except Exception as e:
        record(f"user{i}.phases_get", False, str(e))

    # ---- Tick off all of this phase's weekly tasks (required before project submission) ----
    if phase_id:
        try:
            r = session.get(f"{BASE}/api/phases", headers=headers, timeout=30)
            phases = r.json() if r.status_code == 200 else []
            this_phase = next((p for p in phases if p["id"] == phase_id), None)
            tick_ok = True
            if this_phase:
                for task in this_phase.get("tasks", []):
                    rt = session.post(f"{BASE}/api/progress/update", json={
                        "progress_id": task["id"], "is_completed": True,
                    }, headers=headers, timeout=30)
                    if rt.status_code != 200:
                        tick_ok = False
            record(f"user{i}.tick_tasks", tick_ok, "one or more progress/update calls failed")
        except Exception as e:
            record(f"user{i}.tick_tasks", False, str(e))

    # ---- Project submit ----
    if phase_id:
        try:
            r = session.post(f"{BASE}/api/projects/submit", json={
                "phase_id": phase_id, "submission_type": "code",
                "content": "demo_approve\ndef hello():\n    print('hello world')\nhello()",
            }, headers=headers, timeout=40)
            record(f"user{i}.project_submit", r.status_code == 200, f"status={r.status_code} body={r.text[:400]}")
        except Exception as e:
            record(f"user{i}.project_submit", False, str(e))

    # ---- Proctored test start/submit ----
    attempt_id = None
    total_qs = 0
    if phase_id:
        try:
            r = session.post(f"{BASE}/api/tests/start", json={"phase_id": phase_id}, headers=headers, timeout=40)
            ok = r.status_code == 200 and len(r.json().get("questions", [])) > 0
            record(f"user{i}.test_start", ok, f"status={r.status_code} body={r.text[:400]}")
            if ok:
                attempt_id = r.json()["attempt_id"]
                total_qs = len(r.json()["questions"])
        except Exception as e:
            record(f"user{i}.test_start", False, str(e))

    if attempt_id:
        try:
            answers = [{"index": idx, "selected_option": 0} for idx in range(total_qs)]
            r = session.post(f"{BASE}/api/tests/submit", json={
                "attempt_id": attempt_id, "answers": answers,
            }, headers=headers, timeout=40)
            record(f"user{i}.test_submit", r.status_code == 200, f"status={r.status_code} body={r.text[:400]}")
        except Exception as e:
            record(f"user{i}.test_submit", False, str(e))

    # ---- Mock Interview: start -> answer all -> finish -> history -> detail ----
    interview_session_id = None
    try:
        r = session.post(f"{BASE}/api/interview/start", headers=headers, timeout=40)
        ok = r.status_code == 200 and len(r.json().get("questions", [])) > 0
        record(f"user{i}.interview_start", ok, f"status={r.status_code} body={r.text[:400]}")
        if ok:
            interview_session_id = r.json()["session_id"]
            questions = r.json()["questions"]
    except Exception as e:
        record(f"user{i}.interview_start", False, str(e))
        questions = []

    if interview_session_id:
        answer_ok_all = True
        for q in questions:
            try:
                r = session.post(f"{BASE}/api/interview/answer", json={
                    "session_id": interview_session_id, "index": q["index"],
                    "answer": "I handled this by breaking the problem into smaller steps, communicating with my team, and delivering on time.",
                    "time_taken_seconds": 45,
                }, headers=headers, timeout=40)
                if r.status_code != 200 or "score" not in r.json():
                    answer_ok_all = False
                    record(f"user{i}.interview_answer[{q['index']}]", False, f"status={r.status_code} body={r.text[:400]}")
            except Exception as e:
                answer_ok_all = False
                record(f"user{i}.interview_answer[{q['index']}]", False, str(e))
        record(f"user{i}.interview_answer_all", answer_ok_all, "one or more answer submissions failed")

        try:
            r = session.post(f"{BASE}/api/interview/finish", json={"session_id": interview_session_id}, headers=headers, timeout=40)
            ok = r.status_code == 200 and "overall_score" in r.json()
            record(f"user{i}.interview_finish", ok, f"status={r.status_code} body={r.text[:400]}")
        except Exception as e:
            record(f"user{i}.interview_finish", False, str(e))

        try:
            r = session.get(f"{BASE}/api/interview/history", headers=headers, timeout=30)
            ok = r.status_code == 200 and len(r.json().get("sessions", [])) >= 1
            record(f"user{i}.interview_history", ok, f"status={r.status_code} body={r.text[:300]}")
        except Exception as e:
            record(f"user{i}.interview_history", False, str(e))

        try:
            r = session.get(f"{BASE}/api/interview/{interview_session_id}", headers=headers, timeout=30)
            ok = r.status_code == 200 and r.json().get("status") == "completed"
            record(f"user{i}.interview_detail", ok, f"status={r.status_code} body={r.text[:400]}")
        except Exception as e:
            record(f"user{i}.interview_detail", False, str(e))

    # ---- Chat (AI Mentor) ----
    try:
        r = session.post(f"{BASE}/api/chat", json={
            "message": "What should I focus on this week?", "history": [],
        }, headers=headers, timeout=40)
        ok = r.status_code == 200 and len(r.json().get("reply", "")) > 0
        record(f"user{i}.chat", ok, f"status={r.status_code} body={r.text[:400]}")
    except Exception as e:
        record(f"user{i}.chat", False, str(e))

    # ---- Notifications ----
    try:
        r = session.get(f"{BASE}/api/notifications", headers=headers, timeout=30)
        record(f"user{i}.notifications", r.status_code == 200, f"status={r.status_code} body={r.text[:300]}")
    except Exception as e:
        record(f"user{i}.notifications", False, str(e))

    # ---- Leaderboard ----
    try:
        r = session.get(f"{BASE}/api/leaderboard", headers=headers, timeout=30)
        record(f"user{i}.leaderboard", r.status_code == 200, f"status={r.status_code} body={r.text[:300]}")
    except Exception as e:
        record(f"user{i}.leaderboard", False, str(e))

    # ---- Certificate (expected to possibly 404/400 since phase likely incomplete - not a hard failure) ----
    if plan_id:
        try:
            r = session.get(f"{BASE}/api/certificate/{plan_id}", headers=headers, timeout=30)
            # Certificate legitimately requires full completion; 400/404 here is expected, not a bug.
            ok = r.status_code in (200, 400, 404)
            record(f"user{i}.certificate", ok, f"status={r.status_code} body={r.text[:300]}")
        except Exception as e:
            record(f"user{i}.certificate", False, str(e))


if __name__ == "__main__":
    for i in range(1, NUM_USERS + 1):
        try:
            run_user_journey(i)
        except Exception as e:
            fails += 1
            errors.append(f"[user{i}.UNCAUGHT] {e}\n{traceback.format_exc()}")
        if i % 10 == 0:
            print(f"...completed {i}/{NUM_USERS} users", flush=True)

    print("\n" + "=" * 70)
    print(f"TOTAL CHECKS: {passes + fails}   PASS: {passes}   FAIL: {fails}")
    print("=" * 70)
    if errors:
        print(f"\n{len(errors)} FAILURES:\n")
        for e in errors:
            print(e)
            print("-" * 70)
    sys.exit(1 if fails else 0)
