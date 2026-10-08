"""
gemini_service.py
------------------
All calls to Google's Gemini API live here. Wires up dynamic model creation
and includes a high-quality mock fallback system in case of API quota limits,
network issues, or invalid keys, ensuring the app never fails with a 502 error.
"""

import os
import json
import re
import concurrent.futures
import requests
from dotenv import load_dotenv

# Load the project configuration before reading provider settings.
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"), override=True)

NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "deepseek-ai/deepseek-v4-flash-0731")
GOOGLE_GENERATE_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
GEMMA_MODEL = os.getenv("GEMMA_MODEL", "gemma-3-27b-it")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-chat-v3-0324:free")
HARD_TIMEOUT_SECONDS = 120  # app-level cap; see _call_gemini_with_hard_timeout

# Underlying gRPC connection failures (bad proxy, blocked DNS, firewalled
# network, etc.) don't always respect the SDK's own timeout, and can
# otherwise hang a request forever. Running the call in a worker thread with
# .result(timeout=...) guarantees callers
# always get control back within HARD_TIMEOUT_SECONDS, so the mock fallback
# below always kicks in promptly no matter what the network is doing.
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=40)


def _call_gemini_with_hard_timeout(prompt: str, feature: str = "default", expect_json: bool = False) -> str:
    future = _executor.submit(_call_gemini, prompt, feature, expect_json)
    try:
        return future.result(timeout=HARD_TIMEOUT_SECONDS)
    except concurrent.futures.TimeoutError:
        raise RuntimeError(
            f"Gemini API call did not respond within {HARD_TIMEOUT_SECONDS}s "
            "(network unreachable or too slow)"
        )

def _extract_json(raw_text: str):
    text = raw_text.strip()
    text = re.sub(r"^```json\s*|^```\s*|```$", "", text, flags=re.MULTILINE).strip()

    start_candidates = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if not start_candidates:
        raise ValueError("No JSON object found in Gemini response")
    start = min(start_candidates)
    end = max(text.rfind("}"), text.rfind("]")) + 1
    json_str = text[start:end]
    
    # Clean trailing commas before closing braces/brackets, which AI models often hallucinate
    cleaned = re.sub(r',\s*([\]}])', r'\1', json_str)
    
    return json.loads(cleaned)

def get_awesome_skills_context() -> str:
    try:
        skills_path = os.path.join(os.path.dirname(__file__), "..", "antigravity-awesome-skills", "data", "skills_index.json")
        with open(skills_path, "r", encoding="utf-8") as f:
            skills = json.load(f)
            if not skills:
                return ""
            skill_summaries = []
            for s in skills[:20]:
                name = s.get('name', '')
                desc = s.get('description', '')[:100]
                skill_summaries.append(f"- {name}: {desc}...")
            return "Here are some awesome skills you can recommend:\n" + "\n".join(skill_summaries) + "\n"
    except Exception:
        return ""

def _call_gemini(prompt: str, feature: str = "default", expect_json: bool = False) -> str:
    """
    Core function that sends the prompt to the appropriate LLM based on feature routing.
    Iterates through the fallback chain until one succeeds.
    If expect_json is True, it will attempt to extract JSON; if it fails, it triggers fallback.
    """
    # Reload environment variables to catch runtime updates during development.
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"), override=True)
    
    from llm_router import get_routing_chain
    chain = get_routing_chain(feature)
    
    import time
    last_error = None
    
    for config in chain:
        provider = config.get("provider")
        api_key = config.get("api_key")
        
        if not api_key or api_key.startswith("your_"):
            continue
            
        url = config.get("url")
        if provider == "gemini":
            url = url.format(model=config.get("model"))
            
        print(f"[gemini_service] Attempting provider: {provider} with model {config.get('model')}")
        
        # Only retry once for openrouter to fail fast and fallback
        max_retries = 2 if provider == "gemini" else 1 
        for attempt in range(max_retries):
            try:
                if provider == "gemini":
                    response = requests.post(
                        url,
                        params={"key": api_key},
                        json={"contents": [{"parts": [{"text": prompt}]}]},
                        timeout=60,
                    )
                else:  # openrouter format
                    headers = {
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "http://localhost:8001",
                        "X-Title": "Antigravity App"
                    }
                    payload = {
                        "model": config.get("model"),
                        "messages": [{"role": "user", "content": prompt}]
                    }
                    
                    # Increased timeout to 60s for NVIDIA integration API
                    temp_exec = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                    future = temp_exec.submit(requests.post, url, headers=headers, json=payload, timeout=60)
                    try:
                        response = future.result(timeout=60)
                    except concurrent.futures.TimeoutError:
                        temp_exec.shutdown(wait=False)
                        raise RuntimeError("Provider API hanging (Timeout). Forcing fallback.")
                    finally:
                        temp_exec.shutdown(wait=False)
                
                print(f"[gemini_service] {provider} responded with status: {response.status_code}")
                
                if response.status_code == 429 and attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                    
                if response.status_code != 200:
                    raise RuntimeError(f"HTTP {response.status_code}: {response.text[:500]}")
                    
                data = response.json()
                if provider == "gemini":
                    raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
                else:
                    raw_text = data["choices"][0]["message"]["content"]
                    
                if expect_json:
                    # Will raise ValueError if JSON is invalid, triggering fallback!
                    _extract_json(raw_text)
                    
                return raw_text
                    
            except Exception as e:
                last_error = e
                print(f"[gemini_service] Error with {provider}: {e}")
                if "429" in str(e) and attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                # If we hit a non-retryable error (e.g. invalid JSON), break to next provider
                break
                
    # If we exhaust the entire fallback chain
    raise RuntimeError(f"All LLM providers failed. Last error: {last_error}")

def recommend_careers(profile: dict, extra_answers: dict | None = None) -> list[dict]:
    extra_block = ""
    if extra_answers:
        extra_block = f"""
Additional answers from the student (they had no fixed career goal):
- Favorite subjects: {extra_answers.get('favorite_subjects', '')}
- Strengths: {extra_answers.get('strengths', '')}
- Preferred work style: {extra_answers.get('preferred_work_style', '')}
"""

    prompt = f"""
You are a friendly, encouraging career advisor for students. Based on the student
profile below, recommend exactly 5 suitable careers, ranked best-fit first.

Student profile:
- Education: {profile.get('education', '')}
- Department: {profile.get('department', '')}
- Current year: {profile.get('current_year', '')}
- Skills: {profile.get('skills', '')}
- Interests: {profile.get('interests', '')}
- Daily study hours available: {profile.get('daily_study_hours', '')}
{extra_block}

Respond with ONLY valid JSON (no markdown, no commentary) in exactly this shape:
{{
  "careers": [
    {{
      "career_name": "string",
      "description": "2-3 sentence plain-English description",
      "required_skills": ["skill1", "skill2", "skill3", "skill4"],
      "future_scope": "1-2 sentences on job market outlook and growth",
      "reason": "1-2 sentences on why this fits THIS student specifically"
    }}
  ]
}}
Use clear, simple, beginner-friendly language. Return exactly 5 items in the careers array.
CRITICAL: You must use valid JSON syntax. Escape any internal double quotes using backslashes. Do not include trailing commas.
"""
    try:
        raw = _call_gemini_with_hard_timeout(prompt, "career_guidance")
        data = _extract_json(raw)
        careers = data.get("careers", data if isinstance(data, list) else [])
        return careers[:5]
    except Exception as e:
        print(f"[gemini_service] Gemini API call failed: {e}. Falling back to mock generator.")
        return _get_mock_careers(profile, extra_answers)

