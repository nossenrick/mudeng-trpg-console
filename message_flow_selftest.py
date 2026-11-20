import json
import sqlite3
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

DB = Path(r"F:\codex备份\跑团\trpg.sqlite3")
API = "http://127.0.0.1:8000"

def req(path, method="GET", body=None, token="", participant=""):
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    url = f"{API}{path}"
    if participant:
        sep = "&" if "?" in url else "?"
        url += f"{sep}participant_id={urllib.parse.quote(participant)}"
    r = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json", "X-Participant-Token": token})
    with urllib.request.urlopen(r, timeout=10) as response:
        return response.status, json.loads(response.read().decode())

import urllib.parse
# clone current room state but empty chat/log
db = sqlite3.connect(DB); db.row_factory = sqlite3.Row
current = json.loads(db.execute("select state_json from rooms where id='VPAW80'").fetchone()["state_json"])
state = json.loads(json.dumps(current, ensure_ascii=False))
state["chatMessages"] = []
state["logs"] = []
state["storyEvents"] = []
state["chapterMemories"] = []
state["aiControl"] = {"enabled": False, "paused": True, "busy": False, "mode": "assist", "lastError": "", "queue": [], "activeQueueId": ""}
state["aiPlayer"] = {"enabled": False, "running": False, "paused": True, "pendingReaction": False}
host_device = "device_selftest_host"
player_device = "device_selftest_player"
status, created = req("/api/rooms", "POST", {"name": "SELFTEST", "host_name": "测试主持", "device_id": host_device, "state": state})
room = created["room"]; host = created["participant"]
room_id = room["id"]
player_source = current["players"][1]
status, joined = req(f"/api/rooms/{room_id}/join", "POST", {"name": "测试玩家", "player_id": player_source["id"], "character_snapshot": player_source, "device_id": player_device})
player = joined["participant"]
print("created", room_id, "host", host["id"], "player", player["id"])

room_session_host = {"roomId": room_id, "roomName": "SELFTEST", "revision": created["room"]["revision"], "participantId": host["id"], "role": "gm", "playerId": "", "name": "测试主持", "token": host["token"]}
room_session_player = {"roomId": room_id, "roomName": "SELFTEST", "revision": joined["room"]["revision"], "participantId": player["id"], "role": "player", "playerId": player["playerId"], "name": "测试玩家", "token": player["token"]}

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    def make_context(room_session):
        ctx = browser.new_context()
        page = ctx.new_page()
        page.route("**/unpkg.com/**", lambda route: route.abort())
        page.route("**/cdn.jsdelivr.net/**", lambda route: route.abort())
        page.route("**/cdnjs.cloudflare.com/**", lambda route: route.abort())
        page.goto(API, wait_until="commit")
        page.evaluate("([r,d])=>{localStorage.setItem('trpg-room-session-v1',JSON.stringify(r));localStorage.setItem('trpg-device-session-v1',JSON.stringify(d));}", [room_session, {"deviceId": host_device if room_session["role"]=="gm" else player_device, "name": "selftest"}])
        page.reload(wait_until="commit")
        page.wait_for_timeout(2500)
        return page
    host_page = make_context(room_session_host)
    player_page = make_context(room_session_player)
    player_page.locator("#playerChatForm [name=message]").fill("测试玩家消息：我们走吗？")
    player_page.locator("#playerChatForm button[type=submit]").click()
    player_page.wait_for_timeout(1500)
    host_page.wait_for_timeout(3000)
    host_text = host_page.locator("#gmChatFeed").inner_text()
    print("player_status", player_page.locator("#roomStatus").inner_text())
    print("host_contains", "测试玩家消息" in host_text)
    print("host_tail", host_text[-300:])
    browser.close()

# inspect DB and clean test room
db = sqlite3.connect(DB)
row = db.execute("select state_json from rooms where id=?", (room_id,)).fetchone()
if row:
    s = json.loads(row[0])
    print("server_messages", len(s.get("chatMessages", [])))
db.execute("delete from participants where room_id=?", (room_id,))
db.execute("delete from action_requests where room_id=?", (room_id,))
db.execute("delete from room_snapshots where room_id=?", (room_id,))
db.execute("delete from rooms where id=?", (room_id,))
db.commit()
print("cleaned", room_id)
