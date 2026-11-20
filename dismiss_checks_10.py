import json
import sqlite3
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
row = db.execute("select state_json from rooms where id='10DVXF'").fetchone()
state = json.loads(row[0])
changed = 0
for request in state.get("playerCheckRequests", []):
    if request.get("status") == "pending":
        request["status"] = "dismissed"
        request["dismissedAt"] = "2026-11-09T07:45:00+00:00"
        changed += 1
if changed:
    db.execute("update rooms set state_json=?, revision=revision+1, updated_at=datetime('now') where id='10DVXF'", (json.dumps(state, ensure_ascii=False),))
    db.commit()
print("dismissed", changed)
