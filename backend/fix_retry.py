import sys

filepath = r"c:\Users\acer\Videos\0.1\fixedclaude\rkle\backend\gemini_service.py"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

old_block = """    failures = []
    for provider_name, api_format, url, model, api_key in providers:
        try:
            if api_format == "google":
                response = requests.post(
                    url.format(model=model),
                    params={"key": api_key},
                    json={"contents": [{"parts": [{"text": prompt}]}]},
                    timeout=8,
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
                        "temperature": 0.7,
                        "max_tokens": 2048,
                    },
                    timeout=8,
                )
            if response.status_code != 200:
                raise RuntimeError(f"HTTP {response.status_code}: {response.text[:500]}")
            data = response.json()
            if api_format == "google":
                return data["candidates"][0]["content"]["parts"][0]["text"]
            return data["choices"][0]["message"]["content"]
        except Exception as error:
            failures.append(f"{provider_name}: {error}")"""

new_block = """    import time
    failures = []
    for provider_name, api_format, url, model, api_key in providers:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if api_format == "google":
                    response = requests.post(
                        url.format(model=model),
                        params={"key": api_key},
                        json={"contents": [{"parts": [{"text": prompt}]}]},
                        timeout=8,
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
                            "temperature": 0.7,
                            "max_tokens": 2048,
                        },
                        timeout=8,
                    )
                if response.status_code == 429 and attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                if response.status_code != 200:
                    raise RuntimeError(f"HTTP {response.status_code}: {response.text[:500]}")
                data = response.json()
                if api_format == "google":
                    return data["candidates"][0]["content"]["parts"][0]["text"]
                return data["choices"][0]["message"]["content"]
            except Exception as error:
                if "429" in str(error) and attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                failures.append(f"{provider_name}: {error}")
                break"""

if old_block not in content:
    print("Could not find the block to replace!")
    sys.exit(1)

content = content.replace(old_block, new_block)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("Successfully added retry logic!")
