import json
import sqlite3
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
row = db.execute("select state_json from rooms where id='10DVXF'").fetchone()
state = json.loads(row[0])
changed = 0
for clue in state.get("clues", []):
    if clue.get("status") == "已发现" and not clue.get("published"):
        clue["published"] = True
        clue["publishMode"] = "public"
        changed += 1
db.execute("update rooms set state_json=?, revision=revision+1, updated_at=datetime('now') where id='10DVXF'", (json.dumps(state, ensure_ascii=False),))
db.commit()
print("published", changed)
