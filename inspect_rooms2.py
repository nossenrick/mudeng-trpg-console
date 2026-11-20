import json
import sqlite3
import sys
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
db.row_factory = sqlite3.Row
for room in db.execute("select id,name,revision,updated_at from rooms order by updated_at desc"):
    state = json.loads(db.execute("select state_json from rooms where id=?", (room["id"],)).fetchone()[0])
    players = [(p.get("id"), p.get("name"), p.get("originCharacterId")) for p in state.get("players", [])]
    gm = db.execute("select id,name,role,player_id,device_id,last_seen_at from participants where room_id=? and role='gm'", (room["id"],)).fetchone()
    sys.stdout.buffer.write((f"{room['id']} {room['name']} rev={room['revision']} updated={room['updated_at']} players={players} gm={dict(gm) if gm else None}\n").encode("utf-8"))
