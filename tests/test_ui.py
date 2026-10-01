import os, re

_frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'frontend')
js_dir = os.path.join(_frontend_dir, 'js')
html_dir = os.path.join(_frontend_dir, 'pages')

for js_file in os.listdir(js_dir):
    if not js_file.endswith('.js'): continue
    with open(os.path.join(js_dir, js_file), encoding='utf-8') as f:
        content = f.read()
    ids = re.findall(r'getElementById\([\'\"](.*?)[\'\"]\)', content)
    if not ids: continue
    
    html_file = js_file.replace('.js', '.html')
    if js_file == 'career.js': html_file = 'career-advisor.html'
    if js_file == 'planner.js': html_file = 'learning-planner.html'
    if js_file == 'interview.js': html_file = 'mock-interview.html'
    
    # auth.js applies to multiple files, so let's skip it here and check it manually if needed
    if js_file == 'auth.js' or js_file == 'api.js': continue 
    
    html_path = os.path.join(html_dir, html_file)
    if not os.path.exists(html_path):
        print(f'{js_file} -> {html_file} NOT FOUND')
        continue
    with open(html_path, encoding='utf-8') as f:
        html_content = f.read()
    
    for id_ in set(ids):
        if f'id="{id_}"' not in html_content and f"id='{id_}'" not in html_content:
            print(f'Missing ID: {id_} in {html_file} (from {js_file})')
