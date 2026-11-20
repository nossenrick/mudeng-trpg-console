import json
import sqlite3
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
row = db.execute("select id,name,state_json,revision from rooms where id='10DVXF'").fetchone()
state = json.loads(row[2])
print("room", row[0], row[1], row[3])
print("control", json.dumps(state.get("aiControl", {}), ensure_ascii=False))
print("preview", "yes" if state.get("aiTurnPreview") else "no")
print("pending", state.get("pendingPlayerInteraction"))
print("suggested", state.get("playFlow", {}).get("suggestedActions"))
