import json
import sqlite3
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
db.row_factory = sqlite3.Row
state_row = db.execute("select state_json from rooms where id='VPAW80'").fetchone()
snap_row = db.execute("select state_json from room_snapshots where room_id='VPAW80' and revision=124 order by created_at desc limit 1").fetchone()
state = json.loads(state_row["state_json"])
snap = json.loads(snap_row["state_json"])
print("current players", [(p.get("id"), p.get("name"), p.get("originCharacterId")) for p in state.get("players", [])])
print("snapshot players", [(p.get("id"), p.get("name"), p.get("originCharacterId")) for p in snap.get("players", [])])
print("tokens", state.get("map", {}).get("tokens"))
print("participants", [dict(r) for r in db.execute("select id,player_id,name from participants where room_id='VPAW80'")])
