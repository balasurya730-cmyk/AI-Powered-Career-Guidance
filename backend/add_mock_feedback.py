import sys
filepath = r"c:\Users\acer\Videos\0.1\fixedclaude\rkle\backend\gemini_service.py"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

if "def _get_mock_interview_feedback" in content:
    print("Already exists.")
    sys.exit(0)

mock_func = """

def _get_mock_interview_feedback(answer: str) -> dict:
    return {
        "score": 6,
        "feedback": "[AI coach unreachable - generic feedback] Your answer was recorded. Once the AI service is reachable, resubmitting will give you a detailed, personalized critique.",
        "strengths": ["You gave a complete answer", "Clear articulation"],
        "weaknesses": ["Could use more specific industry examples", "Lacked a strong conclusion"],
        "ideal_answer": "An ideal answer would directly address the core of the question using the STAR method (Situation, Task, Action, Result) with specific metrics."
    }
"""

with open(filepath, "a", encoding="utf-8") as f:
    f.write(mock_func)

print("Added mock feedback function.")
