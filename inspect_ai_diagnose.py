import json
import sqlite3
import sys
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
db.row_factory = sqlite3.Row
rows = db.execute("select id,name,revision,updated_at,state_json from rooms order by updated_at desc limit 3").fetchall()
for row in rows:
    state = json.loads(row["state_json"])
    print("ROOM", row["id"], row["name"], "rev", row["revision"], "updated", row["updated_at"])
    print("players", [(p.get("id"), p.get("name")) for p in state.get("players", [])])
    print("aiControl", json.dumps(state.get("aiControl", {}), ensure_ascii=False)[:2500])
    print("aiPlayer", json.dumps(state.get("aiPlayer", {}), ensure_ascii=False)[:1000])
    print("preview", json.dumps(state.get("aiTurnPreview"), ensure_ascii=False)[:800])
    print("suggested", state.get("playFlow", {}).get("suggestedActions"))
    print("chat tail")
    for m in state.get("chatMessages", [])[-6:]:
        sys.stdout.buffer.write((f"{m.get('time')} {m.get('speakerName')}: {str(m.get('text',''))[:100]}\n").encode("utf-8"))
    print("logs tail")
    for log in state.get("logs", [])[-10:]:
        sys.stdout.buffer.write((f"{log.get('time')} {log.get('title')}: {str(log.get('text',''))[:100]}\n").encode("utf-8"))
    print("---")
