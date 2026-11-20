import json
import sqlite3
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
db.row_factory = sqlite3.Row
row = db.execute("select state_json,revision from rooms where id='VPAW80'").fetchone()
state = json.loads(row["state_json"])
print("revision", row["revision"])
print("aiControl", json.dumps(state.get("aiControl", {}), ensure_ascii=False, indent=2))
print("aiPlayer", json.dumps(state.get("aiPlayer", {}), ensure_ascii=False, indent=2)[:2000])
print("logs tail")
for log in state.get("logs", [])[-12:]:
    print(log.get("time"), log.get("title"), str(log.get("text", ""))[:80])