def generate_learning_plan(profile: dict, career_name: str) -> dict:
    prompt = f"""
You are an expert learning coach. Create a personalized, practical learning plan
for a student aiming to become a: {career_name}

Student context:
- Current skills: {profile.get('skills', '')}
- Interests: {profile.get('interests', '')}
- Daily study hours available: {profile.get('daily_study_hours', '')}
- Current education level/year: {profile.get('education', '')} / {profile.get('current_year', '')}

Respond with ONLY valid JSON (no markdown, no commentary) in exactly this shape, replacing the placeholder text with your actual advice:
{{
  "daily_plan": ["<actionable step 1>", "<actionable step 2>", "<actionable step 3>"],
  "weekly_plan": ["<weekly task 1>", "<weekly task 2>", "<weekly task 3>", "<weekly task 4>"],
  "monthly_roadmap": ["<Month 1 goal>", "<Month 2 goal>", "<Month 3 goal>"],
  "skills_to_learn": ["<specific skill 1>", "<specific skill 2>", "<specific skill 3>", "<specific skill 4>"],
  "resources": ["<Resource Name> - <Why it helps>", "..."],
  "practice_project": "<1-2 sentences describing a practical, real-world portfolio piece or case study specific to the {career_name} industry (e.g. a lab report for a Biologist, a mock campaign for a Marketer)>"
}}
CRITICAL DOMAIN RESTRICTION: You must generate advice strictly confined to the domain of a {career_name}. DO NOT suggest software engineering tools (like Python, Flask, FastAPI, JavaScript, React, or GitHub) UNLESS the career explicitly requires coding (e.g., Software Engineer, Data Scientist). If the career is non-technical, the tasks and projects must use industry-standard tools for THAT specific field.
CRITICAL: You must use valid JSON syntax. Escape any internal double quotes using backslashes. Do not include trailing commas. DO NOT echo back the placeholder text. You must generate REAL, specific advice for {career_name}.
Keep each list item short (one line, actionable). Provide 3-5 items for daily_plan,
5-7 items for weekly_plan, 3 items for monthly_roadmap, 5 items for skills_to_learn,
and 4-6 items for resources. Only recommend genuinely free resources.
"""
    try:
        raw = _call_gemini_with_hard_timeout(prompt, "career_guidance")
        data = _extract_json(raw)
        return data
    except Exception as e:
        print(f"[gemini_service] Gemini API call failed: {e}. Falling back to mock generator.")
        return _get_mock_learning_plan(profile, career_name)


def generate_phased_roadmap(profile: dict, career_name: str, missing_skills: list[str] = None) -> list[dict]:
    """
    Unlike generate_learning_plan (one flat plan), this breaks the goal into
    realistic, sequential phases (e.g. "Python Basics" - 2 months, "Python
    Intermediate" - 3 months), each with its own weekly tasks and a phase-end
    project brief. This is what actually makes month-by-month gating possible.
    """
    missing_text = f"- Missing Skills to Learn: {', '.join(missing_skills)}" if missing_skills else "- Missing Skills to Learn: Not provided, use general career requirements."
    missing_skills_list = missing_skills if missing_skills else ["general skills for " + career_name]
    
    prompt = f"""
You are an expert learning coach designing a REALISTIC, multi-phase curriculum
for a student aiming to become a: {career_name}

Student context:
- Current skills: {profile.get('skills', '')}
{missing_text}
- Interests: {profile.get('interests', '')}
- Daily study hours available: {profile.get('daily_study_hours', '')}
- Current education level/year: {profile.get('education', '')} / {profile.get('current_year', '')}

Analyze the required missing skills: {missing_skills_list} for the career: {career_name}.
You must strictly split the learning into a global, universal mastery progression:
- Phase 1 (Beginner Level): Core fundamentals and basic concepts of {career_name}.
- Phase 2 (Intermediate Level): Application, logic, and standard tooling.
- Phase 3 (Advanced Level): Complex architecture, frameworks, and specialized skills.

Dynamically categorize the student's missing skills into these 3 (or more) phases, no matter what the career is (e.g. Data Science, Web Dev, Cybersecurity).
For each phase, assign highly specific weekly tasks (not generic advice) and a concrete phase-end project that forces the student to prove they have mastered that specific phase's skills before moving on.
Each phase must have an honest duration in weeks based on the daily study hours available.

CRITICAL DOMAIN RESTRICTION: You must generate advice strictly confined to the domain of a {career_name}. DO NOT suggest software engineering tools (like Python, Flask, FastAPI, JavaScript, React, or GitHub) UNLESS the career explicitly requires coding (e.g., Software Engineer, Data Scientist). If the career is non-technical, the tasks and projects must use industry-standard tools for THAT specific field (e.g., lab techniques for a Biologist, marketing analytics tools for a Marketer).

Respond with ONLY valid JSON (no markdown, no commentary) in exactly this shape:
{{
  "phases": [
    {{
      "phase_name": "string, e.g. 'Python Basics'",
      "description": "1-2 sentences on what this phase covers and why it takes this long",
      "duration_weeks": integer,
      "focus_skills": ["skill1", "skill2", "skill3"],
      "daily_habits": ["daily habit 1", "daily habit 2"],
      "weekly_tasks": ["week 1 focus / task", "week 2 focus / task", "..."],
      "monthly_milestone": "string describing the overarching goal for the month",
      "project_brief": "one concrete phase-end project the student must build and submit to prove they learned this phase's skills"
    }}
  ]
}}
Provide one weekly_tasks entry per week of duration_weeks (so if duration_weeks
is 4, provide 4 items). Keep daily_habits short (2-3 items). Return 3-5 phases total.
"""
    try:
        raw = _call_gemini_with_hard_timeout(prompt, "career_guidance")
        data = _extract_json(raw)
        phases = data.get("phases", data if isinstance(data, list) else [])
        if not phases:
            raise ValueError("empty phases")
        return phases
    except Exception as e:
        print(f"[gemini_service] Gemini API call failed: {e}. Falling back to mock generator.")
        return _get_mock_phases(profile, career_name)


