import json
import sqlite3
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
state = json.loads(db.execute("select state_json from rooms where id='VPAW80'").fetchone()[0])
print("clues", len(state.get("clues", [])))
for clue in state.get("clues", []):
    print(clue.get("id"), "|", clue.get("title"), "|", clue.get("status"), "|", clue.get("published"), "|", clue.get("publishMode"))
print("scenario nodes", len(state.get("scenarioNodes", [])))
print("module clues", len((state.get("module") or {}).get("clues", []) or []))
