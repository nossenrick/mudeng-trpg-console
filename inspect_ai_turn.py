import json
import sqlite3
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
state = json.loads(db.execute("select state_json from rooms where id='10DVXF'").fetchone()[0])
print("preview", json.dumps(state.get("aiTurnPreview"), ensure_ascii=False)[:2000])
print("suggested", state.get("playFlow", {}).get("suggestedActions"))
for log in state.get("logs", [])[-10:]:
    print(log.get("time"), log.get("title"), str(log.get("text", ""))[:100])
