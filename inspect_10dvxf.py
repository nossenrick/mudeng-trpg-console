import json
import sqlite3
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
db.row_factory = sqlite3.Row
room = db.execute("select id,name,state_json,revision from rooms where id='10DVXF'").fetchone()
state = json.loads(room["state_json"])
print("players", [(p.get("id"), p.get("name"), p.get("originCharacterId")) for p in state.get("players", [])])
print("tokens", state.get("map", {}).get("tokens"))
for row in db.execute("select id,name,role,player_id,account_id,device_id,last_seen_at from participants where room_id='10DVXF'"):
    print(dict(row))
