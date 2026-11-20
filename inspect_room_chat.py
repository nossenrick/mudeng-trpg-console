import json
import sqlite3
import sys
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
db.row_factory = sqlite3.Row
row = db.execute("select state_json, revision, updated_at from rooms where id = ?", ("VPAN8O",)).fetchone()
if not row:
    print("missing")
    raise SystemExit
state = json.loads(row["state_json"])
sys.stdout.buffer.write(f"rev={row['revision']} messages={len(state.get('chatMessages', []))}\n".encode())
for message in state.get("chatMessages", [])[-15:]:
    sys.stdout.buffer.write((json.dumps(message, ensure_ascii=False)[:500] + "\n").encode("utf-8"))
