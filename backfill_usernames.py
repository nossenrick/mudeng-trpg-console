import json
import sqlite3
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
db.row_factory = sqlite3.Row
row = db.execute("select state_json, revision from rooms where id='VPAW80'").fetchone()
state = json.loads(row["state_json"])
for participant in db.execute("select name, player_id from participants where room_id='VPAW80' and role='player'"):
    for player in state.get("players", []):
        if player.get("id") == participant["player_id"]:
            player["userName"] = participant["name"]
revision = int(row["revision"]) + 1
db.execute("update rooms set state_json=?, revision=?, updated_at=datetime('now') where id='VPAW80'", (json.dumps(state, ensure_ascii=False), revision))
db.commit()
print("revision", revision, [(p.get("name"), p.get("userName")) for p in state.get("players", [])])
