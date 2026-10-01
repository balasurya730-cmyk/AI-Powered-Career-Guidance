import os, re
js_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'frontend', 'js')
api_calls = set()
for f in os.listdir(js_dir):
    if not f.endswith('.js'): continue
    with open(os.path.join(js_dir, f), encoding='utf-8') as file:
        for m in re.finditer(r'apiRequest\(["\']([^"\']+)["\']', file.read()):
            api_calls.add(m.group(1))

with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'backend', 'main.py'), encoding='utf-8') as file:
    main_py = file.read()

print('Missing endpoints:')
for endpoint in api_calls:
    path = endpoint.split('?')[0].split(' + ')[0].strip()  # strip query string / string-concat leftovers
    if f'"{path}"' not in main_py and f"'{path}'" not in main_py:
        print(endpoint)
