import json
import sqlite3
import sys
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
db.row_factory = sqlite3.Row
rows = db.execute("select id, state_json, revision, updated_at from rooms order by updated_at desc limit 10").fetchall()
for row in rows:
    state = json.loads(row["state_json"])
    messages = state.get("chatMessages", [])
    sys.stdout.buffer.write(f"{row['id']} rev={row['revision']} messages={len(messages)} updated={row['updated_at']}\n".encode())
    for message in messages[-2:]:
        sys.stdout.buffer.write((f"  {message.get('speakerName')} | {message.get('role')} | {str(message.get('text',''))[:80]}\n").encode("utf-8"))
