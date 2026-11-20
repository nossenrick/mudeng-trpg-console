import json
import sqlite3
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
state = json.loads(db.execute("select state_json from rooms where id='10DVXF'").fetchone()[0])
print("removed", state.get("removedPlayerIds"))
print("aiPlayer", json.dumps(state.get("aiPlayer", {}), ensure_ascii=False)[:1000])
print("players", [(p.get("id"), p.get("name")) for p in state.get("players", [])])
