import os, re
html_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'frontend', 'pages')
html_files = [f for f in os.listdir(html_dir) if f.endswith('.html')]
for f in html_files:
    with open(os.path.join(html_dir, f), encoding='utf-8') as file:
        content = file.read()
    for m in re.finditer(r'href=["\']([^"\']+\.html)["\']', content):
        target = m.group(1).split('#')[0].split('?')[0]
        if target not in html_files and target != 'mentor-dashboard.html':
            print(f'Broken link in {f}: {target}')