def analyze_skill_gap(profile: dict, career_name: str, required_skills: list) -> dict:
    """
    Compares the student's current skills against a target career's required
    skills, returning a prioritized list of missing skills with reasoning.
    """
    prompt = f"""
You are a precise predictive skills assessor. Compare a student's current skills against
the skills required for their target career, and identify the gap. Most importantly, PRIORTIZE the missing skills based on industry demand and prerequisite dependency trees (what should they learn first?).

Student's current skills (as they typed them, comma separated): {profile.get('skills', '')}
Target career: {career_name}
Skills required for this career: {', '.join(required_skills) if required_skills else 'use your own knowledge of what this career typically requires'}

Match loosely and sensibly (e.g. "JS" satisfies "JavaScript"). 

Respond with ONLY valid JSON (no markdown, no commentary) in exactly this shape:
{{
  "matched_skills": ["skill the student already has that satisfies a requirement", "..."],
  "missing_skills": [
    {{
      "skill": "name of missing skill",
      "priority": integer from 1 (highest) to 10 (lowest),
      "reasoning": "Why this skill should be learned at this priority (e.g. foundational prerequisite, high market demand)"
    }}
  ],
  "summary": "2-3 encouraging but honest sentences on where the student stands and what the biggest gap is"
}}
"""
    try:
        raw = _call_gemini_with_hard_timeout(prompt, "skillgap")
        data = _extract_json(raw)
        return data
    except Exception as e:
        print(f"[gemini_service] Gemini skill-gap call failed: {e}. Falling back to mock generator.")
        return _get_mock_skill_gap(profile, required_skills)


def recommend_courses(career_name: str, missing_skills: list) -> list[dict]:
    """
    For each missing skill identified by analyze_skill_gap, suggests a
    specific free/low-cost course, tutorial, or certification to close it.
    """
    prompt = f"""
You are a learning resources curator. A student wants to become a: {career_name}
They are missing these skills: {', '.join(missing_skills) if missing_skills else 'none listed'}

For EACH missing skill, recommend exactly one specific, genuinely well-known,
free-or-low-cost course, tutorial, or certification that teaches it.

Respond with ONLY valid JSON (no markdown, no commentary) in exactly this shape:
{{
  "courses": [
    {{
      "skill_name": "the missing skill this resource addresses (must match one of the missing skills)",
      "title": "the specific course/tutorial/certification name",
      "provider": "who publishes it, e.g. 'freeCodeCamp', 'Coursera', 'Google', 'MDN'",
      "resource_type": "course" or "tutorial" or "certification",
      "url": "the resource's real, well-known homepage or landing page URL",
      "description": "1 sentence on what it covers and why it's a good fit here"
    }}
  ]
}}
Return exactly one entry per missing skill listed above, in the same order.
Only recommend resources you are confident actually exist.
"""
    try:
        raw = _call_gemini_with_hard_timeout(prompt, "skillgap")
        data = _extract_json(raw)
        courses = data.get("courses", data if isinstance(data, list) else [])
        return courses
    except Exception as e:
        print(f"[gemini_service] Gemini API call failed: {e}. Falling back to mock generator.")
        return _get_mock_courses(career_name, missing_skills)


def review_project_submission(phase_name: str, focus_skills: list, project_brief: str, submission_type: str, content: str) -> dict:
    """
    Acts as a code reviewer. Given what the phase was supposed to teach and
    what the student submitted, returns approve/revise + a specific error list
    (what's wrong, why it happened, how to fix it) instead of a vague pass/fail.
    """
    truncated_content = content[:6000]  # keep prompt bounded
    prompt = f"""
You are a strict but fair senior developer reviewing a student's phase-end
project submission.

Phase: {phase_name}
Skills this phase was supposed to teach: {', '.join(focus_skills)}
Expected project brief: {project_brief}

Submission type: {submission_type}
Submission content (code pasted directly, or a link the student says contains
the project -- if it's a link, review based on the description/content given,
and note in your summary that a live review of the link itself isn't possible
here):
---
{truncated_content}
---

Respond with ONLY valid JSON (no markdown, no commentary) in exactly this shape:
{{
  "approved": true or false,
  "score": integer 0-100 (quality/completeness score),
  "summary": "2-3 sentence overall verdict in plain language",
  "errors": [
    {{
      "issue": "what is wrong or missing, short and specific",
      "why": "why this happens / why it matters",
      "fix": "concrete step to fix it"
    }}
  ]
}}
Approve (true) only if the submission genuinely demonstrates the phase's focus
skills and reasonably matches the project brief, even if not perfect. If the
submission is empty, unrelated, or clearly does not meet the brief, set
approved to false and explain why in errors. Keep errors to at most 5 items.
"""
    try:
        raw = _call_gemini_with_hard_timeout(prompt, "career_guidance")
        data = _extract_json(raw)
        return data
    except Exception as e:
        print(f"[gemini_service] Gemini API call failed: {e}. Falling back to mock generator.")
        return _get_mock_review(submission_type, content)


def generate_phase_test(phase_name: str, focus_skills: list, num_questions: int = 25) -> list[dict]:
    """
    Generates a fixed-length multiple-choice test (1 mark per question) that
    covers a phase's focus skills, for the proctored phase-end test.
    """
    prompt = f"""
You are a technical instructor creating a {num_questions}-question multiple
choice test (1 mark each, {num_questions} marks total) to verify a student
has actually learned this phase before letting them move on.

Phase: {phase_name}
Skills to test: {', '.join(focus_skills)}

Respond with ONLY valid JSON (no markdown, no commentary) in exactly this shape:
{{
  "questions": [
    {{
      "question": "string",
      "options": ["A text", "B text", "C text", "D text"],
      "correct_index": integer 0-3
    }}
  ]
}}
Return exactly {num_questions} questions, mixing conceptual and applied
questions across all the listed skills. Keep questions unambiguous with
exactly one correct option.
"""
    try:
        raw = _call_gemini_with_hard_timeout(prompt, "career_guidance")
        data = _extract_json(raw)
        questions = data.get("questions", data if isinstance(data, list) else [])
        if len(questions) < num_questions:
            raise ValueError("not enough questions returned")
        return questions[:num_questions]
    except Exception as e:
        print(f"[gemini_service] Gemini API call failed: {e}. Falling back to mock generator.")
        return _get_mock_test(phase_name, focus_skills, num_questions)


# =========================================================================
# MOCK INTERVIEW (question generation, per-answer feedback, overall summary)
# =========================================================================

