import requests

import os
key = os.environ.get("OPENROUTER_API_KEY", "your-api-key-here")
url = "https://openrouter.ai/api/v1/chat/completions"

headers = {
    "Authorization": f"Bearer {key}",
    "Content-Type": "application/json"
}

data = {
    "model": "meta-llama/llama-3.1-8b-instruct:free",
    "messages": [{"role": "user", "content": "Output {\"status\": \"ok\"}"}]
}

try:
    r = requests.post(url, headers=headers, json=data)
    print("Status:", r.status_code)
    print("Response:", r.text)
except Exception as e:
    print(e)
