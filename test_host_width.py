import json
import sqlite3
from pathlib import Path
from playwright.sync_api import sync_playwright

db=sqlite3.connect(Path("trpg.sqlite3")); db.row_factory=sqlite3.Row
room_id="EEYLYT"
r=db.execute("select id,name,revision from rooms where id=?", (room_id,)).fetchone()
p=db.execute("select * from participants where room_id=? and role='gm'", (room_id,)).fetchone()
if not r or not p:
    raise SystemExit("host room missing")
with sync_playwright() as pw:
 b=pw.chromium.launch(headless=True, executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe")
 page=b.new_page(viewport={"width":1806,"height":965})
 page.route("**/unpkg.com/**", lambda x:x.abort()); page.route("**/cdn.jsdelivr.net/**", lambda x:x.abort()); page.route("**/cdnjs.cloudflare.com/**", lambda x:x.abort())
 page.goto("http://127.0.0.1:8000/", wait_until="commit")
 page.evaluate("([r,d])=>{localStorage.setItem('trpg-room-session-v1',JSON.stringify(r));localStorage.setItem('trpg-device-session-v1',JSON.stringify(d));}", [{"roomId":r["id"],"roomName":r["name"],"revision":r["revision"],"participantId":p["id"],"role":"gm","playerId":"","name":p["name"],"token":p["token"]},{"deviceId":p["device_id"],"name":p["name"]}])
 page.reload(wait_until="commit"); page.wait_for_timeout(3000)
 print("scroll", page.evaluate("[document.documentElement.scrollWidth,document.documentElement.clientWidth,document.documentElement.scrollHeight,document.documentElement.clientHeight]"))
 print("grid", page.evaluate("getComputedStyle(document.querySelector('.workspace')).gridTemplateColumns"))
 print("cmd", page.evaluate("(()=>{const r=document.querySelector('.command-panel').getBoundingClientRect();return [r.x,r.y,r.width,r.height]})()"))
 print("chat", page.evaluate("(()=>{const r=document.querySelector('.host-chat-column').getBoundingClientRect();return [r.x,r.y,r.width,r.height]})()"))
 page.screenshot(path="host_width_balanced.png", full_page=False)
 b.close()