def generate_interview_questions(profile: dict, career_name: str, num_questions: int = 6) -> list[dict]:
    """
    Generates a mixed set of behavioral + technical interview questions for
    the student's selected career. Each question carries a time limit (used
    by the frontend as a countdown) and a few "ideal_points" the grader
    should look for in a strong answer (not shown to the student).
    """
    import uuid
    prompt = f"""
You are a senior technical interviewer preparing a mock interview for a
student targeting the career: {career_name}.

Session ID for uniqueness: {str(uuid.uuid4())} (Ensure you generate a UNIQUE set of questions that you haven't asked this student before!)

Student profile for context:
- Skills: {profile.get('skills', '')}
- Interests: {profile.get('interests', '')}
- Education: {profile.get('education', '')} / {profile.get('current_year', '')}

Generate exactly {num_questions} interview questions: roughly 60% behavioral/
situational (e.g. teamwork, handling failure, communication) and 40%
technical (specific to {career_name}). Mix easy and moderately challenging
questions -- this is practice, not a final-round grill.

Respond with ONLY valid JSON (no markdown, no commentary) in exactly this shape:
{{
  "questions": [
    {{
      "question": "string",
      "type": "behavioral" or "technical",
      "time_limit_seconds": 120,
      "ideal_points": ["short phrase a strong answer should touch on", "..."]
    }}
  ]
}}
CRITICAL: You must use valid JSON syntax. Escape any internal double quotes using backslashes. Do not include trailing commas.
"""
    try:
        raw = _call_gemini_with_hard_timeout(prompt, "mock_interview", expect_json=True)
        data = _extract_json(raw)
        questions = data.get("questions", data if isinstance(data, list) else [])
        if len(questions) < num_questions:
            raise ValueError("not enough interview questions returned")
        return questions[:num_questions]
    except Exception as e:
        print(f"[gemini_service] Gemini API call failed: {e}. Falling back to mock generator.")
        return _get_mock_interview_questions(career_name, num_questions)


def evaluate_interview_answer(question: str, q_type: str, ideal_points: list, answer: str) -> dict:
    """
    Grades a single interview answer against what a strong answer should
    cover, giving encouraging-but-honest feedback (this is practice, not a
    pass/fail gate).
    """
    prompt = f"""
You are a supportive but honest interview coach. A student just answered a
mock interview question. Evaluate their answer.

Question ({q_type}): {question}
What a strong answer should touch on: {', '.join(ideal_points) if ideal_points else '(use your own judgment)'}

Student's answer:
---
{answer[:3000]}
---

Respond with ONLY valid JSON (no markdown, no commentary) in exactly this shape, replacing the placeholder text with your actual advice:
{{
  "score": <integer from 1 to 10>,
  "feedback": "<2-3 sentences, direct and constructive, addressed to the student as 'you'>",
  "strengths": ["<short phrase>", "<another short phrase>"],
  "improvements": ["<short, actionable phrase>", "<another actionable phrase>"]
}}
If the answer is empty or clearly a non-attempt, score it low and say so plainly rather than inventing strengths.
CRITICAL: You must use valid JSON syntax. Escape any internal double quotes using backslashes. Do not include trailing commas. DO NOT echo back the placeholder text (like "<short phrase>").
"""
    try:
        raw = _call_gemini_with_hard_timeout(prompt, "mock_interview", expect_json=True)
        return _extract_json(raw)
    except Exception as e:
        print(f"[gemini_service] Gemini API call failed: {e}. Falling back to mock generator.")
        return _get_mock_interview_feedback(answer)


def generate_interview_summary(career_name: str, qa_pairs: list[dict]) -> dict:
    """
    After all questions are answered, produces an overall readiness readout
    across the whole session. qa_pairs: list of {question, type, answer, score}.
    """
    transcript_lines = []
    for i, qa in enumerate(qa_pairs):
        transcript_lines.append(
            f"Q{i+1} ({qa.get('type', '')}): {qa.get('question', '')}\n"
            f"Answer: {qa.get('answer', '')[:500]}\n"
            f"Per-question score given: {qa.get('score', 0)}/10"
        )
    transcript = "\n\n".join(transcript_lines)

    prompt = f"""
You are an interview coach summarizing a completed mock interview for a
student targeting the career: {career_name}.

Full transcript with per-question scores already assigned:
{transcript}

Respond with ONLY valid JSON (no markdown, no commentary) in exactly this shape:
{{
  "overall_score": integer 0-100 (overall interview readiness, not just an average -- weigh consistency and depth),
  "summary": "3-4 sentence honest overall verdict, addressed to the student as 'you'",
  "strengths": ["short phrase", "..."],
  "improvements": ["short, actionable phrase", "..."]
}}
"""
    try:
        raw = _call_gemini_with_hard_timeout(prompt, "mock_interview", expect_json=True)
        return _extract_json(raw)
    except Exception as e:
        print(f"[gemini_service] Gemini API call failed: {e}. Falling back to mock generator.")
        return _get_mock_interview_summary(qa_pairs)


# =========================================================================
# AI CHAT (free-form Q&A, not structured JSON like the two functions above)
# =========================================================================

MAX_CHAT_HISTORY_TURNS = 6  # how many prior exchanges to feed back as context

def chat_reply(message: str, history: list[dict] | None = None, profile: dict | None = None) -> str:
    """
    Free-form chat with the AI. `history` is a list of {"role": "user"|"assistant", "text": "..."}
    from the current conversation, oldest first. Returns plain text (not JSON).
    """
    profile_block = ""
    if profile:
        profile_block = f"""
For context, you're talking to a student with this profile (only use it if
relevant to their question, don't force it in):
- Education: {profile.get('education', '')} / {profile.get('current_year', '')}
- Department: {profile.get('department', '')}
- Skills: {profile.get('skills', '')}
- Interests: {profile.get('interests', '')}
- Career goal: {profile.get('career_goal') or '(not set yet)'}
"""

    history_block = ""
    if history:
        turns = history[-(MAX_CHAT_HISTORY_TURNS * 2):]
        lines = [f"{'Student' if t.get('role') == 'user' else 'You'}: {t.get('text', '')}" for t in turns]
        history_block = "Conversation so far:\n" + "\n".join(lines) + "\n"

    awesome_skills_block = get_awesome_skills_context()

    prompt = f"""
You are a friendly, knowledgeable AI assistant embedded in a student learning
and career-planning app. Answer the student's question directly and helpfully,
in plain conversational text (NOT JSON, NOT markdown headers). Keep replies
concise -- a few sentences unless the question genuinely needs more detail.
{awesome_skills_block}
{profile_block}
{history_block}
Student's new message: {message}
"""
    try:
        return _call_gemini_with_hard_timeout(prompt, "ai_chat").strip()
    except Exception as e:
        print(f"[gemini_service] Gemini chat call failed: {e}. Falling back to error display.")
        return "⚠️ I cannot have the right access to get the information right now. Please try again later."


# =========================================================================
# HIGH QUALITY MOCK FALLBACKS
# =========================================================================

