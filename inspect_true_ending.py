import json
import sqlite3
import sys
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
db.row_factory = sqlite3.Row
state = json.loads(db.execute("select state_json from rooms where id='VPAW80'").fetchone()["state_json"])
nodes = state.get("scenarioNodes", []) or state.get("module", {}).get("scenarioNodes", [])
for node in nodes:
    title = str(node.get("title") or "")
    if "尾声" in title or "布莱克伍德庄园" in title:
        sys.stdout.buffer.write(json.dumps(node, ensure_ascii=False, indent=2).encode("utf-8"))
        sys.stdout.buffer.write(b"\n")
