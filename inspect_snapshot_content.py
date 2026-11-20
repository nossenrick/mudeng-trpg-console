import json
import sqlite3
import sys
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
db.row_factory = sqlite3.Row
for revision in (899, 921, 931):
    row = db.execute("select state_json from room_snapshots where room_id='VPAW80' and revision=? order by created_at desc limit 1", (revision,)).fetchone()
    if not row:
        continue
    state = json.loads(row["state_json"])
    print("REV", revision, "messages", len(state.get("chatMessages", [])))
    for message in state.get("chatMessages", [])[-3:]:
        print(" msg", message.get("time"), str(message.get("text", ""))[:80])
    control = state.get("aiControl", {})
    print(" ai", control.get("paused"), control.get("mode"), "queue", len(control.get("queue", [])))
    for log in state.get("logs", [])[-3:]:
        print(" log", log.get("time"), log.get("title"))