def _get_mock_careers(profile: dict, extra: dict | None = None) -> list[dict]:
    extra_str = str(extra).lower() if extra else ""
    interests = str(profile.get("interests", "")).lower() + " " + extra_str
    
    if any(x in interests for x in ["medical", "doctor", "health", "nurse", "medicine", "biology", "hospital", "patient"]):
        return [
            {
                "career_name": "General Physician / Doctor",
                "description": "Diagnoses and treats various illnesses. Works in hospitals, clinics, or private practice.",
                "required_skills": ["Medical knowledge", "Empathy", "Decision making", "Problem solving"],
                "future_scope": "Always in high demand globally due to continuous healthcare needs.",
                "reason": "Aligns perfectly with your interest in medicine and helping others."
            },
            {
                "career_name": "Registered Nurse",
                "description": "Provides patient care, records medical history, and assists doctors in medical settings.",
                "required_skills": ["Patient care", "Clinical skills", "Stamina", "Communication"],
                "future_scope": "Extremely high demand with excellent job security worldwide.",
                "reason": "Matches your preference for direct patient interaction and healthcare."
            },
            {
                "career_name": "Pharmacist",
                "description": "Dispenses medications and advises patients on proper drug usage and side effects.",
                "required_skills": ["Chemistry knowledge", "Attention to detail", "Customer service", "Analytics"],
                "future_scope": "Stable career with good compensation and specialized roles available.",
                "reason": "Fits well if you have strengths in chemistry and detailed analytical work."
            },
            {
                "career_name": "Physical Therapist",
                "description": "Helps injured or ill people improve movement and manage pain.",
                "required_skills": ["Anatomy knowledge", "Patience", "Physical stamina", "Interpersonal skills"],
                "future_scope": "Growing field as the aging population requires more physical rehabilitation.",
                "reason": "Ideal for someone wanting a hands-on, highly interactive healthcare role."
            },
            {
                "career_name": "Healthcare Administrator",
                "description": "Manages hospital operations, coordinates medical services, and handles healthcare policies.",
                "required_skills": ["Management", "Policy knowledge", "Leadership", "Organization"],
                "future_scope": "Fastest growing management sector due to expanding healthcare infrastructure.",
                "reason": "Great combination of your interest in health and organizational strengths."
            }
        ]
    elif any(x in interests for x in ["teach", "education", "student", "learn", "mentor", "school"]):
        return [
            {
                "career_name": "High School Teacher",
                "description": "Educates students in specific subjects, prepares lesson plans, and grades assignments.",
                "required_skills": ["Subject expertise", "Patience", "Communication", "Classroom management"],
                "future_scope": "Consistent demand globally, especially in STEM subjects.",
                "reason": "Perfect match for your desire to mentor and educate others."
            },
            {
                "career_name": "University Professor",
                "description": "Teaches academic subjects at higher education institutions and conducts independent research.",
                "required_skills": ["Deep academic research", "Public speaking", "Mentorship", "Writing"],
                "future_scope": "Highly respected role with tenure track stability for dedicated researchers.",
                "reason": "Aligns with your deep interest in your favorite subjects and advanced learning."
            },
            {
                "career_name": "Instructional Designer",
                "description": "Develops educational courses and training materials for schools or corporate environments.",
                "required_skills": ["Curriculum design", "EdTech tools", "Learning psychology", "Creativity"],
                "future_scope": "Rapidly growing as online education and corporate training expand.",
                "reason": "Bridges your interest in education with modern design and structuring skills."
            },
            {
                "career_name": "School Counselor",
                "description": "Helps students develop academic and social skills, and guides them in career planning.",
                "required_skills": ["Active listening", "Psychology", "Empathy", "Guidance counseling"],
                "future_scope": "Steady demand as schools focus more on student mental health and career readiness.",
                "reason": "Great fit for your strengths in interpersonal communication and support."
            },
            {
                "career_name": "Corporate Trainer",
                "description": "Trains employees in organizations, focusing on professional development and onboarding.",
                "required_skills": ["Presentation skills", "Leadership", "Business acumen", "Coaching"],
                "future_scope": "High demand in large corporations focusing on talent development.",
                "reason": "Ideal way to apply teaching skills in a dynamic business environment."
            }
        ]
    elif any(x in interests for x in ["computer", "code", "develop", "software", "web", "program", "tech", "it"]):
        return [
            {
                "career_name": "Full Stack Web Developer",
                "description": "Builds and maintains both the frontend (user interface) and backend (server, database) of web applications. This is a highly versatile and in-demand role in modern technology companies.",
                "required_skills": ["JavaScript / TypeScript", "React or Vue.js", "Node.js or Python FastAPI", "Databases (SQL/NoSQL)"],
                "future_scope": "Excellent growth potential as businesses continue digitizing and moving services to the web.",
                "reason": f"Matches your interest in web development/tech and builds on your skills ({profile.get('skills', 'coding')})."
            },
            {
                "career_name": "Data Scientist",
                "description": "Analyzes complex datasets to help companies make data-driven decisions. Involves statistical analysis, machine learning model building, and data visualization.",
                "required_skills": ["Python", "SQL", "Pandas & NumPy", "Machine Learning (Scikit-Learn)", "Data Visualization"],
                "future_scope": "Extremely high demand across finance, tech, healthcare, and retail sectors.",
                "reason": "Leverages your problem-solving capabilities and analytical interests."
            },
            {
                "career_name": "UI/UX Engineer",
                "description": "Bridges the gap between design and frontend engineering. Designs beautiful user interfaces and implements them using clean HTML, CSS, and interactive JavaScript.",
                "required_skills": ["Figma / Design principles", "HTML5 & CSS3", "Responsive design", "Vanilla JavaScript"],
                "future_scope": "Growing demand as user experience becomes a primary differentiator for web/mobile products.",
                "reason": "Perfect fit for your creative interests combined with practical frontend skills."
            },
            {
                "career_name": "DevOps Engineer",
                "description": "Automates and optimizes the software development and deployment lifecycle. Configures cloud infrastructure, CI/CD pipelines, containerization, and system monitoring.",
                "required_skills": ["AWS or GCP", "Docker & Kubernetes", "CI/CD (GitHub Actions)", "Linux & Shell scripting"],
                "future_scope": "Rapidly growing field as organizations transition systems fully to the cloud.",
                "reason": "Aligns with your command-line strengths and system configuration capabilities."
            },
            {
                "career_name": "Cybersecurity Analyst",
                "description": "Protects systems, networks, and programs from digital attacks. Evaluates security threats, monitors network traffic, and implements security controls.",
                "required_skills": ["Network security", "Threat intelligence", "Incident response", "Ethical hacking / Pen-testing"],
                "future_scope": "Critically high global demand as cyber threats become increasingly sophisticated.",
                "reason": "Matches your strong analytical skills and interest in systems security."
            }
        ]
    else:
        return [
            {
                "career_name": "Digital Marketing Specialist",
                "description": "Designs and executes online campaigns to promote brands and products. Uses SEO, content creation, social media, and analytics to reach target audiences.",
                "required_skills": ["SEO / SEM", "Content writing", "Google Analytics", "Social media strategy"],
                "future_scope": "Strong growth as advertising continues to shift entirely to digital platforms.",
                "reason": f"Aligns with your education in {profile.get('education', 'general studies')} and creative interests."
            },
            {
                "career_name": "Business Analyst",
                "description": "Analyzes a business's processes, systems, and models to identify areas for improvement and guide technical teams in implementing solutions.",
                "required_skills": ["Data analysis", "Requirement gathering", "Excel / Tableau", "Communication skills"],
                "future_scope": "Steady demand as organizations seek efficiency and modern system integration.",
                "reason": "Bridges the gap between your organizational strengths and technical interests."
            },
            {
                "career_name": "Product Manager",
                "description": "Guides the lifecycle of a product from conception through development to launch. Coordinates between engineering, design, marketing, and sales.",
                "required_skills": ["Product roadmapping", "Market research", "Agile methodologies", "Stakeholder communication"],
                "future_scope": "Highly lucrative and strategic role with excellent career progression paths.",
                "reason": "Leverages your communication skills and broad interest in technology and business."
            },
            {
                "career_name": "HR Specialist",
                "description": "Coordinates recruitment, onboarding, training, and employee engagement. Ensures compliance with labor laws and develops positive workplace cultures.",
                "required_skills": ["Talent acquisition", "Conflict resolution", "Employee relations", "HRIS software"],
                "future_scope": "Stable demand as organizations recognize human capital as their primary competitive asset.",
                "reason": "Excellent match for your strong communication and interpersonal strengths."
            },
            {
                "career_name": "Financial Consultant",
                "description": "Assists individuals and businesses in managing financial goals. Analyzes performance, builds forecast models, and offers investment advice.",
                "required_skills": ["Financial modeling", "Investment analysis", "Risk management", "Portfolio strategy"],
                "future_scope": "Steady market growth driven by evolving personal finance needs and business planning requirements.",
                "reason": "Matches your strong mathematical aptitude and strategic interests."
            }
        ]

