import sys
import os
sys.path.append(os.path.dirname(__file__))
import gemini_service

try:
    print(gemini_service._call_gemini("hi", "ai_chat"))
except Exception as e:
    print("Error:", e)
