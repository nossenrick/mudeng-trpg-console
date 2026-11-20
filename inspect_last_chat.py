import json
import sqlite3
import sys
from pathlib import Path

db = sqlite3.connect(Path("trpg.sqlite3"))
db.row_factory = sqlite3.Row
state = json.loads(db.execute("select state_json from rooms where id='VPAW80'").fetchone()["state_json"])
for message in state.get("chatMessages", [])[-30:]:
    sys.stdout.buffer.write(
        (f"{message.get('time')} | {message.get('speakerName')} | {message.get('role')} | {str(message.get('text') or '')[:180]}\n").encode("utf-8")
    )
