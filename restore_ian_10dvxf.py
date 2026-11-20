import json
import sqlite3
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
db.row_factory = sqlite3.Row
current_row = db.execute("select state_json, revision from rooms where id='10DVXF'").fetchone()
source_row = db.execute("select state_json from rooms where id='VPAW80'").fetchone()
current = json.loads(current_row["state_json"])
source = json.loads(source_row["state_json"])
source_ian = next((p for p in source.get("players", []) if p.get("id") == "p_char_mvtbl1djap3rm"), None)
if source_ian is None:
    source_ian = next((p for p in source.get("players", []) if p.get("name") == "伊恩·佩洛兹"), None)
if source_ian is None:
    raise SystemExit("missing Ian source")
players = current.setdefault("players", [])
if not any(p.get("id") == source_ian.get("id") for p in players):
    players.append(source_ian)
map_data = current.setdefault("map", {})
tokens = map_data.setdefault("tokens", [])
if not any(t.get("id") == source_ian.get("id") for t in tokens):
    tokens.append({
        "id": source_ian.get("id"),
        "name": source_ian.get("name"),
        "type": "player",
        "npcId": "",
        "row": 2,
        "col": 1,
    })
combat = current.setdefault("combat", {})
turn_order = combat.setdefault("turnOrder", [])
if source_ian.get("id") not in turn_order:
    turn_order.append(source_ian.get("id"))
revision = int(current_row["revision"]) + 1
db.execute("update rooms set state_json=?, revision=?, updated_at=datetime('now') where id='10DVXF'", (json.dumps(current, ensure_ascii=False), revision))
db.commit()
print("revision", revision, "players", [(p.get("id"), p.get("name")) for p in players])
