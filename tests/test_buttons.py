import os, re
html_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'frontend', 'pages')
buttons = []
for f in os.listdir(html_dir):
    if not f.endswith('.html'): continue
    with open(os.path.join(html_dir, f), encoding='utf-8') as file:
        content = file.read()
    for m in re.finditer(r'<button[^>]*id=["\']([^"\']+)["\'][^>]*>', content):
        buttons.append((f, m.group(1)))
print("Found buttons:")
for b in buttons:
    print(f"  {b[0]}: {b[1]}")
