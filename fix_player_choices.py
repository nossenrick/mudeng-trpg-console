import json
import sqlite3
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
db.row_factory = sqlite3.Row
row = db.execute("select state_json, revision from rooms where id='10DVXF'").fetchone()
state = json.loads(row["state_json"])
flow = state.setdefault("playFlow", {})
choices = flow.get("suggestedActions") or []
actor = "p_MPg0NYSyAh0"
flow["suggestedActionsActorId"] = actor
flow["suggestedActionsByPlayer"] = {actor: choices}
revision = int(row["revision"]) + 1
db.execute("update rooms set state_json=?, revision=?, updated_at=datetime('now') where id='10DVXF'", (json.dumps(state, ensure_ascii=False), revision))
db.commit()
print("revision", revision, "actor", actor, "choices", choices)
