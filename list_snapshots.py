import json
import sqlite3
import sys
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
db.row_factory = sqlite3.Row
rows = db.execute(
    "select id, revision, reason, created_at, state_json from room_snapshots where room_id='VPAW80' order by revision desc limit 40"
).fetchall()
print("snapshots", len(rows))
for row in rows:
    state = json.loads(row["state_json"])
    messages = state.get("chatMessages", [])
    logs = state.get("logs", [])
    ai = state.get("aiControl", {})
    last_message = messages[-1] if messages else {}
    last_log = logs[-1] if logs else {}
    sys.stdout.buffer.write(
        f"rev={row['revision']} {row['created_at']} {row['reason']} msgs={len(messages)} "
        f"lastMsg={last_message.get('time')} lastLog={last_log.get('time')} "
        f"ai={ai.get('enabled')}/{ai.get('paused')}/{ai.get('mode')} queue={len(ai.get('queue', []))}\n".encode("utf-8")
    )
