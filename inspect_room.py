import json
import sqlite3
import sys
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
db.row_factory = sqlite3.Row
room = db.execute("select id,state_json,revision,updated_at from rooms where id='VPAW80'").fetchone()
if not room:
    print("missing VPAW80")
    raise SystemExit
state = json.loads(room["state_json"])
print("room", room["id"], "revision", room["revision"], "messages", len(state.get("chatMessages", [])))
for p in db.execute("select id,name,role,player_id,device_id,created_at,last_seen_at from participants where room_id='VPAW80'"):
    print(dict(p))
print("last messages")
for m in state.get("chatMessages", [])[-8:]:
    print(json.dumps({k: m.get(k) for k in ("id","speakerId","speakerName","role","visibility","text","time")}, ensure_ascii=False)[:500])
