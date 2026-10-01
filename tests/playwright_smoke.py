import os
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1] / 'frontend' / 'pages'
BASE_URL = os.getenv('APP_BASE_URL')

def file_url(page_path: Path) -> str:
    if BASE_URL:
        return f"{BASE_URL}/{page_path.name}"
    return page_path.resolve().as_uri()

def login(page):
    login_url = f"{BASE_URL}/login.html" if BASE_URL else ROOT / 'login.html'
    if BASE_URL:
        page.goto(login_url, wait_until='domcontentloaded')
    else:
        page.goto(str(login_url), wait_until='domcontentloaded')

    page.fill('#email', 'demo@student.com')
    page.fill('#password', 'demo1234')
    page.click('#submitBtn')
    page.wait_for_url(f"{BASE_URL}/dashboard.html" if BASE_URL else 'dashboard.html', timeout=5000)

    return page


def check_page(url, checks):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        if BASE_URL:
            login(page)
        page.goto(url, wait_until='networkidle')
        if BASE_URL:
            page.wait_for_load_state('networkidle', timeout=5000)
        for desc, selector in checks:
            try:
                page.wait_for_selector(selector, timeout=1000, state='attached')
                print(f"{url} - {desc}: FOUND")
            except Exception:
                print(f"{url} - {desc}: MISSING")
                try:
                    content = page.content()
                    snippet = content[:1000].replace('\n',' ')
                    print(f"PAGE SNIPPET: {snippet}...")
                except Exception as e:
                    print(f"Could not read page content: {e}")
        browser.close()

def main():
    pages = [
        ('group-chat', ROOT / 'group-chat.html', [
            ('groups list', '#groupsUl'),
            ('create group input', '#newGroupName'),
            ('create button', '#btnCreateGroup'),
        ]),
        ('video-meet', ROOT / 'video-meet.html', [
            ('room input', '#roomNameInput'),
            ('join button', '#btnJoinMeet'),
            ('jitsi container', '#jitsi-container'),
        ]),
        ('mock-interview', ROOT / 'mock-interview.html', [
            ('start button', '#startBtn'),
            ('question card', '#questionCard'),
        ]),
    ]

    for name, path, checks in pages:
        if not path.exists():
            print(f"SKIP {name}: {path} not found")
            continue
        url = file_url(path)
        check_page(url, checks)

if __name__ == '__main__':
    main()
