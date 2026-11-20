import json
import sqlite3
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
state = json.loads(db.execute("select state_json from rooms where id='10DVXF'").fetchone()[0])
print(json.dumps(state.get("playFlow", {}), ensure_ascii=False)[:1500])
print("queue tail", [(x.get("playerId"), x.get("playerName"), x.get("status")) for x in state.get("aiControl", {}).get("queue", [])[-4:]])
