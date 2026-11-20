import json
import sqlite3
import sys
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
db.row_factory = sqlite3.Row
rows = db.execute("select id,revision,reason,created_at,state_json from room_snapshots where room_id='VPAW80' order by created_at desc limit 10").fetchall()
print("snapshots", len(rows))
for row in rows:
    state = json.loads(row["state_json"])
    players = state.get("players", [])
    summary = [(p.get("id"), p.get("name"), p.get("originCharacterId")) for p in players]
    sys.stdout.buffer.write(f"{row['id']} rev={row['revision']} {row['reason']} {row['created_at']} players={summary}\n".encode("utf-8"))
