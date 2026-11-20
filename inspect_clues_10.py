import json
import sqlite3
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
row = db.execute("select state_json,revision from rooms where id='10DVXF'").fetchone()
state = json.loads(row[0])
for clue in state.get("clues", []):
    print(clue.get("id"), "|", clue.get("title"), "|", clue.get("status"), "|", clue.get("published"), "|", clue.get("publishMode"))