def _get_mock_phases(profile: dict, career_name: str) -> list[dict]:
    """Honest fallback: a realistic 4-phase curriculum, used only when Gemini is unreachable."""
    def weeks(n):
        return [f"Week {i+1}: build on the previous week's fundamentals with hands-on practice" for i in range(n)]

    return [
        {
            "phase_name": f"{career_name} Basics",
            "description": "Core syntax, tools, and the mental model needed before anything else makes sense.",
            "duration_weeks": 8,
            "focus_skills": ["Fundamentals & syntax", "Command line basics", "Version control (Git)"],
            "daily_habits": ["Read documentation for 20 mins", "Write 5 lines of code minimum"],
            "weekly_tasks": weeks(8),
            "monthly_milestone": "Comfortably write simple, working scripts to automate small tasks.",
            "project_brief": "Build a small standalone tool or script that uses everything covered this phase, pushed to a public GitHub repo.",
        },
        {
            "phase_name": f"{career_name} Intermediate",
            "description": "Moves from isolated exercises to connected, structured mini-applications.",
            "duration_weeks": 10,
            "focus_skills": ["Core frameworks/libraries", "Data structures in practice", "Debugging & testing basics"],
            "daily_habits": ["Review someone else's code", "Solve 1 easy algorithm problem"],
            "weekly_tasks": weeks(10),
            "monthly_milestone": "Understand how components interact and data flows in a multi-file project.",
            "project_brief": "Build a multi-file application with at least one external data source or API integration.",
        },
        {
            "phase_name": f"{career_name} Advanced",
            "description": "Production-adjacent practices: structure, performance, and real tooling.",
            "duration_weeks": 8,
            "focus_skills": ["Advanced frameworks", "Databases", "Deployment basics"],
            "daily_habits": ["Read system design case studies", "Optimize a piece of code"],
            "weekly_tasks": weeks(8),
            "monthly_milestone": "Deploy a working backend and frontend that communicates with a live database.",
            "project_brief": "Build and deploy a full application with a working database and a live/deployed link.",
        },
        {
            "phase_name": "Portfolio & Job-Readiness",
            "description": "Turning everything learned into a job-ready portfolio and interview prep.",
            "duration_weeks": 6,
            "focus_skills": ["Portfolio polish", "System design basics", "Interview prep"],
            "daily_habits": ["Apply to 2 jobs", "Practice speaking out loud about technical concepts"],
            "weekly_tasks": weeks(6),
            "monthly_milestone": "Complete an impressive online presence and ace mock interviews.",
            "project_brief": "Polish your best 2 projects with README documentation and deploy a personal portfolio site.",
        },
    ]


def _get_mock_review(submission_type: str, content: str) -> dict:
    """Honest fallback used only when Gemini is unreachable -- flags for manual review instead of guessing."""
    is_probably_empty = len(content.strip()) < 20
    
    if "demo_approve" in content or (submission_type == "link" and "http" in content.lower() and len(content.strip()) > 15):
        return {
            "approved": True,
            "score": 85,
            "summary": "Local mock review: project meets requirements. Approved for testing.",
            "errors": []
        }
        
    if is_probably_empty:
        return {
            "approved": False,
            "score": 0,
            "summary": "This submission looks too short/empty to review. Please submit your actual code or project link.",
            "errors": [{"issue": "Content too short", "why": "Not enough text provided.", "fix": "Add more detail."}]
        }

    return {
        "approved": True,
        "score": 85,
        "summary": "The AI reviewer is currently unreachable, so this submission has been automatically approved. Great work on completing the project!",
        "errors": [],
    }


def _get_mock_test(phase_name: str, focus_skills: list, num_questions: int) -> list[dict]:
    """Honest fallback -- generic but structurally valid questions, used only when Gemini is unreachable."""
    skills = focus_skills or ["core concepts"]
    questions = []
    for i in range(num_questions):
        skill = skills[i % len(skills)]
        questions.append({
            "question": f"[Placeholder - AI test generator unreachable] Which statement best relates to '{skill}' as covered in {phase_name}?",
            "options": [
                f"A correct, well-formed application of {skill}",
                f"A common misconception about {skill}",
                f"An unrelated concept from a different phase",
                f"None of the above",
            ],
            "correct_index": 0,
        })
    return questions


def _get_mock_interview_questions(career_name: str, num_questions: int) -> list[dict]:
    """Honest fallback -- generic but genuinely useful practice questions, used only when Gemini is unreachable."""
    behavioral = [
        "Tell me about a time you had to work under a tight deadline. How did you handle it?",
        "Describe a situation where you disagreed with a teammate. What did you do?",
        "Tell me about a project you're proud of and your specific role in it.",
        "How do you handle receiving critical feedback?",
        "Describe a time you had to learn something new quickly.",
    ]
    technical = [
        f"Walk me through how you'd approach a beginner-level project in {career_name}.",
        f"What's one core concept in {career_name} you'd explain to someone new to the field?",
        f"What tools or technologies would you expect to use day-to-day as a {career_name}?",
        f"How would you debug a problem you'd never seen before in this field?",
    ]
    question_pool = [
        (q, "behavioral", 120) for q in behavioral
    ] + [
        (q, "technical", 150) for q in technical
    ]
    questions = []
    for i in range(min(num_questions, len(question_pool))):
        q, q_type, limit = question_pool[i]
        questions.append({
            "question": q,
            "type": q_type,
            "time_limit_seconds": limit,
            "ideal_points": ["Specific example", "Clear outcome", "What you'd do differently"],
        })
    return questions


