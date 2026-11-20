from playwright.sync_api import sync_playwright
import json

with sync_playwright() as p:
    b = p.chromium.launch(headless=True, executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    page = b.new_page()
    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.on("console", lambda msg: errors.append(f"console:{msg.type}:{msg.text}") if msg.type == "error" else None)
    page.route("**/unpkg.com/**", lambda route: route.abort())
    page.route("**/cdn.jsdelivr.net/**", lambda route: route.abort())
    page.route("**/cdnjs.cloudflare.com/**", lambda route: route.abort())
    page.goto("http://127.0.0.1:8000/", wait_until="commit", timeout=10000)
    page.wait_for_timeout(5000)
    print("title", page.title())
    print("body", page.locator("body").inner_text()[:300].replace("\n", " | "))
    print("errors", errors[:10])
    b.close()
