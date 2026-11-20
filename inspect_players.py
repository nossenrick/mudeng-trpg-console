import json
import sqlite3
import sys
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
db.row_factory = sqlite3.Row
rows = db.execute("select id,state_json from rooms order by updated_at desc limit 10").fetchall()
out = []
for row in rows:
    state = json.loads(row["state_json"])
    out.append({
        "room": row["id"],
        "players": [
            {key: player.get(key) for key in ("id", "name", "concept", "maxHp", "maxSkillPoints", "ruleSystem", "originCharacterId")}
            for player in state.get("players", [])
        ],
        "campaign": (state.get("session") or {}).get("campaign"),
    })
sys.stdout.buffer.write(json.dumps(out, ensure_ascii=False, indent=2).encode("utf-8"))
