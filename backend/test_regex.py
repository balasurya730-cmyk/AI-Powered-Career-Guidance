import re
import ast
import json
import sys

def test_json():
    text = "{\n  \"score\": 6,\n  \"feedback\": \"Good job.\",\n}"
    cleaned = re.sub(r',\s*([\]}])', r'\1', text)
    print(json.loads(cleaned))

if __name__ == "__main__":
    test_json()