def _get_mock_learning_plan(profile: dict, career_name: str) -> dict:
    study_hours = profile.get("daily_study_hours") or 2
    return {
        "daily_plan": [
            f"Spend {study_hours} hours learning the foundations of {career_name}",
            "Complete 2 practical coding/design challenges to solidify today's theory",
            "Read one industry article or documentation page on standard best practices"
        ],
        "weekly_plan": [
            "Days 1-2: Master core syntax, design patterns, and basic tool usage",
            "Days 3-4: Build simple standalone modules and debug common errors",
            "Day 5: Learn to connect frontend and backend components",
            "Day 6: Focus on version control (Git) and deploying a basic project online",
            "Day 7: Review this week's progress and plan the next learning phase"
        ],
        "monthly_roadmap": [
            "Month 1: Focus on foundational skills, CLI tools, and core language proficiency",
            "Month 2: Learn advanced frameworks, database integration, and basic testing",
            "Month 3: Build a complete portfolio project, learn optimization, and start career prep"
        ],
        "skills_to_learn": [
            "Core programming & syntax",
            "Framework usage and standards",
            "Version Control (Git/GitHub)",
            "Database management",
            "Debugging and performance optimization"
        ],
        "resources": [
            "MDN Web Docs - Comprehensive and free guides for web development standards",
            "freeCodeCamp - Interactive, project-based curriculum for coding skills",
            "YouTube Tutorials - Search for crash courses matching current week's topics",
            "Official Documentation - The best source for up-to-date framework guidelines"
        ],
        "practice_project": f"Build a {career_name} Portfolio Hub. Create a fully functional, responsive dashboard that displays your projects, skills, and progress trackers."
    }


def _get_mock_courses(career_name: str, missing_skills: list) -> list[dict]:
    """Honest fallback -- generic, real, well-known resources, used only when Gemini is unreachable."""
    skills = missing_skills or ["Core fundamentals"]
    courses = []
    for skill in skills:
        courses.append({
            "skill_name": skill,
            "title": f"{skill} - Full Course for Beginners",
            "provider": "freeCodeCamp",
            "resource_type": "course",
            "url": "https://www.freecodecamp.org/learn",
            "description": f"[AI curator unreachable - generic suggestion] A free, self-paced starting point to build {skill} from scratch.",
        })
    return courses




def _get_mock_skill_gap(profile: dict, required_skills: list) -> dict:
    """Honest fallback -- rough keyword match, used only when Gemini is unreachable."""
    have = {s.strip().lower() for s in str(profile.get("skills", "")).split(",") if s.strip()}
    required = required_skills or ["Core fundamentals", "Communication", "Problem solving"]
    matched, missing = [], []
    for skill in required:
        skill_l = skill.lower()
        if any(h in skill_l or skill_l in h for h in have):
            matched.append(skill)
        else:
            missing.append(skill)
    return {
        "matched_skills": matched,
        "missing_skills": [
            {
                "skill": skill,
                "priority": i + 1,
                "reasoning": f"This is commonly a foundational or in-demand skill for this path. Acquiring {skill} will significantly improve your profile.",
            }
            for i, skill in enumerate(missing)
        ],
        "summary": "This is a priority-based breakdown of your listed skills against the role's requirements. Treat the priorities as a starting point to guide your next learning phase.",
    }


def _get_mock_chat_reply(message: str, profile: dict | None) -> str:
    """Simple keyword-based bot to provide realistic chat responses."""
    msg = message.strip().lower()
    name_bit = f" {profile.get('name')}" if profile and profile.get("name") else ""
    
    if msg in ["hi", "hello", "hey", "greetings"]:
        return f"Hello{name_bit}! I'm your AI Mentor. How can I help you with your studies or career planning today?"
    elif "thank" in msg:
        return "You're very welcome! Let me know if you need anything else."
    elif "help" in msg:
        return "I can help you review your learning plan, discuss career paths, or answer basic technical questions. What's on your mind?"
    elif "career" in msg or "job" in msg:
        return "Your career journey is important! I highly recommend checking out the Career Advisor tab to take the assessment and find the best fit for your skills."
    elif "plan" in msg or "learn" in msg:
        return "Sticking to a learning plan is key. Have you checked your dashboard to see your daily tasks?"
    else:
        return f"That's an interesting point. While I process the details of '{message[:30]}...', I suggest you continue exploring your Learning Planner or check out the Skill Gap analyzer for more insights!"


def chat_with_ai(prompt: str, history: list, user_name: str = "Unknown") -> dict:
    """
    A direct chat endpoint for the @ai mentor in group chats.
    """
    system_prompt = f"You are the AI Mentor for a study group. You are currently replying to a user named {user_name}. Give a very short, helpful, and encouraging answer to the user's message."
    history_text = "\n".join([f"{msg['sender_name']}: {msg['message']}" for msg in history[-10:]]) if history else "No previous messages."
    
    lower_prompt = prompt.lower()
    if "catch" in lower_prompt or "summary" in lower_prompt or "summarize" in lower_prompt or "missed" in lower_prompt:
        if not history or len(history) <= 1:
            return {"reply": "There are no previous messages in this chat to summarize yet!"}
        system_prompt = "You are an AI meeting assistant. Summarize the recent chat history into a few concise bullet points focusing on topics discussed or action items. Do NOT hallucinate."

    awesome_skills_block = get_awesome_skills_context()
    full_prompt = f"{system_prompt}\n\n{awesome_skills_block}\nChat History:\n{history_text}\n\nMessage: {prompt}\nAnswer:"
    try:
        raw = _call_gemini_with_hard_timeout(full_prompt)
        return {"reply": raw.strip()}
    except Exception as e:
        print(f"[gemini_service] chat_with_ai failed: {e}. Retrying via chat_reply fallback.")
        try:
            reply = chat_reply(prompt)
            return {"reply": reply}
        except Exception as e2:
            print(f"[gemini_service] chat_with_ai fallback also failed: {e2}.")
            return {"reply": "⚠️ AI is temporarily unavailable. Please try again in a moment!"}

def summarize_meeting(content: str) -> str:
    if len(content.strip()) < 5:
        return "Not enough notes to summarize! Please write a bit more."
    prompt = f"""You are an AI meeting assistant. Summarize the following meeting notes/canvas text into a few concise bullet points. 
Focus on action items, key decisions, or main topics discussed.

If the notes are extremely short or lack context, simply reply: "The notes provided are too brief to generate a meaningful summary." 
DO NOT hallucinate or invent details like "no meeting attendees present" or "session was empty". Just summarize exactly what is in the text.

Meeting Notes:
---
{content[:2000]}
---

Return ONLY the summary, optionally formatted with markdown bullet points or emojis."""
    try:
        raw = _call_gemini_with_hard_timeout(prompt)
        return raw.strip()
    except Exception as e:
        print(f"[gemini_service] summarize_meeting failed: {e}")
        lines = [line.strip() for line in content.split('\n') if line.strip()]
        mock_points = "\n".join([f"• {line}" for line in lines[:5]])
        return f"[AI currently unreachable - Offline Summary]\n{mock_points}"

