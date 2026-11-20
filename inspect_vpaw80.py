import json
import sqlite3
import sys
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
db.row_factory = sqlite3.Row
row = db.execute("select state_json, revision, updated_at from rooms where id='VPAW80'").fetchone()
if not row:
    print("missing")
    raise SystemExit
state = json.loads(row["state_json"])
sys.stdout.buffer.write(f"revision={row['revision']} updated={row['updated_at']}\n".encode())
print("players:")
for p in state.get("players", []):
    sys.stdout.buffer.write(json.dumps({k: p.get(k) for k in ("id", "name", "concept", "originCharacterId", "joinedByParticipant", "protectFromGmSnapshot")}, ensure_ascii=False).encode() + b"\n")
print("messages:")
for m in state.get("chatMessages", [])[-10:]:
    sys.stdout.buffer.write(json.dumps({k: m.get(k) for k in ("id", "speakerId", "speakerName", "role", "visibility", "text", "time")}, ensure_ascii=False).encode() + b"\n")
print("participants:")
for p in db.execute("select id,name,role,player_id,device_id,last_seen_at from participants where room_id='VPAW80'"):
    print(dict(p))
