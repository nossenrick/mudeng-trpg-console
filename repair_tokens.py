import json
import sqlite3
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
db.row_factory = sqlite3.Row
row = db.execute("select state_json, revision from rooms where id='VPAW80'").fetchone()
state = json.loads(row["state_json"])
names = {str(p.get("id")): str(p.get("name")) for p in state.get("players", [])}
for token in state.get("map", {}).get("tokens", []):
    if token.get("id") in names:
        token["name"] = names[token["id"]]
revision = int(row["revision"]) + 1
db.execute("update rooms set state_json=?, revision=?, updated_at=datetime('now') where id='VPAW80'", (json.dumps(state, ensure_ascii=False), revision))
db.commit()
print(revision, [(t.get("id"), t.get("name")) for t in state.get("map", {}).get("tokens", [])])