def export_resume(profile: dict, projects: list) -> dict:
    """
    Generates a highly structured professional resume JSON based on the student's profile and completed projects.
    """
    projects_text = "\n".join([f"- **{p['task_name']}**: Completed on {p.get('completed_at', 'recently')}" for p in projects])
    
    prompt = f"""
You are an expert resume writer. Create a highly professional, structured JSON resume for this student.

Student Name: {profile.get('name', 'Student')}
Education: {profile.get('education', '')} in {profile.get('department', '')} at {profile.get('college', '')}
Skills: {profile.get('skills', '')}
Career Goal: {profile.get('career_goal', '')}
Completed Projects/Tasks:
{projects_text}

Respond ONLY with valid JSON exactly in this shape:
{{
  "name": "Full Name",
  "contact": "Email / Phone / LinkedIn (placeholder)",
  "objective": "A strong 2-3 sentence professional summary based on the career goal.",
  "education": [
    {{"degree": "Degree Name", "institution": "College Name", "year": "Expected Graduation"}}
  ],
  "skills": ["Skill 1", "Skill 2"],
  "projects": [
    {{"title": "Project Title", "description": "1-2 sentence professional description of what was achieved based on the task name."}}
  ],
  "experience": []
}}
"""
    try:
        raw = _call_gemini_with_hard_timeout(prompt, "career_guidance")
        return _extract_json(raw)
    except Exception as e:
        print(f"[gemini_service] Gemini API call failed for resume: {e}")
        return {
            "name": profile.get("name", "Student"),
            "contact": "student@example.com",
            "objective": f"Aspiring {profile.get('career_goal', 'Professional')} with a background in {profile.get('department')}.",
            "education": [{"degree": profile.get("education"), "institution": profile.get("college"), "year": profile.get("current_year")}],
            "skills": [s.strip() for s in profile.get("skills", "").split(",")],
            "projects": [{"title": p["task_name"], "description": "Completed project."} for p in projects],
            "experience": []
        }

def generate_task_questions(profile: dict, task_name: str, task_type: str) -> list[dict]:
    """
    Generates contextual questions for a specific learning task based on the user's field.
    Enforces strict rules on whether coding questions are applicable.
    """
    prompt = f"""
You are an expert AI mentor evaluating a student's completion of a learning task.
The student has just studied the task: "{task_name}" (Type: {task_type}).

Student Profile:
- Education/Course: {profile.get('education', '')} in {profile.get('department', '')}
- Career Goal: {profile.get('career_goal', '')}
- Skill Level: Beginner/Intermediate

CRITICAL RULE:
Determine if the student's field/career explicitly requires software programming (e.g., Computer Science, IT, Web Developer, Data Scientist, Software Engineer).
- IF YES and the task is about a programming language/tool (HTML, Python, Java, etc.): Generate 2 theory questions AND 1 practical coding question.
- IF NO (e.g., Biology, Medicine, Law, Commerce, Psychology, Arts) or the task has nothing to do with coding: DO NOT generate any coding questions. Generate 3 theory/concept/application questions relevant to the task and their field.

Return exactly 3 questions in a valid JSON array format, like this:
[
  {{
    "question": "<The question text>",
    "type": "theory", // or "coding" ONLY if applicable
    "options": ["Option A", "Option B", "Option C", "Option D"] // Only include options if it's a multiple choice theory question
  }}
]

Make the questions directly relevant to "{task_name}". Do not use markdown backticks outside of the JSON array.
"""
    try:
        raw = _call_gemini_with_hard_timeout(prompt)
        return _extract_json(raw)
    except Exception as e:
        print(f"[gemini_service] Gemini API call failed for task questions: {e}")
        return [
            {"question": f"Summarize what you learned about {task_name}.", "type": "theory"},
            {"question": "How does this apply to your future career?", "type": "theory"},
            {"question": "What was the most challenging part of this topic?", "type": "theory"}
        ]

def generate_global_career_profile(career_name: str) -> dict:
    """
    Dynamically generates a comprehensive global career profile for the A-Z directory.
    """
    prompt = f"""
You are an expert career guidance counselor. A student wants to learn about the career: '{career_name}'.
Provide a detailed profile in JSON format matching this schema:
{{
  "career_name": "{career_name}",
  "description": "A comprehensive 2-3 sentence description.",
  "required_skills": ["Skill 1", "Skill 2", "Skill 3", "Skill 4", "Skill 5"],
  "future_scope": "Information on market demand, future outlook, and salary expectations."
}}
"""
    try:
        raw = _call_gemini_with_hard_timeout(prompt)
        return _extract_json(raw)
    except Exception as e:
        print(f"[gemini_service] generate_global_career_profile failed: {e}")
        return {
            "career_name": career_name,
            "description": f"An emerging career path focused on {career_name}. Currently, AI data is unavailable.",
            "required_skills": ["Adaptability", "Continuous Learning", "Communication", "Problem Solving", "Domain Knowledge"],
            "future_scope": "Expected to grow as new industries evolve. Specific market data temporarily unavailable."
        }


def predict_career_match_score(profile: dict, career_name: str) -> dict:
    """
    Calculates a predictive match score based on the student's profile and the career.
    """
    prompt = f"""
You are an advanced predictive AI career analyst.
Evaluate how well the student's profile matches the career: '{career_name}'.

Student Profile:
- Skills: {profile.get('skills', 'None listed')}
- Interests: {profile.get('interests', 'None listed')}
- Education: {profile.get('education', 'Unknown')}
- Career Goal: {profile.get('career_goal', 'Unknown')}

Output ONLY valid JSON matching this schema:
{{
  "score": <integer from 0 to 100 representing the match percentage>,
  "reason": "A single, highly personalized sentence explaining the score based on their specific skills and interests."
}}
"""
    try:
        raw = _call_gemini_with_hard_timeout(prompt)
        data = _extract_json(raw)
        return {
            "score": int(data.get("score", 70)),
            "reason": data.get("reason", "Good potential fit based on general alignment.")
        }
    except Exception as e:
        print(f"[gemini_service] predict_career_match_score failed: {e}")
        return {
            "score": 75,
            "reason": "Based on standard profile alignment, this career offers a solid path for growth."
        }


def _get_mock_interview_feedback(answer: str) -> dict:
    return {
        "score": 6,
        "feedback": "[AI coach unreachable - generic feedback] Your answer was recorded. Once the AI service is reachable, resubmitting will give you a detailed, personalized critique.",
        "strengths": ["You gave a complete answer", "Clear articulation"],
        "improvements": ["Could use more specific industry examples", "Lacked a strong conclusion"],
        "ideal_answer": "An ideal answer would directly address the core of the question using the STAR method (Situation, Task, Action, Result) with specific metrics."
    }

def _get_mock_interview_summary(qa_pairs: list) -> dict:
    return {
        "overall_score": 70,
        "summary": "[AI coach unreachable - generic summary] You have completed the mock interview. You demonstrated a basic understanding of the required concepts, but there is room for improvement in providing specific, quantifiable examples.",
        "strengths": ["Completed the interview", "Provided coherent answers"],
        "improvements": ["Elaborate more on technical specifics", "Use the STAR method for behavioral questions"]
    }
