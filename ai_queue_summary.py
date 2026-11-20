import json
import sqlite3
from collections import Counter
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
db.row_factory = sqlite3.Row
row = db.execute("select state_json, revision from rooms where id='VPAW80'").fetchone()
state = json.loads(row["state_json"])
control = state.get("aiControl", {})
queue = control.get("queue", [])
print("revision", row["revision"], "paused", control.get("paused"), "enabled", control.get("enabled"), "mode", control.get("mode"), "busy", control.get("busy"))
print("statuses", Counter(item.get("status") for item in queue))
for item in queue:
    print(item.get("status"), item.get("createdAt"), item.get("playerName"), str(item.get("text", ""))[:45])
print("logs")
for log in state.get("logs", [])[-15:]:
    print(log.get("time"), log.get("title"), str(log.get("text", ""))[:50])
