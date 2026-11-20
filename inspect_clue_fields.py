import json
import sqlite3
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
state = json.loads(db.execute("select state_json from rooms where id='VPAW80'").fetchone()[0])
for i in (0, 5, 17, 24):
    print(json.dumps(state["clues"][i], ensure_ascii=False, indent=2))
