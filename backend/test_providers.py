import os
import requests
from dotenv import load_dotenv

load_dotenv()

# Match the logic in gemini_service.py
NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "deepseek-ai/deepseek-v4-flash-0731")
GOOGLE_GENERATE_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

nvidia_key = os.getenv("NVIDIA_API_KEY")
gemini_key = os.getenv("GEMINI_API_KEY")
gemma_key = os.getenv("GEMMA_API_KEY")
openrouter_key = os.getenv("OPENROUTER_API_KEY")
cohere_key = os.getenv("COHERE_API_KEY")
z_ai_key = os.getenv("Z_AI_API_KEY")
poolside_key = os.getenv("POOLSIDE_API_KEY")
inglink_key = os.getenv("INGLINK_API_KEY")
liquid_key = os.getenv("LIQUID_API_KEY")

providers = []
if openrouter_key and not openrouter_key.startswith("your_"):
    providers.append(("OpenRouter", "openai", OPENROUTER_URL, os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-chat-v3-0324:free"), openrouter_key))
if gemini_key and not gemini_key.startswith("your_"):
    providers.append(("Gemini", "google", GOOGLE_GENERATE_URL, os.getenv("GEMINI_MODEL", "gemini-2.0-flash"), gemini_key))
if gemma_key and not gemma_key.startswith("your_"):
    if gemma_key.startswith("sk-or"):
        providers.append(("Gemma (OpenRouter)", "openai", OPENROUTER_URL, os.getenv("GEMMA_MODEL", "google/gemma-3-27b-it"), gemma_key))
    else:
        providers.append(("Gemma", "google", GOOGLE_GENERATE_URL, os.getenv("GEMMA_MODEL", "gemma-3-27b-it"), gemma_key))
if cohere_key and not cohere_key.startswith("your_"):
    providers.append(("Cohere (OpenRouter)", "openai", OPENROUTER_URL, os.getenv("COHERE_MODEL", "cohere/command-r-plus"), cohere_key))
if z_ai_key and not z_ai_key.startswith("your_"):
    providers.append(("Z.AI (OpenRouter)", "openai", OPENROUTER_URL, os.getenv("Z_AI_MODEL", "x-ai/grok-2"), z_ai_key))
if poolside_key and not poolside_key.startswith("your_"):
    providers.append(("Poolside (OpenRouter)", "openai", OPENROUTER_URL, os.getenv("POOLSIDE_MODEL", "poolside/poolside-model"), poolside_key))
if inglink_key and not inglink_key.startswith("your_"):
    providers.append(("Inglink (OpenRouter)", "openai", OPENROUTER_URL, os.getenv("INGLINK_MODEL", "liquid/lfm-40b"), inglink_key))
if liquid_key and not liquid_key.startswith("your_"):
    providers.append(("Liquid (OpenRouter)", "openai", OPENROUTER_URL, os.getenv("LIQUID_MODEL", "liquid/lfm-40b"), liquid_key))
if nvidia_key and not nvidia_key.startswith("your_"):
    providers.append(("NVIDIA", "openai", NVIDIA_URL, os.getenv("NVIDIA_MODEL", NVIDIA_MODEL), nvidia_key))

print(f"Found {len(providers)} providers to test.\\n")

for provider_name, api_format, url, model, api_key in providers:
    print(f"Testing {provider_name} (Model: {model})...")
    prompt = f"Say exactly 'Hello from {provider_name}' and nothing else."
    try:
        if api_format == "google":
            response = requests.post(
                url.format(model=model),
                params={"key": api_key},
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=15,
            )
        else:
            response = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 50,
                },
                timeout=15,
            )
        
        if response.status_code == 200:
            data = response.json()
            if api_format == "google":
                result = data["candidates"][0]["content"]["parts"][0]["text"]
            else:
                result = data["choices"][0]["message"]["content"]
            print(f"SUCCESS! Response: {result.strip()}\\n")
        else:
            print(f"FAILED! HTTP {response.status_code}: {response.text[:200]}\\n")
    except Exception as e:
        print(f"FAILED! Error: {e}\\n")
