import json
import sqlite3
from pathlib import Path
from playwright.sync_api import sync_playwright

DB = Path(r"F:\codex备份\跑团\trpg.sqlite3")
BASE = "http://127.0.0.1:8000/"
db = sqlite3.connect(DB); db.row_factory = sqlite3.Row
room = db.execute("select id,name,revision from rooms where id='VPAW80'").fetchone()
participant = db.execute("select * from participants where room_id='VPAW80' and role='gm'").fetchone()

result = {}
with sync_playwright() as p:
    b = p.chromium.launch(headless=True, executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    ctx = b.new_context(accept_downloads=True)
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.on("console", lambda msg: errors.append(f"{msg.type}:{msg.text}") if msg.type == "error" else None)
    page.route("**/unpkg.com/**", lambda route: route.abort())
    page.route("**/cdn.jsdelivr.net/**", lambda route: route.abort())
    page.route("**/cdnjs.cloudflare.com/**", lambda route: route.abort())
    page.goto(BASE, wait_until="commit", timeout=10000)
    page.evaluate("""([room, device]) => {
      localStorage.setItem('trpg-room-session-v1', JSON.stringify(room));
      localStorage.setItem('trpg-device-session-v1', JSON.stringify(device));
    }""", [{
        "roomId": room["id"], "roomName": room["name"], "revision": room["revision"],
        "participantId": participant["id"], "role": "gm", "playerId": "",
        "name": participant["name"], "token": participant["token"],
    }, {"deviceId": participant["device_id"], "name": participant["name"]}])
    page.reload(wait_until="commit", timeout=10000)
    page.wait_for_timeout(4000)
    result["title"] = page.title()
    result["roomStatus"] = page.evaluate("document.querySelector('#roomStatus')?.textContent || ''")
    result["ruleMode"] = page.evaluate("document.body.dataset.ruleMode")
    result["buttonCount"] = page.evaluate("document.querySelectorAll('button').length")
    result["draft"] = page.evaluate("""() => { const b=document.querySelector('#draftButton'); if(!b) return 'missing'; b.click(); return document.querySelector('#draftText')?.textContent?.slice(0,100) || ''; }""")
    result["npcLine"] = page.evaluate("""() => { const b=document.querySelector('#npcLineButton'); if(!b) return 'missing'; b.click(); return document.querySelector('#draftText')?.textContent?.slice(0,100) || ''; }""")
    result["command"] = page.evaluate("""() => { const f=document.querySelector('#gmChatForm'); const i=f?.querySelector('[name=message]'); if(!f||!i) return 'missing'; i.value='$帮助'; f.requestSubmit(); return document.querySelector('#aiStatus')?.textContent || ''; }""")
    result["transcriptButton"] = page.evaluate("Boolean(document.querySelector('#downloadTranscriptButton'))")
    result["errors"] = errors[:20]
    Path(r"F:\codex备份\跑团\browser_selftest_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    b.close()
