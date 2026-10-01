import sys
import os

filepath = r"c:\Users\acer\Videos\0.1\fixedclaude\rkle\backend\gemini_service.py"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

start_str = "def _get_mock_interview_questions(career_name: str, num_questions: int) -> list[dict]:"
end_str = "def _get_mock_courses("

start_idx = content.find(start_str)
end_idx = content.find(end_str)

if start_idx == -1 or end_idx == -1:
    print("Could not find start or end index.")
    sys.exit(1)

correct_code = """def _get_mock_interview_questions(career_name: str, num_questions: int) -> list[dict]:
    \"\"\"Honest fallback -- generic but genuinely useful practice questions, used only when Gemini is unreachable.\"\"\"
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


"""

new_content = content[:start_idx] + correct_code + content[end_idx:]

with open(filepath, "w", encoding="utf-8") as f:
    f.write(new_content)

print("Successfully fixed gemini_service.py")
