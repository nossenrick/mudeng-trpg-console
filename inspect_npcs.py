import json
import sqlite3
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
state = json.loads(db.execute("select state_json from rooms where id='VPAW80'").fetchone()[0])
print("npc count", len(state.get("npcs", [])))
print(json.dumps(state.get("npcs", [])[:5], ensure_ascii=False, indent=2)[:7000])
print("memory", json.dumps(state.get("aiMemory", {}), ensure_ascii=False)[:2000])
