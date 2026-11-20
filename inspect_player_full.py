import json
import sqlite3
import sys
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
db.row_factory = sqlite3.Row
row = db.execute("select state_json from rooms where id='EEYLYT'").fetchone()
state = json.loads(row["state_json"])
for player in state.get("players", []):
    sys.stdout.buffer.write((json.dumps(player, ensure_ascii=False, indent=2) + "\n---\n").encode("utf-8"))
