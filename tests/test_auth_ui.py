import os, re
_frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'frontend')
js_file = os.path.join(_frontend_dir, 'js', 'auth.js')
with open(js_file, encoding='utf-8') as f:
    content = f.read()
ids = set(re.findall(r'getElementById\([\'\"](.*?)[\'\"]\)', content))

html_files = [
    os.path.join(_frontend_dir, 'pages', 'login.html'),
    os.path.join(_frontend_dir, 'pages', 'register.html'),
    os.path.join(_frontend_dir, 'pages', 'forgot-password.html'),
    os.path.join(_frontend_dir, 'pages', 'reset-password.html'),
]

all_html = ""
for html_path in html_files:
    try:
        with open(html_path, encoding='utf-8') as f:
            all_html += f.read()
    except FileNotFoundError:
        pass

for id_ in ids:
    if f'id="{id_}"' not in all_html and f"id='{id_}'" not in all_html:
        print(f'Missing ID: {id_} in any auth page')
