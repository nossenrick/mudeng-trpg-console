import json
import sqlite3
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
db.row_factory = sqlite3.Row
row = db.execute("select state_json from rooms where id='VPAW80'").fetchone()
state = json.loads(row["state_json"])
print("map", state.get("map", {}).get("enabled"), state.get("map", {}).get("published"), state.get("map", {}).get("name"))
print("combat", state.get("combat"))
print("scene", state.get("scene", {}).get("title"), state.get("scene", {}).get("activeNodeId"))
print("chat tail", [(m.get("time"), m.get("text", "")[:50]) for m in state.get("chatMessages", [])[-4:]])
