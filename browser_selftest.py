import json
import sqlite3
from pathlib import Path
from playwright.sync_api import sync_playwright

DB = Path(r"F:\codex备份\跑团\trpg.sqlite3")
BASE = "http://127.0.0.1:8000/"

db = sqlite3.connect(DB)
db.row_factory = sqlite3.Row
room = db.execute("select id,name,revision from rooms where id='VPAW80'").fetchone()
participant = db.execute("select * from participants where room_id='VPAW80' and role='gm'").fetchone()
device = db.execute("select * from devices where id=?", (participant["device_id"],)).fetchone()

room_session = {
    "roomId": room["id"],
    "roomName": room["name"],
    "revision": room["revision"],
    "participantId": participant["id"],
    "role": "gm",
    "playerId": "",
    "name": participant["name"],
    "token": participant["token"],
}
device_session = {"deviceId": participant["device_id"], "name": device["name"] if device else participant["name"]}

errors = []
result = {"console": [], "pageErrors": [], "smoke": [], "buttons": {}, "downloads": []}

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    context = browser.new_context(accept_downloads=True)
    page = context.new_page()
    page.route("**/unpkg.com/**", lambda route: route.abort())
    page.route("**/cdn.jsdelivr.net/**", lambda route: route.abort())
    page.route("**/cdnjs.cloudflare.com/**", lambda route: route.abort())
    page.on("console", lambda msg: errors.append(f"console {msg.type}: {msg.text}") if msg.type == "error" else None)
    page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))
    page.goto(BASE, wait_until="commit")
    page.evaluate("([room, device]) => { localStorage.setItem('trpg-room-session-v1', JSON.stringify(room)); localStorage.setItem('trpg-device-session-v1', JSON.stringify(device)); }", [room_session, device_session])
    page.reload(wait_until="commit")
    page.wait_for_timeout(5000)
    result["title"] = page.title()
    result["room_status"] = page.locator("#roomStatus").inner_text() if page.locator("#roomStatus").count() else ""
    result["body_rule"] = page.evaluate("document.body.dataset.ruleMode")
    result["button_count"] = page.locator("button").count()
    # Existing internal smoke test
    try:
        result["smoke"] = page.evaluate("async () => await runUiSmokeTest()")
    except Exception as exc:
        result["smoke_error"] = str(exc)
    page.wait_for_timeout(500)
    # Draft button
    try:
        page.locator("#draftButton").click()
        page.wait_for_timeout(200)
        result["buttons"]["draft"] = page.locator("#draftText").inner_text()[:120]
    except Exception as exc:
        result["buttons"]["draft"] = f"FAIL {exc}"
    # NPC line
    try:
        page.locator("#npcLineButton").click()
        page.wait_for_timeout(200)
        result["buttons"]["npcLine"] = page.locator("#draftText").inner_text()[:120]
    except Exception as exc:
        result["buttons"]["npcLine"] = f"FAIL {exc}"
    # Download transcript
    try:
        with page.expect_download(timeout=5000) as dl:
            page.locator("#downloadTranscriptButton").click()
        download = dl.value
        result["downloads"].append(download.suggested_filename)
    except Exception as exc:
        result["downloads"].append(f"FAIL {exc}")
    # Command $帮助 through GM form
    try:
        page.locator("#gmChatForm [name=message]").fill("$帮助")
        page.locator("#gmChatForm button[type=submit]").click()
        page.wait_for_timeout(300)
        result["buttons"]["commandHelp"] = page.locator("#aiStatus").inner_text()[:120]
    except Exception as exc:
        result["buttons"]["commandHelp"] = f"FAIL {exc}"
    result["errors"] = errors[:30]
    browser.close()

Path(r"F:\codex备份\跑团\browser_selftest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False, indent=2)[:6000])
